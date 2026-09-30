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
    assert card.open_btn.text() == i18n.t("puzzle.sources.open")
    dialog.accept()


def test_card_open_location_button(qapp, monkeypatch):
    """点击「打开文件位置」应定位到该图片文件。"""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from deltaforcebox.games.puzzle import source_dialog

    calls = []
    monkeypatch.setattr(source_dialog, "open_file_location", calls.append)

    i18n = I18nManager()
    dialog = SourceDialog(i18n)
    first = load_manifest()[0]
    card = dialog.list.itemWidget(dialog.list.item(0))
    # 找到对应第一张图的卡片（排序未启用，插入序即清单序）
    QTest.mouseClick(card.open_btn, Qt.MouseButton.LeftButton)
    assert calls == [str(first.path)]
    dialog.accept()
