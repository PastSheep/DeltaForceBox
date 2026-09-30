"""拼图单人模式页面：QGraphicsView 场景装配、开局、完成流程。

对应网页端 init() / checkSolved() / showAuthorInfo() 的桌面实现。
"""

from __future__ import annotations

import random

from PySide6.QtCore import (
    QEasingCurve,
    QElapsedTimer,
    QPointF,
    QRectF,
    Qt,
    QTimer,
)
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.i18n import I18nManager
from ...core.records import format_time, save_best_time
from ...core.theme import ThemeManager
from .grid import compute_grid_dynamic, create_knob_styles, create_knobs
from .image_source import (
    PuzzleImage,
    make_grid_texture,
    pick_random_image,
    texture_brush,
)
from .path_builder import build_piece_path
from .piece_item import SNAP_THRESHOLD, PieceItem
from .source_dialog import SourceDialog

# 与网页端一致的参数
TARGET_CELL = 18.0  # 桌面端单块目标尺寸
SCATTER_ROTATE_RANGE = 25.0  # 打散随机旋转 ±25°
KNOB_RADIUS_FACTOR = 0.18

# 范围框（画布底衬）颜色：深色主题深灰、浅色主题浅灰
BOARD_COLOR_DARK = QColor("#232730")
BOARD_COLOR_LIGHT = QColor("#dfe3ea")


class PuzzleView(QGraphicsView):
    """保持宽高比的拼图画布。"""

    def __init__(self, scene: QGraphicsScene, parent=None) -> None:
        super().__init__(scene, parent)
        self.setObjectName("puzzleView")
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def fit_board(self) -> None:
        if self.scene() is None or self.scene().sceneRect().isNull():
            return
        # 与网页端 90vw/90vh 的自适应语义一致：保持比例并留边距
        rect = self.scene().sceneRect().adjusted(-8, -8, 8, 8)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit_board()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.fit_board()


class PuzzlePage(QWidget):
    """侧边栏“拼图”页：单人拼图，体感对齐网页端。"""

    def __init__(
        self, i18n: I18nManager, theme: ThemeManager, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._i18n = i18n
        self._theme = theme

        self._scene = QGraphicsScene(self)
        self._pieces: list[PieceItem] = []
        self._board_rect = QRectF()
        self._board_item = None
        self._end_item: QGraphicsPixmapItem | None = None
        self._texture: QPixmap | None = None
        self._current_image: PuzzleImage | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(8)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel()
        self.title_label.setObjectName("pageTitle")
        title_font = self.title_label.font()
        title_font.setPointSize(16)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.sources_btn = QPushButton()
        self.sources_btn.setObjectName("puzzleSources")
        self.sources_btn.clicked.connect(self._open_sources)
        self.restart_btn = QPushButton()
        self.restart_btn.setObjectName("puzzleRestart")
        self.restart_btn.clicked.connect(self.start_new)
        self.timer_label = QLabel()
        self.timer_label.setObjectName("timer")
        self.timer_label.setText(format_time(0.0))
        controls.addWidget(self.title_label)
        controls.addStretch(1)
        controls.addWidget(self.timer_label)
        controls.addWidget(self.sources_btn)
        controls.addWidget(self.restart_btn)

        self.view = PuzzleView(self._scene)
        self.author_label = QLabel()
        self.author_label.setObjectName("puzzleAuthor")
        self.author_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        root.addLayout(controls)
        root.addWidget(self.view, 1)
        root.addWidget(self.author_label)

        theme.changed.connect(self._update_board_color)
        self._elapsed = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(100)  # 0.1s 刷新显示
        self._timer.timeout.connect(self._update_timer_label)
        self.retranslate()
        self.start_new()

    # ── 翻译 ──────────────────────────────────────────────

    def retranslate(self) -> None:
        self.title_label.setText(self._i18n.t("puzzle.title"))
        self.sources_btn.setText(self._i18n.t("puzzle.sources"))
        self.restart_btn.setText(self._i18n.t("puzzle.restart"))

    # ── 图片来源窗口 ───────────────────────────────────────

    def _open_sources(self) -> None:
        """弹出图片来源与作者窗口（非模态，不阻塞主窗口；重复点击复用实例）。"""
        dialog = getattr(self, "_sources_dialog", None)
        if dialog is not None and dialog.isVisible():
            dialog.raise_()
            dialog.activateWindow()
            return
        dialog = SourceDialog(self._i18n, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.finished.connect(lambda: self._on_sources_closed(dialog))
        self._sources_dialog = dialog
        dialog.show()

    def _on_sources_closed(self, dialog: SourceDialog) -> None:
        if getattr(self, "_sources_dialog", None) is dialog:
            self._sources_dialog = None

    # ── 开局 ──────────────────────────────────────────────

    def start_new(self) -> None:
        """随机选图并开局（与网页端 init() 一致）。"""
        self._scene.clear()
        self._pieces = []
        self._end_item = None
        self.author_label.setText("")
        self.author_label.hide()
        # 重置计时器：重新开局后从第一次拿起碎片重新计时
        self._timer.stop()
        self._elapsed.invalidate()
        self.timer_label.setText(format_time(0.0))

        try:
            image = pick_random_image()
            img_w, img_h = self._image_size(image)
            # 与网页端一致：先归一化到高=100 的 viewBox 比例，再计算网格
            h_base = 100.0
            w_base = (img_w / img_h) * h_base
            rows, cols, cell_w, cell_h = compute_grid_dynamic(w_base, h_base, TARGET_CELL)
            grid_w = cols * cell_w
            grid_h = rows * cell_h
            self._board_rect = QRectF(0, 0, grid_w, grid_h)
            self._scene.setSceneRect(self._board_rect)

            texture, unit_scale = make_grid_texture(image, grid_w, grid_h)
            self._texture = texture
            self._unit_scale = unit_scale
            self._current_image = image

            self._draw_board(grid_w, grid_h)
            h_knobs, v_knobs = create_knobs(rows, cols)
            h_styles, v_styles = create_knob_styles(rows, cols)
            knob_r = min(cell_w, cell_h) * KNOB_RADIUS_FACTOR

            for r in range(rows):
                for c in range(cols):
                    path = build_piece_path(
                        r, c, cell_w, cell_h, rows, cols,
                        h_knobs, v_knobs, h_styles, v_styles,
                    )
                    brush = texture_brush(texture, c, r, cell_w, cell_h, unit_scale)
                    origin = QPointF(c * cell_w, r * cell_h)
                    target = origin
                    piece = PieceItem(path, brush, target, origin=origin)
                    piece.released.connect(self._on_piece_released)
                    piece.picked.connect(self._on_piece_picked)
                    self._scene.addItem(piece)
                    self._pieces.append(piece)
                    self._scatter_piece(piece, c, r, cell_w, cell_h, knob_r, grid_w, grid_h)

            self.view.fit_board()
        except (FileNotFoundError, OSError) as exc:
            self.author_label.setText(f"加载失败：{exc}")
            self.author_label.show()

    def _image_size(self, image: PuzzleImage) -> tuple[int, int]:
        # 用 QImage 探测实际像素尺寸（对应网页端自然宽高）
        from PySide6.QtGui import QImage

        img = QImage(str(image.path))
        return (img.width(), img.height())

    def _draw_board(self, grid_w: float, grid_h: float) -> None:
        """范围框底衬：直角矩形，颜色随主题（深灰/浅灰），不裁碎片圆角。"""
        path = QPainterPath()
        path.addRect(QRectF(0, 0, grid_w, grid_h))
        item = self._scene.addPath(
            path,
            QPen(QColor(0, 0, 0, 0)),
            QBrush(self._card_color()),
        )
        item.setZValue(-1)
        self._board_item = item

    def _card_color(self) -> QColor:
        return BOARD_COLOR_DARK if self._theme.theme() == "dark" else BOARD_COLOR_LIGHT

    def _update_board_color(self) -> None:
        if self._board_item is not None:
            self._board_item.setBrush(QBrush(self._card_color()))

    def _scatter_piece(
        self,
        piece: PieceItem,
        c: int,
        r: int,
        cell_w: float,
        cell_h: float,
        knob_r: float,
        grid_w: float,
        grid_h: float,
    ) -> None:
        """随机打散：限界偏移（防凸起出框）+ 随机旋转 ±25°（对齐网页端）。"""
        piece_left = c * cell_w - knob_r
        piece_top = r * cell_h - knob_r
        piece_right = (c + 1) * cell_w + knob_r
        piece_bottom = (r + 1) * cell_h + knob_r

        max_left = max(0.0, piece_left)
        max_top = max(0.0, piece_top)
        max_right = max(0.0, grid_w - piece_right)
        max_bottom = max(0.0, grid_h - piece_bottom)

        rx = random.uniform(-max_left, max_right)
        ry = random.uniform(-max_top, max_bottom)
        rr = random.uniform(-SCATTER_ROTATE_RANGE, SCATTER_ROTATE_RANGE)
        piece.setPos(piece.target_pos() + QPointF(rx, ry))
        piece.setRotation(rr)
        piece.setScale(1.0)
        piece.setZValue(2)  # 自由层

    # ── 计时器 ────────────────────────────────────────────

    def _on_piece_picked(self, _piece: PieceItem) -> None:
        """第一次拿起碎片时开始计时（后续拿起不再重置）。"""
        if not self._elapsed.isValid():
            self._elapsed.start()
            self._timer.start()

    def _update_timer_label(self) -> None:
        self.timer_label.setText(format_time(self._elapsed.elapsed() / 1000.0))

    def _on_game_completed(self) -> None:
        """完成：停止计时并持久化本图最快用时。"""
        if not self._elapsed.isValid():
            return
        self._timer.stop()
        total = self._elapsed.elapsed() / 1000.0
        self._elapsed.invalidate()
        self.timer_label.setText(format_time(total))
        if self._current_image is not None:
            save_best_time(self._current_image.path.name, total)

    # ── 交互与完成判定 ────────────────────────────────────

    def _on_piece_released(self, piece: PieceItem) -> None:
        """释放后判定吸附与完成（对齐网页 onRelease + checkSolved）。"""
        dx = piece.pos().x() - piece.target_pos().x()
        dy = piece.pos().y() - piece.target_pos().y()
        if abs(dx) < SNAP_THRESHOLD and abs(dy) < SNAP_THRESHOLD:
            anim = piece.snap_to_target()
            anim.start()
            piece.setZValue(1)  # 已放置层（圆角呈现）
            anim.finished.connect(lambda p=piece: self._after_snap(p))
        else:
            piece.setZValue(2)
        self._check_solved()

    def _after_snap(self, piece: PieceItem) -> None:
        piece.setRotation(0.0)
        self._check_solved()

    def _check_solved(self) -> None:
        """全部碎片偏移总和 < 1 即完成（对齐网页端）。"""
        total = sum(
            abs(p.pos().x() - p.target_pos().x()) + abs(p.pos().y() - p.target_pos().y())
            for p in self._pieces
        )
        if total < 1.0 and self._end_item is None:
            self._show_complete()

    def _show_complete(self) -> None:
        """完成：记录用时并持久化，完整原图 0.8s 淡入 + 底部作者署名。"""
        self._on_game_completed()
        if self._texture is None:
            return
        end = QGraphicsPixmapItem(self._texture)
        # 纹理像素 → 场景单位（与碎片纹理相同的映射）
        end.setScale(1.0 / self._unit_scale)
        end.setZValue(10)
        end.setOpacity(0.0)
        self._scene.addItem(end)
        self._end_item = end

        from PySide6.QtCore import QVariantAnimation

        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(800)
        anim.setEasingCurve(QEasingCurve.Type.InOutQuad)  # 对齐 GSAP power2.inOut
        anim.valueChanged.connect(lambda v: end.setOpacity(float(v)))
        anim.start()

        if self._current_image is not None:
            self.author_label.setText(f"© {self._current_image.author}")
            self.author_label.show()
