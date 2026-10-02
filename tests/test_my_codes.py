"""我的改枪码测试：解析规则 / 候选提取 / 持久化 / 页面增删改查与筛选。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deltaforcebox.core.i18n import I18nManager
from deltaforcebox.core.my_codes import (
    load_candidates,
    load_my_codes,
    new_code_id,
    parse_gun_code,
    save_my_codes,
)
from deltaforcebox.core.theme import ThemeManager
from deltaforcebox.widgets.pages.my_codes_page import CARD_HEIGHT, MyCodesPage

# ── 解析规则 ─────────────────────────────────────────

def test_parse_gun_code_three_parts() -> None:
    assert parse_gun_code("M700狙击步枪-烽火地带-6ID3HD806QOMQD6J47QJA") == (
        "M700狙击步枪",
        "烽火地带",
        "6ID3HD806QOMQD6J47QJA",
    )


def test_parse_gun_code_legacy_two_parts() -> None:
    """旧格式 `枪械名-纯数字码`：第二段视为识别码，地图为空。"""
    assert parse_gun_code("K416突击步枪-5116089348491576161") == (
        "K416突击步枪",
        "",
        "5116089348491576161",
    )


def test_parse_gun_code_single_part() -> None:
    assert parse_gun_code("M700狙击步枪") == ("M700狙击步枪", "", "")


def test_parse_gun_code_extra_dashes() -> None:
    """识别码自身含 `-` 时，其后各段合并为识别码。"""
    assert parse_gun_code("枪A-烽火地带-码1-码2-码3") == ("枪A", "烽火地带", "码1-码2-码3")


def test_parse_gun_code_empty_and_whitespace() -> None:
    assert parse_gun_code("") == ("", "", "")
    assert parse_gun_code("   ") == ("", "", "")
    # 空段被忽略后退化为两段：第二段视为识别码
    assert parse_gun_code("枪A--烽火地带") == ("枪A", "", "烽火地带")


# ── 候选提取（与主播推荐一致） ───────────────────────

def _write_guns_cache(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "saved_at": "t",
                "source": "shushu.fan",
                "solutions": [
                    {"id": 1, "gun_name": "M7战斗步枪", "weapon_type": "突击步枪"},
                    {"id": 2, "gun_name": "M700狙击步枪", "weapon_type": "狙击步枪"},
                    {"id": 3, "gun_name": "M7战斗步枪", "weapon_type": "突击步枪"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_load_candidates_from_cache(tmp_path: Path) -> None:
    path = tmp_path / "guns_cache.json"
    _write_guns_cache(path)
    weapons, guns = load_candidates(path)
    assert weapons == ["狙击步枪", "突击步枪"]
    assert guns == ["M700狙击步枪", "M7战斗步枪"]


def test_load_candidates_missing_cache(tmp_path: Path) -> None:
    assert load_candidates(tmp_path / "nope.json") == ([], [])


def test_load_candidates_corrupt_cache(tmp_path: Path) -> None:
    path = tmp_path / "guns_cache.json"
    path.write_text("{bad", encoding="utf-8")
    assert load_candidates(path) == ([], [])


# ── 持久化 ───────────────────────────────────────────

def test_save_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "my_gun_codes.json"
    records = [
        {
            "id": "a",
            "name": "满改M7",
            "code": "M7战斗步枪-烽火地带-CODE",
            "description": "",
            "weapon": "M7战斗步枪",
            "weapon_type": "突击步枪",
            "created_at": "t",
            "updated_at": "t",
        }
    ]
    save_my_codes(records, path)
    assert json.loads(path.read_text(encoding="utf-8")) == {"codes": records}
    assert load_my_codes(path) == records


def test_load_missing_returns_empty(tmp_path: Path) -> None:
    assert load_my_codes(tmp_path / "nope.json") == []


def test_load_corrupt_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "my_gun_codes.json"
    path.write_text("{broken", encoding="utf-8")
    assert load_my_codes(path) == []


def test_load_non_list_codes_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "my_gun_codes.json"
    path.write_text(json.dumps({"codes": "oops"}), encoding="utf-8")
    assert load_my_codes(path) == []


def test_new_code_id_unique() -> None:
    assert len({new_code_id() for _ in range(100)}) == 100


# ── 页面交互 ─────────────────────────────────────────

@pytest.fixture()
def page(qapp, tmp_path: Path) -> MyCodesPage:
    """临时数据文件的页面（不污染 data/）。"""
    return MyCodesPage(
        I18nManager(),
        ThemeManager(),
        codes_path=tmp_path / "my_gun_codes.json",
        guns_cache_path=tmp_path / "guns_cache.json",
    )


def _add(
    page: MyCodesPage,
    name: str,
    code: str,
    desc: str = "",
    weapon: str = "",
    weapon_type: str = "",
) -> None:
    page.name_input.setText(name)
    page.code_input.setText(code)
    page.desc_input.setText(desc)
    page.weapon_combo.setEditText(weapon)
    page.weapon_type_combo.setEditText(weapon_type)
    page._save()


def _meta_text(card) -> str:
    from PySide6.QtWidgets import QLabel

    metas = [
        lbl for lbl in card.findChildren(QLabel) if lbl.objectName() == "gunMeta"
    ]
    assert metas, "卡片缺少 gunMeta 标签"
    return metas[0].text()


def test_add_renders_and_persists(page: MyCodesPage) -> None:
    _add(
        page,
        "满改M7",
        "M7战斗步枪-烽火地带-6ID3HD806QOMQD6J47QJA",
        "近战猛攻",
        "M7战斗步枪",
        "突击步枪",
    )
    assert len(page._records) == 1
    assert len(page._cards) == 1
    record = page._records[0]
    assert record["name"] == "满改M7"
    assert record["description"] == "近战猛攻"
    assert record["weapon"] == "M7战斗步枪"
    assert record["weapon_type"] == "突击步枪"
    # 持久化落盘
    assert len(load_my_codes(page._codes_path)) == 1


def test_card_meta_and_copy_style(page: MyCodesPage) -> None:
    """卡片显示「枪械名称 · 武器类型」，复制按钮与主播推荐同款 gunCopy 样式。"""
    _add(page, "满改M7", "M7战斗步枪-烽火地带-CODE1", weapon="M7战斗步枪", weapon_type="突击步枪")
    card = page._cards[0]
    assert card.copy_button.objectName() == "gunCopy"
    assert _meta_text(card) == "M7战斗步枪 · 突击步枪"


def test_card_meta_fallback_for_legacy_record(page: MyCodesPage) -> None:
    """旧记录（无 weapon 字段）以改枪码首段兜底显示枪名。"""
    _add(page, "旧记录", "M700狙击步枪-长弓溪谷-CODE2")
    assert _meta_text(page._cards[0]) == "M700狙击步枪"


def test_card_height_reduced(page: MyCodesPage) -> None:
    """省略图片/作者/改枪码区后卡片高度控制在紧凑范围。"""
    _add(page, "甲", "枪A-烽火地带-CODE1")
    assert CARD_HEIGHT <= 200


def test_add_requires_name_and_code(page: MyCodesPage) -> None:
    page.name_input.setText("")
    page.code_input.setText("X")
    page._save()
    assert page._records == []
    assert page.form_hint.text() == "命名与改枪码不能为空"
    page.name_input.setText("名字")
    page.code_input.setText("")
    page._save()
    assert page._records == []
    assert page.form_hint.text() == "命名与改枪码不能为空"


def test_edit_updates_record(page: MyCodesPage) -> None:
    _add(page, "旧名", "枪A-烽火地带-CODE1", "旧描述", "枪A", "突击步枪")
    record = page._records[0]
    page._start_edit(record)
    assert page.name_input.text() == "旧名"
    assert page.code_input.text() == "枪A-烽火地带-CODE1"
    page.name_input.setText("新名")
    page.desc_input.setText("新描述")
    page.weapon_type_combo.setEditText("狙击步枪")
    page._save()
    assert len(page._records) == 1
    record = page._records[0]
    assert record["name"] == "新名"
    assert record["description"] == "新描述"
    assert record["code"] == "枪A-烽火地带-CODE1"
    assert record["weapon_type"] == "狙击步枪"


def test_edit_backfills_legacy_fields(page: MyCodesPage) -> None:
    """旧记录（无 weapon/weapon_type）编辑保存后补齐字段。"""
    page._records = [
        {
            "id": "old",
            "name": "旧",
            "code": "M7战斗步枪-烽火地带-CODE9",
            "description": "",
            "created_at": "t",
            "updated_at": "t",
        }
    ]
    page._start_edit(page._records[0])
    assert page.weapon_combo.currentText() == ""
    page.weapon_combo.setEditText("M7战斗步枪")
    page._save()
    assert page._records[0]["weapon"] == "M7战斗步枪"


def test_delete_confirm_removes(page: MyCodesPage, monkeypatch) -> None:
    _add(page, "甲", "枪A-烽火地带-CODE1")
    _add(page, "乙", "枪B-烽火地带-CODE2")
    assert len(page._records) == 2

    class FakeBox:
        """模拟用户点击「删除」确认按钮。"""

        ButtonRole = type("ButtonRole", (), {"AcceptRole": 1, "RejectRole": 2})

        def __init__(self, *args, **kwargs) -> None:
            self._btn = object()

        def setWindowTitle(self, text) -> None:  # noqa: N802
            pass

        def setText(self, text) -> None:  # noqa: N802
            pass

        def addButton(self, text, role) -> object:  # noqa: N802
            return self._btn

        def exec(self) -> None:  # noqa: A003
            pass

        def clickedButton(self) -> object:  # noqa: N802
            return self._btn

    monkeypatch.setattr("deltaforcebox.widgets.pages.my_codes_page.QMessageBox", FakeBox)
    page._confirm_delete(page._records[0])
    assert len(page._records) == 1
    assert page._records[0]["name"] == "乙"
    assert len(load_my_codes(page._codes_path)) == 1


def test_copy_button_writes_clipboard(page: MyCodesPage, qapp) -> None:
    from PySide6.QtWidgets import QApplication

    _add(page, "满改M7", "M7战斗步枪-烽火地带-6ID3HD806QOMQD6J47QJA")
    page._cards[0]._copy()
    assert QApplication.clipboard().text() == "M7战斗步枪-烽火地带-6ID3HD806QOMQD6J47QJA"


def test_filter_by_gun_and_weapon(qapp, tmp_path: Path) -> None:
    """筛选需要候选下拉有对应选项：本测试注入带候选的缓存。"""
    cache = tmp_path / "guns_cache.json"
    _write_guns_cache(cache)
    page = MyCodesPage(
        I18nManager(),
        ThemeManager(),
        codes_path=tmp_path / "my_gun_codes.json",
        guns_cache_path=cache,
    )
    _add(page, "甲", "枪A-烽火地带-CODE1", weapon="M7战斗步枪", weapon_type="突击步枪")
    _add(page, "乙", "枪B-长弓溪谷-CODE2", weapon="M700狙击步枪", weapon_type="狙击步枪")
    _add(page, "丙", "枪C-零号大坝-CODE3", weapon="M7战斗步枪", weapon_type="突击步枪")
    assert len(page._cards) == 3

    # 按枪械筛选
    page.filter_gun_combo.setCurrentIndex(
        page.filter_gun_combo.findData("M7战斗步枪")
    )
    assert len(page._cards) == 2
    # 叠加武器类型筛选
    page.filter_weapon_combo.setCurrentIndex(
        page.filter_weapon_combo.findData("狙击步枪")
    )
    assert len(page._cards) == 0
    assert page.empty_label.text() == "没有符合筛选条件的改枪码"
    # 全部重置恢复
    page._reset_filters()
    assert len(page._cards) == 3


def test_filter_candidates_from_guns_cache(qapp, tmp_path: Path) -> None:
    """筛选框候选与主播推荐一致（来自 guns_cache.json 去重排序）。"""
    cache = tmp_path / "guns_cache.json"
    _write_guns_cache(cache)
    page = MyCodesPage(
        I18nManager(),
        ThemeManager(),
        codes_path=tmp_path / "my_gun_codes.json",
        guns_cache_path=cache,
    )
    gun_items = [
        page.filter_gun_combo.itemText(i) for i in range(page.filter_gun_combo.count())
    ]
    weapon_items = [
        page.filter_weapon_combo.itemText(i)
        for i in range(page.filter_weapon_combo.count())
    ]
    assert gun_items == ["全部", "M700狙击步枪", "M7战斗步枪"]
    assert weapon_items == ["全部", "狙击步枪", "突击步枪"]


def test_empty_state_and_count(page: MyCodesPage) -> None:
    assert page.empty_label.isVisibleTo(page)
    assert page.status_label.text() == "共 0 条"
    _add(page, "甲", "枪A-烽火地带-CODE1")
    assert not page.empty_label.isVisibleTo(page)
    assert page.status_label.text() == "共 1 条"


def test_sidebar_and_pages_registered(qapp, tmp_path: Path) -> None:
    """构建应用后「我的改枪码」在侧栏与页面字典中注册。"""
    from deltaforcebox.app import build_app

    _app, window = build_app(
        settings_path=tmp_path / "settings.json",
        config_path=tmp_path / "config.json",
    )
    assert "my_codes" in window.pages
    assert window.pages["my_codes"].title_label.text() == "我的改枪码"
    # 侧栏存在对应条目
    assert window._find_item_by_key("my_codes") is not None

def test_filter_by_input_contains(page: MyCodesPage) -> None:
    """筛选框输入支持包含匹配（Beta-4.1）。"""
    _add(page, "甲", "枪A-烽火地带-CODE1", weapon="M7战斗步枪", weapon_type="突击步枪")
    _add(page, "乙", "枪B-长弓溪谷-CODE2", weapon="K416突击步枪", weapon_type="狙击步枪")
    page.filter_gun_combo.setEditText("M7战")
    assert len(page._cards) == 1
    page.filter_gun_combo.setEditText("")
    page.filter_weapon_combo.setEditText("狙")
    assert len(page._cards) == 1
    page.filter_weapon_combo.setEditText("")
    assert len(page._cards) == 2


def test_no_description_placeholder(page: MyCodesPage) -> None:
    """未填写描述时卡片显示「暂无详细介绍」（Beta-4.1）。"""
    from PySide6.QtWidgets import QLabel

    _add(page, "无描述", "枪A-烽火地带-CODE1")
    descs = [
        lbl for lbl in page._cards[0].findChildren(QLabel) if lbl.objectName() == "gunDesc"
    ]
    assert descs and descs[0].text() == "暂无详细介绍"
    _add(page, "有描述", "枪B-烽火地带-CODE2", "详细说明")
    descs = [
        lbl for lbl in page._cards[1].findChildren(QLabel) if lbl.objectName() == "gunDesc"
    ]
    assert descs and descs[0].text() == "详细说明"


def test_delete_button_red_style(page: MyCodesPage) -> None:
    """删除按钮使用红色样式 objectName myCodeDelete（Beta-4.1）。"""
    from PySide6.QtWidgets import QPushButton

    _add(page, "甲", "枪A-烽火地带-CODE1")
    btns = [
        b
        for b in page._cards[0].findChildren(QPushButton)
        if b.objectName() == "myCodeDelete"
    ]
    assert btns and btns[0].text() == "删除"


def test_filter_labels_shown(page: MyCodesPage) -> None:
    """筛选框补齐文字提示（Beta-4.1）。"""
    assert page.filter_gun_label.text() == "枪械名称"
    assert page.filter_weapon_label.text() == "武器类型"
