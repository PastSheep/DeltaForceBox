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


def test_themes_style_scrollbar(qapp):
    """明暗主题均须包含滚动条规则（曾缺失而用系统默认亮色滚动条）。"""
    from deltaforcebox.core.paths import THEMES_DIR

    for name in ("dark", "light"):
        qss = (THEMES_DIR / f"{name}.qss").read_text(encoding="utf-8")
        assert "QScrollBar:vertical" in qss
        assert "QScrollBar:horizontal" in qss
        assert "QScrollBar::handle" in qss, f"{name} 主题缺少滚动条滑块规则"
        assert "QScrollBar::add-page" in qss


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
    if first.author_url:
        # URL 应为可点击的富文本链接（点击在浏览器打开）
        assert card.url_label.openExternalLinks()
        assert f'href="{first.author_url}"' in card.url_label.text()
        assert "<a href=" in card.url_label.text()
    dialog.accept()


def test_sources_dialog_non_modal_and_reused(qapp):
    """图片来源窗口应为非模态，且重复点击复用同一实例。"""
    window = MainWindow(I18nManager(), ThemeManager())
    page = window.pages["puzzle"]

    page._open_sources()
    dialog = page._sources_dialog
    assert dialog is not None
    assert dialog.isVisible()
    assert not dialog.isModal(), "来源窗口不应阻塞主窗口"

    page._open_sources()  # 再次点击：复用实例，不新建
    assert page._sources_dialog is dialog

    dialog.close()
    assert page._sources_dialog is None
    window.close()


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


def test_source_card_best_time_row(qapp, monkeypatch):
    """卡片最下方显示本图最快完成用时（无记录时显示 —）。"""
    from deltaforcebox.games.puzzle import source_dialog as sd

    i18n = I18nManager()
    first = load_manifest()[0]
    prefix = i18n.t("puzzle.sources.best")

    # 无记录：显示占位
    monkeypatch.setattr(sd, "load_best_times", lambda: {})
    dialog = SourceDialog(i18n)
    card = next(
        dialog.list.itemWidget(dialog.list.item(i))
        for i in range(dialog.list.count())
        if dialog.list.itemWidget(dialog.list.item(i)).thumb_label.toolTip()
        == first.path.name
    )
    assert card.best_label.text() == f"{prefix}：—"
    dialog.accept()

    # 有记录：显示格式化后的最快用时
    monkeypatch.setattr(sd, "load_best_times", lambda: {first.path.name: 65.5})
    dialog = SourceDialog(i18n)
    card = next(
        dialog.list.itemWidget(dialog.list.item(i))
        for i in range(dialog.list.count())
        if dialog.list.itemWidget(dialog.list.item(i)).thumb_label.toolTip()
        == first.path.name
    )
    assert card.best_label.text() == f"{prefix}：1:05.5"
    dialog.accept()


def test_puzzle_timer_and_best_record(qapp, tmp_path, monkeypatch):
    """第一次拿起碎片开始计时，完成停止并持久化本图最快用时。"""
    from PySide6.QtTest import QTest

    from deltaforcebox.core import records as rec
    from deltaforcebox.games.puzzle.piece_item import PieceItem

    monkeypatch.setattr(rec, "best_times_path", lambda *a: tmp_path / "best_times.json")
    window = MainWindow(I18nManager(), ThemeManager())
    page = window.pages["puzzle"]

    assert page.timer_label.text() == rec.format_time(0.0)
    assert not page._timer.isActive()

    # 第一次拿起碎片 → 开始计时
    piece: PieceItem = page._pieces[0]
    page._on_piece_picked(piece)
    assert page._elapsed.isValid()
    assert page._timer.isActive()

    QTest.qWait(250)  # 等计时器刷新显示
    assert page.timer_label.text() != rec.format_time(0.0)

    # 完成 → 停止计时并记录最快用时
    page._on_game_completed()
    assert not page._timer.isActive()
    assert page._current_image is not None
    saved = rec.load_best_times()
    assert page._current_image.path.name in saved
    assert saved[page._current_image.path.name] > 0.0

    # 重新开局 → 计时重置
    page.start_new()
    assert page.timer_label.text() == rec.format_time(0.0)
    assert not page._timer.isActive()
    window.close()


def test_changelog_parses_latest_section(tmp_path):
    """版本日志解析：取顶部最新版本节，忽略历史版本。"""
    from deltaforcebox.core import changelog

    doc = tmp_path / "版本日志.md"
    doc.write_text(
        """# 版本日志

## Beta-2.0（2026-10-02）

**当前版本**：测试简介。

### 新功能

- 功能 A
- 功能 B

---

## Beta-1.0（2026-10-01）

### 旧功能

- 旧功能 X
""",
        encoding="utf-8",
    )
    update = changelog.load_latest_update(doc)
    assert update["version"] == "Beta-2.0"
    assert update["intro"] == "当前版本：测试简介。"
    assert update["sections"] == [
        {"title": "新功能", "items": ["功能 A", "功能 B"]}
    ]


def test_changelog_missing_file_returns_none(tmp_path):
    from deltaforcebox.core import changelog

    assert changelog.load_latest_update(tmp_path / "不存在.md") is None


def test_home_shows_version_and_latest_update(qapp):
    """首页版本行带冒号，且显示最近一次版本更新内容。"""
    from deltaforcebox import __version__

    window = MainWindow(I18nManager(), ThemeManager())
    home = window.pages["home"]
    assert home.version_label.text() == f"版本：{__version__}"
    window.show()
    qapp.processEvents()
    assert home.update_title_label.isVisible()
    assert home.update_body_label.isVisible()
    assert home.update_body_label.text() != ""
    assert __version__ in home.update_title_label.text()
    window.close()
