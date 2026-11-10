"""Native pixel canvas with continuous strokes and one undo step per gesture."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from .materials import TRANSPARENT_OUTLINE, display_color
from .model import PixelDesign
from .model import is_transparent
from .operations import flood_fill_changes
from .shapes import SHAPE_TOOLS, shape_cells
from .theme import BORDER, EMPTY_ALT, GRID, MUTED, PINK, WHITE


class PixelCanvas(QWidget):
    changed = Signal()
    stroke_finished = Signal(object, object)
    color_picked = Signal(str)
    hovered = Signal(int, int)
    MARGIN = 26

    def __init__(self, design: PixelDesign, parent=None):
        super().__init__(parent)
        self.design = design
        self.cell_size = 16
        self.color = "#E7794B"
        self.tool = "pencil"
        self.shape_filled = False
        self.show_grid = True
        self.display_mode = "squares"
        self._before: dict[int, str | None] = {}
        self._drawing = False
        self._erase = False
        self._last: tuple[int, int] | None = None
        self._hover: tuple[int, int] | None = None
        self._stroke_button = None
        self._shape_preview: dict[int, str] = {}
        self._shape_start: tuple[int, int] | None = None
        self._shape_end: tuple[int, int] | None = None
        self._shape_tool: str | None = None
        self._shape_color = self.color
        self._shape_fill = False
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setObjectName("pixelCanvas")
        self.setAccessibleName("Grade de pixel art")
        self._resize()

    def _resize(self):
        self.setFixedSize(self.design.width * self.cell_size + 2 * self.MARGIN,
                          self.design.height * self.cell_size + 2 * self.MARGIN)
        self.update()

    @property
    def has_pending_changes(self) -> bool:
        """Whether an in-progress freehand stroke has changed document pixels."""
        return bool(self._before)

    @property
    def is_erasing(self) -> bool:
        """Describe the current stroke without exposing its private gesture state."""
        return self._erase

    def set_design(self, design: PixelDesign):
        self.finish_stroke()
        self.design = design
        self._hover = None
        self._resize()

    def set_zoom(self, percent: int):
        self.cell_size = max(4, round(16 * percent / 100))
        self._resize()

    def set_display_mode(self, mode: str):
        """Change only the preview; every cell still represents one piece."""
        if mode not in ("squares", "beads"):
            raise ValueError("O modo de exibição deve ser 'squares' ou 'beads'.")
        if mode != self.display_mode:
            self.display_mode = mode
            self.update()

    @staticmethod
    def _paint_bead(painter: QPainter, left: int, top: int, size: int, color: str):
        outer = QRectF(left + size * 0.06, top + size * 0.06,
                       size * 0.88, size * 0.88)
        hole_size = max(2.4, size * 0.36)
        hole_offset = (size - hole_size) / 2
        hole = QRectF(left + hole_offset, top + hole_offset,
                      hole_size, hole_size)
        ring = QPainterPath()
        ring.setFillRule(Qt.FillRule.OddEvenFill)
        ring.addEllipse(outer)
        outer_outline = QPainterPath(ring)
        ring.addEllipse(hole)

        base = QColor(display_color(color))
        gradient = QRadialGradient(QPointF(left + size * 0.35, top + size * 0.28),
                                   size * 0.76)
        gradient.setColorAt(0, base.lighter(108))
        gradient.setColorAt(0.55, base)
        gradient.setColorAt(1, base.darker(108))
        outline = QColor(TRANSPARENT_OUTLINE) if is_transparent(color) else (
            QColor(BORDER) if base.lightness() > 235 else base.darker(115)
        )
        painter.fillPath(ring, gradient)
        painter.strokePath(outer_outline, QPen(outline, max(0.4, min(0.8, size * 0.03))))
        if is_transparent(color):
            painter.strokePath(ring, QPen(outline, max(0.7, min(1.2, size * 0.05))))

    def cell_at(self, point: QPoint):
        x = (point.x() - self.MARGIN) // self.cell_size
        y = (point.y() - self.MARGIN) // self.cell_size
        return (x, y) if 0 <= x < self.design.width and 0 <= y < self.design.height else None

    def cell_center(self, x: int, y: int) -> QPoint:
        return QPoint(self.MARGIN + x * self.cell_size + self.cell_size // 2,
                      self.MARGIN + y * self.cell_size + self.cell_size // 2)

    def _clamped_cell(self, point: QPoint) -> tuple[int, int]:
        """Keep a dragged shape's endpoint on the nearest canvas cell."""
        x = (point.x() - self.MARGIN) // self.cell_size
        y = (point.y() - self.MARGIN) // self.cell_size
        return (max(0, min(self.design.width - 1, x)),
                max(0, min(self.design.height - 1, y)))

    def _update_shape_preview(self, end: tuple[int, int]):
        self._shape_end = end
        cells = shape_cells(self._shape_tool, self._shape_start, end, self._shape_fill)
        self._shape_preview = {
            y * self.design.width + x: self._shape_color for x, y in cells
        }
        self.update()

    def _clear_shape_preview(self):
        self._shape_preview = {}
        self._shape_start = None
        self._shape_end = None
        self._shape_tool = None

    def paintEvent(self, event):
        painter = QPainter(self)
        m, size = self.MARGIN, self.cell_size
        width, height = self.design.width, self.design.height
        beads = self.display_mode == "beads"
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, beads)
        for y in range(height):
            for x in range(width):
                index = y * width + x
                color = self._shape_preview.get(index, self.design.pixels[index])
                background = WHITE if (x + y) % 2 == 0 else EMPTY_ALT
                left, top = m + x * size, m + y * size
                fill = background if beads or color is None else display_color(color)
                painter.fillRect(left, top, size, size, QColor(fill))
                if beads and color is not None:
                    self._paint_bead(painter, left, top, size, color)
                elif is_transparent(color):
                    painter.setPen(QPen(QColor(TRANSPARENT_OUTLINE), max(1, min(2, size // 8))))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(left + 1, top + 1, max(0, size - 3), max(0, size - 3))
                    painter.setPen(Qt.PenStyle.NoPen)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if self.show_grid and size >= 7:
            painter.setPen(QPen(QColor(GRID), 1))
            for x in range(width + 1):
                painter.drawLine(m + x * size, m, m + x * size, m + height * size)
            for y in range(height + 1):
                painter.drawLine(m, m + y * size, m + width * size, m + y * size)
        painter.setPen(QPen(QColor(BORDER), 1))
        painter.drawRect(m, m, width * size, height * size)
        painter.setPen(QColor(MUTED))
        font = painter.font()
        font.setPixelSize(9)
        painter.setFont(font)
        step = 4 if size >= 12 else 8
        for x in range(width):
            if x == 0 or (x + 1) % step == 0:
                painter.drawText(QRect(m + x * size - 3, 3, size + 6, 18), Qt.AlignmentFlag.AlignCenter, str(x + 1))
        for y in range(height):
            if y == 0 or (y + 1) % step == 0:
                painter.drawText(QRect(0, m + y * size, 21, size), Qt.AlignmentFlag.AlignCenter, str(y + 1))
        if self._hover:
            x, y = self._hover
            painter.setPen(QPen(QColor(PINK), 2))
            painter.drawRect(m + x * size + 1, m + y * size + 1, size - 2, size - 2)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            return
        cell = self.cell_at(event.position().toPoint())
        if cell is None:
            return
        self.finish_stroke()
        if self.tool in SHAPE_TOOLS and event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._drawing = True
            self._erase = False
            self._before = {}
            self._last = None
            self._stroke_button = event.button()
            self._shape_start = cell
            self._shape_tool = self.tool
            self._shape_color = self.color
            self._shape_fill = self.shape_filled
            self._update_shape_preview(cell)
            return
        if self.tool == "bucket" and event.button() == Qt.MouseButton.LeftButton:
            self._erase = False
            changes = flood_fill_changes(self.design, *cell, self.color)
            if changes:
                before = {index: self.design.pixels[index] for index in changes}
                for index, color in changes.items():
                    self.design.pixels[index] = color
                self.changed.emit()
                self.stroke_finished.emit(before, changes)
                self.update()
            return
        if self.tool == "picker" and event.button() == Qt.MouseButton.LeftButton:
            color = self.design.get_pixel(*cell)
            if color:
                self.color_picked.emit(color)
            return
        self._drawing = True
        self._erase = self.tool == "eraser" or event.button() == Qt.MouseButton.RightButton
        self._before = {}
        self._last = cell
        self._stroke_button = event.button()
        self._paint_cell(*cell)

    def _paint_cell(self, x, y):
        index = y * self.design.width + x
        color = None if self._erase else self.color
        if self.design.pixels[index] != color:
            self._before.setdefault(index, self.design.pixels[index])
            self.design.pixels[index] = color
            self.changed.emit()
            self.update()

    def _paint_line(self, start, end):
        x, y = start
        ex, ey = end
        dx, dy = abs(ex - x), -abs(ey - y)
        sx, sy = 1 if x < ex else -1, 1 if y < ey else -1
        error = dx + dy
        while True:
            self._paint_cell(x, y)
            if (x, y) == (ex, ey):
                break
            doubled = error * 2
            if doubled >= dy:
                error += dy
                x += sx
            if doubled <= dx:
                error += dx
                y += sy

    def mouseMoveEvent(self, event: QMouseEvent):
        cell = self.cell_at(event.position().toPoint())
        self._hover = cell
        if cell:
            self.hovered.emit(*cell)
        if self._drawing:
            if self._shape_tool is not None:
                self._update_shape_preview(self._clamped_cell(event.position().toPoint()))
            else:
                if cell:
                    self._paint_line(self._last or cell, cell)
                self._last = cell
        self.update()

    def mouseReleaseEvent(self, event):
        if not self._drawing or event.button() != self._stroke_button:
            return
        if self._shape_tool is not None:
            self._update_shape_preview(self._clamped_cell(event.position().toPoint()))
        self.finish_stroke()

    def finish_stroke(self):
        if not self._drawing:
            return
        self._drawing = False
        self._stroke_button = None
        if self._shape_tool is not None:
            after = {index: color for index, color in self._shape_preview.items()
                     if self.design.pixels[index] != color}
            before = {index: self.design.pixels[index] for index in after}
            self._before = {}
            self._last = None
            self._clear_shape_preview()
            for index, color in after.items():
                self.design.pixels[index] = color
            if after:
                self.changed.emit()
                self.stroke_finished.emit(before, after)
            self.update()
            return
        after = {i: self.design.pixels[i] for i in self._before
                 if self.design.pixels[i] != self._before[i]}
        before = {i: self._before[i] for i in after}
        self._before = {}
        self._last = None
        if before:
            self.stroke_finished.emit(before, after)

    def cancel_stroke(self) -> bool:
        """Discard an uncommitted geometric preview without changing the design."""
        if self._shape_tool is None:
            return False
        self._drawing = False
        self._stroke_button = None
        self._before = {}
        self._last = None
        self._clear_shape_preview()
        self.update()
        return True

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.cancel_stroke():
            event.accept()
            return
        super().keyPressEvent(event)

    def leaveEvent(self, event):
        self._hover = None
        self.update()
