"""我的改枪码测试：解析规则 / 持久化 / 页面增删改查。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deltaforcebox.core.i18n import I18nManager
from deltaforcebox.core.my_codes import (
    load_my_codes,
    new_code_id,
    parse_gun_code,
    save_my_codes,
)
from deltaforcebox.core.theme import ThemeManager
from deltaforcebox.widgets.pages.my_codes_page import MyCodesPage

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
    assert parse_gun_code("枪A--烽火地带") == ("枪A", "", "烽火地带")


# ── 持久化 ───────────────────────────────────────────

def test_save_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "my_gun_codes.json"
    records = [
        {
            "id": "a",
            "name": "满改M7",
            "code": "M7战斗步枪-烽火地带-CODE",
            "description": "",
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
    )


def _add(page: MyCodesPage, name: str, code: str, desc: str = "") -> None:
    page.name_input.setText(name)
    page.code_input.setText(code)
    page.desc_input.setText(desc)
    page._save()


def test_add_renders_and_persists(page: MyCodesPage) -> None:
    _add(page, "满改M7", "M7战斗步枪-烽火地带-6ID3HD806QOMQD6J47QJA", "近战猛攻")
    assert len(page._records) == 1
    assert len(page._cards) == 1
    assert page._records[0]["name"] == "满改M7"
    assert page._records[0]["description"] == "近战猛攻"
    # 持久化落盘
    assert len(load_my_codes(page._codes_path)) == 1
    # 卡片内容：命名 + 枪械·地图
    assert page._cards[0].findChildren(type(page._cards[0].children()[0]))  # 结构存在即可


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
    _add(page, "旧名", "枪A-烽火地带-CODE1", "旧描述")
    record = page._records[0]
    page._start_edit(record)
    assert page.name_input.text() == "旧名"
    assert page.code_input.text() == "枪A-烽火地带-CODE1"
    page.name_input.setText("新名")
    page.desc_input.setText("新描述")
    page._save()
    assert len(page._records) == 1
    assert page._records[0]["name"] == "新名"
    assert page._records[0]["description"] == "新描述"
    assert page._records[0]["code"] == "枪A-烽火地带-CODE1"


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
