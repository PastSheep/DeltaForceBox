"""应用装配：QApplication、国际化、主题与主窗口。"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from .core.i18n import I18nManager
from .core.theme import ThemeManager
from .widgets.main_window import MainWindow


def build_app(argv: list[str] | None = None) -> tuple[QApplication, MainWindow]:
    """创建应用实例并装配全部组件。"""
    app = QApplication(argv or [])
    app.setApplicationName("Delta Force Box")
    app.setApplicationDisplayName("Delta Force Box")

    i18n = I18nManager()
    theme = ThemeManager()
    theme.apply()

    window = MainWindow(i18n, theme)
    return app, window
