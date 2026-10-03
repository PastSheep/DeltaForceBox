"""每日密码页面：多源拉取、缓存优先显示、跨日自动刷新。

数据流：
- 启动即显示本地缓存（如有），避免空白等待与频繁请求（上游限频）；
- 缓存标注的更新日期非今日时，后台线程按优先级顺序拉取最新密码，
  成功后写入缓存并刷新界面；全部来源失败则回退显示缓存并提示；
- 页面驻留期间每分钟检查一次跨日，跨日自动触发刷新；
- 手动刷新按钮可强制重新拉取。

线程边界：网络请求全部在 QThread 后台执行，UI 只在主线程更新。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QWidgetItem,
)
from shiboken6 import isValid as _shiboken_is_valid

from ...core.daily_password import (
    DEFAULT_SOURCE_ORDER,
    FETCH_TIMEOUT,
    DailyPasswordData,
    cache_is_today,
    fetch_password,
    load_cache,
    save_cache,
)
from ...core.i18n import I18nManager
from ...core.paths import RESOURCES_DIR
from ...core.theme import ThemeManager

# 地图缩略图目录（scripts/prepare_map_thumbs.py 预处理产物，640×360 黑边填充）
MAP_IMAGE_DIR = RESOURCES_DIR / "images" / "daily_password"

# 位置描述本地资源：密码房位置是静态信息，直接内置，无需依赖数据源提供
# （tmini 源实时描述优先，缺失时回退本地资源）
_LOCATIONS_FILE = RESOURCES_DIR / "daily_password_locations.json"
LOCAL_LOCATIONS: dict[str, str] = {}
if _LOCATIONS_FILE.exists():
    try:
        LOCAL_LOCATIONS = {
            str(k): str(v)
            for k, v in json.loads(_LOCATIONS_FILE.read_text(encoding="utf-8")).items()
            if v
        }
    except (OSError, ValueError):
        LOCAL_LOCATIONS = {}


def _normalize_map_name(name: str) -> str:
    """地图名归一化：兼容 "AZ3核电站"（tmini 命名）与本地资源 key "AZ3"。"""
    return name.replace("核电站", "")


def _map_location(name: str, from_source: str) -> str:
    """位置描述：数据源实时描述优先，缺失时回退本地静态资源。"""
    return from_source or LOCAL_LOCATIONS.get(_normalize_map_name(name), "")

# 卡片尺寸范围：宽度随视口自适应伸缩（填满每行），高度固定保证等高
CARD_WIDTH = 240   # 默认宽度（首次渲染/兜底）
CARD_HEIGHT = 252
MIN_CARD_WIDTH = 200  # 宽度下限：低于则减少每行列数
MAX_CARD_WIDTH = 280  # 宽度上限：窄窗口（1-2 列）时避免过宽
GRID_PADDING = 12     # 卡片间距

# 地图显示顺序（固定）：不同数据源返回顺序可能不同，渲染一律按此顺序，
# 避免同一张图在不同来源下位置跳动；卡片标题也用这里的标准名。
MAP_ORDER = ("零号大坝", "长弓溪谷", "巴克什", "航天基地", "潮汐监狱", "AZ3")

# 图片区固定高度；宽最大按 16:9（黑边图，轻微拉伸由黑边吸收）
IMAGE_HEIGHT = 100

# 位置描述滚动区高度（全文可滚动查看，保证卡片等高）
DESC_AREA_HEIGHT = 64


def resolve_map_image(name: str) -> Path | None:
    """地图名 -> 缩略图文件；兼容 "AZ3核电站" 等带后缀命名（文件名为 AZ3.jpg）。"""
    for cand in (name, name.replace("核电站", "")):
        path = MAP_IMAGE_DIR / f"{cand}.jpg"
        if path.exists():
            return path
    return None


# 运行中的后台线程注册表：持有 QThread 引用，防止页面被回收时线程仍在运行
# 导致 "QThread: Destroyed while thread is still running" 硬崩溃（0xC0000409）。
# _shutdown 限时等待后若请求仍进行中（HTTP 最长 FETCH_TIMEOUT=10s），线程由
# 注册表持有到自然结束再移除，窗口关闭不会回收运行中的 QThread。
_ACTIVE_WORKERS: list[QThread] = []


def _track_worker(worker: QThread) -> None:
    """登记后台线程；finished 后自动移除。"""
    _ACTIVE_WORKERS.append(worker)

    def _on_done() -> None:
        try:
            _ACTIVE_WORKERS.remove(worker)
        except ValueError:
            pass

    worker.finished.connect(_on_done)


class _FetchWorker(QThread):
    """后台拉取线程：按优先级尝试各来源，成功/失败各发一个信号。"""

    ok = Signal(object)
    fail = Signal(str)

    def __init__(
        self,
        order: tuple[str, ...],
        fetchers: dict[str, object] | None = None,
        timeout: int = FETCH_TIMEOUT,
    ) -> None:
        super().__init__()
        self._order = order
        self._fetchers = fetchers
        self._timeout = timeout

    def run(self) -> None:
        try:
            data = fetch_password(
                self._order,
                timeout=self._timeout,
                fetchers=self._fetchers,
                should_stop=self.isInterruptionRequested,
            )
        except Exception as exc:  # noqa: BLE001 - 线程边界，失败统一走 fail 信号
            self.fail.emit(str(exc))
            return
        if data is not None:
            self.ok.emit(data)
        else:
            self.fail.emit("")


class PasswordCard(QFrame):
    """每日密码卡片：地图缩略图 + 标题 + 密码 + 可滚动位置描述。

    固定尺寸（与骇爪美图来源窗口一致），描述区固定高度、全文可滚动，
    保证所有卡片等高、布局统一；列表按可用宽度自适应每行卡片数。
    左键点击卡片触发 clicked（用于弹出大图预览）。
    """

    clicked = Signal(object)  # 参数：卡片自身

    def __init__(
        self,
        name: str,
        code: str,
        location: str,
        pixmap: QPixmap | None,
        no_loc_text: str,
        image_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pwdCard")
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.name = name
        self.code = code
        self.image_path = image_path
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        box = QVBoxLayout(self)
        box.setContentsMargins(12, 8, 12, 8)
        box.setSpacing(5)

        if pixmap is not None and not pixmap.isNull():
            self.image_label = QLabel()
            self.image_label.setObjectName("pwdImage")
            self.image_label.setPixmap(pixmap)
            self.image_label.setScaledContents(True)
            self.image_label.setFixedHeight(IMAGE_HEIGHT)
            self.image_label.setMaximumWidth(round(IMAGE_HEIGHT * 16 / 9))
            box.addWidget(self.image_label, 0, Qt.AlignmentFlag.AlignHCenter)

        title = QLabel(name)
        title.setObjectName("pwdTitle")
        code_label = QLabel(code)
        code_label.setObjectName("pwdCode")
        code_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # 位置描述：固定高度滚动区，长文本可滚动查看全文
        self.desc_scroll = QScrollArea()
        self.desc_scroll.setObjectName("pwdDescScroll")
        self.desc_scroll.setWidgetResizable(True)
        self.desc_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.desc_scroll.setFixedHeight(DESC_AREA_HEIGHT)
        inner = QLabel(location or no_loc_text)
        inner.setObjectName("pwdLoc")
        inner.setWordWrap(True)
        inner.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.desc_scroll.setWidget(inner)

        box.addWidget(title)
        box.addWidget(code_label)
        box.addWidget(self.desc_scroll)
        box.addStretch(1)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self)
            event.accept()
        super().mousePressEvent(event)


class _PreviewWindow(QWidget):
    """点击卡片弹出的大图预览悬浮窗。

    无边框、置顶、非模态；显示地图名 + 密码 + 原始尺寸大图，
    点击窗口任意位置即关闭（WA_DeleteOnClose 自动销毁）。
    打开状态下可被页面复用（update_content 替换标题与图片）。
    """

    def __init__(self, title: str, image_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pwdPreview")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box = QVBoxLayout(self)
        box.setContentsMargins(16, 12, 16, 16)
        box.setSpacing(10)

        self.cap_label = QLabel()
        self.cap_label.setObjectName("pwdPreviewTitle")
        self.cap_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.image_label = QLabel()
        self.image_label.setObjectName("pwdPreviewImage")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        box.addWidget(self.cap_label)
        box.addWidget(self.image_label)

        # 窗口自身与所有子控件统一拦截鼠标按下：点击任意位置关闭
        for w in (self, self.cap_label, self.image_label):
            w.installEventFilter(self)
        self.update_content(title, image_path)

    def update_content(self, title: str, image_path: Path) -> None:
        """替换窗口内容（标题 + 大图），保持窗口打开状态。"""
        self.cap_label.setText(title)
        pix = QPixmap(str(image_path))
        if pix.isNull():  # 图片缺失时兜底显示占位文案
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText("(image)")
        else:
            self.image_label.setText("")
            self.image_label.setPixmap(pix)
            self.image_label.setFixedSize(pix.size())
        self.adjustSize()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt 命名
        if event.type() == QEvent.Type.MouseButtonPress:
            self.close()
            return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self.close()


class _FlowLayout(QLayout):
    """简易流式布局：按可用宽度换行放置等尺寸卡片。

    完全由外部控制卡片尺寸（reflow 统一 setFixedWidth），本类只负责
    逐行放置与换行，行间距 = spacing；行为确定、无 Qt 网格黑盒取整。
    """

    def __init__(self, parent: QWidget | None = None, spacing: int = 0) -> None:
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self._spacing = spacing
        self._items: list[QWidgetItem] = []

    def addItem(self, item: QWidgetItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i: int) -> QWidgetItem | None:
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i: int) -> QWidgetItem | None:
        if 0 <= i < len(self._items):
            return self._items.pop(i)
        return None

    def expandingDirections(self) -> Qt.Orientations:
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(width, test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect.width(), test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, width: int, test_only: bool) -> int:
        m = self.contentsMargins()
        eff_width = width - m.left() - m.right()
        x, y = m.left(), m.top()
        row_h = 0
        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > m.left() + eff_width and x > m.left():
                x = m.left()
                y += row_h + self._spacing
                row_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            row_h = max(row_h, hint.height())
        return y + row_h + m.bottom()


class DailyPasswordPage(QWidget):
    def __init__(
        self,
        i18n: I18nManager,
        theme: ThemeManager,
        source_order: tuple[str, ...] | None = None,
        cache_file: Path | None = None,
        fetchers: dict[str, object] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._i18n = i18n
        self._theme = theme
        self._order = tuple(source_order) if source_order else DEFAULT_SOURCE_ORDER
        self._cache_file = cache_file
        self._fetchers = fetchers
        self._fetching = False
        self._worker: _FetchWorker | None = None
        self._has_content = False
        # 地图缩略图内存缓存（避免重复读盘；None 表示无图）
        self._pixmap_cache: dict[str, QPixmap | None] = {}
        self._preview: _PreviewWindow | None = None  # 大图预览悬浮窗
        # 刷新节流：拿到非今日数据或全部失败时延后重试，
        # 避免源更新滞后/网络异常导致每分钟循环请求打满上游限频
        self._throttle_until: datetime | None = None
        self._retry_delay = timedelta(minutes=15)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)

        self.title_label = QLabel()
        font = self.title_label.font()
        font.setPointSize(15)
        font.setBold(True)
        self.title_label.setFont(font)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.status_label = QLabel()
        self.status_label.setObjectName("hint")
        self.status_label.setWordWrap(True)
        self.refresh_button = QPushButton()
        self.refresh_button.setObjectName("ghost")
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        head.addWidget(self.status_label, 1)
        head.addWidget(self.refresh_button)

        self.empty_label = QLabel()
        self.empty_label.setObjectName("hint")
        self.empty_label.setAlignment(Qt.AlignCenter)

        # 卡片流式网格：QScrollArea + FlowLayout 完全手动布局，
        # 每行卡片数/宽度由 reflow 统一控制（可预期、无 Qt 网格取整）
        self.scroll = QScrollArea()
        self.scroll.setObjectName("pwdList")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._flow_host = QWidget()
        self._flow_host.setObjectName("pwdFlowHost")
        self._flow = _FlowLayout(self._flow_host, spacing=GRID_PADDING)
        self.scroll.setWidget(self._flow_host)

        root.addWidget(self.title_label)
        root.addLayout(head)
        root.addWidget(self.empty_label)
        root.addWidget(self.scroll, 1)

        # 卡片宽度自适应：监听滚动区自身 resize（viewport 已就绪）重排
        self._card_w = CARD_WIDTH
        self._cols: int | None = None
        self.scroll.installEventFilter(self)

        self.refresh_button.clicked.connect(self._refresh_now)

        # 跨日检查：页面驻留期间每分钟比对缓存日期，跨日自动刷新
        self._timer = QTimer(self)
        self._timer.setInterval(60_000)
        self._timer.timeout.connect(self._maybe_refresh)
        self._timer.start()

        self._apply_cache()
        self._maybe_refresh()

    # ── 卡片宽度自适应（填满每行）────────────────────

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt 命名
        if obj is self.scroll and event.type() == QEvent.Type.Resize:
            self._reflow()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().resizeEvent(event)
        # 兜底：页面级 resize 后延迟重排（父级先于子列表 resize）
        QTimer.singleShot(0, self._reflow)

    def _reflow(self) -> None:
        """按可用宽度重排卡片：宽度在 [MIN, MAX] 内伸缩，填满每行。

        列数为可用宽度的单调函数（avail 增大列数不减），拖拽调整窗口时
        不会来回跳变闪烁；列数变化仅发生在宽度触及 MIN/MAX 边界。
        """
        avail = self.scroll.viewport().width()
        card_count = self._flow.count()
        if avail <= 0 or card_count == 0:
            return
        lead = 4  # 视口左侧起始偏移（与滚动区边距对齐）
        max_cols = max(1, (avail - lead) // (MIN_CARD_WIDTH + GRID_PADDING))
        max_cols = min(max_cols, card_count)  # 列数不超过卡片总数
        cols = 1
        for c in range(max_cols, 0, -1):
            w = (avail - lead) // c - GRID_PADDING
            w = min(w, MAX_CARD_WIDTH)
            # clamp 后整行宽度仍放得下才选该列数（尽量填满）
            if c * w + GRID_PADDING * (c - 1) <= avail - lead:
                cols = c
                break
        width = (avail - lead) // cols - GRID_PADDING
        width = min(max(width, MIN_CARD_WIDTH), MAX_CARD_WIDTH)
        if width == self._card_w and cols == self._cols:
            return  # 无变化：跳过重排
        self._cols = cols
        self._card_w = width
        for i in range(self._flow.count()):
            card = self._flow.itemAt(i).widget()
            if card is not None:
                card.setFixedWidth(width)
        # 卡片尺寸变化后让流式布局失效重算（行数/位置随之更新）
        self._flow.invalidate()
        self._flow_host.updateGeometry()

    # ── 数据展示 ─────────────────────────────────────

    def _apply_cache(self) -> None:
        """读取缓存并渲染；缓存缺失/损坏时跳过。"""
        cache = load_cache(self._cache_file)
        if cache is None:
            return
        try:
            data = DailyPasswordData(
                source=str(cache.get("source", "")),
                update_date=str(cache.get("update_date", "")),
                updated_at=str(cache.get("updated_at", "")),
                passwords={
                    str(k): str(v)
                    for k, v in (cache.get("passwords") or {}).items()
                    if v
                },
                locations={
                    str(k): str(v)
                    for k, v in (cache.get("locations") or {}).items()
                    if v
                },
            )
        except Exception:
            return
        if not data.passwords:
            return
        self._render_data(data, stale=True)

    def _render_data(self, data: DailyPasswordData, stale: bool = False) -> None:
        """渲染数据到卡片流式网格与状态行。

        卡片按 MAP_ORDER 固定顺序显示（兼容源命名的后缀变体，
        如 tmini 的 "AZ3核电站" 归一为 "AZ3"），与源返回顺序无关。
        """
        self._clear_cards()
        normalized = {
            _normalize_map_name(k): (k, v) for k, v in data.passwords.items()
        }
        for name in MAP_ORDER:
            entry = normalized.get(name)
            if entry is None:
                continue
            actual, code = entry
            self._flow.addWidget(
                self._build_card(
                    name,
                    code,
                    _map_location(actual, data.locations.get(actual, "")),
                )
            )
        self._has_content = True
        self.empty_label.hide()

        parts = [
            f"{self._i18n.t('dailypwd.update_date')}：{data.update_date or '—'}",
            f"{self._i18n.t('dailypwd.updated_at')}：{data.updated_at or '—'}",
            f"{self._i18n.t('dailypwd.source')}：{data.source or '—'}",
        ]
        if stale:
            parts.append(self._i18n.t("dailypwd.stale_hint"))
        self.status_label.setText(" · ".join(parts))

    def _build_card(self, name: str, code: str, location: str) -> PasswordCard:
        path = resolve_map_image(name)
        card = PasswordCard(
            name,
            code,
            location,
            pixmap=self._load_pixmap(name),
            no_loc_text=self._i18n.t("dailypwd.no_location"),
            image_path=path,
        )
        card.clicked.connect(self._show_preview)
        return card

    def _load_pixmap(self, name: str) -> QPixmap | None:
        """按地图名加载缩略图（带缓存）；无对应图片返回 None。"""
        if name in self._pixmap_cache:
            return self._pixmap_cache[name]
        path = resolve_map_image(name)
        pix = QPixmap(str(path)) if path is not None else QPixmap()
        result = pix if not pix.isNull() else None
        self._pixmap_cache[name] = result
        return result

    def _show_preview(self, card: PasswordCard) -> None:
        """点击卡片：弹出/替换大图预览悬浮窗（同一时刻仅一个窗口）。

        预览已打开（未被点击关闭销毁）时复用窗口替换内容；
        已关闭销毁则新建。窗口居中于主窗口，点击任意处关闭。
        """
        if card.image_path is None:
            return
        title = f"{card.name} · {card.code}"
        if self._preview is not None and _shiboken_is_valid(self._preview):
            self._preview.update_content(title, card.image_path)
            self._preview.raise_()
            self._preview.activateWindow()
            return
        self._preview = _PreviewWindow(title, card.image_path, self)
        self._preview.show()
        center = self.window().frameGeometry().center()
        self._preview.move(
            center - QPoint(self._preview.width() // 2, self._preview.height() // 2)
        )

    def set_source_order(self, order: tuple[str, ...] | None) -> None:
        """运行时更新来源优先级（设置页修改后实时同步，无需重启）。

        仅更新顺序，不立即拉取：下次手动刷新/跨日刷新时按新顺序请求。
        """
        new_order = tuple(order) if order else DEFAULT_SOURCE_ORDER
        if new_order == self._order:
            return
        self._order = new_order

    def _clear_cards(self) -> None:
        """移除全部卡片。

        使用 shiboken6.delete 立即删除 C++ 对象（而非 deleteLater）：
        deleteLater 在事件循环/应用退出时才处理 DeferredDelete，若此时
        Python 包装器仍被引用会触发双重删除崩溃（Qt Python 绑定经典问题）。
        """
        while self._flow.count():
            item = self._flow.takeAt(0)
            widget = item.widget()
            if widget is not None:
                try:
                    from shiboken6 import delete as _qt_delete
                except ImportError:
                    widget.deleteLater()
                else:
                    _qt_delete(widget)

    # ── 刷新调度 ─────────────────────────────────────

    def _maybe_refresh(self) -> None:
        """缓存非今日或无缓存时后台刷新；当日缓存直接复用（限频友好）。"""
        if self._fetching:
            return
        if self._throttle_until is not None and datetime.now() < self._throttle_until:
            return
        cache = load_cache(self._cache_file)
        if cache is not None and cache_is_today(cache.get("update_date", "")):
            return
        self._start_fetch()

    def _refresh_now(self) -> None:
        """手动刷新：强制重新拉取（即使当日缓存也刷新）。"""
        if self._fetching:
            return
        self._start_fetch()

    def _start_fetch(self) -> None:
        self._fetching = True
        self.refresh_button.setEnabled(False)
        self.status_label.setText(self._i18n.t("dailypwd.loading"))
        self._worker = _FetchWorker(self._order, self._fetchers)
        _track_worker(self._worker)
        self._worker.ok.connect(self._on_fetch_ok)
        self._worker.fail.connect(self._on_fetch_fail)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _shutdown(self) -> None:
        """请求后台拉取线程停止并等待，避免 QThread 运行时被回收（窗口关闭时调用）。

        由 MainWindow.closeEvent 统一遍历页面调用（getattr 兜底）。
        组合策略（防 0xC0000409 硬崩溃）：
        - _ACTIVE_WORKERS 注册表持有 worker：页面回收不会立即析构运行中的 QThread；
        - wait 上限取 FETCH_TIMEOUT + 余量：请求进行中关闭时阻塞等待其自然结束，
          确保进程退出前线程已 finished（慢请求最长 FETCH_TIMEOUT=10s，正常请求
          1-2s 内完成，wait 在 finished 时立即返回，不额外卡顿）。
        """
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait(FETCH_TIMEOUT * 1000 + 2000)

    def _on_fetch_ok(self, data: DailyPasswordData) -> None:
        save_cache(data, self._cache_file)
        self._render_data(data)
        # 源更新滞后（返回非今日数据）：延后重试，避免循环请求
        self._throttle_until = (
            datetime.now() + self._retry_delay
            if not cache_is_today(data.update_date)
            else None
        )

    def _on_fetch_fail(self, _reason: str) -> None:
        self._throttle_until = datetime.now() + self._retry_delay
        if self._has_content:
            self.status_label.setText(self._i18n.t("dailypwd.failed_with_cache"))
        else:
            self.status_label.setText(self._i18n.t("dailypwd.failed"))
            self.empty_label.setText(self._i18n.t("dailypwd.failed_empty"))
            self.empty_label.show()

    def _on_worker_finished(self) -> None:
        self._fetching = False
        self.refresh_button.setEnabled(True)
        self._worker = None

    def retranslate(self) -> None:
        self.title_label.setText(self._i18n.t("dailypwd.title"))
        self.refresh_button.setText(self._i18n.t("dailypwd.refresh"))
