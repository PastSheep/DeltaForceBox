"""设置持久化：读写 data/settings.json 与 resources/config/app_config.json。

- data/settings.json：设置界面显现给用户的设置（主题 / 语言 / 密码来源顺序）；
- resources/config/app_config.json：不进入设置界面的隐藏配置（拼图碎片数、
  改枪码同步间隔、图片内存缓存上限、每页卡片数），随程序资源分发，可手改；
- 两者缺失或损坏（JSON 解析失败）时均回退默认值，不中断启动；
- 写入采用「临时文件 + 原子替换」，避免写一半损坏；
- data/ 已被 .gitignore 忽略（用户数据）；resources/config/ 随版本库分发。
"""

from __future__ import annotations

import json
from pathlib import Path

from .paths import DATA_DIR, RESOURCES_DIR

SETTINGS_PATH = DATA_DIR / "settings.json"
APP_CONFIG_PATH = RESOURCES_DIR / "config" / "app_config.json"

# 设置界面可见的默认设置，与 core/theme.py、core/i18n.py 的 DEFAULT_* 保持一致
DEFAULT_SETTINGS: dict[str, str | int | list[str]] = {
    "theme": "dark",
    "language": "zh",
    # 每日密码来源优先级（顺序即优先级，靠前者优先尝试）：
    # 可在设置界面更改首选来源，也可在配置文件中手改完整顺序
    "password_source_order": ["tmini", "shushu_fan"],
}

# 隐藏配置默认值（仅修改 resources/config/app_config.json，不在设置界面显示）
DEFAULT_APP_CONFIG: dict[str, int] = {
    # 拼图目标碎片数：控制开局碎片多少，取值 [4, 200]，默认 48
    "puzzle_pieces": 48,
    # 改枪码同步间隔（天）：控制从 shushu.fan 拉取主播推荐方案的频率，默认 10 天
    "gun_sync_interval_days": 10,
    # 改枪码图片内存缓存上限（MB）：QPixmapCache 全局 LRU 容量，默认 64 MB；设 0 可禁用
    "image_cache_limit_mb": 64,
    # 改枪码每页卡片数：越小每页渲染/首屏越快、图片下载越分散，默认 20
    "gun_render_page_size": 20,
}


def load_settings(path: Path | None = None) -> dict[str, str | int | list[str]]:
    """读取界面设置；缺失或损坏时返回默认值（只取界面可见 key）。"""
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
    """原子写入界面设置文件（先写临时文件再替换）。

    只写 DEFAULT_SETTINGS 内的 key：隐藏配置字段不落盘到 data/settings.json。
    """
    settings_path = path or SETTINGS_PATH
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = settings_path.with_suffix(".tmp")
    payload = {k: values[k] for k in DEFAULT_SETTINGS if k in values}
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(settings_path)


def load_app_config(path: Path | None = None) -> dict[str, int]:
    """读取隐藏配置（resources/config/app_config.json）。

    - 文件缺失时自动写入默认文件（便于用户发现并手改）；
    - 损坏（JSON 解析失败）时回退默认值，不中断启动；
    - 只取 DEFAULT_APP_CONFIG 内的 key，未知字段忽略。
    """
    config_path = path or APP_CONFIG_PATH
    values = dict(DEFAULT_APP_CONFIG)
    try:
        with config_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            values.update({k: data[k] for k in DEFAULT_APP_CONFIG if k in data})
    except FileNotFoundError:
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                json.dumps(DEFAULT_APP_CONFIG, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
    except (OSError, ValueError):
        pass
    return values
