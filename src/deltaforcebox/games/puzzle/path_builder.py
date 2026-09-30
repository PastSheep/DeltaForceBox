"""拼图碎片路径构建：将网页端 SVG path（d 字符串）移植为 QPainterPath。

对应 script.js 的 buildPiecePath / lineWithKnobH / lineWithKnobV：
- 每块碎片由四条边组成，内部边界按共享凸凹状态取反号，保证相邻咬合；
- 凸凹基础形状为半径受限的半圆（SVG A 圆弧），Qt 用逐点折线等价绘制；
- 每段 90° 弧再以「cusp-顶点」连线（弦）为轴镜像翻转：cusp 根部变平滑，
  两段弧在原平滑顶点处汇合成 ~179° 超锐利尖角——即"尖角凸凹"观感。
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


def _mirror(
    p: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
) -> tuple[float, float]:
    """点 p 关于直线 ab 的镜像（用于尖角凸凹变换）。"""
    vx, vy = b[0] - a[0], b[1] - a[1]
    t = ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / (vx * vx + vy * vy)
    return (2 * (a[0] + t * vx) - p[0], 2 * (a[1] + t * vy) - p[1])


def _arc_fit(
    path: QPainterPath,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    r: float,
    cx: float,
    cy: float,
    mirror_axis: tuple[tuple[float, float], tuple[float, float]] | None = None,
) -> None:
    """按 2° 步长采样圆心 (cx,cy)、半径 r、从 (x1,y1) 到 (x2,y2) 的圆弧。

    起止点由 atan2 确定，走短弧方向；每步一个 lineTo 采样点，
    高密度折线在任意缩放级别下视觉等于平滑圆弧。

    mirror_axis 非空时，将整段弧关于给定直线做镜像翻转：原本的
    "半圆弧"（cusp 尖角在根部、顶点平滑）翻转为"凹弧"——cusp 根部
    变平滑，而两段弧在原平滑顶点处汇合成超锐利的尖角（实测转角
    ~179°），即用户要求的"尖角凸凹"形状。
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
        px, py = cx + r * math.cos(a), cy + r * math.sin(a)
        if mirror_axis is not None:
            px, py = _mirror((px, py), mirror_axis[0], mirror_axis[1])
        path.lineTo(px, py)


def _edge_top(
    path: QPainterPath,
    x: float,
    y: float,
    w: float,
    param: float,
    radius: float,
    style: bool = False,
) -> None:
    """顶边（左→右）。param>0 向下凸，param<0 向上凹。

    style=False：半圆凸凹（网页版原始）；style=True：弧以「cusp-顶点」
    连线为轴镜像翻转——根部平滑、顶点 ~179° 尖角。
    """
    if param == 0:
        path.lineTo(x + w, y)
        return
    mx = x + w / 2.0
    r = min(radius, w * KNOB_MAX_FACTOR)
    vt = (mx, y + param * r)
    path.lineTo(mx - r, y)
    _arc_fit(
        path, mx - r, y, mx, y + param * r, r, mx, y,
        mirror_axis=((mx - r, y), vt) if style else None,
    )
    _arc_fit(
        path, mx, y + param * r, mx + r, y, r, mx, y,
        mirror_axis=(vt, (mx + r, y)) if style else None,
    )
    path.lineTo(x + w, y)


def _edge_bottom(
    path: QPainterPath,
    x: float,
    y: float,
    w: float,
    param: float,
    radius: float,
    style: bool = False,
) -> None:
    """底边（右→左，行进方向与顶边相反）。param>0 向下凸，param<0 向上凹。"""
    if param == 0:
        path.lineTo(x, y)
        return
    mx = x + w / 2.0
    r = min(radius, w * KNOB_MAX_FACTOR)
    vt = (mx, y + param * r)
    path.lineTo(mx + r, y)
    _arc_fit(
        path, mx + r, y, mx, y + param * r, r, mx, y,
        mirror_axis=((mx + r, y), vt) if style else None,
    )
    _arc_fit(
        path, mx, y + param * r, mx - r, y, r, mx, y,
        mirror_axis=(vt, (mx - r, y)) if style else None,
    )
    path.lineTo(x, y)


def _edge_right(
    path: QPainterPath,
    x: float,
    y: float,
    h: float,
    param: float,
    radius: float,
    style: bool = False,
) -> None:
    """右边（上→下）。param>0 向右凸，param<0 向左凹。"""
    if param == 0:
        path.lineTo(x, y + h)
        return
    my = y + h / 2.0
    r = min(radius, h * KNOB_MAX_FACTOR)
    vt = (x + param * r, my)
    path.lineTo(x, my - r)
    _arc_fit(
        path, x, my - r, x + param * r, my, r, x, my,
        mirror_axis=((x, my - r), vt) if style else None,
    )
    _arc_fit(
        path, x + param * r, my, x, my + r, r, x, my,
        mirror_axis=(vt, (x, my + r)) if style else None,
    )
    path.lineTo(x, y + h)


def _edge_left(
    path: QPainterPath,
    x: float,
    y: float,
    h: float,
    param: float,
    radius: float,
    style: bool = False,
) -> None:
    """左边（下→上，行进方向与右边相反）。param<0 向左凸，param>0 向右凹。"""
    if param == 0:
        path.lineTo(x, y)
        return
    my = y + h / 2.0
    r = min(radius, h * KNOB_MAX_FACTOR)
    vt = (x + param * r, my)
    path.lineTo(x, my + r)
    _arc_fit(
        path, x, my + r, x + param * r, my, r, x, my,
        mirror_axis=((x, my + r), vt) if style else None,
    )
    _arc_fit(
        path, x + param * r, my, x, my - r, r, x, my,
        mirror_axis=(vt, (x, my - r)) if style else None,
    )
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
    h_styles: list[list[int]] | None = None,
    v_styles: list[list[int]] | None = None,
) -> QPainterPath:
    """构建第 (r, c) 块碎片的完整路径（与网页端几何一致）。

    outward 符号含义：相对当前块，+1 表示该边朝“块外”凸起，-1 表示朝内凹陷。

    h_styles/v_styles 为可选样式矩阵（与 h_knobs/v_knobs 同形状）：
    0=半圆凸凹（网页版原始），1=尖角凸凹（弧镜像翻转）；缺省时全部为半圆。
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

    # 样式：0=半圆、1=尖角（相邻块共享同一边 → 样式一致）
    top_style = bool(h_styles and h_styles[r - 1][c]) if r > 0 else False
    bottom_style = bool(h_styles and h_styles[r][c]) if r < rows - 1 else False
    right_style = bool(v_styles and v_styles[r][c]) if c < cols - 1 else False
    left_style = bool(v_styles and v_styles[r][c - 1]) if c > 0 else False

    path = QPainterPath()
    path.moveTo(x, y)
    _edge_top(path, x, y, w, top_param, radius, top_style)
    _edge_right(path, x + w, y, h, right_param, radius, right_style)
    _edge_bottom(path, x, y + h, w, bottom_param, radius, bottom_style)
    _edge_left(path, x, y, h, left_param, radius, left_style)
    path.closeSubpath()
    return path
