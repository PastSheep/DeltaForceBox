"""拼图网格与凸凹方向算法。

从网页端 script.js 逐行移植（computeGridDynamic / createKnobs），保证
同一张图片在桌面端生成的碎片布局与网页端一致。
"""

from __future__ import annotations

import math
import random

__all__ = ["compute_grid_dynamic", "create_knobs", "create_knob_styles"]


# 目标碎片总数：不同宽高比的图片都稳定在该值附近，体验一致
TARGET_PIECES = 48
# 单块最小可玩尺寸（逻辑单位）：cell 低于此值碎片过小、难以拖拽
MIN_CELL = 10.0
# 最大行数（cell 下限防御）：极端小图不至于碎片爆炸
MAX_ROWS = 15


def compute_grid_dynamic(
    width: float,
    height: float,
    target_pieces: int = TARGET_PIECES,
    min_pieces: int = 4,
) -> tuple[int, int, float, float]:
    """按“目标碎片总数”计算行列数，返回 (rows, cols, cell_w, cell_h)。

    正方形 cell + floor 取整下，碎片数 n = floor(h/c)·floor(w/c) ≈ 面积/c²，
    由面积决定、与宽高比弱相关（无需额外几何约束）。算法：
    - 直接解 c0 = sqrt(面积/target_pieces) 作为初值；
    - 在 c0 邻域枚举候选 cell（保持正方形，行列数由 floor 决定），
      选 |n − target_pieces| 最小、cell ≥ MIN_CELL 且 n ≥ min_pieces 的组合；
    - 行列数向下取整且至少为 2。
    """
    short_side = min(width, height)
    c_min = max(MIN_CELL, short_side / MAX_ROWS)
    c0 = math.sqrt(width * height / target_pieces)

    best: tuple[int, int, int, float] | None = None  # (score, rows, cols, cell)
    for k in range(-3, 4):
        cell = max(c_min, c0 + k * 0.5)
        rows = max(2, math.floor(height / cell))
        cols = max(2, math.floor(width / cell))
        n = rows * cols
        if n < min_pieces:
            continue
        score = abs(n - target_pieces)
        # 平分时取更大的 cell（碎片更易拖拽）
        if best is None or score < best[0] or (score == best[0] and cell > best[3]):
            best = (score, rows, cols, cell)
    assert best is not None  # 行列至少 2×2，n >= min_pieces，候选必非空
    _, rows, cols, cell = best
    return rows, cols, cell, cell


def create_knobs(rows: int, cols: int) -> tuple[list[list[int]], list[list[int]]]:
    """为内部边界随机生成凸/凹方向，返回 (h_knobs, v_knobs)。

    - h_knobs[r][c]：水平边界，r 在 [0, rows-2]，表示第 r 行与第 r+1 行之间的边；
      +1 表示“下凸”（对上方那块），-1 表示“上凸”。
    - v_knobs[r][c]：垂直边界，c 在 [0, cols-2]；+1 表示“右凸”（对左边那块）。
    相邻两块共享同一条边且符号相反，保证咬合匹配。
    """
    h_knobs = [
        [1 if random.random() > 0.5 else -1 for _ in range(cols)]
        for _ in range(rows - 1)
    ]
    v_knobs = [
        [1 if random.random() > 0.5 else -1 for _ in range(cols - 1)]
        for _ in range(rows)
    ]
    return h_knobs, v_knobs


def create_knob_styles(rows: int, cols: int) -> tuple[list[list[int]], list[list[int]]]:
    """随机生成凸凹样式矩阵，返回 (h_styles, v_styles)。

    形状与 create_knobs 的 h_knobs/v_knobs 一一对应：
    - 0：半圆凸凹（网页版原始形状：圆滑顶点 + 根部 cusp 尖角）；
    - 1：尖角凸凹（弧镜像翻转后：根部平滑、顶点 ~179° 超锐利尖角）。
    相邻两块共享同一条边且样式一致，保证咬合匹配。
    """
    h_styles = [
        [1 if random.random() > 0.5 else 0 for _ in range(cols)]
        for _ in range(rows - 1)
    ]
    v_styles = [
        [1 if random.random() > 0.5 else 0 for _ in range(cols - 1)]
        for _ in range(rows)
    ]
    return h_styles, v_styles
