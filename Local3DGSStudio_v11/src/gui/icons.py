"""Lightweight, dependency-free sidebar icons.

The theme calls for consistent, single-accent-colored icons on every
sidebar item ("Do not use text-only sidebar buttons"). Rather than ship
binary icon assets, each icon is a small set of simple geometric shapes
drawn with QPainter at a fixed size/stroke weight and tinted with the
theme's accent color -- consistent visual weight by construction, no
external files to manage.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap

ACCENT_COLOR = "#9D00FF"
_SIZE = 20
_STROKE = 1.6


def _new_painter(color: str) -> tuple[QPixmap, QPainter]:
    pixmap = QPixmap(_SIZE, _SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color)
    pen.setWidthF(_STROKE)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    return pixmap, painter


def _finish(pixmap: QPixmap, painter: QPainter) -> QIcon:
    painter.end()
    return QIcon(pixmap)


def _dashboard_icon(color: str) -> QIcon:
    pixmap, painter = _new_painter(color)
    m = 3.5
    half = _SIZE / 2
    painter.drawRect(QRectF(m, m, half - m - 1, half - m - 1))
    painter.drawRect(QRectF(half + 1, m, half - m - 1, half - m - 1))
    painter.drawRect(QRectF(m, half + 1, half - m - 1, half - m - 1))
    painter.drawRect(QRectF(half + 1, half + 1, half - m - 1, half - m - 1))
    return _finish(pixmap, painter)


def _image_icon(color: str) -> QIcon:
    pixmap, painter = _new_painter(color)
    painter.drawRect(QRectF(3, 4, _SIZE - 6, _SIZE - 8))
    painter.drawEllipse(QPointF(8, 9), 1.6, 1.6)
    painter.drawPolyline([QPointF(5, 14), QPointF(9, 10), QPointF(12, 13), QPointF(15, 9), QPointF(17, 12)])
    return _finish(pixmap, painter)


def _camera_icon(color: str) -> QIcon:
    pixmap, painter = _new_painter(color)
    painter.drawRoundedRect(QRectF(3, 6, _SIZE - 6, 10), 2, 2)
    painter.drawRect(QRectF(7, 3.5, 6, 3))
    painter.drawEllipse(QPointF(_SIZE / 2, 11), 3.2, 3.2)
    return _finish(pixmap, painter)


def _point_cloud_icon(color: str) -> QIcon:
    pixmap, painter = _new_painter(color)
    points = [
        QPointF(5, 6), QPointF(11, 4), QPointF(16, 7), QPointF(6, 11),
        QPointF(13, 12), QPointF(17, 15), QPointF(9, 16), QPointF(4, 15),
    ]
    for p in points:
        painter.drawPoint(p)
        painter.drawEllipse(p, 0.9, 0.9)
    return _finish(pixmap, painter)


def _gaussian_icon(color: str) -> QIcon:
    pixmap, painter = _new_painter(color)
    center = QPointF(_SIZE / 2, _SIZE / 2)
    for radius in (7, 4.5, 2):
        painter.drawEllipse(center, radius, radius * 0.6)
    return _finish(pixmap, painter)


def _training_icon(color: str) -> QIcon:
    pixmap, painter = _new_painter(color)
    base = _SIZE - 4
    painter.drawPolyline([QPointF(3, base), QPointF(3, 4), QPointF(_SIZE - 3, 4)])
    painter.drawPolyline([QPointF(4, base - 2), QPointF(8, base - 8), QPointF(11, base - 10), QPointF(16, base - 15)])
    return _finish(pixmap, painter)


def _cleanup_icon(color: str) -> QIcon:
    pixmap, painter = _new_painter(color)
    painter.drawLine(QPointF(6, 6), QPointF(14, 14))
    painter.drawLine(QPointF(14, 6), QPointF(6, 14))
    painter.drawEllipse(QPointF(_SIZE / 2, _SIZE / 2), 8, 8)
    return _finish(pixmap, painter)


def _render_icon(color: str) -> QIcon:
    pixmap, painter = _new_painter(color)
    painter.drawEllipse(QRectF(3, 3, _SIZE - 6, _SIZE - 6))
    painter.drawLine(QPointF(_SIZE / 2, 3), QPointF(_SIZE / 2, _SIZE - 3))
    painter.drawLine(QPointF(3, _SIZE / 2), QPointF(_SIZE - 3, _SIZE / 2))
    return _finish(pixmap, painter)


def _export_icon(color: str) -> QIcon:
    pixmap, painter = _new_painter(color)
    painter.drawRect(QRectF(4, 10, _SIZE - 8, 7))
    painter.drawPolyline([QPointF(_SIZE / 2, 3), QPointF(_SIZE / 2, 12)])
    painter.drawPolyline([QPointF(7, 8), QPointF(_SIZE / 2, 3), QPointF(13, 8)])
    return _finish(pixmap, painter)


_ICON_BUILDERS = {
    "dashboard": _dashboard_icon,
    "image": _image_icon,
    "camera": _camera_icon,
    "pointCloud": _point_cloud_icon,
    "gaussian": _gaussian_icon,
    "training": _training_icon,
    "cleanup": _cleanup_icon,
    "render": _render_icon,
    "export": _export_icon,
}


def workflow_icon(icon_id: str, color: str = ACCENT_COLOR) -> QIcon:
    """Return the icon for a sidebar item id (see the builders above).
    Falls back to a plain dot if the id isn't recognized, so an unknown
    id never crashes the sidebar -- it just looks generic."""
    builder = _ICON_BUILDERS.get(icon_id)
    if builder is None:
        pixmap, painter = _new_painter(color)
        painter.drawEllipse(QPointF(_SIZE / 2, _SIZE / 2), 3, 3)
        return _finish(pixmap, painter)
    return builder(color)
