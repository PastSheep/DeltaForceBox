"""拼图算法单元测试：网格计算、凸凹方向、路径几何。

验证要点（对照网页端行为）：
- 网格行列 ≥2，短边块数 ≥4，单元格为正方形；
- 相邻碎片共享边凸凹互补：共享边界处的圆弧路径在两块上几何重合；
- 碎片路径闭合，包围盒含凸起范围（0.18×cell 外扩）。
"""

from __future__ import annotations

import random

from PySide6.QtCore import QPointF

from deltaforcebox.games.puzzle import build_piece_path, compute_grid_dynamic, create_knobs

KNOB_R = 0.18


def test_grid_basic():
    rows, cols, cell_w, cell_h = compute_grid_dynamic(100, 100, target_cell=18)
    assert rows >= 2 and cols >= 2
    assert rows == cols  # 正方形图片
    assert abs(cell_w - cell_h) < 1e-9
    assert max(rows, cols) >= 4  # 短边块数 >= 4
    assert abs(rows * cell_w - 100) < 1e-6  # 网格覆盖面积 ≈ 原图


def test_grid_wide_image():
    rows, cols, cell_w, cell_h = compute_grid_dynamic(178, 100, target_cell=18)
    assert rows >= 2 and cols >= 2
    assert abs(cell_w - cell_h) < 1e-9
    assert abs(rows * cell_h - 100) < 1e-6


def test_knobs_shape():
    rows, cols = 5, 7
    h_knobs, v_knobs = create_knobs(rows, cols)
    assert len(h_knobs) == rows - 1
    assert all(len(row) == cols for row in h_knobs)
    assert len(v_knobs) == rows
    assert all(len(row) == cols - 1 for row in v_knobs)
    for row in h_knobs + v_knobs:
        for val in row:
            assert val in (1, -1)


def test_knobs_deterministic_with_seed():
    random.seed(42)
    a_h, a_v = create_knobs(4, 4)
    random.seed(42)
    b_h, b_v = create_knobs(4, 4)
    assert a_h == b_h and a_v == b_v


def test_shared_edges_interlock_horizontal():
    """上下相邻两块：共享边的凸起只属于凸出方向那块（凹块让位），凸凹互补。"""
    random.seed(7)
    rows, cols = 6, 8
    cell = 16.0
    h_knobs, v_knobs = create_knobs(rows, cols)
    for r in range(rows - 1):
        for c in range(cols):
            top = build_piece_path(r, c, cell, cell, rows, cols, h_knobs, v_knobs)
            bottom = build_piece_path(r + 1, c, cell, cell, rows, cols, h_knobs, v_knobs)
            edge_y = (r + 1) * cell
            mx = c * cell + cell / 2.0
            knob_r = cell * KNOB_R
            # 凸点（向 h 方向偏移 1px 的内偏点，避开轮廓边界浮点误差）
            inset = 1.0
            mid = QPointF(mx, edge_y + h_knobs[r][c] * (knob_r - inset))
            # h=+1 底边下凸 -> 凸月牙属于上块；h=-1 顶边上凸 -> 属于下块
            assert top.contains(mid) == (h_knobs[r][c] == 1), f"top({r},{c})"
            assert bottom.contains(mid) == (h_knobs[r][c] == -1), f"bottom({r+1},{c})"


def test_shared_edges_interlock_vertical():
    """左右相邻两块：共享边的凸起只属于凸出方向那块（凹块让位），凸凹互补。"""
    random.seed(13)
    rows, cols = 6, 8
    cell = 16.0
    h_knobs, v_knobs = create_knobs(rows, cols)
    for r in range(rows):
        for c in range(cols - 1):
            left = build_piece_path(r, c, cell, cell, rows, cols, h_knobs, v_knobs)
            right = build_piece_path(r, c + 1, cell, cell, rows, cols, h_knobs, v_knobs)
            edge_x = (c + 1) * cell
            my = r * cell + cell / 2.0
            knob_r = cell * KNOB_R
            inset = 1.0
            mid = QPointF(edge_x + v_knobs[r][c] * (knob_r - inset), my)
            # v=+1 右凸 -> 凸月牙属于左块；v=-1 左凸 -> 属于右块
            assert left.contains(mid) == (v_knobs[r][c] == 1), f"left({r},{c})"
            assert right.contains(mid) == (v_knobs[r][c] == -1), f"right({r},{c+1})"


def test_path_closed_and_within_bounds():
    """路径闭合且包围盒不超过 cell + 凸起范围。"""
    random.seed(3)
    rows, cols = 5, 5
    cell = 20.0
    h_knobs, v_knobs = create_knobs(rows, cols)
    knob_r = cell * KNOB_R
    for r in range(rows):
        for c in range(cols):
            p = build_piece_path(r, c, cell, cell, rows, cols, h_knobs, v_knobs)
            assert p.elementCount() > 3
            rect = p.boundingRect()
            # 三次贝塞尔拟合圆弧有约 0.04px 的极值凸出，容差取 0.5px
            tol = 0.5
            assert rect.left() >= c * cell - knob_r - tol
            assert rect.right() <= (c + 1) * cell + knob_r + tol
            assert rect.top() >= r * cell - knob_r - tol
            assert rect.bottom() <= (r + 1) * cell + knob_r + tol
