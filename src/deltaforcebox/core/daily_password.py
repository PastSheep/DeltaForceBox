"""每日密码：多数据源拉取、优先级回退与本地缓存。

数据源：
- tmini（https://tmini.net/api/sjzmm?type=json）：免费、无鉴权、结构化 JSON，
  含六图密码、位置描述与示意图，每日更新；限频 10 次/分钟。
- shushu_fan（https://shushu.fan/）：Next.js SSR 直出 HTML，无需 JS 即可抓取；
  数据未经官方交叉验证（历史出现与官方不一致），仅作备用降级源。

缓存策略（data/daily_password_cache.json）：
- 缓存携带 update_date 与抓取时间；当日缓存视为新鲜，启动/跨日检查时直接使用，
  避免频繁请求（尊重上游限频）；跨日或缺失时才发起网络刷新；
- 网络全部失败时回退到缓存展示（即使过期，仍标注原日期与来源）。
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .paths import DATA_DIR

# 缓存文件（位于 data/，不入库）
PASSWORD_CACHE_FILE = "daily_password_cache.json"

# 各数据源优先级默认顺序（可被配置覆盖；顺序靠前者优先尝试）
DEFAULT_SOURCE_ORDER = ("tmini", "shushu_fan")

# 网络请求默认超时（秒）
FETCH_TIMEOUT = 10
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DeltaForceBox/1.1"

# shushu_fan 六张地图名（固定顺序，与页面卡片一致）
SHUSHU_MAPS = ("零号大坝", "长弓溪谷", "巴克什", "航天基地", "潮汐监狱", "AZ3")


@dataclass
class DailyPasswordData:
    """一次成功拉取的每日密码数据。"""

    source: str  # 数据源标识（tmini / shushu_fan）
    update_date: str  # 上游标注的更新日期提示（如 "10月01日每日密码已更新"）
    updated_at: str = ""  # 上游更新时间（字符串，尽量保留原格式）
    passwords: dict[str, str] = field(default_factory=dict)  # 地图名 -> 4 位密码
    locations: dict[str, str] = field(default_factory=dict)  # 地图名 -> 位置描述（可选）


# ── 数据源实现 ─────────────────────────────────────────

def _http_get(url: str, timeout: int) -> str:
    """带 UA 的 GET 请求，返回 UTF-8 文本；失败抛异常。"""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_tmini(timeout: int = FETCH_TIMEOUT) -> DailyPasswordData:
    """从 tmini 接口拉取：https://tmini.net/api/sjzmm?type=json"""
    url = "https://tmini.net/api/sjzmm?type=json"
    payload = json.loads(_http_get(url, timeout))
    data = payload.get("data") or {}
    passwords: dict[str, str] = {}
    locations: dict[str, str] = {}
    for item in data.get("passwords", []):
        name = item.get("map_name")
        code = item.get("password")
        if name and code:
            passwords[str(name)] = str(code)
            loc = (item.get("location_info") or {}).get("description")
            if loc:
                locations[str(name)] = str(loc)
    if not passwords:
        raise ValueError("tmini 返回数据为空")
    updated_at = str(data.get("last_updated", "")).strip()
    if not updated_at:
        # 后备：last_updated 缺失时用 timestamp（Unix 秒）转换
        ts = data.get("timestamp")
        if isinstance(ts, (int, float)):
            updated_at = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    return DailyPasswordData(
        source="tmini",
        update_date=str(data.get("update_date", "")),
        updated_at=updated_at,
        passwords=passwords,
        locations=locations,
    )


def fetch_shushu_fan(timeout: int = FETCH_TIMEOUT) -> DailyPasswordData:
    """从 shushu.fan 首页抓取（SSR 直出 HTML）。

    解析：地图名 span 之后的 4 位数字 span。该站数据未经官方交叉验证，
    仅作备用降级源；update_date 取本地当天（站内无日期标注）。
    """
    html = _http_get("https://shushu.fan/", timeout)
    passwords: dict[str, str] = {}
    for name in SHUSHU_MAPS:
        # 地图名 span 与数字 span 之间可能隔多个样式 span（text-shadow 分段）
        pat = re.compile(
            rf"{re.escape(name)}</span>.*?([0-9]{{4}})</span>",
            re.DOTALL,
        )
        m = pat.search(html)
        if m:
            passwords[name] = m.group(1)
    if len(passwords) < 6:
        raise ValueError(f"shushu_fan 解析不完整（{len(passwords)}/6）")
    today = datetime.now().strftime("%m月%d日")
    return DailyPasswordData(
        source="shushu_fan",
        update_date=f"{today}每日密码已更新",
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        passwords=passwords,
    )


# 数据源注册表：标识 -> 拉取函数
PASSWORD_FETCHERS: dict[str, object] = {
    "tmini": fetch_tmini,
    "shushu_fan": fetch_shushu_fan,
}


def fetch_password(
    order: tuple[str, ...] = DEFAULT_SOURCE_ORDER,
    timeout: int = FETCH_TIMEOUT,
    fetchers: dict[str, object] | None = None,
) -> DailyPasswordData | None:
    """按优先级顺序尝试各数据源，返回首个成功结果；全部失败返回 None。

    fetchers 参数供测试注入 mock，替换真实网络调用。
    """
    table = fetchers if fetchers is not None else PASSWORD_FETCHERS
    for name in order:
        fetcher = table.get(name)
        if fetcher is None:
            continue
        try:
            data = fetcher(timeout)
            if data is not None and data.passwords:
                return data
        except Exception:
            continue  # 当前源失败，尝试下一个
    return None


# ── 本地缓存 ─────────────────────────────────────────

def cache_path(path: Path | None = None) -> Path:
    """缓存文件路径；测试可注入临时路径。"""
    return path if path is not None else DATA_DIR / PASSWORD_CACHE_FILE


def load_cache(path: Path | None = None) -> dict | None:
    """读取缓存；缺失或损坏时返回 None。"""
    p = cache_path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("passwords"):
        return None
    return data


def save_cache(data: DailyPasswordData, path: Path | None = None) -> None:
    """原子写入缓存：含抓取时间与来源，供离线/限频时使用。"""
    p = cache_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    record = asdict(data)
    record["saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def parse_update_date(update_date: str) -> tuple[int, int] | None:
    """从更新日期提示解析 (月, 日)；无法解析返回 None。

    兼容 "10月01日每日密码已更新" / "10月1日" 等格式。
    """
    m = re.search(r"(\d{1,2})月(\d{1,2})日", update_date or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def cache_is_today(update_date: str, now: datetime | None = None) -> bool:
    """缓存标注的更新日期是否就是今天（跨日判定）。"""
    parsed = parse_update_date(update_date)
    if parsed is None:
        return False  # 无法判定视为过期，触发刷新
    today = now or datetime.now()
    return parsed == (today.month, today.day)


def normalize_source_order(order: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    """清洗来源顺序配置：只保留已知数据源、去重、保底默认顺序。

    用于 settings.json 中用户手改的顺序（非法值/未知源被过滤）。
    """
    known = list(PASSWORD_FETCHERS)
    cleaned: list[str] = []
    for name in order or []:
        if name in known and name not in cleaned:
            cleaned.append(name)
    for name in DEFAULT_SOURCE_ORDER:
        if name not in cleaned:
            cleaned.append(name)
    return tuple(cleaned)
