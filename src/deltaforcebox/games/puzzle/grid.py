"""拼图网格与凸凹方向算法。

从网页端 script.js 逐行移植（computeGridDynamic / createKnobs），保证
同一张图片在桌面端生成的碎片布局与网页端一致。
"""

from __future__ import annotations

import math
import random

__all__ = ["compute_grid_dynamic", "create_knobs", "create_knob_styles"]


def compute_grid_dynamic(
    width: float,
    height: float,
    target_cell: float = 18.0,
    min_pieces: int = 4,
) -> tuple[int, int, float, float]:
    """按“单块目标尺寸”计算行列数，返回 (rows, cols, cell_w, cell_h)。

    与网页端 computeGridDynamic 一致：
    - 基于短边估算短边块数（至少 min_pieces）；
    - 以正方形单元格尺寸为准，行列数向下取整且至少为 2。
    """
    short_side = min(width, height)
    short_count = max(min_pieces, round(short_side / target_cell))
    cell_size = short_side / short_count
    rows = max(2, math.floor(height / cell_size))
    cols = max(2, math.floor(width / cell_size))
    return rows, cols, cell_size, cell_size


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
