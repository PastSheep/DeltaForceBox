"""拼图碎片路径构建：将网页端 SVG path（d 字符串）移植为 QPainterPath。

对应 script.js 的 buildPiecePath / lineWithKnobH / lineWithKnobV：
- 每块碎片由四条边组成，内部边界按共享凸凹状态取反号，保证相邻咬合；
- 凸凹用半径受限的半圆（SVG A 圆弧），Qt 用 QPainterPath.arcTo 等价绘制。
"""

from __future__ import annotations

import math

from PySide6.QtGui import QPainterPath

__all__ = ["build_piece_path", "KNOB_RADIUS_FACTOR", "KNOB_MAX_FACTOR"]


KNOB_RADIUS_FACTOR = 0.18  # 凸凹半径 = min(cell_w, cell_h) * 0.18
KNOB_MAX_FACTOR = 0.35  # 半径上限 = 边长 * 0.35

# 圆弧采样步长：2°/段。不用三次贝塞尔，因为 QPainter 对贝塞尔路径的
# 内部细分阈值约 0.25 逻辑单位——半径 3.6 单位的半圆只会被切分成
# 4~5 段（约 45°/段），经视图放大后轮廓呈明显的折角梯形；改为逐点
# lineTo 折线后 Qt 不再做二次细分，任何放大级别下视觉都与圆弧一致。
_ARC_STEP_DEG = 2.0


def _arc_fit(
    path: QPainterPath,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    r: float,
    cx: float,
    cy: float,
) -> None:
    """按 2° 步长采样圆心 (cx,cy)、半径 r、从 (x1,y1) 到 (x2,y2) 的圆弧。

    起止点由 atan2 确定，走短弧方向；每步一个 lineTo 采样点，
    高密度折线在任意缩放级别下视觉等于平滑圆弧（与网页端 SVG 一致）。
    """
    a1 = math.atan2(y1 - cy, x1 - cx)
    a2 = math.atan2(y2 - cy, x2 - cx)
    span = a2 - a1
    while span <= -math.pi:
        span += 2.0 * math.pi
    while span > math.pi:
        span -= 2.0 * math.pi

    n = max(2, int(math.ceil(abs(span) / math.radians(_ARC_STEP_DEG))))
    for i in range(1, n + 1):
        a = a1 + span * (i / n)
        path.lineTo(cx + r * math.cos(a), cy + r * math.sin(a))


def _edge_top(
    path: QPainterPath, x: float, y: float, w: float, param: float, radius: float
) -> None:
    """顶边（左→右）。param>0 向下凸，param<0 向上凹。"""
    if param == 0:
        path.lineTo(x + w, y)
        return
    mx = x + w / 2.0
    r = min(radius, w * KNOB_MAX_FACTOR)
    path.lineTo(mx - r, y)
    _arc_fit(path, mx - r, y, mx, y + param * r, r, mx, y)
    _arc_fit(path, mx, y + param * r, mx + r, y, r, mx, y)
    path.lineTo(x + w, y)


def _edge_bottom(
    path: QPainterPath, x: float, y: float, w: float, param: float, radius: float
) -> None:
    """底边（右→左，行进方向与顶边相反）。param>0 向下凸，param<0 向上凹。"""
    if param == 0:
        path.lineTo(x, y)
        return
    mx = x + w / 2.0
    r = min(radius, w * KNOB_MAX_FACTOR)
    path.lineTo(mx + r, y)
    _arc_fit(path, mx + r, y, mx, y + param * r, r, mx, y)
    _arc_fit(path, mx, y + param * r, mx - r, y, r, mx, y)
    path.lineTo(x, y)


def _edge_right(
    path: QPainterPath, x: float, y: float, h: float, param: float, radius: float
) -> None:
    """右边（上→下）。param>0 向右凸，param<0 向左凹。"""
    if param == 0:
        path.lineTo(x, y + h)
        return
    my = y + h / 2.0
    r = min(radius, h * KNOB_MAX_FACTOR)
    path.lineTo(x, my - r)
    _arc_fit(path, x, my - r, x + param * r, my, r, x, my)
    _arc_fit(path, x + param * r, my, x, my + r, r, x, my)
    path.lineTo(x, y + h)


def _edge_left(
    path: QPainterPath, x: float, y: float, h: float, param: float, radius: float
) -> None:
    """左边（下→上，行进方向与右边相反）。param<0 向左凸，param>0 向右凹。"""
    if param == 0:
        path.lineTo(x, y)
        return
    my = y + h / 2.0
    r = min(radius, h * KNOB_MAX_FACTOR)
    path.lineTo(x, my + r)
    _arc_fit(path, x, my + r, x + param * r, my, r, x, my)
    _arc_fit(path, x + param * r, my, x, my - r, r, x, my)
    path.lineTo(x, y)


def build_piece_path(
    r: int,
    c: int,
    cell_w: float,
    cell_h: float,
    rows: int,
    cols: int,
    h_knobs: list[list[int]],
    v_knobs: list[list[int]],
) -> QPainterPath:
    """构建第 (r, c) 块碎片的完整路径（与网页端几何一致）。

    outward 符号含义：相对当前块，+1 表示该边朝“块外”凸起，-1 表示朝内凹陷。
    """
    x = c * cell_w
    y = r * cell_h
    w = cell_w
    h = cell_h
    radius = min(w, h) * KNOB_RADIUS_FACTOR

    # 与网页端 buildPiecePath 的 outwardSign 完全一致
    top_out = -h_knobs[r - 1][c] if r > 0 else 0
    right_out = v_knobs[r][c] if c < cols - 1 else 0
    bottom_out = h_knobs[r][c] if r < rows - 1 else 0
    left_out = -v_knobs[r][c - 1] if c > 0 else 0

    # 映射为各边绘制函数的位移参数（lineWithKnobH/V 正号语义）
    top_param = -top_out
    bottom_param = bottom_out
    right_param = right_out
    left_param = -left_out

    path = QPainterPath()
    path.moveTo(x, y)
    _edge_top(path, x, y, w, top_param, radius)
    _edge_right(path, x + w, y, h, right_param, radius)
    _edge_bottom(path, x, y + h, w, bottom_param, radius)
    _edge_left(path, x, y, h, left_param, radius)
    path.closeSubpath()
    return path
