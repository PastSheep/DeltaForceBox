"""改枪码页面 GUI 测试：四维筛选 / 卡片描述滚动区 / 下拉联动。"""

from __future__ import annotations

from pathlib import Path

import pytest

from deltaforcebox.core.gun_solutions import (
    GunSolution,
    parse_gun_solutions,
    save_guns_cache,
)
from deltaforcebox.widgets.pages.gun_code_page import (
    DESC_AREA_HEIGHT,
    GunCodePage,
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
    combo.setCurrentIndex(0)  # 全部
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


def test_render_first_page_only(page: GunCodePage) -> None:
    """100 条（5 页）-> 初始只渲染第 1 页 20 张；翻页控件状态正确。"""
    page._set_solutions(_make_solutions(100))
    assert page._page_size == 20
    assert len(page._cards) == 20
    assert page._page_index == 0
    assert page._total_pages == 5
    assert page.page_label.text() == "第 1 / 5 页"
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
    assert page.page_label.text() == "第 2 / 5 页"
    assert page.prev_btn.isEnabled()
    assert page.next_btn.isEnabled()
    assert page._cards[0].solution.id == 20


def test_goto_last_page(page: GunCodePage) -> None:
    """跳到末页：100 条恰好整除 -> 末页仍是 20 张，next 禁用。"""
    page._set_solutions(_make_solutions(100))
    page._goto_page(4)
    assert page._page_index == 4
    assert len(page._cards) == 20
    assert page.page_label.text() == "第 5 / 5 页"
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
    assert page.page_label.text() == "第 2 / 5 页"
    page.prev_btn.click()
    assert page._page_index == 0
    assert page.page_label.text() == "第 1 / 5 页"


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
