"""骇爪美图「图片来源与作者」窗口。

读取 resources/images/puzzle/manifest.json，以表格展示每张图片的
缩略图、文件名、作者与来源 URL；缩略图用 QImageReader 按需解码
（缩放 + 居中裁剪为正方形），避免一次性加载 75 张大图。
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ...core.i18n import I18nManager
from .image_source import load_manifest

THUMB_SIZE = 56  # 缩略图边长（正方形）
COL_THUMB, COL_FILE, COL_AUTHOR, COL_URL = 0, 1, 2, 3


def _load_thumb(path: str, size: int) -> QIcon:
    """高效生成正方形缩略图：缩放 + 居中裁剪，不解码原图全尺寸。"""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    src = reader.size()
    if src.isEmpty() or src.width() <= 0 or src.height() <= 0:
        return QIcon()
    factor = max(size / src.width(), size / src.height())
    reader.setScaledSize(QSize(round(src.width() * factor), round(src.height() * factor)))
    side = size / factor
    x = max(0.0, (src.width() - side) / 2.0)
    y = max(0.0, (src.height() - side) / 2.0)
    reader.setScaledClipRect(QRect(round(x), round(y), round(side), round(side)))
    img = reader.read()
    if img.isNull():
        return QIcon()
    return QIcon(QPixmap.fromImage(img))


class SourceDialog(QDialog):
    """展示 manifest.json 中全部图片来源与作者的窗口。"""

    def __init__(self, i18n: I18nManager, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.t("puzzle.sources.title"))
        self.setMinimumSize(760, 500)
        self.resize(880, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        # 顶部：标题 + 图片总数
        header = QHBoxLayout()
        title = QLabel()
        title.setObjectName("pageTitle")
        font = title.font()
        font.setPointSize(15)
        font.setBold(True)
        title.setFont(font)
        self.count_label = QLabel()
        self.count_label.setObjectName("hint")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.count_label)
        root.addLayout(header)

        # 表格：缩略图 / 文件名 / 作者 / 来源
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            [
                "",
                i18n.t("puzzle.sources.file"),
                i18n.t("puzzle.sources.author"),
                i18n.t("puzzle.sources.url"),
            ]
        )
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(COL_THUMB, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(COL_THUMB, THUMB_SIZE + 12)
        header_view.setSectionResizeMode(COL_FILE, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(COL_AUTHOR, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(COL_URL, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionsClickable(True)
        root.addWidget(self.table, 1)

        # 底部：关闭按钮
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        close_btn = QPushButton(i18n.t("common.close"))
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        root.addLayout(bottom)

        self._populate(i18n)

    def _populate(self, i18n: I18nManager) -> None:
        try:
            images = load_manifest()
        except (OSError, ValueError) as exc:
            self.count_label.setText(f"加载失败：{exc}")
            return

        self.count_label.setText(i18n.t("puzzle.sources.count", len(images)))
        app = QApplication.instance()
        if app is not None:
            app.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.table.setSortingEnabled(False)  # 填充期间关闭排序避免行错位
            self.table.setRowCount(len(images))
            for row, image in enumerate(images):
                thumb_item = QTableWidgetItem()
                thumb_item.setIcon(_load_thumb(str(image.path), THUMB_SIZE))
                thumb_item.setToolTip(image.path.name)
                thumb_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                file_item = QTableWidgetItem(image.path.name)
                file_item.setToolTip(str(image.path))
                author_item = QTableWidgetItem(image.author)
                url_item = QTableWidgetItem(image.author_url or "")
                url_item.setToolTip(image.author_url or "")
                for col, item in enumerate(
                    (thumb_item, file_item, author_item, url_item)
                ):
                    self.table.setItem(row, col, item)
            self.table.setSortingEnabled(True)
        finally:
            if app is not None:
                app.restoreOverrideCursor()
