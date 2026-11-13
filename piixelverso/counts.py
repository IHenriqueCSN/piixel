"""Contagem virtualizada: apenas as linhas visíveis são desenhadas pelo Qt."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QTableView,
)

from .materials import TRANSPARENT_OUTLINE, display_color, material_reference
from .model import is_transparent
from .theme import (
    BORDER, HOVER, INK, MUTED, WHITE, apply_themed_stylesheet, theme_color,
)

class _CountsModel(QAbstractTableModel):
    def __init__(self, color_names: dict[str, str], parent=None):
        super().__init__(parent)
        self._color_names = color_names
        self._rows: list[tuple[str, int, str]] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 2

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        color, count, name = self._rows[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return color, count, name
        if role == Qt.ItemDataRole.DisplayRole:
            return name if index.column() == 0 else f"{count:,}".replace(",", ".")
        if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleTextRole):
            return f"{name} · {material_reference(color)} · {count:,} peças".replace(",", ".")
        return None

    def set_counts(self, counts: dict[str, int]):
        rows = [
            (color, count, self._color_names.get(color, "Personalizada"))
            for color, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


class _CountsDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        payload = index.data(Qt.ItemDataRole.UserRole)
        if payload is None:
            return
        color, count, name = payload
        rect = option.rect
        view = self.parent()
        hovered = getattr(view, "_hover_row", -1) == index.row()
        hovered = hovered or bool(option.state & QStyle.StateFlag.State_MouseOver)

        painter.save()
        painter.setClipRect(rect)
        painter.fillRect(rect, QColor(theme_color("hover" if hovered else "white")))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if index.column() == 0:
            painter.setPen(QPen(QColor(
                TRANSPARENT_OUTLINE if is_transparent(color) else BORDER
            ), 2 if is_transparent(color) else 1))
            painter.setBrush(QColor(display_color(color)))
            painter.drawRoundedRect(QRect(rect.x() + 1, rect.y() + 12, 27, 27), 6, 6)

            name_font = QFont(option.font)
            name_font.setPixelSize(12)
            name_font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(name_font)
            painter.setPen(QColor(theme_color("ink")))
            available = max(0, rect.width() - 42)
            label = painter.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, available)
            painter.drawText(rect.x() + 40, rect.y() + 22, label)

            hex_font = QFont(option.font)
            hex_font.setPixelSize(10)
            hex_font.setWeight(QFont.Weight.Normal)
            painter.setFont(hex_font)
            painter.setPen(QColor(theme_color("muted")))
            painter.drawText(rect.x() + 40, rect.y() + 38, material_reference(color))
        else:
            count_font = QFont(option.font)
            count_font.setPixelSize(14)
            count_font.setWeight(QFont.Weight.Bold)
            painter.setFont(count_font)
            painter.setPen(QColor(theme_color("ink")))
            painter.drawText(
                rect.adjusted(0, 0, -1, 0),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{count:,}".replace(",", "."),
            )

        painter.setPen(QPen(QColor(theme_color("border")), 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        painter.restore()


class ColorCountsView(QTableView):
    """Tabela de contagens sem criar um QWidget para cada cor do design."""

    color_selected = Signal(str)

    def __init__(self, color_names: dict[str, str], parent=None):
        super().__init__(parent)
        self._hover_row = -1
        self._counts_model = _CountsModel(color_names, self)
        self.setModel(self._counts_model)
        self.setItemDelegate(_CountsDelegate(self))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        apply_themed_stylesheet(
            self, f"QTableView {{ background: {WHITE}; border: none; }}"
        )

        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(52)
        self.verticalHeader().setMinimumSectionSize(52)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().hide()
        self.horizontalHeader().setStretchLastSection(False)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(1, 60)
        self.clicked.connect(self._select_color)

    def set_counts(self, counts: dict[str, int]):
        self._hover_row = -1
        self._counts_model.set_counts(counts)
        self.viewport().update()

    def _select_color(self, index):
        payload = index.data(Qt.ItemDataRole.UserRole)
        if payload is not None:
            self.color_selected.emit(payload[0])

    def mouseMoveEvent(self, event):
        row = self.rowAt(event.position().toPoint().y())
        if row != self._hover_row:
            self._hover_row = row
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_row = -1
        self.viewport().update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._counts_model.rowCount() != 0:
            return
        painter = QPainter(self.viewport())
        painter.setPen(QColor(theme_color("muted")))
        font = QFont(self.font())
        font.setPixelSize(12)
        painter.setFont(font)
        painter.drawText(
            self.viewport().rect().adjusted(12, 36, -12, -12),
            Qt.AlignmentFlag.AlignHCenter
            | Qt.AlignmentFlag.AlignTop
            | Qt.TextFlag.TextWordWrap,
            "Sua criação começa aqui.\n\n"
            "Escolha uma cor e pinte a grade para ver a quantidade de cada peça.",
        )
        painter.end()
