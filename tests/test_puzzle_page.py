"""拼图页面 GUI 冒烟测试（offscreen 平台，不打开真实窗口）。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from deltaforcebox.core.i18n import I18nManager
from deltaforcebox.core.theme import ThemeManager
from deltaforcebox.games.puzzle.puzzle_page import PuzzlePage


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


@pytest.fixture()
def page(app):
    page = PuzzlePage(I18nManager(), ThemeManager())
    return page


def test_page_creates_pieces(page):
    """开局后生成不少于 4 块的碎片。"""
    assert len(page._pieces) >= 4
    assert page._scene is not None
    assert not page._scene.sceneRect().isNull()


def test_pieces_are_scattered(page):
    """碎片已打散：至少一块偏移大于 0。"""
    assert any(p.offset().manhattanLength() > 0.1 for p in page._pieces)


def test_check_solved_not_fired_at_start(page):
    """开局未完成：完整图未显示、作者未显示。"""
    assert page._end_item is None
    assert not page.author_label.isVisible()


def test_force_solve_triggers_complete(page):
    """把所有碎片吸附到目标位置后，完成流程被触发。"""
    for p in page._pieces:
        p.setPos(p.target_pos())
        p.setRotation(0.0)
    page._check_solved()
    assert page._end_item is not None
    assert "©" in page.author_label.text()


def test_restart_rebuilds(page):
    """重新开始后碎片重建且都在场景中。"""
    page.start_new()
    assert len(page._pieces) >= 4
    assert all(p.scene() is page._scene for p in page._pieces)
    # 目标位置无重复（每块唯一）
    targets = [(p.target_pos().x(), p.target_pos().y()) for p in page._pieces]
    assert len(targets) == len(set(targets))
