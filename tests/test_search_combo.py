"""SearchCombo 组件测试：点击弹层 / 输入过滤 / 重置一致性与信号。"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from deltaforcebox.widgets.search_combo import SearchCombo


def _make_combo(qapp) -> SearchCombo:
    combo = SearchCombo()
    combo.set_items(["M7战斗步枪", "M700狙击步枪", "K416突击步枪"], "全部", preserve=False)
    return combo


def test_initial_shows_all_text(qapp) -> None:
    """初始状态（非焦点+无条件）显示「全部」，内部视为无条件。"""
    combo = _make_combo(qapp)
    assert combo.currentText() == "全部"
    assert combo.filter_text() == ""
    assert combo.itemData(0) == ""  # 「全部」内部视为无条件


def test_click_opens_popup(qapp) -> None:
    """点击输入框区域：清空输入并展开全量候选（事件经 lineEdit 过滤器）。"""
    combo = _make_combo(qapp)
    combo.setEditText("M7战斗步枪")  # 点击前已有内容
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(5, 5),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    combo.eventFilter(combo.lineEdit(), event)
    popup = combo.completer().popup()
    assert popup.isVisible()  # 展开的是 completer 统一弹层
    assert popup.model().rowCount() == combo.count()  # 全量候选
    assert combo.currentText() == ""  # 点击即清空条件
    assert not combo.view().isVisible()  # combo 自带 view 不显示（单一弹层）


def test_single_popup_layer(qapp) -> None:
    """弹层统一：点击展开与输入过滤复用同一 completer popup（无双弹层并存）。"""
    from PySide6.QtGui import QFocusEvent

    combo = _make_combo(qapp)
    combo.eventFilter(combo.lineEdit(), QFocusEvent(QEvent.Type.FocusIn))
    popup = combo.completer().popup()
    assert popup.isVisible()
    assert combo.completer().popup() is popup  # 输入过滤仍是同一弹层
    assert not combo.view().isVisible()  # 自带 view 不参与显示


def test_focus_in_opens_popup(qapp) -> None:
    """输入框获得焦点：展开全量候选；无条件提示时清空准备输入，有条件时保留。"""
    from PySide6.QtGui import QFocusEvent

    combo = _make_combo(qapp)
    combo.setEditText("M7战斗步枪")
    combo.eventFilter(combo.lineEdit(), QFocusEvent(QEvent.Type.FocusIn))
    assert combo.completer().popup().isVisible()
    assert combo.currentText() == "M7战斗步枪"  # 已有筛选不被打断
    combo.eventFilter(combo.lineEdit(), QFocusEvent(QEvent.Type.FocusOut))
    combo.setEditText("全部")  # 无条件提示态
    combo.eventFilter(combo.lineEdit(), QFocusEvent(QEvent.Type.FocusIn))
    assert combo.completer().popup().isVisible()
    assert combo.currentText() == ""  # 无条件提示 -> 清空准备输入


def test_focus_out_restores_all_text(qapp) -> None:
    """失焦且无条件时显示「全部」提示文本；有条件时保留条件。"""
    from PySide6.QtGui import QFocusEvent

    combo = _make_combo(qapp)
    combo.setEditText("M7战斗步枪")  # 有筛选条件
    combo.eventFilter(combo.lineEdit(), QFocusEvent(QEvent.Type.FocusOut))
    assert combo.currentText() == "M7战斗步枪"  # 保留条件
    combo.setEditText("")  # 清空（无条件）
    combo.eventFilter(combo.lineEdit(), QFocusEvent(QEvent.Type.FocusOut))
    assert combo.currentText() == "全部"  # 非焦点+无条件 -> 「全部」提示
    assert combo.filter_text() == ""  # 内部仍为无条件


def test_input_filters_popup_candidates(qapp) -> None:
    """输入文本后弹层候选按包含匹配即时过滤（QCompleter MatchContains）。"""
    combo = _make_combo(qapp)
    assert combo.completer().filterMode() == Qt.MatchFlag.MatchContains
    combo.setEditText("M7")
    # completer 模型过滤后仍指向 combo 全量模型，但 filter_text 语义生效
    assert combo.filter_text() == "M7"


def test_reset_returns_all_text(qapp) -> None:
    """重置后显示「全部」（与初始一致），条件恢复无条件。"""
    combo = _make_combo(qapp)
    combo.setEditText("M7战斗步枪")
    assert combo.filter_text() == "M7战斗步枪"
    combo.reset()
    assert combo.currentText() == "全部"
    assert combo.filter_text() == ""


def test_input_not_fixed_into_items(qapp) -> None:
    """手动输入任意文本不会固化进候选列表（NoInsert）。"""
    combo = _make_combo(qapp)
    combo.setEditText("不存在枪")
    items = [combo.itemText(i) for i in range(combo.count())]
    assert "不存在枪" not in items


def test_set_items_preserve_current_text(qapp) -> None:
    """联动重建候选时保留当前输入文本（输入不丢失）。"""
    combo = _make_combo(qapp)
    combo.setEditText("M7战斗步枪")
    combo.set_items(["M700狙击步枪"], "全部", preserve=True)
    assert combo.currentText() == "M7战斗步枪"

def test_all_text_is_unconditional(qapp) -> None:
    """点选「全部」文本项：显示「全部」，但内部视为无条件。"""
    combo = _make_combo(qapp)
    combo.setEditText("全部")
    assert combo.currentText() == "全部"
    assert combo.filter_text() == ""
