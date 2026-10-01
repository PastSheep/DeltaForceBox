"""预处理每日密码地图缩略图：统一尺寸、黑边填充、保持原图比例。

源：.tmp/新建文件夹/*.png（以地图名命名）
输出：resources/images/daily_password/*.jpg（640×360，JPEG 质量 85）

用法：python scripts/prepare_map_thumbs.py
重新执行会覆盖旧输出，可安全重复运行。
"""

from __future__ import annotations

import pathlib

from PIL import Image

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / ".tmp" / "新建文件夹"
DST_DIR = PROJECT_ROOT / "resources" / "images" / "daily_password"

TARGET_W, TARGET_H = 640, 360  # 16:9
JPEG_QUALITY = 85


def prepare(src: pathlib.Path, dst: pathlib.Path) -> tuple[int, int]:
    """等比缩放至目标框内并黑边填充，返回最终画布尺寸。"""
    img = Image.open(src).convert("RGB")
    scale = min(TARGET_W / img.width, TARGET_H / img.height)
    new_w = max(1, round(img.width * scale))
    new_h = max(1, round(img.height * scale))
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (TARGET_W, TARGET_H), (0, 0, 0))
    canvas.paste(img, ((TARGET_W - new_w) // 2, (TARGET_H - new_h) // 2))
    canvas.save(dst, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return img.size, canvas.size


def main() -> None:
    if not SRC_DIR.is_dir():
        raise SystemExit(f"源目录不存在: {SRC_DIR}")
    DST_DIR.mkdir(parents=True, exist_ok=True)
    for src in sorted(SRC_DIR.glob("*.png")):
        dst = DST_DIR / (src.stem + ".jpg")
        inner, canvas = prepare(src, dst)
        size_kb = dst.stat().st_size // 1024
        print(
            f"{src.name:16s} {inner[0]}x{inner[1]} -> {dst.name} "
            f"{canvas[0]}x{canvas[1]} ({size_kb} KB)"
        )


if __name__ == "__main__":
    main()
