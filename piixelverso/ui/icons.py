"""Shared vector command icons for the native interface."""
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from ..brand import app_icon
from ..theme import theme_color


def icon(kind: str, color=None) -> QIcon:
    if color is None:
        color = theme_color("ink")
    if kind == "brand":
        return app_icon()
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if kind == "pencil":
        p.drawPolygon([QPoint(x, y) for x, y in [(5, 19), (7, 13), (16, 4), (20, 8), (11, 17)]])
        p.drawLine(14, 6, 18, 10)
    elif kind == "line":
        p.drawLine(5, 19, 19, 5)
        p.drawRect(3, 17, 4, 4); p.drawRect(17, 3, 4, 4)
    elif kind == "rectangle":
        p.drawRect(4, 6, 16, 12)
    elif kind == "ellipse":
        p.drawEllipse(4, 5, 16, 14)
    elif kind == "shape_fill":
        p.fillRect(5, 6, 14, 12, QColor(color))
    elif kind == "eraser":
        p.drawLine(5, 16, 14, 5); p.drawLine(14, 5, 20, 10)
        p.drawLine(20, 10, 12, 20); p.drawLine(12, 20, 8, 20); p.drawLine(8, 20, 5, 16)
        p.drawLine(9, 12, 16, 17); p.drawLine(12, 20, 21, 20)
    elif kind == "bucket":
        p.drawPolygon([QPoint(x, y) for x, y in [(4, 11), (11, 4), (18, 11), (11, 18)]])
        p.drawLine(8, 3, 15, 10); p.drawLine(4, 11, 18, 11)
        p.drawLine(20, 13, 18, 17); p.drawLine(18, 17, 18, 19)
        p.drawArc(18, 17, 4, 4, 180 * 16, 180 * 16); p.drawLine(22, 19, 20, 13)
    elif kind == "replace_color":
        p.drawRoundedRect(3, 4, 7, 7, 1, 1)
        p.drawRoundedRect(14, 13, 7, 7, 1, 1)
        p.drawLine(13, 6, 20, 6); p.drawLine(20, 6, 17, 3)
        p.drawLine(20, 6, 17, 9)
        p.drawLine(11, 18, 4, 18); p.drawLine(4, 18, 7, 15)
        p.drawLine(4, 18, 7, 21)
    elif kind == "picker":
        p.drawLine(7, 14, 16, 5); p.drawLine(11, 18, 20, 9)
        p.drawLine(16, 5, 20, 9); p.drawLine(7, 14, 6, 20)
        p.drawLine(6, 20, 11, 18); p.drawLine(13, 5, 20, 12)
    elif kind == "selection":
        p.setPen(QPen(QColor(color), 1.7, Qt.PenStyle.DashLine))
        p.drawRect(4, 4, 16, 16)
    elif kind == "copy":
        p.drawRoundedRect(7, 7, 13, 13, 2, 2)
        p.drawRoundedRect(4, 4, 13, 13, 2, 2)
    elif kind == "cut":
        p.drawEllipse(4, 15, 5, 5); p.drawEllipse(15, 15, 5, 5)
        p.drawLine(8, 16, 17, 5); p.drawLine(16, 16, 7, 5)
    elif kind == "paste":
        p.drawRoundedRect(5, 6, 14, 15, 2, 2)
        p.drawRect(8, 3, 8, 5)
    elif kind in ("undo", "redo"):
        if kind == "redo":
            p.translate(24, 0); p.scale(-1, 1)
        p.drawArc(6, 7, 14, 14, -60 * 16, 240 * 16)
        p.drawLine(6, 7, 6, 13); p.drawLine(6, 13, 12, 13)
    elif kind in ("save", "save_as"):
        p.drawRoundedRect(4, 4, 16, 16, 2, 2)
        p.drawRect(8, 4, 8, 6); p.drawRect(8, 14, 8, 6)
        if kind == "save_as":
            p.drawLine(15, 19, 21, 13); p.drawLine(18, 13, 21, 16)
    elif kind == "palette":
        p.drawEllipse(3, 3, 18, 18)
        for x, y in [(8, 7), (14, 6), (17, 12), (8, 14)]:
            p.drawEllipse(x - 1, y - 1, 2, 2)
    elif kind == "folder":
        p.drawLine(3, 8, 3, 19); p.drawLine(3, 19, 21, 19)
        p.drawLine(21, 19, 21, 8); p.drawLine(21, 8, 12, 8)
        p.drawLine(12, 8, 10, 5); p.drawLine(10, 5, 3, 5); p.drawLine(3, 5, 3, 8)
    elif kind == "plus":
        p.drawLine(12, 5, 12, 19); p.drawLine(5, 12, 19, 12)
    elif kind == "fit":
        for x, y, sx, sy in [(4, 4, 1, 1), (20, 4, -1, 1), (4, 20, 1, -1), (20, 20, -1, -1)]:
            p.drawLine(x, y, x + 5 * sx, y); p.drawLine(x, y, x, y + 5 * sy)
    elif kind == "chat":
        p.drawRoundedRect(3, 4, 18, 13, 3, 3)
        p.drawLine(7, 17, 7, 21)
        p.drawLine(7, 21, 12, 17)
        p.drawLine(7, 9, 17, 9)
        p.drawLine(7, 12, 14, 12)
    elif kind == "settings":
        p.drawEllipse(6, 6, 12, 12); p.drawEllipse(10, 10, 4, 4)
        for x, y, ex, ey in [(12, 3, 12, 6), (12, 18, 12, 21), (3, 12, 6, 12),
                             (18, 12, 21, 12), (5, 5, 8, 8), (16, 16, 19, 19),
                             (5, 19, 8, 16), (16, 8, 19, 5)]:
            p.drawLine(x, y, ex, ey)
    elif kind == "export_png":
        p.drawRoundedRect(3, 4, 18, 15, 2, 2)
        p.drawEllipse(6, 7, 3, 3)
        p.drawLine(4, 17, 10, 11); p.drawLine(10, 11, 14, 15)
        p.drawLine(14, 15, 17, 12); p.drawLine(17, 12, 20, 15)
    p.end()
    return QIcon(pixmap)

