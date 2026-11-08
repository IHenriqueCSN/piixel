"""Render a design as an annotated PNG without changing the editor state."""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

from PySide6.QtCore import QIODevice, QPoint, QRect, QRectF, QSaveFile, QSize, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QGuiApplication, QImage, QPainter, QPainterPath,
    QPen, QPolygon,
)

from .model import PixelDesign
from .preferences import DEFAULT_PIECE_SIZE_MM, validate_piece_size_mm


CELL_SIZE = 32
GRID_COLOR = "#CFCFCF"
_FONT_SIZE = 15
_OUTER_MARGIN = 20


@dataclass(frozen=True)
class ExportLayout:
    cell_size: int
    grid_left: int
    grid_top: int
    grid_width: int
    grid_height: int
    image_width: int
    image_height: int
    horizontal_arrow_y: int
    vertical_arrow_x: int
    horizontal_label_rect: QRect
    vertical_label_rect: QRect
    width_label: str
    height_label: str
    design_left: int
    design_top: int
    design_width: int
    design_height: int

    @property
    def has_design(self) -> bool:
        return self.design_width > 0 and self.design_height > 0

    @property
    def design_rect(self) -> QRect:
        return QRect(self.design_left, self.design_top, self.design_width, self.design_height)

    @property
    def grid_rect(self) -> QRect:
        return QRect(self.grid_left, self.grid_top, self.grid_width, self.grid_height)

    @property
    def image_size(self) -> QSize:
        return QSize(self.image_width, self.image_height)


def format_mm(value: float) -> str:
    """Format millimeters using a decimal comma and no redundant zeroes."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("A medida precisa ser um número finito em milímetros.")
    if not math.isfinite(value) or value < 0:
        raise ValueError("A medida precisa ser um número finito em milímetros.")
    text = f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{text} mm"


def occupied_bounds(design: PixelDesign) -> tuple[int, int, int, int] | None:
    """Return occupied cell edges, with exclusive right/bottom; white is a piece."""
    design.validate()
    left, top, right, bottom = design.width, design.height, 0, 0
    for index, color in enumerate(design.pixels):
        if color is not None:
            row, column = divmod(index, design.width)
            left, top = min(left, column), min(top, row)
            right, bottom = max(right, column + 1), max(bottom, row + 1)
    return (left, top, right, bottom) if right > left else None


def measurement_labels(
    design: PixelDesign, piece_size_mm: float = DEFAULT_PIECE_SIZE_MM,
) -> tuple[str, str]:
    """Measure from the outer edge of the first piece to that of the last."""
    bounds = occupied_bounds(design)
    size = validate_piece_size_mm(piece_size_mm)
    if bounds is None:
        return "0 mm", "0 mm"
    left, top, right, bottom = bounds
    return format_mm((right - left) * size), format_mm((bottom - top) * size)


def _dimension_font() -> QFont:
    font = QFont("DejaVu Sans")
    font.setPixelSize(_FONT_SIZE)
    return font


def export_layout(
    design: PixelDesign, piece_size_mm: float = DEFAULT_PIECE_SIZE_MM,
) -> ExportLayout:
    """Reserve enough space for the artwork, arrows, and both measured labels."""
    width_label, height_label = measurement_labels(design, piece_size_mm)
    if QGuiApplication.instance() is None:
        raise RuntimeError("Crie a aplicação Qt antes de exportar uma imagem.")
    metrics = QFontMetrics(_dimension_font())
    font_height = metrics.height()
    width_text = metrics.horizontalAdvance(width_label) + 12
    height_text = metrics.horizontalAdvance(height_label) + 12
    grid_width, grid_height = design.width * CELL_SIZE, design.height * CELL_SIZE
    bounds = occupied_bounds(design)
    min_column, min_row, max_column, max_row = bounds or (0, 0, 0, 0)
    design_width = (max_column - min_column) * CELL_SIZE
    design_height = (max_row - min_row) * CELL_SIZE
    # Labels describe the occupied span; the editable grid keeps its placement.
    span_width = design_width if bounds else grid_width
    span_height = design_height if bounds else grid_height
    offset_x, offset_y = min_column * CELL_SIZE, min_row * CELL_SIZE

    # Left: rotated height label, a clear gap, then the dimension arrow.
    vertical_label_left = _OUTER_MARGIN
    vertical_arrow_x = vertical_label_left + font_height + 16
    grid_left = vertical_arrow_x + 28
    # A short occupied span can have a label wider than the measured design.
    grid_left = max(grid_left, math.ceil((width_text - span_width) / 2) - offset_x + _OUTER_MARGIN)
    horizontal_arrow_y = _OUTER_MARGIN + font_height + 10
    grid_top = horizontal_arrow_y + 28
    grid_top = max(grid_top, math.ceil((height_text - span_height) / 2) - offset_y + _OUTER_MARGIN)
    design_left, design_top = grid_left + offset_x, grid_top + offset_y

    horizontal_label_rect = QRect(
        round(design_left + (span_width - width_text) / 2),
        horizontal_arrow_y - font_height - 8,
        width_text,
        font_height,
    )
    vertical_label_rect = QRect(
        vertical_label_left,
        round(design_top + (span_height - height_text) / 2),
        font_height,
        height_text,
    )
    image_width = max(grid_left + grid_width, horizontal_label_rect.right() + 1) + _OUTER_MARGIN
    image_height = max(grid_top + grid_height, vertical_label_rect.bottom() + 1) + _OUTER_MARGIN
    return ExportLayout(
        CELL_SIZE, grid_left, grid_top, grid_width, grid_height,
        image_width, image_height, horizontal_arrow_y, vertical_arrow_x,
        horizontal_label_rect, vertical_label_rect, width_label, height_label,
        design_left, design_top, design_width, design_height,
    )


def _paint_dimensions(painter: QPainter, layout: ExportLayout) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.setPen(QPen(QColor("#000000"), 1))
    painter.setBrush(QColor("#000000"))
    left, top = layout.design_left, layout.design_top
    right, bottom = left + layout.design_width, top + layout.design_height
    y, x = layout.horizontal_arrow_y, layout.vertical_arrow_x

    if layout.has_design:
        # Extension lines stop just before the actual design's outer edges.
        for edge in (left, right):
            painter.drawLine(edge, y - 6, edge, top - 5)
        for edge in (top, bottom):
            painter.drawLine(x - 6, edge, left - 5, edge)
        painter.drawLine(left, y, right, y)
        painter.drawLine(x, top, x, bottom)
        head = 7
        for points in (
            [(left, y), (left + head, y - 3), (left + head, y + 3)],
            [(right, y), (right - head, y - 3), (right - head, y + 3)],
            [(x, top), (x - 3, top + head), (x + 3, top + head)],
            [(x, bottom), (x - 3, bottom - head), (x + 3, bottom - head)],
        ):
            painter.drawPolygon(QPolygon([QPoint(px, py) for px, py in points]))

    painter.setFont(_dimension_font())
    painter.drawText(layout.horizontal_label_rect, Qt.AlignmentFlag.AlignCenter, layout.width_label)
    rect = layout.vertical_label_rect
    painter.save()
    painter.translate(rect.left(), rect.top() + rect.height())
    painter.rotate(-90)
    painter.drawText(QRect(0, 0, rect.height(), rect.width()),
                     Qt.AlignmentFlag.AlignCenter, layout.height_label)
    painter.restore()


def _paint_bead(painter: QPainter, left: int, top: int, color: str) -> None:
    """Use the canvas's bead proportions while preserving the exact RGB fill."""
    size = CELL_SIZE
    outer = QRectF(left + size * 0.06, top + size * 0.06, size * 0.88, size * 0.88)
    hole_size = size * 0.36
    inset = (size - hole_size) / 2
    hole = QRectF(left + inset, top + inset, hole_size, hole_size)
    ring = QPainterPath()
    ring.setFillRule(Qt.FillRule.OddEvenFill)
    ring.addEllipse(outer)
    ring.addEllipse(hole)
    painter.fillPath(ring, QColor(color))


def render_png(
    design: PixelDesign, *, display_mode: str = "squares", show_grid: bool = True,
    piece_size_mm: float = DEFAULT_PIECE_SIZE_MM,
) -> QImage:
    """Draw the grid and the occupied design's measurements on a white image."""
    if display_mode not in ("squares", "beads"):
        raise ValueError("O modo de exibição deve ser 'squares' ou 'beads'.")
    if not isinstance(show_grid, bool):
        raise ValueError("A opção de grade precisa ser verdadeira ou falsa.")
    size_mm = validate_piece_size_mm(piece_size_mm)
    layout = export_layout(design, size_mm)
    image = QImage(layout.image_size, QImage.Format.Format_ARGB32_Premultiplied)
    if image.isNull():
        raise OSError("Não foi possível reservar memória para a imagem PNG.")
    image.fill(QColor("#FFFFFF"))
    density = round(CELL_SIZE * 1000 / size_mm)
    image.setDotsPerMeterX(density)
    image.setDotsPerMeterY(density)
    painter = QPainter(image)
    if not painter.isActive():
        raise OSError("Não foi possível desenhar a imagem PNG.")
    try:
        beads = display_mode == "beads"
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, beads)
        for row in range(design.height):
            for column in range(design.width):
                color = design.pixels[row * design.width + column]
                if color is None:
                    continue
                left = layout.grid_left + column * CELL_SIZE
                top = layout.grid_top + row * CELL_SIZE
                if beads:
                    _paint_bead(painter, left, top, color)
                else:
                    painter.fillRect(left, top, CELL_SIZE, CELL_SIZE, QColor(color))
        if show_grid:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setPen(QPen(QColor(GRID_COLOR), 1))
            for column in range(design.width + 1):
                x = layout.grid_left + column * CELL_SIZE
                painter.drawLine(x, layout.grid_top, x, layout.grid_top + layout.grid_height)
            for row in range(design.height + 1):
                y = layout.grid_top + row * CELL_SIZE
                painter.drawLine(layout.grid_left, y, layout.grid_left + layout.grid_width, y)
        _paint_dimensions(painter, layout)
    finally:
        painter.end()
    return image


def save_png(
    design: PixelDesign, path: str | Path, *, display_mode: str = "squares",
    show_grid: bool = True, piece_size_mm: float = DEFAULT_PIECE_SIZE_MM,
) -> None:
    """Write atomically so a failed export preserves an existing image."""
    image = render_png(design, display_mode=display_mode, show_grid=show_grid,
                       piece_size_mm=piece_size_mm)
    destination = QSaveFile(str(path))
    if not destination.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(f"Não foi possível criar o PNG: {destination.errorString()}")
    try:
        if not image.save(destination, "PNG"):
            raise OSError(f"Não foi possível gravar o PNG: {destination.errorString()}")
        if not destination.commit():
            raise OSError(f"Não foi possível concluir o PNG: {destination.errorString()}")
    except BaseException:
        if destination.isOpen():
            destination.cancelWriting()
        raise
