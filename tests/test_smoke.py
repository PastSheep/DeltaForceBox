"""GUI 冒烟测试（offscreen）：装配、语言/主题切换、侧栏分组。"""

from __future__ import annotations

from PySide6.QtCore import Qt

from deltaforcebox.core.i18n import I18nManager
from deltaforcebox.core.theme import ThemeManager
from deltaforcebox.widgets.main_window import MainWindow


def test_main_window_builds(qapp):
    i18n = I18nManager()
    theme = ThemeManager()
    window = MainWindow(i18n, theme)
    # 系统标题栏文本隐藏，品牌名在侧栏顶部展示
    assert window.windowTitle() == ""
    assert window.app_title_label.text() == i18n.t("app.title")
    # 一级项：首页 / 小游戏 / 鼠鼠工具 / 设置
    assert window.sidebar.topLevelItemCount() == 4
    assert window.stack.count() == 4


def test_startup_home_selected_and_highlighted(qapp):
    """启动后默认显示首页，且侧栏「首页」项高亮选中。"""
    window = MainWindow(I18nManager(), ThemeManager())
    current = window.sidebar.currentItem()
    assert current is window.sidebar.topLevelItem(0)
    assert current.isSelected()
    assert window.stack.currentWidget() is window.pages["home"]


def test_sidebar_structure_with_group(qapp):
    """一级项：首页 / 小游戏分组 / 鼠鼠工具分组 / 设置；功能页归入各自分组。"""
    i18n = I18nManager()
    window = MainWindow(i18n, ThemeManager())
    sidebar = window.sidebar

    assert sidebar.topLevelItem(0).text(0) == i18n.t("sidebar.home")
    group = sidebar.topLevelItem(1)
    assert group.text(0) == i18n.t("sidebar.games")
    assert group.childCount() == 1
    assert group.child(0).text(0) == i18n.t("sidebar.puzzle")
    tools = sidebar.topLevelItem(2)
    assert tools.text(0) == i18n.t("sidebar.tools")
    assert tools.childCount() == 1
    assert tools.child(0).text(0) == i18n.t("sidebar.daily_password")
    assert sidebar.topLevelItem(3).text(0) == i18n.t("sidebar.settings")

    # 分组默认展开，且分组项不可选中
    assert group.isExpanded()
    assert tools.isExpanded()
    assert not (group.flags() & Qt.ItemFlag.ItemIsSelectable)
    assert not (tools.flags() & Qt.ItemFlag.ItemIsSelectable)


def test_group_click_toggles_expand_and_keeps_page(qapp):
    """点击分组标题切换展开/收起，且不切换页面。"""
    i18n = I18nManager()
    window = MainWindow(i18n, ThemeManager())
    sidebar = window.sidebar
    group = sidebar.topLevelItem(1)

    sidebar.setCurrentItem(sidebar.topLevelItem(0))  # 停在首页
    window._on_item_clicked(group, 0)
    assert not group.isExpanded(), "点击分组应收起"
    assert window.stack.currentIndex() == window.stack.indexOf(window.pages["home"])
    window._on_item_clicked(group, 0)
    assert group.isExpanded(), "再次点击应展开"


def test_leaf_click_switches_page(qapp):
    """点击分组内子项切换到对应页面。"""
    i18n = I18nManager()
    window = MainWindow(i18n, ThemeManager())
    sidebar = window.sidebar
    puzzle_item = sidebar.topLevelItem(1).child(0)

    sidebar.setCurrentItem(puzzle_item)
    assert window.stack.currentWidget() is window.pages["puzzle"]
    sidebar.setCurrentItem(sidebar.topLevelItem(3))
    assert window.stack.currentWidget() is window.pages["settings"]


def test_i18n_chinese_only(qapp):
    """当前仅支持中文：查词与 zh.json 完全一致，切英文无效。"""
    import json

    from deltaforcebox.core.paths import I18N_DIR

    i18n = I18nManager()
    assert i18n.language() == "zh"
    expected = json.loads((I18N_DIR / "zh.json").read_text(encoding="utf-8"))
    for key, value in expected.items():
        assert i18n.t(key) == value, f"key {key} 文案与资源文件不一致"
    # 未知 key 原样返回，避免静默吞错
    assert i18n.t("no.such.key") == "no.such.key"
    # 仅支持 zh：尝试切英文为无效操作，语言与文案不变
    i18n.set_language("en")
    assert i18n.language() == "zh"
    assert i18n.t("sidebar.home") == expected["sidebar.home"]


def test_settings_keeps_language_row_chinese_only(qapp):
    """设置页保留“语言”行，但下拉仅提供中文一项。"""
    from deltaforcebox.widgets.pages.settings_page import LANGUAGE_ITEMS

    assert LANGUAGE_ITEMS == (("zh", "中文"),)
    i18n = I18nManager()
    window = MainWindow(i18n, ThemeManager())
    page = window.pages["settings"]
    assert page.lang_label.text() == i18n.t("settings.language")
    assert page.lang_combo.count() == 1
    assert page.lang_combo.itemData(0) == "zh"
    assert page.lang_combo.currentText() == "中文"


def test_window_native_title_stays_blank(qapp):
    """防回归：Windows 标题栏在窗口标题为空时会回退显示应用显示名，
    因此 applicationDisplayName 必须为空，原生标题栏才会真正无文字。"""
    from deltaforcebox.app import build_app

    app, window = build_app()
    assert app.applicationDisplayName() == ""
    assert window.windowTitle() == ""
    window.close()


def test_title_bar_theme_follows_app_theme(qapp):
    """标题栏配色应跟随应用主题；无原生窗口/非 Windows 时优雅降级。"""
    import sys

    from deltaforcebox.app import build_app
    from deltaforcebox.core.theme import ThemeManager, current_theme
    from deltaforcebox.core.windows import set_title_bar_dark

    # 主题应用后 current_theme() 可查询
    tm = ThemeManager("dark")
    tm.apply()
    assert current_theme() == "dark"
    tm.set_theme("light")
    assert current_theme() == "light"

    # 无真实窗口句柄时不抛异常，返回 bool（offscreen 下 DWM 调用失败静默）
    result = set_title_bar_dark(0xDEADBEEF if sys.platform == "win32" else 1, True)
    assert isinstance(result, bool)

    # 主窗口显示/主题切换路径不崩溃
    app, window = build_app()
    window.show()
    window._apply_title_bar_theme()
    window.close()


def test_app_icon_loaded(qapp):
    """应用图标应设置为 resources/icons/app.ico 且可渲染。"""
    from PySide6.QtCore import QSize

    from deltaforcebox.app import APP_ICON, build_app

    assert APP_ICON.exists()
    app, window = build_app()
    icon = app.windowIcon()
    assert not icon.isNull()
    for size in (16, 32, 64, 256):
        assert not icon.pixmap(QSize(size, size)).isNull(), f"缺 {size}px 图标"
    assert window.windowIcon().cacheKey() == icon.cacheKey() or not window.windowIcon().isNull()
    window.close()


def test_theme_switch_triggers_title_bar_hook(qapp, monkeypatch, tmp_path):
    """设置页切换主题应实时触发标题栏配色钩子（防回归）。"""
    import json

    from deltaforcebox.app import build_app
    from deltaforcebox.core import windows as win_mod

    # 隔离设置文件，保证启动主题确定（不受真实 data/settings.json 影响）
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"theme": "dark", "language": "zh"}), encoding="utf-8")

    calls = []

    def fake_set(hwnd, dark):
        calls.append(bool(dark))
        return True

    monkeypatch.setattr(win_mod, "set_title_bar_dark", fake_set)
    app, window = build_app(settings_path=settings)
    window.show()  # showEvent 首次应用当前主题（dark）
    page = window.pages["settings"]
    page.theme_combo.setCurrentIndex(page.theme_combo.findData("light"))
    page.theme_combo.setCurrentIndex(page.theme_combo.findData("dark"))
    assert calls == [True, False, True], "标题栏应随主题实时切换"
    window.close()


def test_theme_switch_applies_stylesheet(qapp):
    theme = ThemeManager()
    theme.apply()
    theme.set_theme("light")
    assert qapp.styleSheet() != ""
    theme.set_theme("dark")
    assert "QMainWindow" in qapp.styleSheet()
