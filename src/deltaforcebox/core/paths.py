"""路径工具：定位项目根目录与各类资源目录。"""

from pathlib import Path

# src/deltaforcebox/core/paths.py -> 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[3]

RESOURCES_DIR = PROJECT_ROOT / "resources"
I18N_DIR = RESOURCES_DIR / "i18n"
THEMES_DIR = RESOURCES_DIR / "themes"
