"""主窗口：侧边栏 + 堆叠页布局，负责语言/主题切换时的全局刷新。

侧边栏基于 QTreeWidget：无子条目的一级项（首页 / 设置）点击直接导航；
带子条目的分组项（小游戏）点击展开/收起，分组内子项为功能页，
采用自绘 chevron（▸/▾）指示展开状态，对齐 shushu.fan 风格的下拉式分组侧栏。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.i18n import I18nManager
from ..core.theme import ThemeManager
from ..games.puzzle.puzzle_page import PuzzlePage
from .pages.daily_password_page import DailyPasswordPage
from .pages.gun_code_page import GunCodePage
from .pages.home_page import HomePage
from .pages.my_codes_page import MyCodesPage
from .pages.settings_page import SettingsPage
from .update_controller import (
    ACTION_DOWNLOAD,
    ACTION_RETRY,
    ACTION_RUN,
    UpdateController,
)

# 侧边栏可调宽度边界（最小宽度需容纳标题“鼠鼠大王工具箱”完整显示）
SIDEBAR_MIN_WIDTH = 160
SIDEBAR_MAX_WIDTH = 420
SIDEBAR_INITIAL_WIDTH = 190

# 侧边栏条目结构：(页面标识, i18n key, 子条目)
# 子条目为 (key, i18n key) 二元组（叶子页）或 (key, i18n key, 孙条目) 三元组（子分组）
# 有子条目的为可展开分组，无子条目的为直接导航的一级项
SIDEBAR_ITEMS = (
    ("home", "sidebar.home", ()),
    ("games", "sidebar.games", (("puzzle", "sidebar.puzzle"),)),
    (
        "tools",
        "sidebar.tools",
        (
            ("daily_password", "sidebar.daily_password"),
            (
                "gun_code",
                "sidebar.gun_code",
                (
                    ("anchor", "sidebar.anchor"),
                    ("my_codes", "sidebar.my_codes"),
                ),
            ),
        ),
    ),
    ("settings", "sidebar.settings", ()),
)

# 分组项数据角色（标记该条目为可展开分组，与页面标识区分）
GROUP_ROLE = Qt.ItemDataRole.UserRole + 1

# 分组标签配色（随主题）
GROUP_COLORS = {"light": "#7a8699", "dark": "#8b93a1"}


def _chevron_icon(expanded: bool) -> QIcon:
    """自绘 chevron 图标：收起时 ▸ 指向右，展开时 ▾ 指向下。"""
    size = 14
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(
        QColor("#8b93a1"),
        2.0,
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )
    painter.setPen(pen)
    if expanded:
        painter.drawLine(QPoint(3, 4), QPoint(7, 8))
        painter.drawLine(QPoint(7, 8), QPoint(11, 4))
    else:
        painter.drawLine(QPoint(4, 3), QPoint(8, 7))
        painter.drawLine(QPoint(8, 7), QPoint(4, 11))
    painter.end()
    return QIcon(pm)


class MainWindow(QMainWindow):
    def __init__(
        self,
        i18n: I18nManager,
        theme: ThemeManager,
        puzzle_pieces: int = 48,
        password_sources: tuple[str, ...] | None = None,
        gun_sync_interval_days: int = 10,
        gun_render_page_size: int = 20,
        settings_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._i18n = i18n
        self._theme = theme
        self._puzzle_pieces = puzzle_pieces
        self._password_sources = password_sources
        self._gun_sync_interval_days = gun_sync_interval_days
        self._gun_render_page_size = gun_render_page_size
        self._settings_path = settings_path

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 侧边栏
        sidebar_wrap = QWidget()
        sidebar_layout = QVBoxLayout(sidebar_wrap)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        self.app_title_label = QLabel()
        self.app_title_label.setObjectName("appTitle")
        self.sidebar = QTreeWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setRootIsDecorated(False)  # 使用自绘 chevron，隐藏默认展开三角
        self.sidebar.setIndentation(14)
        self.sidebar.setItemsExpandable(True)
        self.sidebar.setExpandsOnDoubleClick(False)
        sidebar_layout.addWidget(self.app_title_label)
        sidebar_layout.addWidget(self.sidebar, 1)

        # 页面
        self.stack = QStackedWidget()
        self.pages = {
            "home": HomePage(i18n),
            "puzzle": PuzzlePage(i18n, theme, puzzle_pieces=self._puzzle_pieces),
            "daily_password": DailyPasswordPage(
                i18n,
                theme,
                source_order=self._password_sources,
            ),
            "anchor": GunCodePage(
                i18n,
                theme,
                sync_interval_days=self._gun_sync_interval_days,
                render_page_size=self._gun_render_page_size,
            ),
            "my_codes": MyCodesPage(i18n, theme),
            "settings": SettingsPage(i18n, theme, settings_path=self._settings_path),
        }
        for key, page in self.pages.items():
            self.stack.addWidget(page)

        # 可调宽侧边栏：QSplitter 分隔，边界内自由拖拽
        sidebar_wrap.setMinimumWidth(SIDEBAR_MIN_WIDTH)
        sidebar_wrap.setMaximumWidth(SIDEBAR_MAX_WIDTH)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("mainSplitter")
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(6)
        self.splitter.addWidget(sidebar_wrap)
        self.splitter.addWidget(self.stack)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([SIDEBAR_INITIAL_WIDTH, 790])

        root.addWidget(self.splitter)

        self._populate_sidebar()
        self.sidebar.itemClicked.connect(self._on_item_clicked)
        self.sidebar.currentItemChanged.connect(self._on_current_changed)
        self.sidebar.itemExpanded.connect(
            lambda item: self._set_group_icon(item, True)
        )
        self.sidebar.itemCollapsed.connect(
            lambda item: self._set_group_icon(item, False)
        )
        self.sidebar.setCurrentItem(self.sidebar.topLevelItem(0))

        i18n.changed.connect(lambda _: self.retranslate())
        theme.changed.connect(self._refresh_group_style)
        theme.changed.connect(lambda _: self._apply_title_bar_theme())
        # 设置页修改来源优先级后实时同步每日密码页（无需重启）
        self.pages["settings"].password_source_changed.connect(
            self._on_password_source_changed
        )
        # 不显示系统标题栏文本（保留最小化/关闭按钮，品牌名见侧栏顶部）
        self.setWindowTitle("")
        self._init_updater()
        self.retranslate()
        self.resize(980, 680)
        # 启动时检查更新（后台线程；按设置模式决定检查/下载/静默）
        self._updater.check_on_start()

    # ── 自动更新 ────────────────────────────────────────────

    def _init_updater(self) -> None:
        """创建更新控制器并接线：信号 → 首页右上角提示条。"""
        self._updater = UpdateController(self)
        self._updater.notice.connect(self._on_update_notice)
        self._updater.progress.connect(self._on_update_progress)

    def _on_update_notice(self, text: str, action: object) -> None:
        """更新通知 → 首页提示条（非弹窗）；空文本表示静默，隐藏提示。"""
        bar = self.pages["home"].notice_bar
        if not text:
            bar.hide_notice()
            return
        if action == ACTION_DOWNLOAD:
            bar.show_notice(
                text, "下载", on_action=self._updater.download_candidate
            )
        elif action == ACTION_RUN:
            bar.show_notice(
                text, "打开位置", on_action=self._updater.open_installer_location
            )
        elif action == ACTION_RETRY:
            bar.show_notice(text, "重试", on_action=self._updater.retry)
        else:
            bar.show_notice(text)

    def _on_update_progress(self, text: str, done: int, total: int) -> None:
        self.pages["home"].notice_bar.show_progress(text, done, total)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # 原生窗口创建后才可设置标题栏配色（跟随应用主题）
        self._apply_title_bar_theme()

    def _apply_title_bar_theme(self) -> None:
        from ..core.windows import apply_title_bar_theme

        apply_title_bar_theme(self)
    # ── 侧边栏构建 ─────────────────────────────────────────

    def _populate_sidebar(self) -> None:
        """重建侧边栏树；分组默认展开，分组项不可选中（避免抢占高亮）。

        支持两级分组：一级分组下可挂子分组（如 鼠鼠工具 > 改枪码 > 主播推荐）。
        """
        self.sidebar.blockSignals(True)
        self.sidebar.clear()
        for key, text_key, children in SIDEBAR_ITEMS:
            item = QTreeWidgetItem([self._i18n.t(text_key)])
            item.setData(0, Qt.ItemDataRole.UserRole, key)
            self._add_sidebar_children(item, children)
            if children:
                self._mark_group(item, level=1)
            self.sidebar.addTopLevelItem(item)
            # 分组默认收起（用户点击展开；对齐 shushu.fan 下拉式侧栏）
        self.sidebar.blockSignals(False)
        self._refresh_group_style()

    def _add_sidebar_children(
        self, parent: QTreeWidgetItem, children: tuple[object, ...]
    ) -> None:
        """递归添加子条目：二元组为叶子页，三元组为子分组。"""
        for child in children:
            if len(child) == 3:
                sub_key, sub_text, sub_children = child  # type: ignore[misc]
                node = QTreeWidgetItem([self._i18n.t(sub_text)])
                node.setData(0, Qt.ItemDataRole.UserRole, sub_key)
                self._add_sidebar_children(node, sub_children)
                self._mark_group(node, level=2)
                parent.addChild(node)
            else:
                child_key, child_text = child  # type: ignore[misc]
                node = QTreeWidgetItem([self._i18n.t(child_text)])
                node.setData(0, Qt.ItemDataRole.UserRole, child_key)
                parent.addChild(node)

    GROUP_FONT_SIZES = {1: 12, 2: 10}  # 一级/二级分组字号（标签页统一默认字号）

    def _mark_group(self, item: QTreeWidgetItem, level: int = 1) -> None:
        """把条目标记为分组：不可选中、弱化字号、自绘 chevron。

        一级分组与二级分组使用不同字号；具体标签页不设字号（全局统一）。
        """
        item.setData(0, GROUP_ROLE, "group")
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        font = item.font(0)
        font.setPointSize(self.GROUP_FONT_SIZES.get(level, 11))
        item.setFont(0, font)
        item.setIcon(0, _chevron_icon(False))  # 分组默认收起

    def _refresh_group_style(self, _theme: str | None = None) -> None:
        """按当前主题刷新分组项前景色（QSS 无法区分分组与普通项）。"""
        color = QColor(GROUP_COLORS.get(self._theme.theme(), "#8b93a1"))

        def _apply(item: QTreeWidgetItem) -> None:
            for i in range(item.childCount()):
                child = item.child(i)
                if child.data(0, GROUP_ROLE) == "group":
                    child.setForeground(0, color)
                _apply(child)

        for i in range(self.sidebar.topLevelItemCount()):
            item = self.sidebar.topLevelItem(i)
            if item.data(0, GROUP_ROLE) == "group":
                item.setForeground(0, color)
            _apply(item)

    def _set_group_icon(self, item: QTreeWidgetItem, expanded: bool) -> None:
        if item.childCount() > 0:
            item.setIcon(0, _chevron_icon(expanded))

    # ── 交互 ───────────────────────────────────────────────

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """分组项：切换展开/收起；叶子项：切换页面。"""
        if item.childCount() > 0:
            item.setExpanded(not item.isExpanded())
            return
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key in self.pages:
            self.stack.setCurrentWidget(self.pages[key])

    def _on_current_changed(
        self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None
    ) -> None:
        if current is None or current.childCount() > 0:
            return
        key = current.data(0, Qt.ItemDataRole.UserRole)
        if key in self.pages:
            self.stack.setCurrentWidget(self.pages[key])

    def _find_item_by_key(self, key: str) -> QTreeWidgetItem | None:
        """按页面标识查找侧栏条目（递归，含分组内子项）。"""

        def _search(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            if item.data(0, Qt.ItemDataRole.UserRole) == key:
                return item
            for i in range(item.childCount()):
                found = _search(item.child(i))
                if found is not None:
                    return found
            return None

        for i in range(self.sidebar.topLevelItemCount()):
            found = _search(self.sidebar.topLevelItem(i))
            if found is not None:
                return found
        return None

    def _on_password_source_changed(self, order: object) -> None:
        """设置页来源优先级变更：实时更新每日密码页顺序并立即重新拉取。"""
        page = self.pages.get("daily_password")
        if page is not None:
            page.set_source_order(tuple(order))  # type: ignore[arg-type]

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """关闭窗口前收尾各页面的后台线程（QThread 运行时被回收会崩溃）。"""
        # auto 模式下如有待安装更新：拉起安装器（独立进程，主程序退出后继续）
        self._updater.on_app_close()
        for page in self.pages.values():
            close = getattr(page, "_shutdown", None)
            if callable(close):
                close()
        super().closeEvent(event)

    def retranslate(self) -> None:
        # 系统标题栏文本保持隐藏，不随语言/文案变化
        self.app_title_label.setText(self._i18n.t("app.title"))
        # 记住当前选中的叶子项，重建后恢复高亮（clear() 会清空选中状态）
        current = self.sidebar.currentItem()
        current_key = (
            current.data(0, Qt.ItemDataRole.UserRole)
            if current is not None and current.childCount() == 0
            else "home"
        )
        self._populate_sidebar()
        item = self._find_item_by_key(current_key) or self._find_item_by_key("home")
        if item is not None:
            # 若所在分组当前收起，先展开父链保证选中项可见
            parent = item.parent()
            while parent is not None:
                if not parent.isExpanded():
                    parent.setExpanded(True)
                    self._set_group_icon(parent, True)
                parent = parent.parent()
            self.sidebar.setCurrentItem(item)
        for page in self.pages.values():
            page.retranslate()
