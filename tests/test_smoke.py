"""GUI 冒烟测试（offscreen）：装配、语言/主题切换。"""

from __future__ import annotations

from deltaforcebox.core.i18n import I18nManager
from deltaforcebox.core.theme import ThemeManager
from deltaforcebox.widgets.main_window import MainWindow


def test_main_window_builds(qapp):
    i18n = I18nManager()
    theme = ThemeManager()
    window = MainWindow(i18n, theme)
    assert window.windowTitle() == "三角洲行动工具箱"
    assert window.sidebar.count() == 2
    assert window.stack.count() == 2


def test_language_switch_refreshes_texts(qapp):
    i18n = I18nManager()
    window = MainWindow(i18n, ThemeManager())
    i18n.set_language("en")
    assert window.windowTitle() == "Delta Force Box"
    assert window.sidebar.item(0).text() == "Home"
    assert window.sidebar.item(1).text() == "Settings"
    i18n.set_language("zh")
    assert window.windowTitle() == "三角洲行动工具箱"


def test_theme_switch_applies_stylesheet(qapp):
    theme = ThemeManager()
    theme.apply()
    theme.set_theme("light")
    assert qapp.styleSheet() != ""
    theme.set_theme("dark")
    assert "QMainWindow" in qapp.styleSheet()
