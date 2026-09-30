"""首页作者信息与图片来源窗口测试。"""

from __future__ import annotations

from deltaforcebox.core.i18n import I18nManager
from deltaforcebox.core.theme import ThemeManager
from deltaforcebox.games.puzzle.image_source import load_manifest
from deltaforcebox.games.puzzle.source_dialog import SourceDialog
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


def test_source_dialog_lists_manifest(qapp):
    i18n = I18nManager()
    dialog = SourceDialog(i18n)
    images = load_manifest()

    assert dialog.table.rowCount() == len(images)
    assert dialog.table.columnCount() == 4
    assert dialog.table.horizontalHeaderItem(1).text() == i18n.t("puzzle.sources.file")
    assert dialog.table.horizontalHeaderItem(2).text() == i18n.t("puzzle.sources.author")
    assert dialog.table.horizontalHeaderItem(3).text() == i18n.t("puzzle.sources.url")

    # 清单中的每张图都应出现在表格中（行序受排序影响，按内容匹配）
    filenames = {
        dialog.table.item(r, 1).text() for r in range(dialog.table.rowCount())
    }
    assert {img.path.name for img in images} == filenames

    # 作者与来源列与清单一致（抽查第一张）
    first = images[0]
    row = next(
        r for r in range(dialog.table.rowCount())
        if dialog.table.item(r, 1).text() == first.path.name
    )
    assert dialog.table.item(row, 2).text() == first.author
    assert dialog.table.item(row, 3).text() == (first.author_url or "")

    # 缩略图已生成
    assert not dialog.table.item(row, 0).icon().isNull()
    dialog.accept()
