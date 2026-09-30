"""拼图最佳用时持久化（data/best_times.json）。

以图片文件名为键记录每张图的最快完成用时（秒，一位小数），
仅当用时更短时更新；文件损坏或缺失时回退为空记录。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .paths import DATA_DIR

BEST_TIMES_FILE = "best_times.json"


def best_times_path(path: Path | None = None) -> Path:
    """记录文件路径；测试可注入临时路径。"""
    return path if path is not None else DATA_DIR / BEST_TIMES_FILE


def load_best_times(path: Path | None = None) -> dict[str, float]:
    """读取全部最佳用时（文件名 → 秒）。"""
    p = best_times_path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in data.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[str(key)] = float(value)
    return out


def save_best_time(filename: str, seconds: float, path: Path | None = None) -> float:
    """写入单图最佳用时：仅当更短时更新；返回最终记录值。"""
    records = load_best_times(path)
    old = records.get(filename)
    if old is not None and old <= seconds:
        return old
    records[filename] = seconds
    p = best_times_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(tmp, p)  # 原子替换，避免写一半损坏
    return seconds


def format_time(seconds: float) -> str:
    """秒 → '分:秒.十分位'（如 1:32.5 / 0:08.4）。"""
    minutes = int(seconds // 60)
    secs = seconds - minutes * 60
    return f"{minutes}:{secs:04.1f}"
