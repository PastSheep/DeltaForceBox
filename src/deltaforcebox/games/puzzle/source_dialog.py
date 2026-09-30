"""骇爪美图「图片来源与作者」窗口。

以卡片网格展示 manifest.json 中每张图片：缩略图 + 作者 + 来源 URL，
底部「打开文件位置」按钮直接打开图片所在文件夹（所有图在同一目录）。
缩略图来自磁盘缓存（data/thumbnails/），首次生成后秒开。
"""

from __future__ import annotations

import subprocess
import sys

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from ...core.i18n import I18nManager
from ...core.thumbs import cached_thumbnail
from .image_source import PUZZLE_IMAGES_DIR, PuzzleImage, load_manifest

CARD_WIDTH = 190      # 卡片整体宽度
CARD_HEIGHT = 230     # 卡片整体高度
THUMB_SIZE = 144      # 缩略图边长（正方形）
GRID_PADDING = 8      # 卡片间距


def open_in_explorer(path: str) -> None:
    """在文件管理器中打开指定路径（文件则定位选中，目录则打开）。"""
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", f"/select,{path}"])
        else:
            subprocess.Popen(["xdg-open", str(__import__("pathlib").Path(path).parent)])
    except OSError:
        pass


def _elided(text: str, width: int, middle: bool = False) -> str:
    """按宽度省略文本（URL 用中间省略，作者用尾部省略）。"""
    mode = Qt.TextElideMode.ElideMiddle if middle else Qt.TextElideMode.ElideRight
    return QFontMetrics(QLabel().font()).elidedText(text, mode, width)


class SourceCard(QFrame):
    """单张图片来源卡片：缩略图 + 作者 + URL。"""

    def __init__(
        self,
        image: PuzzleImage,
        i18n: I18nManager,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("sourceCard")
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self.thumb_label = QLabel()
        self.thumb_label.setObjectName("sourceThumb")
        self.thumb_label.setFixedSize(THUMB_SIZE, THUMB_SIZE)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setToolTip(image.path.name)
        pm = cached_thumbnail(image.path, THUMB_SIZE)
        if pm is not None:
            self.thumb_label.setPixmap(pm)
        else:
            self.thumb_label.setText("?")

        self.author_label = QLabel()
        self.author_label.setObjectName("sourceAuthor")
        author_text = f"{i18n.t('puzzle.sources.author')}：{image.author}"
        self.author_label.setText(_elided(author_text, CARD_WIDTH - 32))
        self.author_label.setToolTip(image.author)

        self.url_label = QLabel()
        self.url_label.setObjectName("sourceUrl")
        url_text = image.author_url or "—"
        self.url_label.setText(_elided(url_text, CARD_WIDTH - 32, middle=True))
        self.url_label.setToolTip(image.author_url or "")

        layout.addWidget(self.thumb_label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.author_label)
        layout.addWidget(self.url_label)
        layout.addStretch(1)


class SourceDialog(QDialog):
    """卡片网格展示 manifest.json 中全部图片来源与作者。"""

    def __init__(self, i18n: I18nManager, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.t("puzzle.sources.title"))
        self.setMinimumSize(680, 480)
        self.resize(900, 580)

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

        # 卡片网格：IconMode 列表自适应列数换行
        self.list = QListWidget()
        self.list.setObjectName("sourceList")
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setFlow(QListWidget.Flow.LeftToRight)
        self.list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list.setUniformItemSizes(True)
        self.list.setSpacing(GRID_PADDING)
        self.list.setGridSize(
            QSize(CARD_WIDTH + GRID_PADDING, CARD_HEIGHT + GRID_PADDING)
        )
        root.addWidget(self.list, 1)

        # 底部：打开文件位置（图片统一在同一个文件夹）+ 关闭
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.open_btn = QPushButton(i18n.t("puzzle.sources.open"))
        self.open_btn.setObjectName("ghost")
        self.open_btn.clicked.connect(
            lambda: open_in_explorer(str(PUZZLE_IMAGES_DIR))
        )
        close_btn = QPushButton(i18n.t("common.close"))
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(self.open_btn)
        bottom.addWidget(close_btn)
        root.addLayout(bottom)

        self._populate(i18n)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # 对话框标题栏配色跟随应用主题
        from ...core.windows import apply_title_bar_theme

        apply_title_bar_theme(self)

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
            for image in images:
                item = QListWidgetItem()
                item.setSizeHint(QSize(CARD_WIDTH, CARD_HEIGHT))
                self.list.addItem(item)
                self.list.setItemWidget(item, SourceCard(image, i18n))
        finally:
            if app is not None:
                app.restoreOverrideCursor()
