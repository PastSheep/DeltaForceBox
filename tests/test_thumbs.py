"""缩略图生成与缓存测试（含黑图回归检查）。"""

from __future__ import annotations

from PySide6.QtGui import QImage

from deltaforcebox.core import thumbs
from deltaforcebox.core.thumbs import cached_thumbnail, make_thumbnail
from deltaforcebox.games.puzzle.image_source import load_manifest


def _avg_brightness(pm) -> float:
    img = pm.toImage().convertToFormat(QImage.Format.Format_RGB32)
    total = 0
    n = 0
    for x in range(0, img.width(), 2):
        for y in range(0, img.height(), 2):
            c = img.pixelColor(x, y)
            total += (c.red() + c.green() + c.blue()) / 3
            n += 1
    return total / n if n else 0


def test_thumbnail_square_and_not_black(qapp):
    """回归：曾因 setScaledClipRect 产出全黑图，现全部应为正常亮度。"""
    for image in load_manifest():
        pm = make_thumbnail(image.path, 72)
        assert pm is not None, image.path.name
        assert pm.width() == pm.height() == 72
        assert _avg_brightness(pm) > 8, f"黑图: {image.path.name}"


def test_thumbnail_cache_roundtrip(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(thumbs, "THUMB_DIR", tmp_path)
    image = load_manifest()[0]

    pm1 = cached_thumbnail(image.path, 72)
    assert pm1 is not None
    cache_file = tmp_path / f"{image.path.stem}_72.png"
    assert cache_file.exists(), "首次调用应生成缓存文件"

    pm2 = cached_thumbnail(image.path, 72)
    assert pm2 is not None
    assert pm1.toImage() == pm2.toImage(), "缓存命中结果应与生成结果一致"
