"""我的改枪码页面：本地收藏主播之外的个人改枪码（鼠鼠工具 → 改枪码 → 我的改枪码）。

- 输入：命名（必填）+ 改枪码（必填，粘贴游戏内复制）+ 描述（可选）；
- 展示：类主播推荐卡片（无图、无作者、无价格），可复制、修改、删除；
- 持久化：data/my_gun_codes.json（缺失/损坏回退空列表）。
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core.i18n import I18nManager
from ...core.my_codes import load_my_codes, new_code_id, parse_gun_code, save_my_codes
from ...core.theme import ThemeManager
from ..flow_layout import FlowLayout

# 卡片与网格（宽度随视口自适应伸缩，高度固定保证等高）
CARD_WIDTH = 260
CARD_HEIGHT = 250
MIN_CARD_WIDTH = 220
MAX_CARD_WIDTH = 300
GRID_PADDING = 12
CODE_AREA_HEIGHT = 64
DESC_AREA_HEIGHT = 64


class MyCodeCard(QFrame):
    """我的改枪码卡片：命名 + 枪械·地图 + 完整改枪码（可复制）+ 描述 + 修改/删除。"""

    def __init__(
        self,
        record: dict,
        texts: dict[str, str],
        on_edit: object,
        on_delete: object,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("gunCard")
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self._record = record
        self._texts = texts
        self._copy_orig_text = texts["copy"]

        box = QVBoxLayout(self)
        box.setContentsMargins(12, 8, 12, 8)
        box.setSpacing(4)

        # 命名
        title = QLabel(record.get("name") or "")
        title.setObjectName("gunTitle")
        title.setWordWrap(True)
        box.addWidget(title)

        # 枪械 · 地图（解析自改枪码）
        gun_name, map_name, _ = parse_gun_code(record.get("code") or "")
        meta = " · ".join(x for x in (gun_name, map_name) if x)
        meta_label = QLabel(meta or "—")
        meta_label.setObjectName("gunMeta")
        meta_label.setWordWrap(True)
        box.addWidget(meta_label)

        # 完整改枪码（等宽、内部滚动）+ 复制按钮
        code_row = QHBoxLayout()
        code_row.setSpacing(6)
        code_scroll = QScrollArea()
        code_scroll.setObjectName("gunDescScroll")
        code_scroll.setWidgetResizable(True)
        code_scroll.setFrameShape(QFrame.Shape.NoFrame)
        code_scroll.setFixedHeight(CODE_AREA_HEIGHT)
        code_inner = QLabel()
        code_inner.setObjectName("myCodeText")
        code_inner.setWordWrap(True)
        code_inner.setText(record.get("code") or "")
        code_scroll.setWidget(code_inner)
        code_row.addWidget(code_scroll, 1)
        self.copy_button = QPushButton(texts["copy"])
        self.copy_button.setObjectName("gunCopy")
        self.copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        code_row.addWidget(self.copy_button)
        box.addLayout(code_row)
        self.copy_button.clicked.connect(self._copy)

        # 描述（可选，固定高度滚动区保持卡片等高）
        desc_scroll = QScrollArea()
        desc_scroll.setObjectName("gunDescScroll")
        desc_scroll.setWidgetResizable(True)
        desc_scroll.setFrameShape(QFrame.Shape.NoFrame)
        desc_scroll.setFixedHeight(DESC_AREA_HEIGHT)
        desc_inner = QLabel()
        desc_inner.setObjectName("gunDesc")
        desc_inner.setWordWrap(True)
        desc_inner.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        desc_inner.setText(record.get("description") or "")
        desc_scroll.setWidget(desc_inner)
        box.addWidget(desc_scroll)

        # 操作行：修改 / 删除
        actions = QHBoxLayout()
        actions.setSpacing(6)
        edit_btn = QPushButton(texts["edit"])
        edit_btn.setObjectName("gunPagerBtn")
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.clicked.connect(lambda: on_edit(self._record))
        actions.addWidget(edit_btn)
        delete_btn = QPushButton(texts["delete"])
        delete_btn.setObjectName("gunPagerBtn")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.clicked.connect(lambda: on_delete(self._record))
        actions.addWidget(delete_btn)
        actions.addStretch(1)
        box.addLayout(actions)

    def _copy(self) -> None:
        QApplication.clipboard().setText(self._record.get("code") or "")
        self.copy_button.setText(self._texts["copied"])
        QTimer.singleShot(1500, lambda: self.copy_button.setText(self._copy_orig_text))


class MyCodesPage(QWidget):
    """我的改枪码页面。"""

    def __init__(
        self,
        i18n: I18nManager,
        theme: ThemeManager,
        codes_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._i18n = i18n
        self._theme = theme
        self._codes_path = codes_path
        self._records = load_my_codes(codes_path)
        self._cards: list[MyCodeCard] = []
        self._editing_id: str | None = None
        self._card_w = CARD_WIDTH

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)

        # 标题行 + 添加按钮
        head = QHBoxLayout()
        self.title_label = QLabel()
        font = self.title_label.font()
        font.setPointSize(15)
        font.setBold(True)
        self.title_label.setFont(font)
        head.addWidget(self.title_label)
        head.addStretch(1)
        self.add_btn = QPushButton()
        self.add_btn.setObjectName("gunPagerBtn")
        self.add_btn.clicked.connect(self._toggle_form)
        head.addWidget(self.add_btn)
        root.addLayout(head)

        self.status_label = QLabel()
        self.status_label.setObjectName("hint")
        root.addWidget(self.status_label)

        # 编辑表单（默认隐藏）：命名 / 改枪码 / 描述
        self.form = QWidget()
        form = QVBoxLayout(self.form)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.name_label = QLabel()
        self.name_label.setObjectName("gunFilterLabel")
        row1.addWidget(self.name_label)
        self.name_input = QLineEdit()
        self.name_input.setObjectName("myCodeInput")
        row1.addWidget(self.name_input, 1)
        self.code_label = QLabel()
        self.code_label.setObjectName("gunFilterLabel")
        row1.addWidget(self.code_label)
        self.code_input = QLineEdit()
        self.code_input.setObjectName("myCodeInput")
        row1.addWidget(self.code_input, 2)
        form.addLayout(row1)

        desc_row = QHBoxLayout()
        desc_row.setSpacing(8)
        self.desc_label = QLabel()
        self.desc_label.setObjectName("gunFilterLabel")
        desc_row.addWidget(self.desc_label)
        self.desc_input = QLineEdit()
        self.desc_input.setObjectName("myCodeInput")
        desc_row.addWidget(self.desc_input, 1)
        form.addLayout(desc_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.save_btn = QPushButton()
        self.save_btn.setObjectName("gunPagerBtn")
        self.save_btn.clicked.connect(self._save)
        btn_row.addWidget(self.save_btn)
        self.cancel_btn = QPushButton()
        self.cancel_btn.setObjectName("gunPagerBtn")
        self.cancel_btn.clicked.connect(lambda: self.form.hide())
        btn_row.addWidget(self.cancel_btn)
        self.form_hint = QLabel()
        self.form_hint.setObjectName("hint")
        btn_row.addWidget(self.form_hint, 1)
        form.addLayout(btn_row)
        self.form.hide()
        root.addWidget(self.form)

        self.empty_label = QLabel()
        self.empty_label.setObjectName("hint")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty_label)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("gunList")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._flow_host = QWidget()
        self._flow_host.setObjectName("gunFlowHost")
        self._flow = FlowLayout(self._flow_host, spacing=GRID_PADDING)
        self.scroll.setWidget(self._flow_host)
        root.addWidget(self.scroll, 1)

        self.scroll.installEventFilter(self)
        self.retranslate()
        self._render()

    # ── 卡片宽度自适应（同改枪码页） ─────────────────

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt 命名
        if obj is self.scroll and event.type() == QEvent.Type.Resize:
            self._reflow()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().resizeEvent(event)
        QTimer.singleShot(0, self._reflow)

    def _reflow(self) -> None:
        avail = self.scroll.viewport().width()
        if avail <= 0 or not self._cards:
            return
        lead = 4
        max_cols = max(1, (avail - lead) // (MIN_CARD_WIDTH + GRID_PADDING))
        max_cols = min(max_cols, len(self._cards))
        cols = 1
        for c in range(max_cols, 0, -1):
            w = min((avail - lead) // c - GRID_PADDING, MAX_CARD_WIDTH)
            if c * w + GRID_PADDING * (c - 1) <= avail - lead:
                cols = c
                break
        width = min(max((avail - lead) // cols - GRID_PADDING, MIN_CARD_WIDTH), MAX_CARD_WIDTH)
        if width == self._card_w:
            return
        self._card_w = width
        for card in self._cards:
            card.setFixedWidth(width)
        self._flow.invalidate()
        self._flow_host.updateGeometry()

    # ── 交互 ─────────────────────────────────────────

    def _toggle_form(self) -> None:
        """添加模式：清空表单并展开。"""
        self._editing_id = None
        for widget in (self.name_input, self.code_input, self.desc_input):
            widget.clear()
        self.form_hint.clear()
        self.form.show()
        self.name_input.setFocus()

    def _save(self) -> None:
        name = self.name_input.text().strip()
        code = self.code_input.text().strip()
        if not name or not code:
            self.form_hint.setText(self._i18n.t("mycodes.required"))
            return
        desc = self.desc_input.text().strip()
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        if self._editing_id is not None:
            for record in self._records:
                if record.get("id") == self._editing_id:
                    record.update(name=name, code=code, description=desc, updated_at=now)
                    break
        else:
            self._records.append(
                {
                    "id": new_code_id(),
                    "name": name,
                    "code": code,
                    "description": desc,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        save_my_codes(self._records, self._codes_path)
        self.form.hide()
        self._render()

    def _start_edit(self, record: dict) -> None:
        """修改模式：表单预填该条。"""
        self._editing_id = record.get("id")
        self.name_input.setText(record.get("name") or "")
        self.code_input.setText(record.get("code") or "")
        self.desc_input.setText(record.get("description") or "")
        self.form_hint.clear()
        self.form.show()
        self.name_input.setFocus()

    def _confirm_delete(self, record: dict) -> None:
        title = record.get("name") or record.get("code") or ""
        box = QMessageBox(self)
        box.setWindowTitle(self._i18n.t("mycodes.delete"))
        box.setText(self._i18n.t("mycodes.delete_confirm").replace("%1", title))
        yes = box.addButton(self._i18n.t("mycodes.delete_yes"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(self._i18n.t("mycodes.delete_no"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not yes:
            return
        self._records = [r for r in self._records if r.get("id") != record.get("id")]
        save_my_codes(self._records, self._codes_path)
        self._render()

    # ── 渲染 ─────────────────────────────────────────

    def _card_texts(self) -> dict[str, str]:
        return {
            "copy": self._i18n.t("mycodes.copy"),
            "copied": self._i18n.t("mycodes.copied"),
            "edit": self._i18n.t("mycodes.edit"),
            "delete": self._i18n.t("mycodes.delete"),
        }

    def _render(self) -> None:
        while self._flow.count():
            item = self._flow.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._cards = []
        for record in self._records:
            card = MyCodeCard(
                record,
                self._card_texts(),
                on_edit=self._start_edit,
                on_delete=self._confirm_delete,
            )
            card.setFixedSize(self._card_w, CARD_HEIGHT)
            self._cards.append(card)
            self._flow.addWidget(card)
        self.status_label.setText(
            self._i18n.t("mycodes.count").replace("%1", str(len(self._records)))
        )
        self.empty_label.setVisible(len(self._records) == 0)
        self._flow.invalidate()
        self._flow_host.updateGeometry()

    def retranslate(self) -> None:
        self.title_label.setText(self._i18n.t("mycodes.title"))
        self.add_btn.setText(self._i18n.t("mycodes.add"))
        self.name_label.setText(self._i18n.t("mycodes.name"))
        self.code_label.setText(self._i18n.t("mycodes.code"))
        self.desc_label.setText(self._i18n.t("mycodes.desc"))
        self.name_input.setPlaceholderText(self._i18n.t("mycodes.name_placeholder"))
        self.code_input.setPlaceholderText(self._i18n.t("mycodes.code_placeholder"))
        self.desc_input.setPlaceholderText(self._i18n.t("mycodes.desc_placeholder"))
        self.save_btn.setText(self._i18n.t("mycodes.save"))
        self.cancel_btn.setText(self._i18n.t("mycodes.cancel"))
        self.empty_label.setText(self._i18n.t("mycodes.empty"))
        if self._cards:
            self._render()
