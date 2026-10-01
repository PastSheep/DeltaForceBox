"""设置持久化：读写 data/settings.json。

- 缺失或损坏（JSON 解析失败）时回退默认值，不中断启动；
- 写入采用「临时文件 + 原子替换」，避免写一半损坏；
- 文件位于 data/（已被 .gitignore 忽略，不进入版本库）。
"""

from __future__ import annotations

import json
from pathlib import Path

from .paths import DATA_DIR

SETTINGS_PATH = DATA_DIR / "settings.json"

# 默认设置，与 core/theme.py、core/i18n.py 的 DEFAULT_* 保持一致
DEFAULT_SETTINGS: dict[str, str | int | list[str]] = {
    "theme": "dark",
    "language": "zh",
    # 拼图目标碎片数（仅配置文件修改，不在设置界面显示）：
    # 控制开局碎片多少，取值 [4, 200]，默认 48
    "puzzle_pieces": 48,
    # 每日密码来源优先级（顺序即优先级，靠前者优先尝试）：
    # 可在设置界面更改首选来源，也可在配置文件中手改完整顺序
    "password_source_order": ["tmini", "shushu_fan"],
}


def load_settings(path: Path | None = None) -> dict[str, str | int | list[str]]:
    """读取设置；缺失或损坏时返回默认值。"""
    settings_path = path or SETTINGS_PATH
    values = dict(DEFAULT_SETTINGS)
    try:
        with settings_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            values.update({k: data[k] for k in DEFAULT_SETTINGS if k in data})
    except (OSError, ValueError):
        pass
    return values


def save_settings(
    values: dict[str, str | int | list[str]], path: Path | None = None
) -> None:
    """原子写入设置文件（先写临时文件再替换）。"""
    settings_path = path or SETTINGS_PATH
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = settings_path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(values, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(settings_path)
