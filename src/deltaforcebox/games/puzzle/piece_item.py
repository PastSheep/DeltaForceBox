"""拼图碎片项：纹理绘制、阴影/高光、拖拽、吸附与动画。

对应网页端 enableDrag / makePiecePath / checkSolved 的交互逻辑：
- 按下：scale 1.06 + 随机旋转 ±5°（0.25s back.out(2)），阴影淡化；
- 释放：回弹（back.out(3)），若偏移 < 9 吸附归位（0.2s power2），否则留在自由层；
- 完成判定由页面遍历全部碎片偏移总和 < 1 触发。
"""

from __future__ import annotations

import random

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsObject

# 与网页端一致的判定/动画参数
SNAP_THRESHOLD = 9.0  # 吸附阈值：|dx|<9 且 |dy|<9
PRESS_SCALE = 1.06
PRESS_ROTATE_RANGE = 5.0
SHADOW_COLOR = QColor(0, 0, 0, 51)  # 黑色 0.2


class PieceItem(QGraphicsObject):
    """一块拼图碎片。

    约定：path 与 corner_clip 在 item 局部坐标中以 (0,0) 为左上角
    （构造时由 origin 平移），pos 即该块左上角在场景中的位置。
    """

    released = Signal(object)  # 释放后通知页面（携带自身，用于完成判定）

    def __init__(
        self,
        path: QPainterPath,
        brush: QBrush,
        target_pos: QPointF,
        corner_clip: QPainterPath | None = None,
        origin: QPointF | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._path = path
        self._brush = brush
        self._target_pos = target_pos
        self._grab_offset = QPointF()
        self._dragging = False
        self._press_animations: list[QPropertyAnimation] = []
        self._shadow_offset = QPointF(1.0, 3.0)
        self._shadow_opacity = 0.2
        self._shadow_scale = 1.0
        self._clip_path = corner_clip
        # path 局部坐标起点为 (c*cell, r*cell)，平移到 (0,0)，
        # 使 item 的 pos 直接对应场景中的碎片位置（否则偏移会叠加导致碎片漂移）
        if origin is not None:
            self._path.translate(-origin.x(), -origin.y())
            if self._clip_path is not None:
                self._clip_path.translate(-origin.x(), -origin.y())
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        # 不使用 DeviceCoordinateCache：缓存会在 item 局部小坐标系下栅格化贝塞尔
        # 曲线，被 view 放大后轮廓出现折角（多边形感）；直接渲染让 QPainter
        # 按设备精度 flatten 曲线，保证与网页端一致的平滑圆弧。
        self.setTransformOriginPoint(self._path.boundingRect().center())

    # ── 几何 ──────────────────────────────────────────────

    def target_pos(self) -> QPointF:
        return self._target_pos

    def offset(self) -> QPointF:
        """当前相对目标位置的偏移（对应网页端 readPieceOffset 的 x/y）。"""
        return self.pos() - self._target_pos

    def boundingRect(self) -> QRectF:
        rect = self._path.boundingRect()
        # 阴影绘制在 path 平移 _shadow_offset(1,3) 的位置，必须并入重绘范围；
        # 否则移动碎片时，超出本区域的阴影不会被擦除，形成拖影。
        rect = rect.united(rect.translated(self._shadow_offset))
        # 描边与抗锯齿余量
        rect = rect.adjusted(-2.0, -2.0, 2.0, 2.0)
        if self._clip_path is not None:
            rect = rect.united(self._clip_path.boundingRect())
        return rect

    def shape(self) -> QPainterPath:
        return self._path

    # ── 绘制 ──────────────────────────────────────────────

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 投影层（黑色半透明，按下时淡化）
        if self._shadow_opacity > 0.0:
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            shadow = QColor(0, 0, 0, round(255 * self._shadow_opacity))
            painter.setBrush(shadow)
            painter.translate(self._shadow_offset)
            painter.scale(self._shadow_scale, self._shadow_scale)
            painter.drawPath(self._path)
            painter.restore()

        # 主体：图片纹理填充
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._brush)
        if self._clip_path is not None:
            painter.setClipPath(self._clip_path)
        painter.drawPath(self._path)
        painter.restore()

        # bevel 高光近似：沿路径描细白边（对应网页端 feSpecularLighting 的顶部高光）
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 48), 0.6))
        painter.drawPath(self._path)
        painter.restore()

    # ── 拖拽 ──────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self._grab_offset = event.scenePos() - self.pos()
        self._dragging = True
        self.setZValue(3)  # 拖拽中置于最顶层
        self._play_press_animation()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            super().mouseMoveEvent(event)
            return
        self.setPos(event.scenePos() - self._grab_offset)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if not self._dragging:
            super().mouseReleaseEvent(event)
            return
        self._dragging = False
        self._play_release_animation()
        self.released.emit(self)
        event.accept()

    # ── 动画（对齐 GSAP back.out / power2） ────────────────

    def _stop_press_animations(self) -> None:
        for anim in self._press_animations:
            anim.stop()
        self._press_animations.clear()

    def _play_press_animation(self) -> None:
        self._stop_press_animations()
        self.setRotation(random.uniform(-PRESS_ROTATE_RANGE, PRESS_ROTATE_RANGE))

        scale_anim = QPropertyAnimation(self, b"scale", self)
        scale_anim.setEndValue(PRESS_SCALE)
        scale_anim.setDuration(250)
        curve = QEasingCurve(QEasingCurve.Type.OutBack)
        curve.setOvershoot(2.0)  # 对齐 GSAP back.out(2)
        scale_anim.setEasingCurve(curve)

        shadow_anim = QPropertyAnimation(self, b"shadowOpacity", self)
        shadow_anim.setEndValue(0.12)
        shadow_anim.setDuration(250)
        shadow_anim.setEasingCurve(QEasingCurve.Type.OutQuad)

        self._press_animations = [scale_anim, shadow_anim]
        for anim in self._press_animations:
            anim.start()

    def _play_release_animation(self) -> None:
        self._stop_press_animations()

        scale_anim = QPropertyAnimation(self, b"scale", self)
        scale_anim.setEndValue(1.0)
        scale_anim.setDuration(200)
        curve = QEasingCurve(QEasingCurve.Type.OutBack)
        curve.setOvershoot(3.0)  # 对齐 GSAP back.out(3)
        scale_anim.setEasingCurve(curve)

        shadow_anim = QPropertyAnimation(self, b"shadowOpacity", self)
        shadow_anim.setEndValue(0.2)
        shadow_anim.setDuration(200)
        shadow_anim.setEasingCurve(QEasingCurve.Type.OutQuad)

        self._press_animations = [scale_anim, shadow_anim]
        for anim in self._press_animations:
            anim.start()

    def snap_to_target(self, duration: int = 200) -> QPropertyAnimation:
        """吸附归位动画（对齐网页 0.2s power2），完成后旋转归零。"""
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setEndValue(self._target_pos)
        anim.setDuration(duration)
        anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        anim.finished.connect(lambda: self.setRotation(0.0))
        return anim

    # ── 阴影状态属性（供 QPropertyAnimation 驱动） ──────────

    def get_shadow_opacity(self) -> float:
        return self._shadow_opacity

    def set_shadow_opacity(self, value: float) -> None:
        self._shadow_opacity = float(value)
        self.update()

    shadowOpacity = Property(float, get_shadow_opacity, set_shadow_opacity)
