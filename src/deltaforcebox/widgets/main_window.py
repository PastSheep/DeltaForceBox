"""主窗口：侧边栏 + 堆叠页布局，负责语言/主题切换时的全局刷新。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.i18n import I18nManager
from ..core.theme import ThemeManager
from .pages.home_page import HomePage
from .pages.settings_page import SettingsPage

# 侧边栏条目：(页面标识, i18n key)
SIDEBAR_ITEMS = (
    ("home", "sidebar.home"),
    ("settings", "sidebar.settings"),
)


class MainWindow(QMainWindow):
    def __init__(self, i18n: I18nManager, theme: ThemeManager) -> None:
        super().__init__()
        self._i18n = i18n
        self._theme = theme

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
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(190)
        sidebar_layout.addWidget(self.app_title_label)
        sidebar_layout.addWidget(self.sidebar, 1)

        # 页面
        self.stack = QStackedWidget()
        self.pages = {
            "home": HomePage(i18n),
            "settings": SettingsPage(i18n, theme),
        }
        for key, page in self.pages.items():
            self.stack.addWidget(page)

        root.addWidget(sidebar_wrap)
        root.addWidget(self.stack, 1)

        self._populate_sidebar()
        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar.setCurrentRow(0)

        i18n.changed.connect(lambda _: self.retranslate())
        self.retranslate()
        self.resize(980, 680)

    def _populate_sidebar(self) -> None:
        self.sidebar.blockSignals(True)
        self.sidebar.clear()
        for key, text_key in SIDEBAR_ITEMS:
            self.sidebar.addItem(self._i18n.t(text_key))
            self.sidebar.item(self.sidebar.count() - 1).setData(Qt.UserRole, key)
        self.sidebar.blockSignals(False)

    def retranslate(self) -> None:
        self.setWindowTitle(self._i18n.t("app.title"))
        self.app_title_label.setText(self._i18n.t("app.title"))
        self._populate_sidebar()
        for page in self.pages.values():
            page.retranslate()
