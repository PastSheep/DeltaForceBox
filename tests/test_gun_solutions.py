"""改枪码（主播推荐）模块测试：解析 / 缓存 / 幂等 / 新鲜度 / 图片缓存。

fixture tests/data/guns_sample.html 为从真实 shushu.fan/guns 页面提取的
RSC 数据（3 条主播推荐方案 + M700 枪械对象，标准 JSON 转义）。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from deltaforcebox.core.gun_solutions import (
    DEFAULT_SYNC_INTERVAL_DAYS,
    GunSolution,
    avatar_image_path,
    cache_is_fresh,
    decode_rsc,
    ensure_image,
    fetch_gun_solutions,
    load_guns_cache,
    parse_blob,
    parse_gun_solutions,
    parse_official_list,
    preview_image_path,
    save_guns_cache,
    sync_official_solutions,
)

FIXTURE = Path(__file__).parent / "data" / "guns_sample.html"


def _fixture_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def _fixture_solutions() -> list[GunSolution]:
    return parse_gun_solutions(_fixture_html())


# ── RSC 解码与解析 ──────────────────────────────────

def test_decode_rsc_handles_escapes() -> None:
    # push 内容为 JSON 字符串字面量：转义引号/unicode 需被正确还原
    html = '<script>self.__next_f.push([1,"{\\"a\\":\\"\\u6d4b\\u8bd5\\",\\"n\\":1}"]);</script>'
    blob = decode_rsc(html)
    assert '"a":"测试","n":1' in blob


def test_parse_real_fixture() -> None:
    solutions = _fixture_solutions()
    assert len(solutions) == 3
    ids = {s.id for s in solutions}
    assert ids == {12825, 12826, 12827}


def test_parse_field_mapping() -> None:
    by_id = {s.id: s for s in _fixture_solutions()}
    s = by_id[12825]
    assert s.name == "稳准狠M700"
    assert s.gun_name == "M700狙击步枪"
    assert s.weapon_type == "狙击步枪"
    assert s.author == "eStar丨Aqing"
    assert s.channel == "douyin"
    assert s.solution_code == "M700狙击步枪-烽火地带-6L8CPOS04C9NGO2DGDCB8"
    assert s.tags == ["远程作战", "满改神器", "赛事同款"]
    assert s.price == 459256
    assert s.preview_pic.startswith("https://playerhub.df.qq.com/")
    assert s.author_avatar.startswith("https://playerhub.df.qq.com/")


def test_parse_filters_authorless() -> None:
    # 无 authorDetail 的方案（官方裸方案）应被过滤：仅保留主播推荐
    blob = (
        '[{"id":1,"name":"官方方案","solutionCode":"X-烽火地带-AAA"},'
        '{"id":2,"name":"主播方案","solutionCode":"Y-烽火地带-BBB",'
        '"authorDetail":{"nickname":"主播","channel":"bilibili","id":9,"avatar":""}}]'
    )
    solutions = parse_blob(blob)
    assert len(solutions) == 1
    assert solutions[0].id == 2
    assert solutions[0].author == "主播"


def test_parse_dedup_by_id() -> None:
    blob = (
        '[{"id":5,"name":"A","solutionCode":"X-1","authorDetail":{"nickname":"a","channel":"douyin"}},'
        '{"id":5,"name":"B","solutionCode":"X-2","authorDetail":{"nickname":"b","channel":"bilibili"}}]'
    )
    solutions = parse_blob(blob)
    assert len(solutions) == 1
    assert solutions[0].name == "A"  # 后到者不覆盖（同 id 只保留首条）


def test_parse_comment_strips_html() -> None:
    blob = (
        '[{"id":7,"name":"C","solutionCode":"X-3",'
        '"authorComment":"<p>极致开镜速度，稳准狠</p>",'
        '"authorDetail":{"nickname":"c","channel":"douyin"}}]'
    )
    solutions = parse_blob(blob)
    assert solutions[0].comment == "极致开镜速度，稳准狠"


# ── 网络拉取 ────────────────────────────────────────

def test_fetch_uses_fetcher(tmp_path: Path) -> None:
    def fake_fetcher(_timeout: int) -> str:
        return _fixture_html()

    solutions = fetch_gun_solutions(fetcher=fake_fetcher)
    assert len(solutions) == 3


def test_fetch_raises_on_empty(tmp_path: Path) -> None:
    def fake_fetcher(_timeout: int) -> str:
        return "<html><body>no data</body></html>"

    with pytest.raises(ValueError):
        fetch_gun_solutions(fetcher=fake_fetcher)


# ── 本地缓存 ────────────────────────────────────────

def test_cache_roundtrip(tmp_path: Path) -> None:
    cache = tmp_path / "guns_cache.json"
    solutions = _fixture_solutions()
    save_guns_cache(solutions, cache)
    data = load_guns_cache(cache)
    assert data is not None
    assert data["source"] == "shushu.fan"
    assert len(data["solutions"]) == 3
    assert data["solutions"][0]["solution_code"].startswith("M700")


def test_cache_dedup_on_save(tmp_path: Path) -> None:
    cache = tmp_path / "guns_cache.json"
    # 同一 id 重复出现：保存时只保留一条（幂等）
    dup = [
        GunSolution(id=1, name="A", author="a"),
        GunSolution(id=1, name="A2", author="a2"),
        GunSolution(id=2, name="B", author="b"),
    ]
    save_guns_cache(dup, cache)
    data = load_guns_cache(cache)
    assert data is not None
    assert len(data["solutions"]) == 2
    names = {s["name"] for s in data["solutions"]}
    assert names == {"A", "B"}


def test_cache_corrupt_returns_none(tmp_path: Path) -> None:
    cache = tmp_path / "guns_cache.json"
    cache.write_text("{not valid json", encoding="utf-8")
    assert load_guns_cache(cache) is None


def test_cache_atomic_write(tmp_path: Path) -> None:
    cache = tmp_path / "guns_cache.json"
    save_guns_cache(_fixture_solutions(), cache)
    assert not cache.with_suffix(".tmp").exists()  # 临时文件已清理


# ── 新鲜度判定 ──────────────────────────────────────

def test_cache_is_fresh_within_interval(tmp_path: Path) -> None:
    cache = tmp_path / "guns_cache.json"
    save_guns_cache(_fixture_solutions(), cache)
    now = datetime.now()
    assert cache_is_fresh(cache, DEFAULT_SYNC_INTERVAL_DAYS, now=now)
    old = now - timedelta(days=DEFAULT_SYNC_INTERVAL_DAYS + 1)
    # 把缓存时间改成 N 天前
    data = load_guns_cache(cache)
    assert data is not None
    data["saved_at"] = old.strftime("%Y-%m-%d %H:%M:%S")
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert not cache_is_fresh(cache, DEFAULT_SYNC_INTERVAL_DAYS, now=now)


def test_cache_is_fresh_missing(tmp_path: Path) -> None:
    assert not cache_is_fresh(tmp_path / "none.json", DEFAULT_SYNC_INTERVAL_DAYS)


def test_cache_is_fresh_corrupt_saved_at(tmp_path: Path) -> None:
    cache = tmp_path / "guns_cache.json"
    cache.write_text(
        json.dumps({"saved_at": "not-a-date", "solutions": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    assert not cache_is_fresh(cache, DEFAULT_SYNC_INTERVAL_DAYS)


# ── 图片磁盘缓存 ────────────────────────────────────

def test_ensure_image_skips_existing(tmp_path: Path) -> None:
    dest = tmp_path / "x.png"
    dest.write_bytes(b"old")
    calls: list[str] = []

    def fake_opener(url: str, _timeout: int) -> bytes:
        calls.append(url)
        return b"new"

    assert ensure_image("http://example/x.png", dest, opener=fake_opener)
    assert calls == []  # 已存在：不发起下载（幂等）
    assert dest.read_bytes() == b"old"


def test_ensure_image_downloads(tmp_path: Path) -> None:
    dest = tmp_path / "x.png"

    def fake_opener(url: str, _timeout: int) -> bytes:
        return b"data"

    assert ensure_image("http://example/x.png", dest, opener=fake_opener)
    assert dest.read_bytes() == b"data"
    assert not dest.with_suffix(".tmp").exists()


def test_ensure_image_failure_cleans_tmp(tmp_path: Path) -> None:
    dest = tmp_path / "x.png"

    def fake_opener(url: str, _timeout: int) -> bytes:
        raise OSError("network down")

    assert not ensure_image("http://example/x.png", dest, opener=fake_opener)
    assert not dest.exists()
    assert not dest.with_suffix(".tmp").exists()


def test_image_paths_under_dir(tmp_path: Path) -> None:
    assert preview_image_path(12825, tmp_path) == tmp_path / "solution_12825.png"
    assert avatar_image_path("主播", tmp_path) == tmp_path / "avatar_主播.png"


# ── 分页 JSON API（全量同步）─────────────────────────

def _api_item(
    sid: int,
    name: str,
    author: str | None = None,
    gun: str = "",
    wtype: str = "",
) -> dict:
    """构造与真实 API 字段一致的方案对象。"""
    obj = {
        "id": sid,
        "name": name,
        "solutionCode": f"{name}-烽火地带-CODE{sid}",
        "price": 123456,
        "previewPic": f"https://playerhub.df.qq.com/playerhub/p{sid}.png",
        "updated_at": "2026-09-11 15:33:35",
        "likeCount": 5,
        "armsID": 1000 + sid,
        "armsDetail": {
            "objectID": 1000 + sid,
            "objectName": gun or "",
            "secondClassCN": wtype or "",
        },
        "authorComment": "<p>评语</p>",
        "tagDetail": [{"tagID": 1, "tagName": "满改神器"}],
    }
    if author is not None:
        obj["authorDetail"] = {
            "nickname": author,
            "channel": "douyin",
            "id": sid,
            "avatar": f"https://playerhub.df.qq.com/playerhub/a{sid}.png",
        }
        obj["authorID"] = sid
    return obj


class _FakeApi:
    """按 page 分发预置页数据的模拟分页 API。"""

    def __init__(self, pages: list[list[dict]], total: int | None = None) -> None:
        self.pages = pages
        self.total = total
        self.calls: list[int] = []  # 请求过的 page 号
        self.sleep_seconds: list[float] = []

    def __call__(self, url: str, _timeout: int) -> str:
        import urllib.parse

        qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        page = int(qs.get("page", ["1"])[0])
        limit = int(qs.get("limit", ["50"])[0])
        self.calls.append(page)
        items = self.pages[page - 1] if page - 1 < len(self.pages) else []
        data = {"list": items[:limit], "page": page, "totalCount": self.total, "likedIds": []}
        return json.dumps({"success": True, "data": data})


def test_parse_official_list_fields() -> None:
    payload = {
        "list": [
            _api_item(1, "稳准狠M700", author="eStar丨Aqing",
                     gun="M700狙击步枪", wtype="狙击步枪")
        ],
        "page": 1,
        "totalCount": 1,
    }
    sols = parse_official_list(payload)
    assert len(sols) == 1
    s = sols[0]
    assert s.name == "稳准狠M700"
    assert s.gun_name == "M700狙击步枪"
    assert s.weapon_type == "狙击步枪"
    assert s.author == "eStar丨Aqing"
    assert s.channel == "douyin"
    assert s.solution_code == "稳准狠M700-烽火地带-CODE1"
    assert s.tags == ["满改神器"]
    assert s.price == 123456
    assert s.comment == "评语"


def test_sync_official_full_pages(monkeypatch) -> None:
    """totalCount 驱动页数：3 条 / limit=2 -> 2 页，合并去重。"""
    sleeps: list[float] = []
    monkeypatch.setattr(
        "deltaforcebox.core.gun_solutions.time.sleep", lambda sec: sleeps.append(sec)
    )
    api = _FakeApi(
        [[_api_item(1, "A", author="a"), _api_item(2, "B", author="b")],
         [_api_item(3, "C", author="c")]],
        total=3,
    )
    sols = sync_official_solutions(fetcher=api, limit=2, page_delay_ms=250)
    assert {s.id for s in sols} == {1, 2, 3}
    assert api.calls == [1, 2]  # 页数 = ceil(3/2) = 2，不请求多余页
    assert sleeps == [0.25]  # 页间一次延迟


def test_sync_official_last_page_short() -> None:
    """最后一页不足 limit：total=2, limit=50 -> 1 页 2 条。"""
    api = _FakeApi([[_api_item(1, "A", author="a"), _api_item(2, "B", author="b")]], total=2)
    sols = sync_official_solutions(fetcher=api, limit=50, page_delay_ms=0)
    assert {s.id for s in sols} == {1, 2}
    assert api.calls == [1]


def test_sync_official_stops_on_empty_page() -> None:
    """totalCount 缺失：以空页为结束信号，不多请求。"""
    api = _FakeApi([[_api_item(1, "A", author="a")], []], total=None)
    sols = sync_official_solutions(fetcher=api, limit=50, page_delay_ms=0)
    assert {s.id for s in sols} == {1}
    assert api.calls == [1, 2]  # 第 2 页为空 -> 停止


def test_sync_official_dynamic_pages(monkeypatch) -> None:
    """totalCount 变化（1268 -> 页数 26 类推）：按第 1 页 total 计算。"""
    sleeps: list[float] = []
    monkeypatch.setattr(
        "deltaforcebox.core.gun_solutions.time.sleep", lambda sec: sleeps.append(sec)
    )
    # total=120, limit=50 -> 3 页（每页满 50）
    pages = [[_api_item(i, f"G{i}", author=f"a{i}") for i in range(1, 51)],
             [_api_item(i, f"G{i}", author=f"a{i}") for i in range(51, 101)],
             [_api_item(i, f"G{i}", author=f"a{i}") for i in range(101, 121)]]
    api = _FakeApi(pages, total=120)
    sols = sync_official_solutions(fetcher=api, limit=50, page_delay_ms=100)
    assert len(sols) == 120
    assert api.calls == [1, 2, 3]
    assert len(sleeps) == 2


def test_sync_official_filters_authorless() -> None:
    """官方裸方案（无 authorDetail）被过滤，只留主播推荐。"""
    api = _FakeApi([[_api_item(1, "官方", gun="M700"), _api_item(2, "主播", author="a")]], total=2)
    sols = sync_official_solutions(fetcher=api, limit=50, page_delay_ms=0)
    assert {s.id for s in sols} == {2}


def test_sync_official_dedup_across_pages() -> None:
    """跨页重复 id：合并时只保留一条（幂等）。"""
    api = _FakeApi(
        [[_api_item(1, "A", author="a"), _api_item(2, "B", author="b")],
         [_api_item(1, "A-dup", author="a2")]],
        total=3,
    )
    sols = sync_official_solutions(fetcher=api, limit=2, page_delay_ms=0)
    assert len(sols) == 2
    assert sols[0].name == "A"  # 首条保留


def test_sync_official_should_stop() -> None:
    """should_stop=True：不再发起请求（窗口关闭中断场景）。"""
    api = _FakeApi([[_api_item(1, "A", author="a")]], total=1)
    sols = sync_official_solutions(fetcher=api, limit=50, page_delay_ms=0, should_stop=lambda: True)
    assert sols == []


def test_sync_official_empty_raises() -> None:
    api = _FakeApi([[]], total=0)
    with pytest.raises(ValueError):
        sync_official_solutions(fetcher=api, limit=50, page_delay_ms=0)


def test_fetch_official_page_returns_data() -> None:
    """fetch_official_page 返回 data 部分（list/page/totalCount）。"""
    api = _FakeApi([[_api_item(1, "A", author="a")]], total=1)
    fetch_official_page = __import__(
        "deltaforcebox.core.gun_solutions", fromlist=["fetch_official_page"]
    ).fetch_official_page
    data = fetch_official_page(fetcher=api, page=1, limit=50)
    assert data["totalCount"] == 1
    assert len(data["list"]) == 1
    assert data["page"] == 1
