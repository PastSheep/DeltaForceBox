"""主窗口：侧边栏 + 堆叠页布局，负责语言/主题切换时的全局刷新。

侧边栏基于 QTreeWidget：无子条目的一级项（首页 / 设置）点击直接导航；
带子条目的分组项（小游戏）点击展开/收起，分组内子项为功能页，
采用自绘 chevron（▸/▾）指示展开状态，对齐 shushu.fan 风格的下拉式分组侧栏。
"""

from __future__ import annotations

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
from .pages.home_page import HomePage
from .pages.settings_page import SettingsPage

# 侧边栏可调宽度边界（最小宽度需容纳标题“鼠鼠大王工具箱”完整显示）
SIDEBAR_MIN_WIDTH = 160
SIDEBAR_MAX_WIDTH = 420
SIDEBAR_INITIAL_WIDTH = 190

# 侧边栏条目结构：(页面标识, i18n key, 子条目((子key, 子i18n key), ...))
# 有子条目的为可展开分组，无子条目的为直接导航的一级项
SIDEBAR_ITEMS = (
    ("home", "sidebar.home", ()),
    ("games", "sidebar.games", (("puzzle", "sidebar.puzzle"),)),
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
    ) -> None:
        super().__init__()
        self._i18n = i18n
        self._theme = theme
        self._puzzle_pieces = puzzle_pieces

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
            "settings": SettingsPage(i18n, theme),
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
        # 不显示系统标题栏文本（保留最小化/关闭按钮，品牌名见侧栏顶部）
        self.setWindowTitle("")
        self.retranslate()
        self.resize(980, 680)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # 原生窗口创建后才可设置标题栏配色（跟随应用主题）
        self._apply_title_bar_theme()

    def _apply_title_bar_theme(self) -> None:
        from ..core.windows import apply_title_bar_theme

        apply_title_bar_theme(self)
    # ── 侧边栏构建 ─────────────────────────────────────────

    def _populate_sidebar(self) -> None:
        """重建侧边栏树；分组默认展开，分组项不可选中（避免抢占高亮）。"""
        self.sidebar.blockSignals(True)
        self.sidebar.clear()
        for key, text_key, children in SIDEBAR_ITEMS:
            item = QTreeWidgetItem([self._i18n.t(text_key)])
            item.setData(0, Qt.ItemDataRole.UserRole, key)
            for child_key, child_text_key in children:
                child = QTreeWidgetItem([self._i18n.t(child_text_key)])
                child.setData(0, Qt.ItemDataRole.UserRole, child_key)
                item.addChild(child)
            if children:
                # 分组项：不参与选中，颜色弱化、字号略小，带 chevron
                item.setData(0, GROUP_ROLE, "group")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                font = item.font(0)
                font.setPointSize(11)
                item.setFont(0, font)
                item.setIcon(0, _chevron_icon(True))
            self.sidebar.addTopLevelItem(item)
            if children:
                # 展开状态需在条目入树后设置才生效
                item.setExpanded(True)
        self.sidebar.blockSignals(False)
        self._refresh_group_style()

    def _refresh_group_style(self, _theme: str | None = None) -> None:
        """按当前主题刷新分组项前景色（QSS 无法区分分组与普通项）。"""
        color = QColor(GROUP_COLORS.get(self._theme.theme(), "#8b93a1"))
        for i in range(self.sidebar.topLevelItemCount()):
            item = self.sidebar.topLevelItem(i)
            if item.data(0, GROUP_ROLE) == "group":
                item.setForeground(0, color)
                for j in range(item.childCount()):
                    item.child(j).setForeground(0, color)

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
        """按页面标识查找侧栏条目（含分组内子项）。"""
        for i in range(self.sidebar.topLevelItemCount()):
            item = self.sidebar.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) == key:
                return item
            for j in range(item.childCount()):
                child = item.child(j)
                if child.data(0, Qt.ItemDataRole.UserRole) == key:
                    return child
        return None

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
            self.sidebar.setCurrentItem(item)
        for page in self.pages.values():
            page.retranslate()
