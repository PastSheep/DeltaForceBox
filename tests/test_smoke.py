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
    assert window.windowTitle() == "三角洲行动工具箱"
    assert window.sidebar.topLevelItemCount() == 3
    assert window.stack.count() == 3


def test_sidebar_structure_with_group(qapp):
    """一级项：首页 / 小游戏分组 / 设置；拼图归入小游戏分组。"""
    i18n = I18nManager()
    window = MainWindow(i18n, ThemeManager())
    sidebar = window.sidebar

    assert sidebar.topLevelItem(0).text(0) == "首页"
    group = sidebar.topLevelItem(1)
    assert group.text(0) == "小游戏"
    assert group.childCount() == 1
    assert group.child(0).text(0) == "骇爪美图"
    assert sidebar.topLevelItem(2).text(0) == "设置"

    # 分组默认展开，且分组项不可选中
    assert group.isExpanded()
    assert not (group.flags() & Qt.ItemFlag.ItemIsSelectable)


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
    sidebar.setCurrentItem(sidebar.topLevelItem(2))
    assert window.stack.currentWidget() is window.pages["settings"]


def test_i18n_chinese_only(qapp):
    """当前仅支持中文：查词返回中文文案，语言标识为 zh，切换英文无效。"""
    i18n = I18nManager()
    assert i18n.language() == "zh"
    assert i18n.t("sidebar.home") == "首页"
    assert i18n.t("sidebar.games") == "小游戏"
    assert i18n.t("sidebar.puzzle") == "骇爪美图"
    assert i18n.t("settings.theme.dark") == "深色"
    # 未知 key 原样返回，避免静默吞错
    assert i18n.t("no.such.key") == "no.such.key"
    # 仅支持 zh：尝试切英文为无效操作，语言与文案不变
    i18n.set_language("en")
    assert i18n.language() == "zh"
    assert i18n.t("sidebar.home") == "首页"


def test_settings_keeps_language_row_chinese_only(qapp):
    """设置页保留“语言”行，但下拉仅提供中文一项。"""
    from deltaforcebox.widgets.pages.settings_page import LANGUAGE_ITEMS

    assert LANGUAGE_ITEMS == (("zh", "中文"),)
    i18n = I18nManager()
    window = MainWindow(i18n, ThemeManager())
    page = window.pages["settings"]
    assert page.lang_label.text() == "语言"
    assert page.lang_combo.count() == 1
    assert page.lang_combo.itemData(0) == "zh"
    assert page.lang_combo.currentText() == "中文"


def test_theme_switch_applies_stylesheet(qapp):
    theme = ThemeManager()
    theme.apply()
    theme.set_theme("light")
    assert qapp.styleSheet() != ""
    theme.set_theme("dark")
    assert "QMainWindow" in qapp.styleSheet()
