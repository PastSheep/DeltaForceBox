"""把源 PNG 转换为多尺寸 Windows 应用图标（.ico）。

用法：
    python scripts/make_icon.py [源图路径] [输出路径]

默认源图为 .tmp/鼠鼠大王工具箱.png，输出为 resources/icons/app.ico。
源图将先居中裁成正方形，再生成 16/24/32/48/64/128/256 共 7 个尺寸。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = PROJECT_ROOT / ".tmp" / "鼠鼠大王工具箱.png"
DEFAULT_OUT = PROJECT_ROOT / "resources" / "icons" / "app.ico"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def make_icon(
    src: Path,
    out: Path,
    sizes: tuple[int, ...] = ICON_SIZES,
) -> Path:
    """转换：居中裁方 → 多尺寸缩放 → 写入 ICO。"""
    im = Image.open(src).convert("RGBA")
    width, height = im.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    im = im.crop((left, top, left + side, top + side))
    # 先放大到 256×256：Pillow 以主图尺寸作为 ICO 最大条目，否则 256 项不会写入
    im = im.resize((256, 256), Image.Resampling.LANCZOS)

    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, format="ICO", sizes=[(s, s) for s in sizes])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="PNG → 多尺寸 ICO 转换")
    parser.add_argument("src", nargs="?", type=Path, default=DEFAULT_SRC)
    parser.add_argument("out", nargs="?", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if not args.src.exists():
        print(f"源图不存在：{args.src}")
        return 1

    out = make_icon(args.src, args.out)
    print(f"已生成：{out}")
    print(f"包含尺寸：{ICON_SIZES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
