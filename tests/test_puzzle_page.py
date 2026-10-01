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


def test_snap_tracking_incremental(page):
    """释放吸附加入集合、拿起已吸附块解除（O(1) 增量维护）。"""
    n = len(page._pieces)
    p = page._pieces[0]
    p.setPos(p.target_pos())
    page._on_piece_released(p)
    assert len(page._snapped) == 1
    # 拿起已吸附块 → 解除
    page._on_piece_picked(p)
    assert len(page._snapped) == 0
    # 拿起后再次释放吸附 → 重新加入
    p.setPos(p.target_pos())
    page._on_piece_released(p)
    assert len(page._snapped) == 1
    assert n >= 1


def test_snap_set_idempotent(page):
    """重复释放同一块不重复计数（集合幂等）。"""
    p = page._pieces[0]
    p.setPos(p.target_pos())
    page._on_piece_released(p)
    page._on_piece_released(p)
    assert len(page._snapped) == 1


def test_complete_fires_after_last_snap_animation(page):
    """全部碎片吸附后，完成判定推迟到最后一块动画结束（不中途弹完成图）。"""
    n = len(page._pieces)
    for p in page._pieces:
        p.setPos(p.target_pos())
        page._on_piece_released(p)
    assert len(page._snapped) == n
    assert page._end_item is None  # 动画均未结束，尚未判定
    page._after_snap(page._pieces[-1])  # 最后一块动画 finished
    assert page._end_item is not None
    assert "©" in page.author_label.text()


def test_picking_snapped_piece_prevents_complete(page):
    """拿起已吸附块后（即使其 snap 动画结束）不触发完成。"""
    n = len(page._pieces)
    p = page._pieces[0]
    for piece in page._pieces:
        piece.setPos(piece.target_pos())
        page._on_piece_released(piece)
    page._on_piece_picked(p)  # 拿起已吸附块
    page._after_snap(p)  # 该块 snap 动画仍会结束（动画未被打断）
    assert len(page._snapped) == n - 1
    assert page._end_item is None


def test_custom_piece_count(app):
    """配置文件指定的碎片数生效：16 块目标 → 碎片数明显低于默认 48 且不小于 4。"""
    page = PuzzlePage(I18nManager(), ThemeManager(), puzzle_pieces=16)
    n = len(page._pieces)
    assert n >= 4
    assert abs(n - 16) <= 12  # floor 取整容差（与网格测试同口径）
    assert n < 48


def test_piece_count_normalization(app):
    """非法/越界配置值回退：0→4、超大→200、非数字→默认 48。"""
    from deltaforcebox.games.puzzle.puzzle_page import _normalize_piece_count

    assert _normalize_piece_count(0) == 4
    assert _normalize_piece_count(99999) == 200
    assert _normalize_piece_count("abc") == 48
    assert _normalize_piece_count(None) == 48
    assert _normalize_piece_count(60) == 60
    assert _normalize_piece_count("16") == 16


def test_restart_rebuilds(page):
    """重新开始后碎片重建且都在场景中。"""
    page.start_new()
    assert len(page._pieces) >= 4
    assert all(p.scene() is page._scene for p in page._pieces)
    # 目标位置无重复（每块唯一）
    targets = [(p.target_pos().x(), p.target_pos().y()) for p in page._pieces]
    assert len(targets) == len(set(targets))
