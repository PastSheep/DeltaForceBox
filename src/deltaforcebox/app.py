"""应用装配：QApplication、国际化、主题、设置持久化与主窗口。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .core.i18n import DEFAULT_LANGUAGE, I18nManager
from .core.paths import RESOURCES_DIR
from .core.settings import DEFAULT_SETTINGS, load_settings, save_settings
from .core.theme import DEFAULT_THEME, ThemeManager
from .widgets.main_window import MainWindow

APP_ICON = RESOURCES_DIR / "icons" / "app.ico"
DEFAULT_PUZZLE_PIECES = int(DEFAULT_SETTINGS["puzzle_pieces"])


def build_app(
    argv: list[str] | None = None,
    settings_path: Path | None = None,
) -> tuple[QApplication, MainWindow]:
    """创建应用实例并装配全部组件。

    按 data/settings.json 中的持久化设置初始化主题与语言，
    运行中发生变更时自动写回；settings_path 供测试注入临时文件。
    """
    app = QApplication.instance() or QApplication(argv or [])
    app.setApplicationName("鼠鼠大王工具箱")
    # 显示名置空：避免 Windows 在窗口标题为空时回退显示应用名，
    # 使原生标题栏真正无文字（任务栏标签随之显示应用名以外内容）
    app.setApplicationDisplayName("")
    # 应用图标：任务栏 / 标题栏 / Alt-Tab 均显示（窗口继承该图标）
    if APP_ICON.exists():
        app.setWindowIcon(QIcon(str(APP_ICON)))

    settings = load_settings(settings_path)
    i18n = I18nManager(language=settings.get("language", DEFAULT_LANGUAGE))
    theme = ThemeManager(theme=settings.get("theme", DEFAULT_THEME))
    theme.apply()

    def _persist(_value: str | None = None) -> None:
        # 先读回现有设置再更新：保留用户在配置文件中手改的字段
        #（如拼图碎片数 puzzle_pieces），避免主题/语言变更时被覆盖丢失
        values = load_settings(settings_path)
        values["theme"] = theme.theme()
        values["language"] = i18n.language()
        save_settings(values, settings_path)

    theme.changed.connect(_persist)
    i18n.changed.connect(_persist)

    puzzle_pieces = settings.get("puzzle_pieces", DEFAULT_PUZZLE_PIECES)
    window = MainWindow(i18n, theme, puzzle_pieces=puzzle_pieces)
    return app, window
