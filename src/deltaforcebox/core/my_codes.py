"""我的改枪码持久化：读写 data/my_gun_codes.json。

- 每条记录：id / name / code / description / created_at / updated_at；
- 缺失或损坏（JSON 解析失败）时回退空列表，不中断启动；
- 写入采用「临时文件 + 原子替换」；
- data/ 已被 .gitignore 忽略（用户数据，不进入版本库）。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from .paths import DATA_DIR

MY_CODES_FILE = DATA_DIR / "my_gun_codes.json"


def load_my_codes(path: Path | None = None) -> list[dict]:
    """读取我的改枪码列表；缺失或损坏时返回空列表。"""
    p = path or MY_CODES_FILE
    try:
        with p.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            codes = data.get("codes")
            if isinstance(codes, list):
                return [c for c in codes if isinstance(c, dict)]
    except (OSError, ValueError):
        pass
    return []


def save_my_codes(codes: list[dict], path: Path | None = None) -> None:
    """原子写入我的改枪码列表（先写临时文件再替换）。"""
    p = path or MY_CODES_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"codes": codes}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(p)


def new_code_id() -> str:
    """生成记录唯一 id。"""
    return uuid.uuid4().hex[:12]


def parse_gun_code(code: str) -> tuple[str, str, str]:
    """解析改枪码为 (枪械名, 地图, 识别码)。

    格式：`枪械名-地图-识别码`。宽容解析：
    - 1 段：整串视为枪械名；
    - 2 段：第二段视为识别码（兼容旧格式 `枪械名-纯数字码`）；
    - 3 段及以上：第二段为地图，其后各段合并为识别码
      （新版识别码为 gzip base64，可能较长，但自身不含 `-`）。
    """
    parts = [p.strip() for p in (code or "").strip().split("-") if p.strip()]
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", ""
    if len(parts) == 2:
        return parts[0], "", parts[1]
    return parts[0], parts[1], "-".join(parts[2:])


def load_candidates(
    guns_cache_path: Path | None = None,
) -> tuple[list[str], list[str]]:
    """从改枪码缓存提取（武器类型, 枪械名称）候选，与主播推荐筛选一致。

    缓存缺失/损坏/无方案时返回空列表（页面只剩「全部」选项）。
    """
    from .gun_solutions import load_guns_cache

    data = load_guns_cache(guns_cache_path)
    if not data:
        return [], []
    weapons: set[str] = set()
    guns: set[str] = set()
    for item in data.get("solutions") or []:
        if not isinstance(item, dict):
            continue
        weapon = str(item.get("weapon_type") or "").strip()
        gun = str(item.get("gun_name") or "").strip()
        if weapon:
            weapons.add(weapon)
        if gun:
            guns.add(gun)
    return sorted(weapons), sorted(guns)
