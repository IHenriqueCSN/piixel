"""Choose a drawing-wide color replacement without changing the design."""
from __future__ import annotations

from collections.abc import Mapping
from html import escape

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSizePolicy, QVBoxLayout,
)

from .model import PixelDesign, normalize_color
from .theme import BORDER, MUTED, PINK


class ReplaceColorDialog(QDialog):
    """Collect RGB colors; the editor applies the replacement after acceptance."""

    def __init__(self, design: PixelDesign, color_names: Mapping[str, str],
                 initial_target: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Substituir cor")
        self.setObjectName("replaceColorDialog")
        self.setMinimumWidth(440)
        self.setMaximumWidth(600)
        self.resize(480, 300)
        self._design = design
        self._last_valid = PINK
        try:
            initial_target = normalize_color(initial_target) or ""
            if initial_target:
                self._last_valid = initial_target
        except ValueError:
            initial_target = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)

        note = QLabel("Troque uma cor em todas as ocorrências do desenho.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {MUTED};")
        layout.addWidget(note)

        layout.addWidget(QLabel("Cor original"))
        self.source_combo = QComboBox()
        self.source_combo.setObjectName("replacementSource")
        self.source_combo.setAccessibleName("Cor original a substituir")
        self.source_combo.setIconSize(QSize(18, 18))
        self.source_combo.setMinimumContentsLength(20)
        self.source_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.source_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.source_combo.view().setTextElideMode(Qt.TextElideMode.ElideRight)
        self.source_combo.setPlaceholderText("Nenhuma cor utilizada")
        metrics = self.source_combo.fontMetrics()
        for color, count in sorted(design.counts().items(), key=lambda item: (-item[1], item[0])):
            name = color_names.get(color, "").strip()
            short_name = metrics.elidedText(name, Qt.TextElideMode.ElideRight, 170)
            quantity = f"{count} peça" if count == 1 else f"{count} peças"
            suffix = f"{color} · {quantity}"
            text = f"{short_name} · {suffix}" if name else suffix
            full_text = f"{name} · {suffix}" if name else suffix
            self.source_combo.addItem(self._color_icon(color), text, color)
            self.source_combo.setItemData(
                self.source_combo.count() - 1,
                f"<p>{escape(full_text)}</p>",
                Qt.ItemDataRole.ToolTipRole,
            )
        if self.source_combo.count():
            self.source_combo.setCurrentIndex(0)
        layout.addWidget(self.source_combo)

        layout.addWidget(QLabel("Nova cor"))
        target_row = QHBoxLayout()
        target_row.setSpacing(10)
        self.target_preview = QLabel()
        self.target_preview.setObjectName("replacementTargetPreview")
        self.target_preview.setFixedSize(36, 36)
        self.target_preview.setAccessibleName("Prévia da nova cor")
        target_row.addWidget(self.target_preview)
        self.target_edit = QLineEdit(initial_target)
        self.target_edit.setObjectName("replacementTarget")
        self.target_edit.setAccessibleName("Código hexadecimal da nova cor")
        self.target_edit.setPlaceholderText("#RRGGBB")
        self.target_edit.setMaxLength(9)
        target_row.addWidget(self.target_edit, 1)
        self.choose_button = QPushButton("Escolher cor…")
        self.choose_button.clicked.connect(self.choose_color)
        target_row.addWidget(self.choose_button)
        layout.addLayout(target_row)

        self.preview_label = QLabel()
        self.preview_label.setObjectName("replacementCount")
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)
        self.error_label = QLabel()
        self.error_label.setObjectName("replacementError")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        layout.addWidget(self.error_label)
        layout.addStretch(1)

        self.buttons = QDialogButtonBox()
        self.buttons.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        self.replace_button = self.buttons.addButton(
            "Substituir", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.replace_button.setObjectName("primary")
        self.replace_button.setDefault(True)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.source_combo.currentIndexChanged.connect(self._validate)
        self.target_edit.textChanged.connect(self._validate)
        self._validate()

    @staticmethod
    def _color_icon(color: str) -> QIcon:
        pixmap = QPixmap(18, 18)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(BORDER), 1))
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(1, 1, 16, 16, 4, 4)
        painter.end()
        return QIcon(pixmap)

    def source_color(self) -> str:
        value = normalize_color(self.source_combo.currentData())
        if value is None or self._design.counts().get(value, 0) == 0:
            raise ValueError("Selecione uma cor utilizada no desenho.")
        return value

    def target_color(self) -> str:
        value = normalize_color(self.target_edit.text().strip())
        if value is None:
            raise ValueError("Use uma cor no formato #RRGGBB.")
        return value

    def _validate(self, *_args) -> bool:
        try:
            source = self.source_color()
        except ValueError:
            source = None
        count = self._design.counts().get(source, 0)
        self.preview_label.setText(
            "Será substituída 1 peça." if count == 1 else f"Serão substituídas {count} peças."
        )
        try:
            target = self.target_color()
        except ValueError:
            target = None
        if target is not None:
            self._last_valid = target
            self.target_preview.setStyleSheet(
                f"background: {target}; border: 1px solid {BORDER}; border-radius: 7px;"
            )
        else:
            self.target_preview.setStyleSheet(
                f"background: transparent; border: 1px dashed {BORDER}; border-radius: 7px;"
            )

        if source is None:
            error = "Não há peças da cor selecionada para substituir."
        elif target is None:
            error = "Use uma cor no formato #RRGGBB."
        elif source == target:
            error = "Escolha uma nova cor diferente da original."
        else:
            error = ""
        self.error_label.setText(error)
        self.error_label.setVisible(bool(error))
        self.replace_button.setEnabled(not error)
        index = self.source_combo.currentIndex()
        self.source_combo.setToolTip(
            self.source_combo.itemData(index, Qt.ItemDataRole.ToolTipRole) or ""
        )
        return not error

    def choose_color(self):
        selected = QColorDialog.getColor(QColor(self._last_valid), self, "Escolher nova cor")
        if selected.isValid():
            self.target_edit.setText(selected.name(QColor.NameFormat.HexRgb).upper())

    def accept(self):
        if not self._validate():
            self.target_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        super().accept()
