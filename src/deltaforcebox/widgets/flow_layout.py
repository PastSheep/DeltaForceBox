"""通用流式布局：按可用宽度换行放置等尺寸卡片。

行为确定、无 Qt 网格黑盒取整：卡片尺寸由外部统一控制
（调用方在 reflow 中 setFixedWidth），本类只负责逐行放置与换行，
行间距 = spacing。
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QWidgetItem


class FlowLayout(QLayout):
    def __init__(self, parent=None, spacing: int = 0) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self._spacing = spacing
        self._items: list[QWidgetItem] = []

    def addItem(self, item: QWidgetItem) -> None:  # noqa: N802 - Qt 命名
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i: int) -> QWidgetItem | None:  # noqa: N802 - Qt 命名
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i: int) -> QWidgetItem | None:  # noqa: N802 - Qt 命名
        if 0 <= i < len(self._items):
            return self._items.pop(i)
        return None

    def expandingDirections(self) -> Qt.Orientations:
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(width, test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - Qt 命名
        super().setGeometry(rect)
        self._do_layout(rect.width(), test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt 命名
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802 - Qt 命名
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, width: int, test_only: bool) -> int:
        m = self.contentsMargins()
        eff_width = width - m.left() - m.right()
        x, y = m.left(), m.top()
        row_h = 0
        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > m.left() + eff_width and x > m.left():
                x = m.left()
                y += row_h + self._spacing
                row_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            row_h = max(row_h, hint.height())
        return y + row_h + m.bottom()
