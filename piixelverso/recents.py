"""Cached design previews and paths, without touching the recent files on disk."""
from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QLabel, QListView, QStackedWidget,
    QStyledItemDelegate, QStyle, QVBoxLayout, QWidget,
)

from .theme import BORDER, HOVER, INK, MUTED, PINK, WHITE

if TYPE_CHECKING:
    from .preferences import RecentFile


class _RecentFilesModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        entry, preview = self.rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return entry.name
        if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleTextRole):
            return f"{entry.name}\n{entry.path}"
        if role == Qt.ItemDataRole.UserRole:
            return entry
        if role == Qt.ItemDataRole.DecorationRole:
            return preview
        return None

    def set_files(self, entries):
        rows = []
        for entry in entries:
            preview = QPixmap()
            if entry.thumbnail:
                preview.loadFromData(entry.thumbnail, "PNG")
            rows.append((entry, preview))
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()


class _RecentDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(280, 96)

    def paint(self, painter: QPainter, option, index):
        entry = index.data(Qt.ItemDataRole.UserRole)
        if entry is None:
            return
        rect = option.rect
        active = bool(option.state & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver))
        painter.save()
        painter.setClipRect(rect)
        painter.fillRect(rect, QColor(HOVER if active else WHITE))
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(rect.x(), rect.y() + 8, 3, rect.height() - 16, QColor(PINK))

        thumbnail_rect = QRect(rect.x() + 10, rect.y() + 15, 66, 66)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(BORDER), 1))
        painter.setBrush(QColor(WHITE))
        painter.drawRoundedRect(thumbnail_rect, 7, 7)
        preview = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(preview, QPixmap) and not preview.isNull():
            scaled = preview.scaled(58, 58, Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.FastTransformation)
            x = thumbnail_rect.center().x() - scaled.width() // 2
            y = thumbnail_rect.center().y() - scaled.height() // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.setPen(QPen(QColor(MUTED), 1.3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(thumbnail_rect.adjusted(21, 17, -20, -17), 2, 2)
            painter.drawLine(thumbnail_rect.x() + 27, thumbnail_rect.y() + 28,
                             thumbnail_rect.x() + 40, thumbnail_rect.y() + 28)
            painter.drawLine(thumbnail_rect.x() + 27, thumbnail_rect.y() + 35,
                             thumbnail_rect.x() + 40, thumbnail_rect.y() + 35)

        text_rect = QRect(rect.x() + 89, rect.y() + 20, max(1, rect.width() - 103), 22)
        font = QFont(option.font)
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor(INK))
        name = painter.fontMetrics().elidedText(entry.name, Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        font.setPixelSize(10)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(QColor(MUTED))
        path = painter.fontMetrics().elidedText(entry.path, Qt.TextElideMode.ElideMiddle, text_rect.width())
        painter.drawText(text_rect.translated(0, 26), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, path)
        painter.setPen(QPen(QColor(BORDER), 1))
        painter.drawLine(rect.x() + 10, rect.bottom(), rect.right() - 10, rect.bottom())
        painter.restore()


class _RecentList(QListView):
    file_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.clicked.connect(self._request)

    def _request(self, index):
        entry = index.data(Qt.ItemDataRole.UserRole)
        if entry is not None:
            self.file_requested.emit(entry.path)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.currentIndex().isValid():
                self._request(self.currentIndex())
            event.accept()
            return
        super().keyPressEvent(event)


class RecentFilesPanel(QFrame):
    file_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("recentFilesPanel")
        self.setAccessibleName("Últimos arquivos modificados")
        self.setMinimumWidth(340)
        self.setStyleSheet(f"""
            QFrame#recentFilesPanel {{ background: {WHITE}; border: 1px solid {BORDER}; border-radius: 15px; }}
            QLabel#recentTitle {{ color: {INK}; font-size: 16px; font-weight: 700; }}
            QLabel#recentEmpty {{ color: {MUTED}; font-size: 12px; }}
            QListView#recentFiles {{ background: {WHITE}; border: 0; outline: none; }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 22, 18, 16)
        layout.setSpacing(14)
        title = QLabel("Últimos arquivos modificados")
        title.setObjectName("recentTitle")
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        layout.addWidget(title)

        self.view = _RecentList()
        self.view.setObjectName("recentFiles")
        self.view.setAccessibleName("Arquivos recentes: nome, miniatura e caminho")
        self.view.setMouseTracking(True)
        self.view.setUniformItemSizes(True)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setItemDelegate(_RecentDelegate(self.view))
        self._model = _RecentFilesModel(self)
        self.view.setModel(self._model)
        self.view.file_requested.connect(self.file_requested.emit)

        self._stack = QStackedWidget()
        self._stack.addWidget(self.view)
        empty = QLabel("Os arquivos abertos ou salvos aparecerão aqui.")
        empty.setObjectName("recentEmpty")
        empty.setTextFormat(Qt.TextFormat.PlainText)
        empty.setWordWrap(True)
        empty.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        empty.setContentsMargins(4, 20, 4, 0)
        self._stack.addWidget(empty)
        self._stack.setCurrentIndex(1)
        layout.addWidget(self._stack, 1)

    def set_files(self, entries: Sequence[RecentFile]):
        self._model.set_files(entries)
        self._stack.setCurrentIndex(0 if self._model.rowCount() else 1)
