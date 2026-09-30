"""拼图游戏模块（移植自 shushu.fan 网页版拼图单人模式）。"""

from __future__ import annotations

from .grid import compute_grid_dynamic, create_knobs
from .path_builder import build_piece_path

__all__ = ["compute_grid_dynamic", "create_knobs", "build_piece_path"]
