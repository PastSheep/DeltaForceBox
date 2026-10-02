"""首页右上角提示条：面向用户的非弹窗提示（更新就绪 / 下载进度 / 失败等）。

- 常驻于页面右上角，可整体显示/隐藏；
- 支持一条动作按钮（如「运行安装包」「立即下载」），回调由调用方注入；
- 支持可选关闭按钮（自动隐藏本提示）；
- 样式走 QSS（objectName: noticeBar），明暗主题适配。
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

ACTION_STYLE = """
QPushButton {
    background: transparent;
    border: none;
    color: #4d8ff7;
    font-weight: bold;
    padding: 0 4px;
}
QPushButton:hover { text-decoration: underline; }
"""


class NoticeBar(QFrame):
    """右上角提示条。

    用法：
        bar.show_notice("更新已就绪：Beta-4.3", action_text="运行安装包",
                        on_action=run_installer)
        bar.show_progress("正在下载更新…", 42, 168)
        bar.hide_notice()
    """

    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("noticeBar")
        self._on_action: Callable[[], None] | None = None
        self._on_close: Callable[[], None] | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setObjectName("noticeMessage")

        self.action_button = QPushButton()
        self.action_button.setObjectName("noticeAction")
        self.action_button.setStyleSheet(ACTION_STYLE)
        self.action_button.clicked.connect(self._trigger_action)

        self.close_button = QPushButton("×")
        self.close_button.setObjectName("noticeClose")
        self.close_button.setFixedSize(18, 18)
        self.close_button.clicked.connect(self._trigger_close)

        layout.addWidget(self.message_label, 1)
        layout.addWidget(self.action_button)
        layout.addWidget(self.close_button)

        self.hide_notice()

    def _trigger_action(self) -> None:
        if self._on_action is not None:
            self._on_action()

    def _trigger_close(self) -> None:
        if self._on_close is not None:
            self._on_close()
        self.hide_notice()
        self.dismissed.emit()

    def show_notice(
        self,
        text: str,
        action_text: str | None = None,
        on_action: Callable[[], None] | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        """显示提示：文本 + 可选动作按钮 + 可选关闭回调。"""
        self.message_label.setText(text)
        self._on_action = on_action
        self._on_close = on_close
        if action_text and on_action is not None:
            self.action_button.setText(action_text)
            self.action_button.show()
        else:
            self.action_button.hide()
        self.show()

    def show_progress(self, text: str, done: int, total: int) -> None:
        """显示下载进度（total<=0 时只显示文本）。"""
        if total > 0:
            percent = max(0, min(100, int(done * 100 / total)))
            self.show_notice(f"{text}（{percent}%）")
        else:
            self.show_notice(text)

    def hide_notice(self) -> None:
        self._on_action = None
        self._on_close = None
        self.hide()
