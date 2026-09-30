"""主题管理：明暗主题 QSS 应用与切换。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from .paths import THEMES_DIR

SUPPORTED_THEMES = ("light", "dark")
DEFAULT_THEME = "dark"

# 最近一次实际生效的主题（供标题栏等原生外观联动查询）
_ACTIVE_THEME: str = DEFAULT_THEME


def current_theme() -> str:
    """返回最近一次实际应用的主题名（未应用过则为默认主题）。"""
    return _ACTIVE_THEME


class ThemeManager(QObject):
    """加载 resources/themes/{name}.qss 并应用到全局。"""

    changed = Signal(str)

    def __init__(self, theme: str = DEFAULT_THEME, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._theme = theme if theme in SUPPORTED_THEMES else DEFAULT_THEME

    def theme(self) -> str:
        return self._theme

    def set_theme(self, theme: str) -> None:
        if theme == self._theme or theme not in SUPPORTED_THEMES:
            return
        self._theme = theme
        self._apply()
        self.changed.emit(theme)

    def _apply(self) -> None:
        global _ACTIVE_THEME
        app = QApplication.instance()
        if app is None:
            return
        path = THEMES_DIR / f"{self._theme}.qss"
        app.setStyleSheet(path.read_text(encoding="utf-8"))
        _ACTIVE_THEME = self._theme

    def apply(self) -> None:
        """应用当前主题（程序启动时调用）。"""
        self._apply()
