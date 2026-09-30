"""首页作者信息与图片来源卡片窗口测试。"""

from __future__ import annotations

from deltaforcebox.core.i18n import I18nManager
from deltaforcebox.core.theme import ThemeManager
from deltaforcebox.games.puzzle.image_source import load_manifest
from deltaforcebox.games.puzzle.source_dialog import SourceCard, SourceDialog
from deltaforcebox.widgets.main_window import MainWindow
from deltaforcebox.widgets.pages.home_page import AUTHOR_EMAIL, AUTHOR_NAME


def test_home_page_shows_author_info(qapp):
    i18n = I18nManager()
    window = MainWindow(i18n, ThemeManager())
    author_label = window.pages["home"].author_label
    email_label = window.pages["home"].email_label
    assert author_label.text() == f"{i18n.t('home.author')}：{AUTHOR_NAME}"
    assert AUTHOR_EMAIL in email_label.text()
    assert f"{i18n.t('home.email')}：" in email_label.text()
    assert "mailto:" in email_label.text()


def test_source_dialog_background_follows_theme(qapp):
    """来源窗口背景应跟随主题（曾缺 QDialog 基础规则而始终亮色）。"""
    from PySide6.QtGui import QImage

    from deltaforcebox.core.i18n import I18nManager
    from deltaforcebox.core.theme import ThemeManager
    from deltaforcebox.games.puzzle.source_dialog import SourceDialog

    def corner_rgb(theme_name: str):
        theme = ThemeManager(theme_name)
        theme.apply()
        dialog = SourceDialog(I18nManager())
        dialog.resize(900, 580)
        image = dialog.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)
        color = image.pixelColor(8, 8)  # 边距空白区即对话框背景
        dialog.accept()
        return color.red(), color.green(), color.blue()

    dark_rgb = corner_rgb("dark")
    assert all(abs(ch - ref) <= 3 for ch, ref in zip(dark_rgb, (0x1C, 0x1F, 0x26))), (
        f"暗色背景不符: {dark_rgb}"
    )
    light_rgb = corner_rgb("light")
    assert all(abs(ch - ref) <= 3 for ch, ref in zip(light_rgb, (0xF5, 0xF6, 0xFA))), (
        f"浅色背景不符: {light_rgb}"
    )


def test_source_dialog_lists_manifest_as_cards(qapp):
    i18n = I18nManager()
    dialog = SourceDialog(i18n)
    images = load_manifest()

    assert dialog.list.count() == len(images)
    assert dialog.count_label.text() == i18n.t("puzzle.sources.count", len(images))

    # 每张清单图片都有一张卡片，卡片上带作者/URL/打开按钮
    card_by_file = {}
    for i in range(dialog.list.count()):
        card = dialog.list.itemWidget(dialog.list.item(i))
        assert isinstance(card, SourceCard)
        card_by_file[card.thumb_label.toolTip()] = card
    assert {img.path.name for img in images} == set(card_by_file)

    first = images[0]
    card = card_by_file[first.path.name]
    assert first.author in card.author_label.text()
    assert card.url_label.toolTip() == (first.author_url or "")
    dialog.accept()


def test_dialog_open_location_button(qapp, monkeypatch):
    """底部「打开文件位置」按钮应打开图片统一所在文件夹。"""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from deltaforcebox.games.puzzle import source_dialog
    from deltaforcebox.games.puzzle.image_source import PUZZLE_IMAGES_DIR

    calls = []
    monkeypatch.setattr(source_dialog, "open_in_explorer", calls.append)

    i18n = I18nManager()
    dialog = SourceDialog(i18n)
    QTest.mouseClick(dialog.open_btn, Qt.MouseButton.LeftButton)
    assert calls == [str(PUZZLE_IMAGES_DIR)]
    dialog.accept()
