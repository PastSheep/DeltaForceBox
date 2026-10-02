"""可输入筛选下拉：保持下拉候选之外新增输入功能。

- `editable` + `NoInsert`：允许输入任意文本，但输入不会固化进候选列表；
- `QCompleter` 包含匹配（大小写不敏感）：输入时弹层候选即时按输入过滤；
- 无条件两种表达：空白输入，或点选候选顶部「全部」文本项（内部一律视为无条件）；
- 输入框提示：非焦点且无筛选条件时显示「全部」文本，便于理解当前为无条件；
- 点击输入框 / 获得焦点：展开全量候选（点击同时清空输入，便于直接输入）；
- `set_items()`：候选顶部固定「全部」文本项，重建时保留当前输入文本。
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QComboBox, QCompleter, QWidget


class SearchCombo(QComboBox):
    """可输入、可下拉、输入即过滤的筛选下拉框（空白/「全部」=无条件）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        completer = self.completer()
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        # 点击输入框区域的事件由 lineEdit 自身消费，QComboBox 收不到；
        # 通过事件过滤器拦截左键点击与焦点变化。
        self.lineEdit().installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt 命名
        """拦截输入框左键点击 / 焦点变化：点击清空并弹出全量候选。

        - 左键点击：清空输入（触发筛选恢复无条件）并展开全量候选；
        - FocusIn：展开全量候选（保留当前文本，不打断已有筛选）；
        - FocusOut：无筛选条件时恢复「全部」提示文本。
        """
        if obj is self.lineEdit():
            t = event.type()
            if t == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.lineEdit().setText("")
                    self.showPopup()
                return False  # 交还 lineEdit 默认处理（聚焦/光标）
            if t == QEvent.Type.FocusIn:
                if not self.filter_text():
                    self.lineEdit().setText("")  # 无条件提示 -> 清空准备输入
                self.showPopup()
                return False
            if t == QEvent.Type.FocusOut:
                if not self.filter_text():
                    edit = self.lineEdit()
                    edit.blockSignals(True)
                    edit.setText(self.itemText(0) if self.count() else "")
                    edit.blockSignals(False)
                return False
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """点击下拉按键区域（若样式保留）：同样清空输入并展开全量候选。"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.lineEdit().setText("")
            self.showPopup()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """左键释放不交给默认处理：防止点击后弹层被 Qt 默认逻辑立即收起。"""
        if event.button() == Qt.MouseButton.LeftButton:
            return
        super().mouseReleaseEvent(event)

    def set_items(self, items: list[str], all_text: str, preserve: bool = True) -> None:
        """重建候选列表：顶部「全部」文本项 + 候选。

        - `preserve=True`（联动重建）：保留当前输入文本，输入不丢失；
        - `preserve=False`（首次/重置填充）：显示「全部」（非焦点+无条件提示）。
        重建期间屏蔽信号，由调用方决定是否触发后续筛选。
        """
        current = self.currentText() if preserve else all_text
        edit = self.lineEdit()
        self.blockSignals(True)
        edit.blockSignals(True)
        self.clear()
        self.addItem(all_text, "")  # 「全部」仅文本显示，内部视为无条件
        for name in items:
            self.addItem(name, name)
        self.setEditText(current)
        edit.blockSignals(False)
        self.blockSignals(False)

    def filter_text(self) -> str:
        """当前筛选条件文本：空白或「全部」项视为无条件（返回空串）。"""
        text = self.currentText().strip()
        if not text or text == self.itemText(0):
            return ""
        return text

    def reset(self) -> None:
        """清空筛选条件，显示「全部」（非焦点+无条件提示；内部仍无条件）。"""
        self.setEditText(self.itemText(0) if self.count() else "")
