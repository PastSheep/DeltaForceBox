"""拼图图片来源：manifest 清单读取、随机选图、网格纹理生成。

对应网页端 getImageInfo / loadImage 逻辑：随机洗牌后逐张试载，
选中的图片按“cover（xMidYMid slice）”语义缩放到网格尺寸。
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QImage, QPixmap, QTransform

from ...core.paths import RESOURCES_DIR

PUZZLE_IMAGES_DIR = RESOURCES_DIR / "images" / "puzzle"
MANIFEST_PATH = PUZZLE_IMAGES_DIR / "manifest.json"


@dataclass(frozen=True)
class PuzzleImage:
    """一张拼图素材：本地路径 + 作者 + 来源 URL。"""

    path: Path
    author: str
    author_url: str | None


def load_manifest() -> list[PuzzleImage]:
    """读取 manifest.json（字段：文件名 / 作者 / 来源URL）。"""
    with MANIFEST_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    images: list[PuzzleImage] = []
    for item in data:
        name = item.get("文件名", "")
        images.append(
            PuzzleImage(
                path=PUZZLE_IMAGES_DIR / name,
                author=item.get("作者", "未知作者"),
                author_url=item.get("来源URL") or None,
            )
        )
    return images


def pick_random_image(images: list[PuzzleImage] | None = None) -> PuzzleImage:
    """洗牌后返回第一张可加载的图片（与网页端 loadFirstAvailable 一致）。"""
    pool = images if images is not None else load_manifest()
    shuffled = list(pool)
    random.shuffle(shuffled)
    for img in shuffled:
        if img.path.exists() and img.path.is_file():
            return img
    raise FileNotFoundError(f"没有可用的拼图图片（目录：{PUZZLE_IMAGES_DIR}）")


def make_grid_texture(
    img: PuzzleImage, grid_w: float, grid_h: float, unit_scale: float = 6.0
) -> tuple[QPixmap, float]:
    """把图片按 cover（xMidYMid slice）语义缩放为 grid 单位的纹理。

    返回 (pixmap, unit_scale)：pixmap 像素尺寸 = grid 单位 × unit_scale，
    供纹理 QBrush 以 1/unit_scale 缩放映射回场景坐标。
    """
    source = QImage(str(img.path))
    if source.isNull():
        raise OSError(f"无法解码图片：{img.path}")
    src_w = source.width()
    src_h = source.height()
    render_w = max(1, round(grid_w * unit_scale))
    render_h = max(1, round(grid_h * unit_scale))
    scale = max(render_w / src_w, render_h / src_h)
    scaled = source.scaled(
        round(src_w * scale),
        round(src_h * scale),
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation,
    )
    x = (scaled.width() - render_w) // 2
    y = (scaled.height() - render_h) // 2
    cropped = scaled.copy(QRect(QPoint(x, y), QPoint(x + render_w, y + render_h)))
    return QPixmap.fromImage(cropped), unit_scale


def texture_brush(
    pixmap: QPixmap,
    col: int,
    row: int,
    cell_w: float,
    cell_h: float,
    unit_scale: float,
) -> object:
    """构造每个碎片的纹理 QBrush：把原图对应区域映射到该碎片局部坐标。

    对应网页端 SVG pattern 的 userSpaceOnUse 填充语义。

    关键约定：碎片 path 已在 PieceItem 中平移到局部 (0,0)，因此
    局部坐标 (x, y) 应采样原图像素 ((x + col*cell) * unit_scale, ...)，
    即像素 v' = v / unit_scale - (col*cell, row*cell)。若平移方向取反，
    所有碎片都会采样原图左上角区域（负坐标被 clamp），导致拼合画面错乱。
    """
    from PySide6.QtGui import QBrush

    brush = QBrush(pixmap)
    transform = QTransform(
        1.0 / unit_scale,
        0.0,
        0.0,
        1.0 / unit_scale,
        -col * cell_w,
        -row * cell_h,
    )
    brush.setTransform(transform)
    return brush
