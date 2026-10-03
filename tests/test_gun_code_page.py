"""改枪码页面 GUI 测试：四维筛选 / 卡片描述滚动区 / 下拉联动。"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from deltaforcebox.core.gun_solutions import (
    GunSolution,
    parse_gun_solutions,
    save_guns_cache,
)
from deltaforcebox.widgets.pages.gun_code_page import (
    DESC_AREA_HEIGHT,
    GunCodePage,
    _solution_from_dict,
)

FIXTURE = Path(__file__).parent / "data" / "guns_sample.html"


@pytest.fixture(scope="module")
def page(qapp, tmp_path_factory) -> GunCodePage:
    """模块级单页面：预写新鲜缓存 + 注入假抓取器。

    页面常驻（与真实程序一致），避免快速创建/销毁 QThread 引发的
    PySide6 崩溃；各测试在 _reset_filters 中回到「全部」状态。
    """
    solutions = parse_gun_solutions(FIXTURE.read_text(encoding="utf-8"))
    cache = tmp_path_factory.mktemp("gun_page") / "guns_cache.json"
    save_guns_cache(solutions, cache)
    page_obj = GunCodePage(
        __import__("deltaforcebox.core.i18n", fromlist=["I18nManager"]).I18nManager(),
        __import__("deltaforcebox.core.theme", fromlist=["ThemeManager"]).ThemeManager(),
        cache_file=cache,
        image_dir=cache.parent / "imgs",
        fetcher=lambda _url, _t: FIXTURE.read_text(encoding="utf-8"),
        image_opener=lambda _url, _t: b"x",  # 立即完成，避免测试内真实下载
    )
    yield page_obj
    page_obj._shutdown()  # teardown：等待后台线程收尾


@pytest.fixture(autouse=True)
def _reset_filters(page: GunCodePage) -> None:
    """每个测试前重置筛选状态为「全部」。"""
    for combo in page._filter_combos.values():
        combo.blockSignals(True)
        combo.setCurrentIndex(0)
        combo.blockSignals(False)
    page._set_solutions(page._all_solutions)  # 重建筛选选项并回到「全部」


def test_page_renders_all_cards(page: GunCodePage) -> None:
    assert len(page._cards) == 3
    assert len(page._all_solutions) == 3
    # 状态行显示共 N 条
    assert "共 3 条方案" in page.status_label.text()


def test_card_has_desc_scroll(page: GunCodePage) -> None:
    """每张卡片都有固定高度描述滚动区（格式统一）。"""
    for card in page._cards:
        assert card.desc_scroll is not None
        assert card.desc_scroll.minimumHeight() == DESC_AREA_HEIGHT
        assert card.desc_scroll.maximumHeight() == DESC_AREA_HEIGHT


def test_filter_weapon(page: GunCodePage) -> None:
    combo = page._filter_combos["weapon"]
    assert combo.findData("狙击步枪") >= 0
    combo.setCurrentIndex(combo.findData("狙击步枪"))
    assert len(page._cards) == 1
    assert page._cards[0].solution.id == 12825
    assert "筛选 1 / 共 3 条方案" in page.status_label.text()


def test_filter_gun(page: GunCodePage) -> None:
    combo = page._filter_combos["gun"]
    combo.setCurrentIndex(combo.findData("K437突击步枪"))
    assert len(page._cards) == 1
    assert page._cards[0].solution.id == 12827


def test_filter_author(page: GunCodePage) -> None:
    combo = page._filter_combos["author"]
    combo.setCurrentIndex(combo.findData("eStar丨Aqing"))
    assert len(page._cards) == 1
    assert page._cards[0].solution.author == "eStar丨Aqing"


def test_filter_tag(page: GunCodePage) -> None:
    combo = page._filter_combos["tag"]
    combo.setCurrentIndex(combo.findData("腰射专用"))
    assert len(page._cards) == 1
    assert page._cards[0].solution.id == 12826


def test_filter_combines_dimensions(page: GunCodePage) -> None:
    """多维度 AND：冲锋枪 + 满改神器 -> 仅 12826。"""
    page._filter_combos["weapon"].setCurrentIndex(
        page._filter_combos["weapon"].findData("冲锋枪")
    )
    page._filter_combos["tag"].setCurrentIndex(
        page._filter_combos["tag"].findData("满改神器")
    )
    assert len(page._cards) == 1
    assert page._cards[0].solution.id == 12826


def test_gun_combo_linkage(page: GunCodePage) -> None:
    """武器类型变化联动枪械下拉：冲锋枪 -> 仅 MK4冲锋枪。"""
    combo_gun = page._filter_combos["gun"]
    assert combo_gun.findData("MK4冲锋枪") >= 0
    assert combo_gun.findData("M700狙击步枪") >= 0
    page._filter_combos["weapon"].setCurrentIndex(
        page._filter_combos["weapon"].findData("冲锋枪")
    )
    # 联动后枪械下拉只剩「全部」+ 冲锋枪
    assert combo_gun.count() == 2
    assert combo_gun.itemData(1) == "MK4冲锋枪"
    assert combo_gun.findData("M700狙击步枪") == -1


def test_filter_reset_to_all(page: GunCodePage) -> None:
    combo = page._filter_combos["author"]
    combo.setCurrentIndex(combo.findData("JDG-duyilin"))
    assert len(page._cards) == 1
    combo.reset()  # 空白=无条件
    assert len(page._cards) == 3


def test_empty_filter_result_shows_hint(page: GunCodePage) -> None:
    """筛选无结果：列表清空但页面不崩。"""
    # 武器=狙击步枪 + 标签=腰射专用（腰射专用属于 MK4 冲锋枪）-> 无交集
    page._filter_combos["weapon"].setCurrentIndex(
        page._filter_combos["weapon"].findData("狙击步枪")
    )
    page._filter_combos["tag"].setCurrentIndex(
        page._filter_combos["tag"].findData("腰射专用")
    )
    assert len(page._cards) == 0


# ── 翻页渲染（默认每页 20 张） ─────────────────────────

def _make_solutions(n: int) -> list[GunSolution]:
    """构造 n 条方案（同枪械同作者，聚焦翻页行为）。"""
    return [
        GunSolution(
            id=i,
            name=f"方案{i}",
            gun_name="M700狙击步枪",
            weapon_type="狙击步枪",
            author="测试主播",
            channel="douyin",
            solution_code=f"M700狙击步枪-烽火地带-CODE{i}",
            tags=["满改神器"],
            price=100,
        )
        for i in range(n)
    ]


def _pager_btns(page: GunCodePage) -> list:
    """当前页码条按钮列表（按显示顺序）。"""
    from PySide6.QtWidgets import QPushButton

    return [
        page.pager_numbers.itemAt(i).widget()
        for i in range(page.pager_numbers.count())
        if isinstance(page.pager_numbers.itemAt(i).widget(), QPushButton)
    ]


def _pager_active_text(page: GunCodePage) -> str:
    """当前高亮页码（objectName=gunPagerNumActive 的按钮文本）。"""
    for btn in _pager_btns(page):
        if btn.objectName() == "gunPagerNumActive":
            return btn.text()
    raise AssertionError("页码条缺少当前页高亮按钮")


def test_reset_all_button(page: GunCodePage) -> None:
    """全部重置：四个筛选框恢复「全部」，渲染恢复全量。"""
    page._set_solutions(_make_solutions(40))
    page._filter_combos["weapon"].setCurrentIndex(
        page._filter_combos["weapon"].findData("狙击步枪")
    )
    page._filter_combos["gun"].setCurrentIndex(
        page._filter_combos["gun"].findData("M700狙击步枪")
    )
    page._filter_combos["author"].setCurrentIndex(
        page._filter_combos["author"].findData("测试主播")
    )
    assert page._filter_combos["weapon"].filter_text() == "狙击步枪"
    assert page.reset_btn.text() == "全部重置"
    page.reset_btn.click()
    for combo in page._filter_combos.values():
        assert combo.filter_text() == ""  # 重置=无条件
        assert combo.currentText() == "全部"  # 非焦点+无条件显示「全部」
    assert len(page._cards) == min(page._page_size, len(page._all_solutions))


def test_channel_badge_i18n(page: GunCodePage) -> None:
    """平台徽标走 i18n：douyin -> 抖音、bilibili -> B站；未知平台回退原标识。"""
    page._set_solutions([
        GunSolution(id=1, name="a", gun_name="枪A", weapon_type="步枪", author="主播A",
                    channel="douyin", solution_code="C1", tags=[], price=1),
        GunSolution(id=2, name="b", gun_name="枪B", weapon_type="步枪", author="主播B",
                    channel="bilibili", solution_code="C2", tags=[], price=1),
        GunSolution(id=3, name="c", gun_name="枪C", weapon_type="步枪", author="主播C",
                    channel="youtube", solution_code="C3", tags=[], price=1),
    ])
    texts = sorted(
        chip.text()
        for card in page._cards
        for chip in card.findChildren(QLabel, "gunChannel")
    )
    assert texts == ["B站", "youtube", "抖音"]


def test_render_first_page_only(page: GunCodePage) -> None:
    """100 条（5 页）-> 初始只渲染第 1 页 20 张；翻页控件状态正确。"""
    page._set_solutions(_make_solutions(100))
    assert page._page_size == 20
    assert len(page._cards) == 20
    assert page._page_index == 0
    assert page._total_pages == 5
    assert [b.text() for b in _pager_btns(page)] == ["1", "2", "3", "4", "5"]
    assert _pager_active_text(page) == "1"
    assert not page.prev_btn.isEnabled()
    assert page.next_btn.isEnabled()
    assert page._cards[0].solution.id == 0
    assert page._cards[-1].solution.id == 19


def test_goto_next_page(page: GunCodePage) -> None:
    """跳到第 2 页：只渲染余下 20 张，边界按钮翻转。"""
    page._set_solutions(_make_solutions(100))
    page._goto_page(1)
    assert page._page_index == 1
    assert len(page._cards) == 20
    assert _pager_active_text(page) == "2"
    assert page.prev_btn.isEnabled()
    assert page.next_btn.isEnabled()
    assert page._cards[0].solution.id == 20


def test_goto_last_page(page: GunCodePage) -> None:
    """跳到末页：100 条恰好整除 -> 末页仍是 20 张，next 禁用。"""
    page._set_solutions(_make_solutions(100))
    page._goto_page(4)
    assert page._page_index == 4
    assert len(page._cards) == 20
    assert _pager_active_text(page) == "5"
    assert not page.next_btn.isEnabled()
    assert page._cards[0].solution.id == 80


def test_goto_page_bounds(page: GunCodePage) -> None:
    """越界跳页自动收敛：负页 -> 第 1 页，超尾 -> 最后一页。"""
    page._set_solutions(_make_solutions(100))
    page._goto_page(-5)
    assert page._page_index == 0
    page._goto_page(99)
    assert page._page_index == page._total_pages - 1
    assert page._page_index == 4
    assert len(page._cards) == 20


def test_filter_resets_to_page_one(page: GunCodePage) -> None:
    """末页时筛选 -> 回到第 1 页渲染。"""
    page._set_solutions(_make_solutions(100))
    page._goto_page(4)
    page._filter_combos["weapon"].setCurrentIndex(
        page._filter_combos["weapon"].findData("狙击步枪")
    )
    assert page._page_index == 0
    assert len(page._cards) == 20


def test_pager_buttons_navigate(page: GunCodePage) -> None:
    """点击上一页/下一页按钮可切换页码。"""
    page._set_solutions(_make_solutions(100))
    page.next_btn.click()
    assert page._page_index == 1
    assert _pager_active_text(page) == "2"
    page.prev_btn.click()
    assert page._page_index == 0
    assert _pager_active_text(page) == "1"


def test_last_page_short(page: GunCodePage) -> None:
    """非整除总数：末页只渲染余数（95 条 -> 末页 15 张）。"""
    page._set_solutions(_make_solutions(95))
    assert page._total_pages == 5
    page._goto_page(4)
    assert len(page._cards) == 15
    assert page._cards[0].solution.id == 80


def test_single_page_disables_both_buttons(page: GunCodePage) -> None:
    """只有 1 页时两个翻页按钮都禁用。"""
    page._set_solutions(_make_solutions(3))
    assert page._total_pages == 1
    assert not page.prev_btn.isEnabled()
    assert not page.next_btn.isEnabled()
    assert len(page._cards) == 3
    assert len(page._all_solutions) == 3
    # 状态行显示共 N 条
    assert "共 3 条方案" in page.status_label.text()


# ── 页码条（1···n-2·n-1·n·n+1·n+2···s） ─────────────

def test_pager_items_all_pages_when_small() -> None:
    """总数 <= 7：全部显示、无省略号。"""
    from deltaforcebox.widgets.pages.gun_code_page import _pager_items

    assert _pager_items(1, 1) == [("1", 1)]
    assert _pager_items(1, 7) == [(str(i), i) for i in range(1, 8)]
    assert _pager_items(4, 7) == [(str(i), i) for i in range(1, 8)]


def test_pager_items_window() -> None:
    """total=64 中部：1···30·31·32·33·34···64。"""
    from deltaforcebox.widgets.pages.gun_code_page import _pager_items

    items = _pager_items(32, 64)
    assert [t for t, _ in items] == ["1", "···", "30", "31", "32", "33", "34", "···", "64"]
    assert items[1][1] == 27  # 左省略跳 32-5
    assert items[-2][1] == 37  # 右省略跳 32+5


def test_pager_items_boundaries() -> None:
    """边界：贴左/贴右/收敛/极小总数。"""
    from deltaforcebox.widgets.pages.gun_code_page import _pager_items

    # n=1：无左省略
    assert [t for t, _ in _pager_items(1, 64)] == ["1", "2", "3", "···", "64"]
    # n=4：窗口贴左，仍无左省略
    assert [t for t, _ in _pager_items(4, 64)] == ["1", "2", "3", "4", "5", "6", "···", "64"]
    # n=64：无右省略
    assert [t for t, _ in _pager_items(64, 64)] == ["1", "···", "62", "63", "64"]
    # n=5：左省略跳转收敛到 2
    assert _pager_items(5, 64)[1] == ("···", 2)
    # n=61：窗口含 63，右端无省略
    assert [t for t, _ in _pager_items(61, 64)] == ["1", "···", "59", "60", "61", "62", "63", "64"]
    # n=60：右省略跳转收敛到 63
    assert _pager_items(60, 64)[-2] == ("···", 63)
    # total=8 的最小省略场景
    assert [t for t, _ in _pager_items(8, 8)] == ["1", "···", "6", "7", "8"]
    # 越界输入收敛
    assert [t for t, _ in _pager_items(0, 64)] == ["1", "2", "3", "···", "64"]
    assert [t for t, _ in _pager_items(99, 64)] == ["1", "···", "62", "63", "64"]


def test_pager_bar_number_click(page: GunCodePage) -> None:
    """数字按钮点击跳转 + 高亮迁移（objectName 区分当前页）。"""
    page._set_solutions(_make_solutions(100))  # 5 页全显示
    btns = _pager_btns(page)
    assert [b.text() for b in btns] == ["1", "2", "3", "4", "5"]
    assert btns[0].objectName() == "gunPagerNumActive"
    assert btns[1].objectName() == "gunPagerNum"
    btns[2].click()  # 第 3 页
    assert page._page_index == 2
    assert _pager_active_text(page) == "3"


def test_pager_bar_ellipsis_click(page: GunCodePage) -> None:
    """省略号点击：向省略方向跳 5 页；多页时显示省略号。"""
    page._set_solutions(_make_solutions(1000))  # 50 页
    page._goto_page(31)  # 第 32 页
    texts = [b.text() for b in _pager_btns(page)]
    assert texts == ["1", "···", "30", "31", "32", "33", "34", "···", "50"]
    _pager_btns(page)[1].click()  # 左省略 -> 第 27 页
    assert page._page_index == 26
    assert _pager_active_text(page) == "27"
    page._goto_page(31)
    _pager_btns(page)[-2].click()  # 右省略 -> 第 37 页
    assert page._page_index == 36
    assert _pager_active_text(page) == "37"


def test_pager_button_symbols(page: GunCodePage) -> None:
    """上一页/下一页按钮显示紧凑符号 < 与 >（i18n 渲染后）。"""
    assert page.prev_btn.text() == "<"
    assert page.next_btn.text() == ">"


def test_filter_combo_width_fits_longest(page: GunCodePage) -> None:
    """筛选框最小宽度按候选项最长文本动态设定，收起时完整显示全部文字。"""
    for dim in ("weapon", "gun", "author", "tag"):
        combo = page._filter_combos[dim]
        fm = combo.fontMetrics()
        widest = max(fm.horizontalAdvance(combo.itemText(i)) for i in range(combo.count()))
        assert combo.minimumWidth() >= widest, f"{dim} 宽度不足以容纳最长候选项"


def test_filter_combo_width_survives_linkage(page: GunCodePage) -> None:
    """武器联动收窄枪械选项后，宽度仍不小于当前候选项最长文本。"""
    page._filter_combos["weapon"].setCurrentIndex(
        page._filter_combos["weapon"].findData("冲锋枪")
    )
    combo = page._filter_combos["gun"]
    fm = combo.fontMetrics()
    widest = max(fm.horizontalAdvance(combo.itemText(i)) for i in range(combo.count()))
    assert combo.minimumWidth() >= widest


def test_pixmap_cache_memory_layer(page: GunCodePage, tmp_path: Path) -> None:
    """QPixmapCache 内存层：磁盘加载入缓存；删盘后仍命中（零磁盘 I/O）。"""
    from PySide6.QtGui import QImage, QPixmapCache

    from deltaforcebox.widgets.pages.gun_code_page import _cached_pixmap

    # 自给自足：QPixmapCache 为全局共享，可能被其他测试（如 image_cache_limit_mb
    # 设为 0 的用例）改小/禁用；本测试显式设回足够上限再清空，避免环境依赖
    QPixmapCache.setCacheLimit(64 * 1024)
    QPixmapCache.clear()
    try:
        img = QImage(8, 8, QImage.Format.Format_RGB32)
        img.fill("blue")
        dest = tmp_path / "preview.png"
        assert img.save(str(dest))

        # 首次：磁盘加载 -> 入缓存
        pm1 = _cached_pixmap(dest, "gun:preview:test1")
        assert pm1 is not None and not pm1.isNull()

        # 删除磁盘文件后仍命中（证明走内存缓存）
        dest.unlink()
        pm2 = _cached_pixmap(dest, "gun:preview:test1")
        assert pm2 is not None and not pm2.isNull()

        # 无磁盘且未缓存 -> None
        assert _cached_pixmap(tmp_path / "nope.png", "gun:preview:nope") is None

        # 不同 key 不串扰
        assert QPixmapCache.find("gun:preview:test1") is not None
        assert QPixmapCache.find("gun:avatar:other") is None
    finally:
        QPixmapCache.clear()

def test_filter_input_contains(page: GunCodePage) -> None:
    """筛选框输入支持包含匹配（Beta-4.1）。"""
    page._set_solutions(_make_solutions(40))
    combo = page._filter_combos["gun"]
    combo.setEditText("M700")
    assert len(page._cards) > 0
    assert all("M700" in card.solution.gun_name for card in page._cards)
    combo.setEditText("")
    assert len(page._cards) == min(page._page_size, len(page._all_solutions))


def test_filter_combo_searchable(page: GunCodePage) -> None:
    """筛选下拉保持候选之外新增输入：editable + 弹层包含匹配（Beta-4.1）。"""
    combo = page._filter_combos["gun"]
    assert combo.isEditable()
    assert combo.completer().filterMode() == Qt.MatchFlag.MatchContains
    # 输入任意文本不会固化进候选列表（NoInsert）
    combo.setEditText("不存在枪")
    items = [combo.itemText(i) for i in range(combo.count())]
    assert "不存在枪" not in items


def test_filter_linkage_by_input(page: GunCodePage) -> None:
    """武器类型输入文本后，枪械候选按包含匹配收窄（Beta-4.1）。"""
    page._set_solutions(_make_solutions(40))
    combo = page._filter_combos["weapon"]
    combo.setEditText("狙击")
    guns = [
        page._filter_combos["gun"].itemText(i)
        for i in range(page._filter_combos["gun"].count())
    ]
    assert "全部" in guns  # 顶部「全部」文本项（内部=无条件）
    assert "M700狙击步枪" in guns

def test_solution_from_dict_guards_id():
    """C 回归：id 缺失/非法跳过该条；author_id 非数字归一为 0。"""
    assert _solution_from_dict({"id": "abc", "name": "x"}) is None
    assert _solution_from_dict({"id": 0, "name": "x"}) is None
    assert _solution_from_dict({"id": -3, "name": "x"}) is None
    ok = _solution_from_dict({"id": 7, "name": "x", "author_id": "oops"})
    assert ok is not None and ok.id == 7
    assert ok.author_id == 0
