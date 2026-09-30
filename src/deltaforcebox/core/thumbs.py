"""拼图图片缩略图：快速生成 + 磁盘缓存。

- 生成：QImageReader 缩放解码（不解码全尺寸）+ 中心裁剪为正方形；
  不使用 setScaledClipRect（实测在部分 PNG 上产出全黑图）。
- 缓存：写入 data/thumbnails/（已被 .gitignore 忽略），源文件更新后
  自动重生成；后续打开来源窗口直接读盘，无需重新解码。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QImageReader, QPixmap

from .paths import DATA_DIR

THUMB_DIR = DATA_DIR / "thumbnails"


def make_thumbnail(path: Path, size: int) -> QPixmap | None:
    """生成 size×size 正方形缩略图（居中裁剪，保持宽高比）。"""
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    src = reader.size()
    if src.isEmpty() or src.width() <= 0 or src.height() <= 0:
        return None
    factor = max(size / src.width(), size / src.height())
    reader.setScaledSize(
        QSize(round(src.width() * factor), round(src.height() * factor))
    )
    img = reader.read()
    if img.isNull():
        return None
    x = max(0, (img.width() - size) // 2)
    y = max(0, (img.height() - size) // 2)
    return QPixmap.fromImage(img.copy(x, y, size, size))


def _cache_path(path: Path, size: int) -> Path:
    return THUMB_DIR / f"{path.stem}_{size}.png"


def cached_thumbnail(path: Path, size: int) -> QPixmap | None:
    """取缩略图：缓存命中直接读盘，否则生成并写缓存。"""
    dest = _cache_path(path, size)
    try:
        if dest.exists() and dest.stat().st_mtime >= path.stat().st_mtime:
            pm = QPixmap(str(dest))
            if not pm.isNull():
                return pm
    except OSError:
        pass
    pm = make_thumbnail(path, size)
    if pm is not None:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            pm.save(str(dest), "PNG")
        except OSError:
            pass
    return pm
