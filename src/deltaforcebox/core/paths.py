"""路径工具：定位项目根目录与各类资源目录。

开发模式（源码运行）下按源码布局推导项目根目录；
冻结模式（PyInstaller 打包）下，resources/、docs/、data/ 均位于
可执行文件同级目录（与 exe 平级）：
- resources/（i18n、themes、icons、拼图图片）
- docs/（版本日志）
- data/（settings.json、best_times.json、thumbnails/，首启自动创建）
Python 运行时（.pyd/.dll）在 PyInstaller 内容目录 _internal/，与路径无关。
"""

from __future__ import annotations

import sys
from pathlib import Path

_FROZEN = getattr(sys, "frozen", False)

if _FROZEN:
    # 外部目录均以 exe 所在目录为基准（与 exe 平级）
    _EXE_DIR = Path(sys.executable).resolve().parent
    PROJECT_ROOT = _EXE_DIR
    RESOURCES_DIR = _EXE_DIR / "resources"
    I18N_DIR = RESOURCES_DIR / "i18n"
    THEMES_DIR = RESOURCES_DIR / "themes"
    DATA_DIR = _EXE_DIR / "data"
else:
    # src/deltaforcebox/core/paths.py -> 项目根目录
    PROJECT_ROOT = Path(__file__).resolve().parents[3]
    RESOURCES_DIR = PROJECT_ROOT / "resources"
    I18N_DIR = RESOURCES_DIR / "i18n"
    THEMES_DIR = RESOURCES_DIR / "themes"
    DATA_DIR = PROJECT_ROOT / "data"
