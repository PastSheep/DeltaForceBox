"""每日密码：数据源解析、优先级回退、缓存与页面展示测试。"""

from __future__ import annotations

import json

import pytest

from deltaforcebox.core.daily_password import (
    DEFAULT_SOURCE_ORDER,
    DailyPasswordData,
    cache_is_today,
    fetch_password,
    fetch_shushu_fan,
    fetch_tmini,
    load_cache,
    normalize_source_order,
    parse_update_date,
    save_cache,
)
from deltaforcebox.core.i18n import I18nManager
from deltaforcebox.core.theme import ThemeManager
from deltaforcebox.widgets.pages.daily_password_page import (
    CARD_HEIGHT,
    DESC_AREA_HEIGHT,
    GRID_PADDING,
    MAX_CARD_WIDTH,
    MIN_CARD_WIDTH,
    DailyPasswordPage,
)

# ── 数据源解析 ─────────────────────────────────────────

TMINI_SAMPLE = {
    "status": "success",
    "data": {
        "update_date": "10月02日每日密码已更新",
        "total_count": 6,
        "passwords": [
            {
                "map_name": "零号大坝",
                "password": "2581",
                "location_info": {"description": "主变电站右侧地下管道尽头"},
            },
            {"map_name": "长弓溪谷", "password": "2715", "location_info": {}},
            {"map_name": "巴克什", "password": "8382"},
        ],
        "last_updated": "2026-10-02 00:05:01",
    },
}


def test_tmini_parses_json(monkeypatch):
    monkeypatch.setattr(
        "deltaforcebox.core.daily_password._http_get",
        lambda url, timeout: json.dumps(TMINI_SAMPLE, ensure_ascii=False),
    )
    data = fetch_tmini()
    assert data.source == "tmini"
    assert data.passwords == {"零号大坝": "2581", "长弓溪谷": "2715", "巴克什": "8382"}
    assert data.locations["零号大坝"] == "主变电站右侧地下管道尽头"
    assert data.update_date == "10月02日每日密码已更新"
    assert data.updated_at == "2026-10-02 00:05:01"


def test_tmini_empty_payload_raises(monkeypatch):
    monkeypatch.setattr(
        "deltaforcebox.core.daily_password._http_get",
        lambda url, timeout: json.dumps({"data": {"passwords": []}}),
    )
    with pytest.raises(ValueError):
        fetch_tmini()


def test_tmini_timestamp_fallback_when_last_updated_missing(monkeypatch):
    """last_updated 缺失时用 timestamp（Unix 秒）转出更新时间。"""
    from datetime import datetime

    payload = dict(TMINI_SAMPLE)
    payload["data"] = dict(TMINI_SAMPLE["data"])
    payload["data"].pop("last_updated")
    payload["data"]["timestamp"] = 1790874266  # 2026-10-02 01:04:26 UTC+8
    monkeypatch.setattr(
        "deltaforcebox.core.daily_password._http_get",
        lambda url, timeout: json.dumps(payload, ensure_ascii=False),
    )
    data = fetch_tmini()
    expected = datetime.fromtimestamp(1790874266).strftime("%Y-%m-%d %H:%M:%S")
    assert data.updated_at == expected


def test_shushu_fan_parses_html(monkeypatch):
    # 模拟 SSR 直出 HTML：地图名 span 与数字 span 之间可能隔多个样式 span
    html = (
        '<div><span class="a">零号大坝</span>'
        '<span class="s1">x</span><span class="s2">y</span>'
        '<span class="n">2581</span></div>'
        '<div><span>长弓溪谷</span><span>2715</span></div>'
        '<div><span>巴克什</span><span>8382</span></div>'
        '<div><span>航天基地</span><span>2457</span></div>'
        '<div><span>潮汐监狱</span><span>8517</span></div>'
        '<div><span>AZ3</span><span>0700</span></div>'
    )
    monkeypatch.setattr(
        "deltaforcebox.core.daily_password._http_get", lambda url, timeout: html
    )
    data = fetch_shushu_fan()
    assert data.source == "shushu_fan"
    assert data.passwords["零号大坝"] == "2581"
    assert data.passwords["AZ3"] == "0700"
    assert len(data.passwords) == 6


def test_shushu_fan_incomplete_raises(monkeypatch):
    monkeypatch.setattr(
        "deltaforcebox.core.daily_password._http_get",
        lambda url, timeout: "<span>零号大坝</span><span>2581</span>",
    )
    with pytest.raises(ValueError):
        fetch_shushu_fan()


# ── 优先级与回退 ───────────────────────────────────────

def _make_fetcher(data: DailyPasswordData | None):
    calls: list[str] = []

    def fetcher(timeout):
        calls.append("called")
        if data is None:
            raise ConnectionError("模拟网络失败")
        return data

    fetcher.calls = calls  # type: ignore[attr-defined]
    return fetcher


def test_priority_skips_failed_source():
    ok = DailyPasswordData(
        source="shushu_fan",
        update_date="10月02日每日密码已更新",
        passwords={"零号大坝": "2581"},
    )
    bad = _make_fetcher(None)
    good = _make_fetcher(ok)
    data = fetch_password(("tmini", "shushu_fan"), fetchers={"tmini": bad, "shushu_fan": good})
    assert data is not None and data.source == "shushu_fan"
    assert bad.calls and good.calls  # 主源失败后确实回退


def test_priority_uses_first_success():
    ok1 = DailyPasswordData(
        source="tmini", update_date="10月02日每日密码已更新", passwords={"a": "1"}
    )
    ok2 = DailyPasswordData(
        source="shushu_fan", update_date="10月02日每日密码已更新", passwords={"b": "2"}
    )
    first = _make_fetcher(ok1)
    second = _make_fetcher(ok2)
    data = fetch_password(("tmini", "shushu_fan"), fetchers={"tmini": first, "shushu_fan": second})
    assert data is not None and data.source == "tmini"
    assert first.calls and not second.calls  # 主源成功，不再尝试备用


def test_all_sources_fail_returns_none():
    bad1 = _make_fetcher(None)
    bad2 = _make_fetcher(None)
    assert (
        fetch_password(
            ("tmini", "shushu_fan"), fetchers={"tmini": bad1, "shushu_fan": bad2}
        )
        is None
    )


def test_unknown_source_skipped():
    ok = _make_fetcher(
        DailyPasswordData(
            source="tmini", update_date="10月02日每日密码已更新", passwords={"a": "1"}
        )
    )
    data = fetch_password(("nope", "tmini"), fetchers={"tmini": ok})
    assert data is not None


# ── 缓存 ───────────────────────────────────────────────

def test_cache_roundtrip(tmp_path):
    path = tmp_path / "cache.json"
    data = DailyPasswordData(
        source="tmini",
        update_date="10月02日每日密码已更新",
        updated_at="2026-10-02 00:05:01",
        passwords={"零号大坝": "2581"},
        locations={"零号大坝": "主变电站"},
    )
    save_cache(data, path)
    cache = load_cache(path)
    assert cache["source"] == "tmini"
    assert cache["passwords"]["零号大坝"] == "2581"
    assert cache["saved_at"]


def test_cache_missing_or_corrupt_returns_none(tmp_path):
    assert load_cache(tmp_path / "nope.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    assert load_cache(bad) is None
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"passwords": {}}), encoding="utf-8")
    assert load_cache(empty) is None


def test_parse_update_date_and_today():
    assert parse_update_date("10月02日每日密码已更新") == (10, 2)
    assert parse_update_date("10月2日每日密码已更新") == (10, 2)
    assert parse_update_date("") is None

    from datetime import datetime

    assert cache_is_today("10月02日每日密码已更新", now=datetime(2026, 10, 2, 8, 0))
    assert not cache_is_today("10月01日每日密码已更新", now=datetime(2026, 10, 2, 8, 0))
    assert not cache_is_today("", now=datetime(2026, 10, 2, 8, 0))


def test_normalize_source_order():
    assert normalize_source_order(None) == DEFAULT_SOURCE_ORDER
    assert normalize_source_order(["shushu_fan", "tmini"]) == ("shushu_fan", "tmini")
    assert normalize_source_order(["bogus", "tmini"]) == ("tmini", "shushu_fan")
    assert normalize_source_order(["tmini", "tmini", "shushu_fan"]) == ("tmini", "shushu_fan")


def test_normalize_source_order_type_guard():
    """#8 回归：非列表/元组类型（如手改成整数）回退默认顺序，不抛 TypeError。"""
    assert normalize_source_order(42) == DEFAULT_SOURCE_ORDER
    assert normalize_source_order("tmini") == DEFAULT_SOURCE_ORDER


def test_fetch_password_should_stop():
    """#1 回归：should_stop 置位时中止拉取（窗口关闭时快速收尾后台线程）。"""
    calls: list[int] = []

    def fetcher(timeout):
        calls.append(timeout)
        return DailyPasswordData(
            source="tmini",
            update_date="10月01日每日密码已更新",
            passwords={"零号大坝": "1234"},
        )

    order = ("tmini", "shushu_fan")
    table = {"tmini": fetcher, "shushu_fan": fetcher}
    stopped = False
    result = fetch_password(order, fetchers=table, should_stop=lambda: stopped)
    assert result is not None
    assert len(calls) == 1

    calls.clear()
    stopped = True
    result2 = fetch_password(order, fetchers=table, should_stop=lambda: stopped)
    assert result2 is None
    assert calls == []  # 首个源尝试前即中止


# ── 页面 ───────────────────────────────────────────────

@pytest.fixture()
def i18n_theme():
    i18n = I18nManager()
    theme = ThemeManager()
    return i18n, theme


def _sample_data(source: str = "tmini") -> DailyPasswordData:
    # 日期动态化为「今天」：页面级测试依赖"当日缓存新鲜"语义，
    # 硬编码固定日期会在跨天后导致误判过期并触发拉取（测试脆弱性）。
    from datetime import datetime

    now = datetime.now()
    return DailyPasswordData(
        source=source,
        update_date=f"{now.month}月{now.day:02d}日每日密码已更新",
        updated_at=now.strftime("%Y-%m-%d %H:%M:%S"),
        passwords={
            "零号大坝": "2581",
            "长弓溪谷": "2715",
            "巴克什": "8382",
            "航天基地": "2457",
            "潮汐监狱": "8517",
            "AZ3": "0700",
        },
        locations={"零号大坝": "主变电站右侧地下管道尽头"},
    )


def test_page_renders_today_cache_without_fetch(qapp, i18n_theme, tmp_path):
    """当日缓存直接渲染，且不发起网络请求（_fetching 保持 False）。"""
    i18n, theme = i18n_theme
    cache = tmp_path / "cache.json"
    save_cache(_sample_data(), cache)

    def boom(timeout):  # 不应被调用
        raise AssertionError("当日缓存不应触发网络请求")

    page = DailyPasswordPage(
        i18n, theme, source_order=("tmini",), cache_file=cache, fetchers={"tmini": boom}
    )
    assert page._fetching is False
    assert page._has_content is True
    assert page._flow.count() == 6
    assert page._worker is None


def test_page_shows_empty_when_no_cache_and_fetch_fails(qapp, i18n_theme, tmp_path):
    i18n, theme = i18n_theme
    cache = tmp_path / "cache.json"

    def boom(timeout):
        raise ConnectionError("no network")

    page = DailyPasswordPage(
        i18n, theme, source_order=("tmini",), cache_file=cache, fetchers={"tmini": boom}
    )
    if page._worker is not None:
        page._worker.wait(2000)  # 等待后台线程结束，避免测试尾段竞态
    page._on_fetch_fail("模拟失败")
    assert page._has_content is False
    assert "获取失败" in page.status_label.text()
    assert not page.empty_label.isHidden()


def test_page_fetch_ok_renders_and_writes_cache(qapp, i18n_theme, tmp_path):
    i18n, theme = i18n_theme
    cache = tmp_path / "cache.json"

    def fake(timeout):
        return _sample_data()

    page = DailyPasswordPage(
        i18n, theme, source_order=("tmini",), cache_file=cache, fetchers={"tmini": fake}
    )
    if page._worker is not None:
        page._worker.wait(2000)
    page._on_fetch_ok(_sample_data())
    assert page._flow.count() == 6
    assert "2581" in page.status_label.text() or page.status_label.text() != ""
    assert load_cache(cache)["passwords"]["零号大坝"] == "2581"


def test_page_manual_refresh_uses_latest(qapp, i18n_theme, tmp_path):
    """手动刷新强制重新拉取（当日缓存也刷新）。"""
    i18n, theme = i18n_theme
    cache = tmp_path / "cache.json"
    save_cache(_sample_data(), cache)
    fresh = _sample_data()
    fresh.passwords = {k: "9999" for k in fresh.passwords}  # 新值

    def fake(timeout):
        return fresh

    page = DailyPasswordPage(
        i18n, theme, source_order=("tmini",), cache_file=cache, fetchers={"tmini": fake}
    )
    assert page._worker is None  # 当日缓存未启动线程
    page._refresh_now()
    if page._worker is not None:
        page._worker.wait(2000)
    page._on_fetch_ok(fresh)
    assert page._flow.count() == 6
    assert load_cache(cache)["passwords"]["零号大坝"] == "9999"


def test_page_throttles_after_failed_fetch(qapp, i18n_theme, tmp_path):
    """全部来源失败后节流 15 分钟，期间不再重复请求。"""
    i18n, theme = i18n_theme
    cache = tmp_path / "cache.json"

    def boom(timeout):
        raise ConnectionError("down")

    page = DailyPasswordPage(
        i18n, theme, source_order=("tmini",), cache_file=cache, fetchers={"tmini": boom}
    )
    if page._worker is not None:
        page._worker.wait(2000)
    page._on_fetch_fail("down")
    assert page._throttle_until is not None
    page._on_worker_finished()  # offscreen 下 queued 信号不派发，手动模拟线程结束
    page._maybe_refresh()
    assert page._worker is None, "节流期间不应再次发起请求"


def test_page_throttles_when_fetch_returns_stale(qapp, i18n_theme, tmp_path):
    """主源更新滞后（返回非今日数据）时延后重试，避免循环请求。"""
    i18n, theme = i18n_theme
    cache = tmp_path / "cache.json"
    stale = _sample_data()
    from datetime import datetime, timedelta

    yesterday = datetime.now() - timedelta(days=1)
    stale.update_date = f"{yesterday.month}月{yesterday.day:02d}日每日密码已更新"  # 非今日

    def fake(timeout):
        return stale

    page = DailyPasswordPage(
        i18n, theme, source_order=("tmini",), cache_file=cache, fetchers={"tmini": fake}
    )
    if page._worker is not None:
        page._worker.wait(2000)
    page._on_fetch_ok(stale)
    assert page._throttle_until is not None
    page._on_worker_finished()  # offscreen 下 queued 信号不派发，手动模拟线程结束
    page._maybe_refresh()
    assert page._worker is None


# ── 地图缩略图与卡片布局 ─────────────────────────────

def test_resolve_map_image_aliases():
    from deltaforcebox.widgets.pages.daily_password_page import (
        MAP_IMAGE_DIR,
        resolve_map_image,
    )

    assert MAP_IMAGE_DIR.is_dir()
    assert (MAP_IMAGE_DIR / "零号大坝.jpg").exists()
    # "AZ3核电站"（tmini 命名）应命中文件 AZ3.jpg
    assert resolve_map_image("AZ3核电站") == MAP_IMAGE_DIR / "AZ3.jpg"
    assert resolve_map_image("零号大坝") == MAP_IMAGE_DIR / "零号大坝.jpg"
    assert resolve_map_image("不存在的图") is None


def test_page_cards_include_map_image(qapp, i18n_theme, tmp_path):
    i18n, theme = i18n_theme
    cache = tmp_path / "cache.json"
    save_cache(_sample_data(), cache)
    page = DailyPasswordPage(
        i18n, theme, source_order=("tmini",), cache_file=cache, fetchers={"tmini": None}
    )
    page.resize(1100, 640)
    page.show()
    qapp.processEvents()
    assert page._flow.count() == 6
    # 流式网格：卡片宽度/列数由 reflow 统一控制
    card = page._flow.itemAt(0).widget()
    assert hasattr(card, "image_label")
    assert not card.image_label.pixmap().isNull()  # 真实缩略图已加载
    # 卡片宽度处于限定范围内且随视口自适应（填满每行）
    assert MIN_CARD_WIDTH <= card.width() <= MAX_CARD_WIDTH
    assert card.width() == page._card_w
    # 描述区固定高度滚动，长文本可滚动查看全文
    assert card.desc_scroll.height() == DESC_AREA_HEIGHT
    inner = card.desc_scroll.widget()
    assert inner.wordWrap()
    assert inner.text()  # 无位置描述时落入占位文案


def test_card_width_reflows_with_viewport(qapp, i18n_theme, tmp_path):
    i18n, theme = i18n_theme
    cache = tmp_path / "cache.json"
    save_cache(_sample_data(), cache)
    page = DailyPasswordPage(
        i18n, theme, source_order=("tmini",), cache_file=cache, fetchers={"tmini": None}
    )
    page.show()
    qapp.processEvents()

    # 宽视口：卡片拉宽填满每行（行尾仅留间距级留白，无大块空白）
    page.resize(1200, 640)
    for _ in range(3):
        qapp.processEvents()  # 等待 singleShot(0) 延迟重排执行
    wide_w = page._card_w
    assert MIN_CARD_WIDTH <= wide_w <= MAX_CARD_WIDTH
    xs = [page._flow.itemAt(i).widget().x() for i in range(page._flow.count())]
    row_w = max(xs) - min(xs) + wide_w
    assert (page.scroll.viewport().width() - row_w) <= 2 * GRID_PADDING + 8
    wide_cols = len({round(x / (wide_w + GRID_PADDING)) for x in xs})
    # 卡片间实际间距 = 同一行内相邻 x 差 - 卡宽
    rows: dict[int, list[int]] = {}
    for i in range(page._flow.count()):
        card = page._flow.itemAt(i).widget()
        rows.setdefault(card.y(), []).append(card.x())
    for col_xs in rows.values():
        col_xs = sorted(col_xs)
        for j in range(len(col_xs) - 1):
            assert col_xs[j + 1] - col_xs[j] - wide_w == GRID_PADDING
    # 卡片纵向间距 = 行间 y 差 - 卡高
    ys = sorted(rows.keys())
    if len(ys) > 1:
        assert ys[1] - ys[0] == CARD_HEIGHT + GRID_PADDING

    # 窄视口：列数减少、卡片宽度仍在限定范围内
    page.resize(660, 640)
    for _ in range(3):
        qapp.processEvents()
    narrow_w = page._card_w
    assert MIN_CARD_WIDTH <= narrow_w <= MAX_CARD_WIDTH
    xs = [page._flow.itemAt(i).widget().x() for i in range(page._flow.count())]
    narrow_cols = len({round(x / narrow_w) for x in xs})
    assert narrow_cols < wide_cols


def test_card_columns_stable_across_smooth_resize(qapp, i18n_theme, tmp_path):
    """平滑调整窗口宽度：列数单调变化（迟滞），不来回跳变闪烁。"""
    i18n, theme = i18n_theme
    cache = tmp_path / "cache.json"
    save_cache(_sample_data(), cache)
    page = DailyPasswordPage(
        i18n, theme, source_order=("tmini",), cache_file=cache, fetchers={"tmini": None}
    )
    page.resize(1000, 640)
    page.show()
    qapp.processEvents()

    cols_history: list[int] = []
    for w in range(1000, 1701, 10):
        page.resize(w, 640)
        for _ in range(2):
            qapp.processEvents()
        xs = [page._flow.itemAt(i).widget().x() for i in range(page._flow.count())]
        cols_history.append(len({round(x / (page._card_w + GRID_PADDING)) for x in xs}))

    # 递增宽度下列数不应减少（迟滞保证临界处无来回跳变）
    assert all(
        b >= a for a, b in zip(cols_history, cols_history[1:])
    ), f"列数出现来回跳变: {cols_history}"
    assert cols_history[-1] > cols_history[0]  # 足够宽后列数确实增加


def test_card_click_opens_large_preview(qapp, i18n_theme, tmp_path):
    """点击卡片弹出大图预览：无边框置顶悬浮窗，显示地图名+密码。"""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    i18n, theme = i18n_theme
    cache = tmp_path / "cache.json"
    save_cache(_sample_data(), cache)
    page = DailyPasswordPage(
        i18n, theme, source_order=("tmini",), cache_file=cache, fetchers={"tmini": None}
    )
    page.resize(1100, 640)
    page.show()
    qapp.processEvents()

    card = page._flow.itemAt(0).widget()
    assert card.image_path is not None  # 有图地图可预览
    assert card.cursor().shape() == Qt.CursorShape.PointingHandCursor

    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(5, 5),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    card.mousePressEvent(press)
    qapp.processEvents()
    assert page._preview is not None and page._preview.isVisible()
    assert page._preview.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert page._preview.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert not page._preview.image_label.pixmap().isNull()  # 大图已加载


def test_preview_closes_on_click_anywhere(qapp, i18n_theme, tmp_path):
    """点击预览窗口任意位置（含标题/图片区）均关闭（WA_DeleteOnClose 销毁）。"""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    from shiboken6 import isValid

    i18n, theme = i18n_theme
    cache = tmp_path / "cache.json"
    save_cache(_sample_data(), cache)
    page = DailyPasswordPage(
        i18n, theme, source_order=("tmini",), cache_file=cache, fetchers={"tmini": None}
    )
    page.resize(1100, 640)
    page.show()
    qapp.processEvents()

    def make_press() -> QMouseEvent:
        return QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(5, 5),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

    # 点击卡片弹出预览（sendEvent 走真实事件分发，触发 override）
    card = page._flow.itemAt(0).widget()
    QApplication.sendEvent(card, make_press())
    qapp.processEvents()
    preview = page._preview
    assert isValid(preview) and preview.isVisible()

    # 点击图片区关闭（走 eventFilter 拦截路径），自动销毁
    QApplication.sendEvent(preview.image_label, make_press())
    qapp.processEvents()
    assert not isValid(preview)

    # 再次点击另一卡片重新弹出，点击窗口空白处也关闭
    card.mousePressEvent(make_press())
    qapp.processEvents()
    preview2 = page._preview
    assert isValid(preview2) and preview2.isVisible()
    QApplication.sendEvent(preview2, make_press())
    qapp.processEvents()
    assert not isValid(preview2)


def test_preview_replaces_instead_of_multiple(qapp, i18n_theme, tmp_path):
    """预览已打开时点击其他卡片：替换同一窗口内容，不新建多个窗口。"""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    from shiboken6 import isValid

    i18n, theme = i18n_theme
    cache = tmp_path / "cache.json"
    save_cache(_sample_data(), cache)
    page = DailyPasswordPage(
        i18n, theme, source_order=("tmini",), cache_file=cache, fetchers={"tmini": None}
    )
    page.resize(1100, 640)
    page.show()
    qapp.processEvents()

    def press() -> QMouseEvent:
        return QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(5, 5),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

    card0 = page._flow.itemAt(0).widget()  # 零号大坝
    card1 = page._flow.itemAt(1).widget()  # 长弓溪谷
    QApplication.sendEvent(card0, press())
    qapp.processEvents()
    preview = page._preview
    assert isValid(preview) and preview.isVisible()
    assert "零号大坝" in preview.cap_label.text()

    # 预览打开时点击另一卡片：同一窗口对象，仅替换标题与图片
    QApplication.sendEvent(card1, press())
    qapp.processEvents()
    assert page._preview is preview
    assert isValid(preview) and preview.isVisible()
    assert "长弓溪谷" in preview.cap_label.text()
    assert not preview.image_label.pixmap().isNull()


def test_local_location_fallback(qapp, i18n_theme, tmp_path):
    """无描述来源（如 shushu_fan）：位置描述回退本地静态资源，不依赖网络。"""
    from deltaforcebox.widgets.pages.daily_password_page import (
        LOCAL_LOCATIONS,
        MAP_ORDER,
    )

    assert LOCAL_LOCATIONS  # 本地描述资源已加载
    i18n, theme = i18n_theme
    cache = tmp_path / "cache.json"
    data = _sample_data()
    data.locations = {}  # 模拟数据源不提供描述
    save_cache(data, cache)
    page = DailyPasswordPage(
        i18n, theme, source_order=("tmini",), cache_file=cache, fetchers={"tmini": None}
    )
    page.resize(1100, 640)
    page.show()
    qapp.processEvents()

    no_loc = i18n.t("dailypwd.no_location")
    for i in range(page._flow.count()):
        card = page._flow.itemAt(i).widget()
        text = card.desc_scroll.widget().text()
        assert text and text != no_loc  # 均有描述且非占位
        assert text == LOCAL_LOCATIONS[MAP_ORDER[i]]


def test_card_order_fixed_across_sources(qapp, i18n_theme, tmp_path):
    """不同源的返回顺序不影响卡片显示顺序（固定 MAP_ORDER，AZ3 变体归一）。"""
    from deltaforcebox.widgets.pages.daily_password_page import MAP_ORDER

    i18n, theme = i18n_theme
    cache = tmp_path / "cache.json"
    data = DailyPasswordData(
        source="tmini",
        update_date="10月02日每日密码已更新",
        passwords={
            "AZ3核电站": "0700",  # tmini 返回顺序：AZ3 在前
            "潮汐监狱": "8517",
            "零号大坝": "2581",
            "航天基地": "2457",
            "巴克什": "8382",
            "长弓溪谷": "2715",
        },
    )
    save_cache(data, cache)
    page = DailyPasswordPage(
        i18n, theme, source_order=("tmini",), cache_file=cache, fetchers={"tmini": None}
    )
    page.resize(1100, 640)
    page.show()
    qapp.processEvents()
    assert page._flow.count() == 6
    titles = [page._flow.itemAt(i).widget().name for i in range(page._flow.count())]
    assert titles == list(MAP_ORDER)
    # AZ3 变体归一并显示标准名
    card_az3 = page._flow.itemAt(5).widget()
    assert card_az3.name == "AZ3"
    assert card_az3.code == "0700"


def test_set_source_order_no_refetch(qapp, i18n_theme, tmp_path):
    """运行时修改来源顺序：仅更新顺序不立即拉取，手动刷新时按新顺序请求。"""
    i18n, theme = i18n_theme
    cache = tmp_path / "cache.json"
    save_cache(_sample_data(), cache)  # 当日缓存：构造时不触发拉取
    calls: list[str] = []

    def fake(timeout):
        calls.append("called")
        return _sample_data(source="shushu_fan")

    page = DailyPasswordPage(
        i18n,
        theme,
        source_order=("tmini",),
        cache_file=cache,
        fetchers={"tmini": fake, "shushu_fan": fake},
    )
    assert page._worker is None
    page.set_source_order(("shushu_fan", "tmini"))
    assert page._order == ("shushu_fan", "tmini")
    assert page._worker is None  # 不立即拉取
    assert not calls
    # 用户点击刷新时按新顺序拉取
    page._refresh_now()
    assert page._worker is not None
    if page._worker is not None:
        page._worker.wait(2000)
    assert calls  # 新顺序的 fetcher 确实被调用
    page._on_worker_finished()


def test_settings_source_signal_emits_order(qapp, i18n_theme, tmp_path):
    """设置页首选来源变更：发出重排后的完整顺序信号并持久化。"""
    from deltaforcebox.core.settings import load_settings
    from deltaforcebox.widgets.pages.settings_page import SettingsPage

    i18n, theme = i18n_theme
    settings = tmp_path / "settings.json"
    page = SettingsPage(i18n, theme, settings_path=settings)
    received: list[tuple[str, ...]] = []
    page.password_source_changed.connect(received.append)
    page.source_combo.setCurrentIndex(page.source_combo.findData("shushu_fan"))
    assert received and received[0] == ("shushu_fan", "tmini")
    assert load_settings(settings)["password_source_order"] == ["shushu_fan", "tmini"]


# ── 侧栏注册 ───────────────────────────────────────────

def test_sidebar_contains_tools_group(qapp, i18n_theme):
    from PySide6.QtCore import Qt

    from deltaforcebox.widgets.main_window import MainWindow

    i18n, theme = i18n_theme
    window = MainWindow(i18n, theme)
    keys = []
    for i in range(window.sidebar.topLevelItemCount()):
        item = window.sidebar.topLevelItem(i)
        keys.append(item.data(0, Qt.ItemDataRole.UserRole))
        for j in range(item.childCount()):
            keys.append(item.child(j).data(0, Qt.ItemDataRole.UserRole))
    assert "tools" in keys
    assert "daily_password" in keys
    window.close()
