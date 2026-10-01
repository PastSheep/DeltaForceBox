"""改枪码（主播推荐）：从 shushu.fan 抓取数据并本地缓存。

数据源：https://shushu.fan/guns 的分页 JSON API
- 页面为 Next.js App Router，首屏 HTML 只内嵌第 1 页 20 条方案（RSC payload）；
  翻页时浏览器实际请求 GET /api/guns-code/official?page=N&limit=L（实测
  无鉴权、可匿名访问、limit 上限 50）；
- 本模块按 totalCount 动态计算页数顺序拉取全量（limit=50 时 1268 条 ≈ 26
  次请求，10 天一次，页间带小间隔，尽量降低对对方服务器的压力）；
- 兼容边界：totalCount 缺失/变化时以「空页」为结束信号；最后一页不足
  limit 条直接取实际条数；页数变化后重新计算（不硬编码 64）；
- 仅保留「主播推荐」方案（带 authorDetail 的方案），官方裸方案过滤；
- 同步间隔由 resources/config/app_config.json 的 gun_sync_interval_days 控制（默认 10 天，不进设置
  界面）；缓存新鲜时启动/运行均不再请求网络。

缓存（data/guns_cache.json）：
- saved_at：本地抓取时间；solutions：全量方案列表；total_count：上游总数；
- 重复数据处理：以方案 id 为键去重后整体替换（幂等，重复拉取无副作用）；
- 图片（方案预览图 / 作者头像）在 data/gun_images/ 磁盘缓存，
  已存在的文件跳过下载。

注意：RSC payload 中的字符串必须用标准 JSON 字符串解码
（json.loads('"' + raw + '"')），不可用 unicode_escape——后者会把 \n 等
转义解成裸控制字符，破坏内嵌 JSON 对象。
"""

from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .paths import DATA_DIR

# 页面 URL 与缓存文件（data/ 目录，不入库）
GUNS_URL = "https://shushu.fan/guns"
GUNS_API_URL = "https://shushu.fan/api/guns-code/official"  # 分页 JSON API
GUNS_CACHE_FILE = "guns_cache.json"
GUN_IMAGES_DIR = DATA_DIR / "gun_images"

# 默认同步间隔（天）：resources/config/app_config.json 的 gun_sync_interval_days 可覆盖
DEFAULT_SYNC_INTERVAL_DAYS = 10

# API 分页：limit 上限实测为 50；页间间隔（毫秒），避免突发请求
OFFICIAL_LIMIT = 50
DEFAULT_PAGE_DELAY_MS = 300

# 网络请求默认超时（秒）
FETCH_TIMEOUT = 15
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DeltaForceBox/2.0"

# 主播平台：channel 值 -> 展示名
# 方案对象内的枪械信息键（armsDetail 可能内嵌枪名，缺失时用全局映射补）
_TAG_RE = re.compile(r"<[^>]+>")
_RSC_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,\s*"((?:[^"\\]|\\.)*)"\]\)')
_SOLUTION_CODE_RE = re.compile(r'"solutionCode"')
_OBJECT_RE = re.compile(r'"objectID"\s*:\s*(\d+)\s*,\s*"objectName"\s*:\s*"([^"]*)"')


@dataclass
class GunSolution:
    """一条主播推荐改枪方案（已提取展示所需字段）。"""

    id: int  # 方案 id（稳定主键，用于去重/合并）
    name: str = ""  # 方案名（如 "稳准狠M700"）
    gun_name: str = ""  # 枪械名（如 "M700狙击步枪"）
    weapon_type: str = ""  # 武器类型（如 "狙击步枪"）
    author: str = ""  # 主播昵称
    author_id: int = 0  # 作者 id（头像缓存键）
    channel: str = ""  # 平台（douyin / bilibili）
    author_avatar: str = ""  # 主播头像 URL
    comment: str = ""  # 主播评语（HTML 已剥离）
    tags: list[str] = field(default_factory=list)  # 标签名列表
    solution_code: str = ""  # 改枪码（游戏内导入用）
    price: int = 0  # 方案造价（游戏货币）
    preview_pic: str = ""  # 方案预览图 URL
    updated_at: str = ""  # 上游更新时间
    like_count: int = 0  # 点赞数


def _strip_html(text: str) -> str:
    """剥离 HTML 标签并压缩空白（authorComment 为 <p>...</p> 形式）。"""
    if not text:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub("", text)).strip()


def decode_rsc(html: str) -> str:
    """提取并拼接 Next.js RSC payload（self.__next_f.push），返回流文本。

    每个 push 段是标准 JSON 字符串字面量，用 json.loads 解码以保证
    转义（\\uXXXX / \\n / \\\\）被正确处理。
    """
    parts: list[str] = []
    for m in _RSC_PUSH_RE.finditer(html):
        try:
            parts.append(json.loads('"' + m.group(1) + '"'))
        except ValueError:
            continue
    return "".join(parts)


def _obj_start(text: str, pos: int) -> int:
    """从 pos 向前找未匹配的 '{'（对象起点），找不到返回 -1。"""
    depth = 0
    i = pos
    while i >= 0:
        c = text[i]
        if c == "}":
            depth += 1
        elif c == "{":
            if depth == 0:
                return i
            depth -= 1
        i -= 1
    return -1


def _take_json(text: str, start: int) -> str | None:
    """从 start 的 '{' 起做括号平衡，返回闭合对象文本；失败返回 None。"""
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    return None


def _parse_solution_obj(obj: dict, gun_map: dict[int, tuple[str, str]]) -> GunSolution | None:
    """从原始方案对象映射为展示字段；非主播方案（无作者）返回 None。"""
    detail = obj.get("authorDetail")
    if not isinstance(detail, dict) or not detail.get("nickname"):
        return None  # 仅保留主播推荐（带作者信息的方案）
    arms_id = obj.get("armsID") or obj.get("primaryArmsID") or 0
    gun_name, weapon_type = gun_map.get(int(arms_id), ("", "")) if arms_id else ("", "")
    tags = [
        str(t.get("tagName", "")).strip() for t in obj.get("tagDetail") or [] if t.get("tagName")
    ]
    try:
        price = int(obj.get("price") or obj.get("costPrice") or 0)
    except (TypeError, ValueError):
        price = 0
    try:
        like_count = int(obj.get("likeCount") or 0)
    except (TypeError, ValueError):
        like_count = 0
    return GunSolution(
        id=int(obj.get("id") or 0),
        name=str(obj.get("name", "") or ""),
        gun_name=gun_name or str(obj.get("armsDetail", {}).get("objectName", "") or ""),
        weapon_type=weapon_type or str(obj.get("armsDetail", {}).get("secondClassCN", "") or ""),
        author=str(detail.get("nickname", "") or ""),
        author_id=int(obj.get("authorID") or 0),
        channel=str(detail.get("channel", "") or ""),
        author_avatar=str(detail.get("avatar", "") or ""),
        comment=_strip_html(str(obj.get("authorComment", "") or "")),
        tags=[t for t in tags if t],
        solution_code=str(obj.get("solutionCode", "") or ""),
        price=price,
        preview_pic=str(obj.get("previewPic", "") or ""),
        updated_at=str(obj.get("updated_at", "") or ""),
        like_count=like_count,
    )


def parse_blob(blob: str) -> list[GunSolution]:
    """解析 RSC 流文本中的全部主播推荐方案（按 id 去重）。

    方案对象以 "solutionCode" 定位，向前回溯对象起点后括号平衡取整段，
    再 json.loads；解析失败的对象跳过（不影响其余方案）。
    """
    gun_map: dict[int, tuple[str, str]] = {}
    for m in _OBJECT_RE.finditer(blob):
        try:
            gun_map[int(m.group(1))] = (m.group(2), "")
        except ValueError:
            continue
    # 从枪械对象补武器类型：定位 objectID 后取整个对象
    for mid in _OBJECT_RE.finditer(blob):
        start = _obj_start(blob, mid.start())
        if start < 0:
            continue
        seg = _take_json(blob, start)
        if not seg:
            continue
        try:
            g = json.loads(seg)
        except ValueError:
            continue
        if g.get("objectID") and g.get("secondClassCN"):
            gun_map[int(g["objectID"])] = (
                str(g.get("objectName", "")), str(g.get("secondClassCN", ""))
            )

    solutions: dict[int, GunSolution] = {}
    for m in _SOLUTION_CODE_RE.finditer(blob):
        start = _obj_start(blob, m.start())
        if start < 0:
            continue
        seg = _take_json(blob, start)
        if not seg:
            continue
        try:
            obj = json.loads(seg)
        except ValueError:
            continue
        if not obj.get("solutionCode"):
            continue
        item = _parse_solution_obj(obj, gun_map)
        if item is not None and item.id not in solutions:
            solutions[item.id] = item
    return sorted(solutions.values(), key=lambda s: s.id)


def parse_gun_solutions(html: str) -> list[GunSolution]:
    """解析 shushu.fan/guns 页面 HTML -> 主播推荐方案列表。"""
    return parse_blob(decode_rsc(html))


def fetch_gun_solutions(
    timeout: int = FETCH_TIMEOUT,
    fetcher: object | None = None,
) -> list[GunSolution]:
    """抓取页面并解析；解析结果为空时抛异常（视为失败）。"""
    if fetcher is not None:
        html = fetcher(timeout)  # type: ignore[call-arg]
    else:
        req = urllib.request.Request(GUNS_URL, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    solutions = parse_gun_solutions(html)
    if not solutions:
        raise ValueError("shushu.fan 改枪码解析为空")
    return solutions


# ── 分页 JSON API（全量同步）──────────────────────────

def _default_fetcher(url: str, timeout: int = FETCH_TIMEOUT) -> str:
    """匿名直连分页 API（仅带 UA，实测无需鉴权/cookie）。"""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_official_page(
    fetcher: Callable[[str, int], str] | None = None,
    page: int = 1,
    limit: int = OFFICIAL_LIMIT,
    timeout: int = FETCH_TIMEOUT,
) -> dict:
    """请求单页分页 API，返回 data 部分（list/page/totalCount）。"""
    url = f"{GUNS_API_URL}?page={page}&limit={limit}"
    if fetcher is not None:
        text = fetcher(url, timeout)
    else:
        text = _default_fetcher(url, timeout)
    payload = json.loads(text)
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError(f"shushu.fan 改枪码 API 响应异常（page={page}）")
    return data


def _build_gun_map(raw: list[dict]) -> dict[int, tuple[str, str]]:
    """从方案内嵌的 armsDetail / armsID 构建 枪械id -> (枪名, 武器类型)。"""
    gun_map: dict[int, tuple[str, str]] = {}
    for obj in raw:
        arms = obj.get("armsDetail")
        name = ""
        weapon = ""
        if isinstance(arms, dict):
            name = str(arms.get("objectName", "") or "")
            weapon = str(arms.get("secondClassCN", "") or "")
            try:
                gun_map[int(arms["objectID"])] = (name, weapon)
            except (KeyError, TypeError, ValueError):
                pass
        for key in ("armsID", "primaryArmsID"):
            aid = obj.get(key)
            if aid and name:
                try:
                    gun_map[int(aid)] = (name, weapon)
                except (TypeError, ValueError):
                    pass
    return gun_map


def _merge_official(raw: list[dict]) -> list[GunSolution]:
    """合并多页原始对象：仅主播推荐（有作者）+ 按 id 去重 + 排序。"""
    gun_map = _build_gun_map(raw)
    seen: dict[int, GunSolution] = {}
    for obj in raw:
        item = _parse_solution_obj(obj, gun_map)
        if item is not None and item.id and item.id not in seen:
            seen[item.id] = item
    return sorted(seen.values(), key=lambda s: s.id)


def parse_official_list(payload: dict) -> list[GunSolution]:
    """解析单页 API 响应 data -> 主播推荐方案列表。"""
    return _merge_official(payload.get("list") or [])


def sync_official_solutions(
    fetcher: Callable[[str, int], str] | None = None,
    limit: int = OFFICIAL_LIMIT,
    page_delay_ms: int = DEFAULT_PAGE_DELAY_MS,
    timeout: int = FETCH_TIMEOUT,
    should_stop: Callable[[], bool] | None = None,
) -> list[GunSolution]:
    """顺序拉取全量分页并合并（动态页数，兼容末尾边界）。

    - 第 1 页响应含 totalCount -> 页数 = ceil(totalCount / limit)；
      若缺失/为 0，则以「空页」为结束信号继续拉取直到数据末尾；
    - 最后一页不足 limit 条时取实际条数（空列表即停止）；
    - totalCount 变化（如中途新方案入库）时仍按旧页数停止，
      多余数据由下一次同步补齐（幂等合并）。
    """
    raw: list[dict] = []
    page = 1
    total_pages: int | None = None
    stopped = False
    while True:
        if should_stop is not None and should_stop():
            stopped = True
            break
        data = fetch_official_page(fetcher=fetcher, page=page, limit=limit, timeout=timeout)
        if total_pages is None:
            total = data.get("totalCount")
            try:
                total_pages = max(1, math.ceil(int(total) / limit)) if total else None
            except (TypeError, ValueError):
                total_pages = None
        items = data.get("list") or []
        raw.extend(items)
        if not items:  # 空页：已到数据末尾
            break
        if total_pages is not None and page >= total_pages:
            break
        page += 1
        if page_delay_ms > 0:
            time.sleep(page_delay_ms / 1000)
    solutions = _merge_official(raw)
    if not solutions and not stopped:  # 中断时返回已收集数据（可能为空）
        raise ValueError("shushu.fan 改枪码 API 解析为空")
    return solutions


# ── 本地缓存 ─────────────────────────────────────────

def cache_path(path: Path | None = None) -> Path:
    """缓存文件路径；测试可注入临时路径。"""
    return path if path is not None else DATA_DIR / GUNS_CACHE_FILE


def load_guns_cache(path: Path | None = None) -> dict | None:
    """读取缓存；缺失或损坏时返回 None。"""
    p = cache_path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("solutions"):
        return None
    return data


def save_guns_cache(
    solutions: list[GunSolution],
    path: Path | None = None,
    total_count: int | None = None,
) -> None:
    """原子写入缓存（临时文件 + replace）；按 id 去重后整体替换（幂等）。"""
    p = cache_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    seen: dict[int, GunSolution] = {}
    for item in solutions:
        if item.id not in seen:  # 重复数据：同 id 只保留首条（幂等，后到者丢弃）
            seen[item.id] = item
    record = {
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "shushu.fan",
        "solutions": [asdict(s) for s in seen.values()],
        **({"total_count": total_count} if total_count is not None else {}),
    }
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def cache_is_fresh(
    path: Path | None = None,
    interval_days: int = DEFAULT_SYNC_INTERVAL_DAYS,
    now: datetime | None = None,
) -> bool:
    """缓存是否在同步间隔内（新鲜则不再请求网络）。"""
    data = load_guns_cache(path)
    if data is None or interval_days <= 0:
        return False
    try:
        saved = datetime.strptime(str(data.get("saved_at", "")), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False
    return (now or datetime.now()) - saved < timedelta(days=interval_days)


# ── 图片磁盘缓存 ─────────────────────────────────────

def image_dir(path: Path | None = None) -> Path:
    """图片缓存目录（data/gun_images/）。"""
    return path if path is not None else GUN_IMAGES_DIR


def preview_image_path(solution_id: int, path: Path | None = None) -> Path:
    """方案预览图本地路径。"""
    return image_dir(path) / f"solution_{solution_id}.png"


def avatar_image_path(author: str, path: Path | None = None) -> Path:
    """作者头像本地路径（按主播昵称缓存）。"""
    return image_dir(path) / f"avatar_{author}.png"


def ensure_image(
    url: str,
    dest: Path,
    timeout: int = FETCH_TIMEOUT,
    opener: object | None = None,
) -> bool:
    """下载图片到磁盘（已存在则跳过，幂等）；失败返回 False。"""
    if not url or dest.exists():
        return dest.exists()
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if opener is not None:
            data = opener(url, timeout)  # type: ignore[call-arg]
        else:
            req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
        tmp = dest.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, dest)
        return True
    except OSError:
        try:
            dest.with_suffix(".tmp").unlink(missing_ok=True)
        except OSError:
            pass
        return False
