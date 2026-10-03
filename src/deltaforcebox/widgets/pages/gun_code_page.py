"""改枪码 · 主播推荐页面：低频同步 + 缓存优先 + 卡片网格 + 四维筛选。

数据流：
- 启动即显示本地缓存（如有），避免空白与重复请求（上游为第三方站点）；
- 缓存超过同步间隔（resources/config/app_config.json 的 gun_sync_interval_days，
  默认 10 天）或缺失时，
  后台线程拉取 shushu.fan/guns 首屏数据并更新缓存；每次同步只 1 次请求；
- 同步失败：保留缓存展示并标注离线，延后 6 小时再自动重试（不频繁请求）；
- 无手动刷新按钮（用户明确要求），同步完全由间隔自动触发；
- 预览图 / 作者头像按需下载到 data/gun_images/，已存在则跳过（幂等）；
- 武器类型 / 枪械名称 / 作者 / 标签 四维筛选为本地过滤（不重新请求）；
- 卡片描述区（评语 + 标签）固定高度滚动条，保证每张卡片格式一致。

线程边界：网络请求全部在 QThread 后台执行，UI 只在主线程更新。
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QPixmap, QPixmapCache
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core.gun_solutions import (
    GunSolution,
    _to_int,
    avatar_image_path,
    cache_is_fresh,
    ensure_image,
    load_guns_cache,
    preview_image_path,
    save_guns_cache,
    sync_official_solutions,
)
from ...core.i18n import I18nManager
from ...core.theme import ThemeManager
from ..flow_layout import FlowLayout
from ..search_combo import SearchCombo

# GunSolution 反序列化字段白名单：只取已知展示字段，旧缓存多/缺字段
# 不会导致 TypeError 整页空白
_SOLUTION_FIELDS = (
    "id",
    "name",
    "gun_name",
    "weapon_type",
    "author",
    "author_id",
    "channel",
    "author_avatar",
    "comment",
    "tags",
    "solution_code",
    "price",
    "preview_pic",
    "updated_at",
    "like_count",
)


def _solution_from_dict(s: dict) -> GunSolution | None:
    """白名单构造 GunSolution；字段/类型异常时返回 None（只跳过该条）。"""
    try:
        vals = {k: s[k] for k in _SOLUTION_FIELDS if k in s}
        # id 必须可解析为正整数：缺失/非法直接跳过该条
        # （避免 id="x" 之类生成 solution_x.png 异常缓存文件名）
        sid = _to_int(vals.get("id"), 0)
        if sid <= 0:
            return None
        vals["id"] = sid
        vals["author_id"] = _to_int(vals.get("author_id"), 0)
        return GunSolution(**vals)
    except (TypeError, ValueError):
        return None


# 卡片尺寸与网格间距（宽度随视口自适应伸缩，高度固定保证等高）
CARD_WIDTH = 260
CARD_HEIGHT = 320
MIN_CARD_WIDTH = 220
MAX_CARD_WIDTH = 300
GRID_PADDING = 12

# 平台标识 -> i18n key（徽标文案走 zh.json，未知平台回退原标识）
_CHANNEL_KEYS = {
    "douyin": "guncode.channel_douyin",
    "bilibili": "guncode.channel_bilibili",
}

# 预览图区固定高度（等比缩放，黑边/留白由布局吸收）
IMAGE_HEIGHT = 120
AVATAR_SIZE = 34

# 翻页渲染：任何时刻只实例化当前页的卡片（内存峰值固定为单页大小，与
# 总量无关）；翻页时销毁旧页、创建新页，图片随之懒加载（QPixmap 随卡片
# 释放，磁盘缓存 data/gun_images/ 保留避免重复下载）。每页卡片数由配置
# gun_render_page_size 控制（resources/config/app_config.json，app.py 装配时
# 传入，默认 20，不进设置界面）。

# QPixmapCache 全局 LRU 上限由配置 image_cache_limit_mb 控制
# （resources/config/app_config.json，app.py 装配时设置）；
# 本模块只负责"先查内存、再读磁盘"的加载路径。
# 描述滚动区固定高度：评语 + 标签超出部分内部滚动，保证卡片格式统一
DESC_AREA_HEIGHT = 72

# 同步失败后的重试间隔（小时）：避免短时间重复请求打满对方服务器
RETRY_DELAY = timedelta(hours=6)

# 运行中的后台线程注册表：持有 QThread 引用，防止页面被回收时
# 线程仍在运行导致 "QThread: Destroyed while thread is still running" 崩溃
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


def _text_contains(field: str, text: str) -> bool:
    """大小写不敏感的包含匹配（筛选输入语义）。"""
    return text.lower() in (field or "").lower()


def _match_solution(solutions: object, filters: dict[str, str]) -> bool:
    """四维 AND 过滤（包含匹配，文本为空视为无条件）。"""
    s = solutions
    return (
        (not filters["weapon"] or _text_contains(s.weapon_type, filters["weapon"]))
        and (not filters["gun"] or _text_contains(s.gun_name, filters["gun"]))
        and (not filters["author"] or _text_contains(s.author, filters["author"]))
        and (
            not filters["tag"]
            or any(_text_contains(t, filters["tag"]) for t in s.tags)
        )
    )


def format_price(price: int) -> str:
    """造价千分位格式化。"""
    return f"{price:,}"


def _pager_items(current: int, total: int) -> list[tuple[str, int]]:
    """分页条显示项：(文本, 目标页)。

    - 总页数 <= 7 时全部显示（无省略号）；
    - 否则固定显示第 1 页与最后一页，当前页前后各 2 页；
    - 存在间隙时插入可点击省略号（"···"，点击向省略方向跳 5 页并收敛到边界）。

    示例（total=64）：n=1 → 1·2·3···64；n=32 → 1···30·31·32·33·34···64；
    n=64 → 1···62·63·64。
    """
    current = max(1, min(current, total))
    if total <= 7:
        return [(str(i), i) for i in range(1, total + 1)]
    left = max(1, current - 2)
    right = min(total, current + 2)
    items: list[tuple[str, int]] = [(str(1), 1)]
    if left > 2:  # 1 与窗口左侧之间有间隙
        items.append(("···", max(2, current - 5)))
    for i in range(left, right + 1):
        if i == 1 or i == total:
            continue  # 两端已在首尾固定显示
        items.append((str(i), i))
    if right < total - 1:  # 窗口右侧与最后一页之间有间隙
        items.append(("···", min(total - 1, current + 5)))
    items.append((str(total), total))
    return items


def _cached_pixmap(path: Path, key: str) -> QPixmap | None:
    """带内存缓存（QPixmapCache LRU）的图片加载：先查内存，再读磁盘。

    命中内存直接返回（翻页往返零磁盘 I/O）；磁盘文件存在则加载并写入
    缓存（后续翻页命中）；均未命中返回 None（由后台下载线程补齐）。
    下载完成的图片在 _on_images_ready 重走本函数时自动入缓存。
    """
    cached = QPixmapCache.find(key)
    if cached is not None and not cached.isNull():
        return cached
    if not path.exists():
        return None
    pm = QPixmap(str(path))
    if pm.isNull():
        return None
    QPixmapCache.insert(key, pm)
    return pm


class _SyncWorker(QThread):
    """后台拉取线程：顺序拉取 shushu.fan 分页 API 全量主播推荐方案。"""

    ok = Signal(object)
    fail = Signal(str)

    def __init__(self, fetcher: object | None = None, timeout: int = 15) -> None:
        super().__init__()
        self._fetcher = fetcher
        self._timeout = timeout

    def run(self) -> None:
        try:
            solutions = sync_official_solutions(
                fetcher=self._fetcher,
                timeout=self._timeout,
                should_stop=self.isInterruptionRequested,
            )
        except Exception as exc:  # noqa: BLE001 - 线程边界，失败统一走 fail 信号
            self.fail.emit(str(exc))
            return
        self.ok.emit(solutions)


class _ImageWorker(QThread):
    """后台图片下载线程：按需补齐缺失的预览图/头像，已存在跳过。"""

    done = Signal()

    def __init__(
        self,
        jobs: list[tuple[str, Path]],
        opener: object | None = None,
    ) -> None:
        super().__init__()
        self._jobs = jobs
        self._opener = opener

    def run(self) -> None:
        for url, dest in self._jobs:
            if self.isInterruptionRequested():
                break
            ensure_image(url, dest, opener=self._opener)
        self.done.emit()


class GunSolutionCard(QFrame):
    """改枪码卡片：预览图 + 标题 + 枪械/类型 + 作者 + 描述滚动区 + 造价 + 复制。

    所有卡片统一结构：中间描述区（评语 + 标签）为固定高度滚动条，
    长文本内部滚动而非撑高卡片，保证每张卡片尺寸一致。
    """

    def __init__(
        self,
        solution: GunSolution,
        copied_text: str,
        no_image_text: str,
        channel_text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("gunCard")
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.solution = solution
        self._copied_text = copied_text
        self._copy_orig_text = ""
        self._channel_text = channel_text

        box = QVBoxLayout(self)
        box.setContentsMargins(12, 8, 12, 8)
        box.setSpacing(4)

        # 预览图（占位色块；图片下载完成后由页面统一刷新）
        self.image_label = QLabel()
        self.image_label.setObjectName("gunPreview")
        self.image_label.setFixedHeight(IMAGE_HEIGHT)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setText(no_image_text)
        box.addWidget(self.image_label)

        title = QLabel(solution.name or solution.solution_code[:16])
        title.setObjectName("gunTitle")
        title.setWordWrap(True)
        box.addWidget(title)

        meta = QLabel(f"{solution.gun_name} · {solution.weapon_type}".strip(" ·"))
        meta.setObjectName("gunMeta")
        meta.setWordWrap(True)
        box.addWidget(meta)

        # 作者行：头像 + 昵称 + 平台徽标
        author_row = QHBoxLayout()
        author_row.setSpacing(6)
        self.avatar_label = QLabel()
        self.avatar_label.setObjectName("gunAvatar")
        self.avatar_label.setFixedSize(AVATAR_SIZE, AVATAR_SIZE)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        author_row.addWidget(self.avatar_label)
        author = QLabel(solution.author)
        author.setObjectName("gunAuthor")
        author_row.addWidget(author, 1)
        channel = self._channel_text
        if channel:
            chip = QLabel(channel)
            chip.setObjectName("gunChannel")
            author_row.addWidget(chip)
        box.addLayout(author_row)

        # 描述滚动区：评语 + 标签，固定高度，超出部分内部滚动
        self.desc_scroll = QScrollArea()
        self.desc_scroll.setObjectName("gunDescScroll")
        self.desc_scroll.setWidgetResizable(True)
        self.desc_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.desc_scroll.setFixedHeight(DESC_AREA_HEIGHT)
        desc_inner = QLabel()
        desc_inner.setObjectName("gunDesc")
        desc_inner.setWordWrap(True)
        desc_inner.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        desc_parts = [solution.comment] if solution.comment else []
        if solution.tags:
            desc_parts.append("  ".join(solution.tags))
        desc_inner.setText("\n".join(desc_parts))
        self.desc_scroll.setWidget(desc_inner)
        box.addWidget(self.desc_scroll)

        # 底部：造价 + 复制按钮
        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        price = QLabel(format_price(solution.price))
        price.setObjectName("gunPrice")
        bottom.addWidget(price, 1)
        self.copy_button = QPushButton(copied_text)
        self.copy_button.setObjectName("gunCopy")
        self.copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_orig_text = copied_text
        bottom.addWidget(self.copy_button)
        box.addLayout(bottom)

        self.copy_button.clicked.connect(self._copy)

    def _copy(self) -> None:
        QApplication.clipboard().setText(self.solution.solution_code)
        self.copy_button.setText(self._copied_text)
        QTimer.singleShot(1500, lambda: self.copy_button.setText(self._copy_orig_text))

    def set_preview(self, pixmap: QPixmap | None) -> None:
        """设置预览图（下载完成后调用）；无图保持占位。"""
        if pixmap is not None and not pixmap.isNull():
            self.image_label.setText("")
            self.image_label.setPixmap(pixmap)
            self.image_label.setScaledContents(True)

    def set_avatar(self, pixmap: QPixmap | None) -> None:
        """设置作者头像（下载完成后调用）；无图显示昵称首字符。"""
        if pixmap is not None and not pixmap.isNull():
            self.avatar_label.setText("")
            self.avatar_label.setPixmap(pixmap)
            self.avatar_label.setScaledContents(True)
            self.avatar_label.setStyleSheet(
                f"border-radius: {AVATAR_SIZE // 2}px;"
            )
        else:
            self.avatar_label.setText(self.solution.author[:1] or "?")


class GunCodePage(QWidget):
    """主播推荐页面：缓存优先 + 低频同步 + 四维本地筛选。"""

    # 筛选维度顺序（与网页一致：武器类型/枪械名称/作者/标签）
    FILTER_DIMS = ("weapon", "gun", "author", "tag")

    def __init__(
        self,
        i18n: I18nManager,
        theme: ThemeManager,
        sync_interval_days: int = 10,
        render_page_size: int = 20,
        cache_file: Path | None = None,
        image_dir: Path | None = None,
        fetcher: object | None = None,
        image_opener: object | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._i18n = i18n
        self._theme = theme
        self._interval_days = sync_interval_days
        self._page_size = max(1, render_page_size)
        self._cache_file = cache_file
        self._image_dir = image_dir
        self._fetcher = fetcher
        self._image_opener = image_opener
        self._sync_worker: _SyncWorker | None = None
        self._image_worker: _ImageWorker | None = None
        # 图片下载串行化：上一轮 worker 运行中到达的新任务并入待办，
        # 结束后再启动，避免多个 worker 并发下载同一文件到同一 .tmp 路径
        self._pending_image_jobs: list[tuple[str, Path]] = []
        self._closing = False  # _shutdown 后禁止再启动新 worker
        self._fetching = False
        self._has_content = False
        self._throttle_until: datetime | None = None
        self._cards: list[GunSolutionCard] = []
        self._all_solutions: list[GunSolution] = []
        self._filtered: list[GunSolution] = []  # 当前筛选结果全集（翻页渲染用）
        self._page_index = 0  # 当前页（0-based）
        self._total_pages = 1
        self._filters: dict[str, str] = {d: "" for d in self.FILTER_DIMS}
        self._card_w = CARD_WIDTH
        self._cols: int | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)

        self.title_label = QLabel()
        font = self.title_label.font()
        font.setPointSize(15)
        font.setBold(True)
        self.title_label.setFont(font)

        self.status_label = QLabel()
        self.status_label.setObjectName("hint")
        self.status_label.setWordWrap(True)

        self.empty_label = QLabel()
        self.empty_label.setObjectName("hint")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 筛选栏：武器类型 / 枪械名称 / 作者 / 标签（本地过滤，不重新请求）
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self._filter_combos: dict[str, QComboBox] = {}
        for dim in self.FILTER_DIMS:
            label = QLabel()
            label.setObjectName("gunFilterLabel")
            label.setProperty("dim", dim)
            filter_row.addWidget(label)
            combo = SearchCombo()
            combo.setObjectName("gunFilter")
            combo.setMinimumWidth(96)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            self._filter_combos[dim] = combo
            filter_row.addWidget(combo)
        filter_row.addStretch(1)

        # 全部重置：将四个筛选框全部恢复为「全部」（位于筛选行右侧）
        self.reset_btn = QPushButton()
        self.reset_btn.setObjectName("gunFilterReset")
        self.reset_btn.clicked.connect(self._on_reset_filters)
        filter_row.addWidget(self.reset_btn)

        # 翻页控件：上一页 / 页码条 / 下一页（独立行居中，按钮文本 < 与 >）
        self.prev_btn = QPushButton()
        self.prev_btn.setObjectName("gunPagerBtn")
        self.prev_btn.clicked.connect(lambda: self._goto_page(self._page_index - 1))
        self.next_btn = QPushButton()
        self.next_btn.setObjectName("gunPagerBtn")
        self.next_btn.clicked.connect(lambda: self._goto_page(self._page_index + 1))
        # 动态页码条：1···n-2·n-1·n·n+1·n+2···s，各项可点击跳转
        self.pager_numbers = QHBoxLayout()
        self.pager_numbers.setSpacing(2)
        pager_row = QHBoxLayout()
        pager_row.addStretch(1)
        pager_row.addWidget(self.prev_btn)
        pager_row.addLayout(self.pager_numbers)
        pager_row.addWidget(self.next_btn)
        pager_row.addStretch(1)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("gunList")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._flow_host = QWidget()
        self._flow_host.setObjectName("gunFlowHost")
        self._flow = FlowLayout(self._flow_host, spacing=GRID_PADDING)
        self.scroll.setWidget(self._flow_host)

        root.addWidget(self.title_label)
        root.addWidget(self.status_label)
        root.addWidget(self.empty_label)
        root.addLayout(filter_row)
        root.addWidget(self.scroll, 1)
        root.addLayout(pager_row)

        # 卡片宽度自适应（宽度随视口伸缩，填满每行，参考每日密码页）
        self.scroll.installEventFilter(self)

        # 筛选联动：武器类型变化 -> 枪械名称选项联动（输入即联动）
        self._filter_combos["weapon"].lineEdit().textChanged.connect(
            self._on_weapon_changed
        )
        for dim in ("gun", "author", "tag"):
            self._filter_combos[dim].lineEdit().textChanged.connect(
                lambda _text, d=dim: self._apply_filters()
            )

        # 驻留期间周期检查：缓存过期且不在重试冷却内时自动同步
        self._timer = QTimer(self)
        self._timer.setInterval(10 * 60_000)
        self._timer.timeout.connect(self._maybe_sync)
        self._timer.start()

        self._apply_cache()
        self._maybe_sync()
        self.retranslate()

    # ── 卡片宽度自适应 ─────────────────────────────

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt 命名
        if obj is self.scroll and event.type() == QEvent.Type.Resize:
            self._reflow()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().resizeEvent(event)
        QTimer.singleShot(0, self._reflow)

    def _reflow(self) -> None:
        avail = self.scroll.viewport().width()
        if avail <= 0 or not self._cards:
            return
        lead = 4
        max_cols = max(1, (avail - lead) // (MIN_CARD_WIDTH + GRID_PADDING))
        max_cols = min(max_cols, len(self._cards))
        cols = 1
        for c in range(max_cols, 0, -1):
            w = min((avail - lead) // c - GRID_PADDING, MAX_CARD_WIDTH)
            if c * w + GRID_PADDING * (c - 1) <= avail - lead:
                cols = c
                break
        width = min(max((avail - lead) // cols - GRID_PADDING, MIN_CARD_WIDTH), MAX_CARD_WIDTH)
        if width == self._card_w and cols == self._cols:
            return
        self._cols = cols
        self._card_w = width
        for card in self._cards:
            card.setFixedWidth(width)
        self._flow.invalidate()
        self._flow_host.updateGeometry()

    # ── 数据与筛选 ──────────────────────────────────

    def _apply_cache(self) -> None:
        """读取缓存并渲染（离线优先展示）。

        反序列化按字段白名单逐条构造：旧版本缓存多/缺字段或类型异常
        只跳过该条，不拖垮整页（GunSolution(**s) 单条 TypeError 会 return 空白页）。
        """
        data = load_guns_cache(self._cache_file)
        if data is None:
            return
        solutions: list[GunSolution] = []
        for s in data.get("solutions", []):
            if not isinstance(s, dict):
                continue
            item = _solution_from_dict(s)
            if item is not None and item.id:
                solutions.append(item)
        if not solutions:
            return
        self._set_solutions(solutions, stale=True)

    def _set_solutions(self, solutions: list[GunSolution], stale: bool = False) -> None:
        """更新全量方案：重建筛选选项后按当前筛选渲染。"""
        self._all_solutions = solutions
        self._populate_filter_options()
        self._render_filtered(stale=stale)

    def _populate_filter_options(self) -> None:
        """从全量方案构建四个筛选维度的下拉选项（去重排序）。"""
        weapons = sorted({s.weapon_type for s in self._all_solutions if s.weapon_type})
        guns = sorted({s.gun_name for s in self._all_solutions if s.gun_name})
        authors = sorted({s.author for s in self._all_solutions if s.author})
        tags = sorted({t for s in self._all_solutions for t in s.tags})

        self._filter_combos["weapon"].blockSignals(True)
        self._filter_combos["gun"].blockSignals(True)
        self._filter_combos["author"].blockSignals(True)
        self._filter_combos["tag"].blockSignals(True)

        all_text = self._i18n.t("guncode.filter_all")
        # SearchCombo：顶部「全部」文本项 + 候选（空白/「全部」均为无条件）
        self._filter_combos["weapon"].set_items(weapons, all_text, preserve=False)
        # 枪械选项初始按全部武器类型列出（联动在 _on_weapon_changed 中处理）
        self._filter_combos["gun"].set_items(guns, all_text, preserve=False)
        self._filter_combos["author"].set_items(authors, all_text, preserve=False)
        self._filter_combos["tag"].set_items(tags, all_text, preserve=False)

        # 动态宽度：按本维度候选项最长文本设置最小宽度，确保收起状态下
        # 也能完整显示全部文字（候选项变化时随重建自动更新）
        for dim in self.FILTER_DIMS:
            combo = self._filter_combos[dim]
            fm = combo.fontMetrics()
            widest = max(
                (fm.horizontalAdvance(combo.itemText(i)) for i in range(combo.count())),
                default=0,
            )
            combo.setMinimumWidth(widest + 28)

        self._filter_combos["weapon"].blockSignals(False)
        self._filter_combos["gun"].blockSignals(False)
        self._filter_combos["author"].blockSignals(False)
        self._filter_combos["tag"].blockSignals(False)
        # 重置为「全部」并清空筛选状态
        self._filters = {d: "" for d in self.FILTER_DIMS}

    def _on_weapon_changed(self, _text: str) -> None:
        """武器类型变化：联动刷新枪械名称选项（保留当前枪械输入），并应用筛选。"""
        weapon = self._filter_combos["weapon"].filter_text()
        combo = self._filter_combos["gun"]
        if weapon:
            guns = sorted(
                {
                    s.gun_name
                    for s in self._all_solutions
                    if s.weapon_type and _text_contains(s.weapon_type, weapon) and s.gun_name
                }
            )
        else:
            guns = sorted({s.gun_name for s in self._all_solutions if s.gun_name})
        combo.set_items(guns, self._i18n.t("guncode.filter_all"), preserve=True)
        self._apply_filters()

    def _apply_filters(self) -> None:
        """按四个维度 AND 过滤全量方案并重新渲染（输入文本为包含匹配）。"""
        for dim in self.FILTER_DIMS:
            self._filters[dim] = self._filter_combos[dim].filter_text()
        result = [s for s in self._all_solutions if _match_solution(s, self._filters)]
        self._render(result, stale=False)

    def _render(self, solutions: list[GunSolution], stale: bool = False) -> None:
        """按筛选结果重置为第 1 页并渲染当前页卡片。

        任何时刻只实例化当前页（RENDER_PAGE_SIZE 张）卡片；翻页时
        _goto_page 销毁旧页、创建新页，内存峰值固定为单页大小。
        """
        self._filtered = solutions
        self._page_index = 0
        self._render_page(stale)

    def _render_page(self, stale: bool = False) -> None:
        """渲染当前页卡片（不重置页码）。"""
        total = len(self._filtered)
        self._total_pages = max(1, math.ceil(total / self._page_size))
        self._clear_cards()
        start = self._page_index * self._page_size
        end = min(start + self._page_size, total)
        self._cards = [self._build_card(s) for s in self._filtered[start:end]]
        for card in self._cards:
            self._flow.addWidget(card)
        self._has_content = True
        self.empty_label.hide()

        # 换页/筛选后回到顶部，避免停留在旧内容位置
        self.scroll.verticalScrollBar().setValue(0)

        self._update_status(stale)
        self._update_pager()
        self._reflow()
        self._ensure_images()

    def _goto_page(self, index: int, stale: bool = False) -> None:
        """跳转到指定页（越界自动收敛），页码不变时不做任何事。"""
        target = max(0, min(index, self._total_pages - 1))
        if target == self._page_index:
            return
        self._page_index = target
        self._render_page(stale)

    def _update_pager(self) -> None:
        """刷新翻页控件：重建页码条 + 边界按钮禁用状态。"""
        total = len(self._filtered)
        self._total_pages = max(1, math.ceil(total / self._page_size))
        self._rebuild_pager_numbers()
        self.prev_btn.setEnabled(self._page_index > 0)
        self.next_btn.setEnabled(self._page_index < self._total_pages - 1)

    def _rebuild_pager_numbers(self) -> None:
        """重建页码条按钮（当前页高亮，数字/省略号均可点击跳转）。

        按钮随 _update_pager 频繁重建，用 shiboken6.delete 立即释放 C++
        对象（deleteLater 在退出场景与 Python GC 双重删除会崩溃）。
        """
        while self.pager_numbers.count():
            item = self.pager_numbers.takeAt(0)
            w = item.widget()
            if w is not None:
                try:
                    from shiboken6 import delete as _qt_delete
                    _qt_delete(w)
                except ImportError:
                    w.deleteLater()
        current = self._page_index + 1
        for text, target in _pager_items(current, self._total_pages):
            btn = QPushButton(text)
            btn.setObjectName("gunPagerNumActive" if target == current else "gunPagerNum")
            btn.setFixedSize(30, 26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(
                lambda _checked=False, page=target: self._goto_page(page - 1)
            )
            self.pager_numbers.addWidget(btn)

    def _update_status(self, stale: bool = False) -> None:
        """更新状态行：方案数 + 更新/来源信息。"""
        data = load_guns_cache(self._cache_file)
        saved_at = str((data or {}).get("saved_at", ""))
        total = len(self._filtered)
        if len(self._all_solutions) != total:
            count_text = self._i18n.t("guncode.count_filtered").replace(
                "%1", str(total)
            ).replace("%2", str(len(self._all_solutions)))
        else:
            count_text = self._i18n.t("guncode.count").replace(
                "%1", str(total)
            )
        parts = [
            count_text,
            f"{self._i18n.t('guncode.updated')}：{saved_at or '—'}",
            f"{self._i18n.t('guncode.source')}：shushu.fan",
        ]
        if stale:
            parts.append(self._i18n.t("guncode.stale_hint"))
        self.status_label.setText(" · ".join(parts))

    def _on_reset_filters(self) -> None:
        """全部重置：清空四个筛选框输入（重建期间屏蔽信号，结束后统一筛选一次）。"""
        combos = list(self._filter_combos.values())
        for combo in combos:
            combo.lineEdit().blockSignals(True)
        try:
            for combo in combos:
                combo.reset()
        finally:
            for combo in combos:
                combo.lineEdit().blockSignals(False)
        # 武器类型无条件 -> 联动刷新枪械候选（保留枪械输入）并统一筛选一次
        self._on_weapon_changed("")

    def _render_filtered(self, stale: bool = False) -> None:
        """应用当前筛选渲染（筛选状态已存在下拉框时）。"""
        if not self._all_solutions:
            return
        # 从下拉框当前输入重建筛选条件（缓存/同步后选项已重建为「全部」）
        for dim in self.FILTER_DIMS:
            self._filters[dim] = self._filter_combos[dim].filter_text()
        result = [s for s in self._all_solutions if _match_solution(s, self._filters)]
        self._render(result, stale=stale)

    def _build_card(self, solution: GunSolution) -> GunSolutionCard:
        card = GunSolutionCard(
            solution,
            copied_text=self._i18n.t("guncode.copy"),
            no_image_text=self._i18n.t("guncode.no_image"),
            channel_text=self._i18n.t(_CHANNEL_KEYS.get(solution.channel, ""))
            or solution.channel,
        )
        # 继承当前自适应列宽（构造器默认 CARD_WIDTH，reflow 后为实际列宽；
        # 不设则翻页新建卡片会退回 260，与既有列宽不一致）
        card.setFixedSize(self._card_w, card.height())
        self._apply_local_images(card)
        return card

    def _apply_local_images(self, card: GunSolutionCard) -> None:
        """卡片渲染时加载本地已有图片（先内存缓存，再磁盘）；缺失交给下载。"""
        s = card.solution
        pm = _cached_pixmap(preview_image_path(s.id, self._image_dir), f"gun:preview:{s.id}")
        if pm is not None:
            card.set_preview(pm)
        pm = _cached_pixmap(avatar_image_path(s.author, self._image_dir), f"gun:avatar:{s.author}")
        if pm is not None:
            card.set_avatar(pm)

    def _ensure_images(self) -> None:
        """后台补齐缺失的预览图/头像（已存在跳过，失败静默）。

        串行化：当前下载 worker 仍在运行时不另起线程，任务并入待办，
        结束后统一再启动（避免并发写同一 .tmp 路径导致缓存损坏）。
        """
        jobs: list[tuple[str, Path]] = []
        for card in self._cards:
            s = card.solution
            if s.preview_pic:
                dest = preview_image_path(s.id, self._image_dir)
                if not dest.exists():
                    jobs.append((s.preview_pic, dest))
            if s.author_avatar:
                dest = avatar_image_path(s.author, self._image_dir)
                if not dest.exists():
                    jobs.append((s.author_avatar, dest))
        if not jobs:
            return
        if self._image_worker is not None and self._image_worker.isRunning():
            self._pending_image_jobs.extend(jobs)
            return
        self._start_image_worker(jobs)

    def _start_image_worker(self, jobs: list[tuple[str, Path]]) -> None:
        self._image_worker = _ImageWorker(jobs, self._image_opener)
        self._image_worker.done.connect(self._on_images_ready)
        worker = self._image_worker
        self._image_worker.finished.connect(
            lambda w=worker: self._on_image_worker_finished(w)
        )
        _track_worker(self._image_worker)
        self._image_worker.start()

    def _on_images_ready(self) -> None:
        for card in self._cards:
            self._apply_local_images(card)

    def _on_image_worker_finished(self, worker: object) -> None:
        if self._image_worker is not worker:
            return  # 旧 worker 的 finished 不覆盖新引用（防 _shutdown 漏掉）
        self._image_worker = None
        if not self._closing and self._pending_image_jobs:
            jobs, self._pending_image_jobs = self._pending_image_jobs, []
            self._start_image_worker(jobs)

    def _shutdown(self) -> None:
        """请求后台线程停止并等待，避免 QThread 运行时被回收（窗口关闭时调用）。"""
        self._closing = True
        for worker in (self._sync_worker, self._image_worker):
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.wait(2000)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._shutdown()
        super().closeEvent(event)

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
        self._cards = []

    # ── 同步调度 ─────────────────────────────────────

    def _maybe_sync(self) -> None:
        """缓存过期/缺失时后台同步；新鲜或冷却期内跳过（限频友好）。"""
        if self._fetching:
            return
        if self._throttle_until is not None and datetime.now() < self._throttle_until:
            return
        if cache_is_fresh(self._cache_file, self._interval_days):
            return
        self._start_sync()

    def _start_sync(self) -> None:
        self._fetching = True
        self.status_label.setText(self._i18n.t("guncode.syncing"))
        self._sync_worker = _SyncWorker(self._fetcher)
        self._sync_worker.ok.connect(self._on_sync_ok)
        self._sync_worker.fail.connect(self._on_sync_fail)
        self._sync_worker.finished.connect(self._on_worker_finished)
        self._sync_worker.finished.connect(self._sync_worker.deleteLater)
        _track_worker(self._sync_worker)
        self._sync_worker.start()

    def _on_sync_ok(self, solutions: object) -> None:
        items = [s for s in solutions if isinstance(s, GunSolution)]  # type: ignore[union-attr]
        if not items:
            self._on_sync_fail("empty")
            return
        save_guns_cache(items, self._cache_file)
        self._set_solutions(items, stale=False)
        self._throttle_until = None

    def _on_sync_fail(self, _reason: str) -> None:
        # 失败后冷却 6 小时再重试，避免循环请求第三方站点
        self._throttle_until = datetime.now() + RETRY_DELAY
        if self._has_content:
            self.status_label.setText(self._i18n.t("guncode.failed_with_cache"))
        else:
            self.status_label.setText(self._i18n.t("guncode.failed_empty"))
            self.empty_label.setText(self._i18n.t("guncode.failed_empty"))
            self.empty_label.show()

    def _on_worker_finished(self) -> None:
        self._fetching = False
        self._sync_worker = None

    def retranslate(self) -> None:
        self.title_label.setText(self._i18n.t("guncode.title"))
        # 筛选栏维度标签与「全部」项文案
        labels = {
            "weapon": "guncode.filter_weapon",
            "gun": "guncode.filter_gun",
            "author": "guncode.filter_author",
            "tag": "guncode.filter_tag",
        }
        for dim, key in labels.items():
            for label in self.findChildren(QLabel, "gunFilterLabel"):
                if label.property("dim") == dim:
                    label.setText(self._i18n.t(key))
        self.prev_btn.setText(self._i18n.t("guncode.prev_page"))
        self.next_btn.setText(self._i18n.t("guncode.next_page"))
        self.reset_btn.setText(self._i18n.t("guncode.reset_all"))
        if self._has_content and self._cards:
            self._update_status()
            self._update_pager()
