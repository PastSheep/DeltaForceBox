"""应用装配：QApplication、国际化、主题、设置持久化与主窗口。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from .core.i18n import DEFAULT_LANGUAGE, I18nManager
from .core.settings import load_settings, save_settings
from .core.theme import DEFAULT_THEME, ThemeManager
from .widgets.main_window import MainWindow


def build_app(
    argv: list[str] | None = None,
    settings_path: Path | None = None,
) -> tuple[QApplication, MainWindow]:
    """创建应用实例并装配全部组件。

    按 data/settings.json 中的持久化设置初始化主题与语言，
    运行中发生变更时自动写回；settings_path 供测试注入临时文件。
    """
    app = QApplication.instance() or QApplication(argv or [])
    app.setApplicationName("Delta Force Box")
    app.setApplicationDisplayName("Delta Force Box")

    settings = load_settings(settings_path)
    i18n = I18nManager(language=settings.get("language", DEFAULT_LANGUAGE))
    theme = ThemeManager(theme=settings.get("theme", DEFAULT_THEME))
    theme.apply()

    def _persist(_value: str | None = None) -> None:
        save_settings(
            {"theme": theme.theme(), "language": i18n.language()},
            settings_path,
        )

    theme.changed.connect(_persist)
    i18n.changed.connect(_persist)

    window = MainWindow(i18n, theme)
    return app, window
