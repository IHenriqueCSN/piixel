"""Choose a session color, with explicit opt-in for a reusable named color."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from .model import normalize_color
from .theme import BORDER, MUTED


class CustomColorDialog(QDialog):
    def __init__(self, initial_color: str | QColor = "#E7794B", parent=None,
                 *, name: str = "", save_for_future: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Cor personalizada")
        self.setMinimumWidth(420)
        if isinstance(initial_color, QColor):
            initial_color = initial_color.name()
        self._last_valid = normalize_color(initial_color) or "#E7794B"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        color_row = QHBoxLayout()
        self.preview = QLabel()
        self.preview.setObjectName("customColorPreview")
        self.preview.setFixedSize(52, 52)
        self.preview.setAccessibleName("Prévia da cor personalizada")
        color_row.addWidget(self.preview)
        self.hex_edit = QLineEdit(self._last_valid)
        self.hex_edit.setObjectName("customColorHex")
        self.hex_edit.setAccessibleName("Código hexadecimal da cor")
        self.hex_edit.setMaxLength(9)
        self.hex_edit.setPlaceholderText("#RRGGBB")
        color_row.addWidget(self.hex_edit, 1)
        self.choose_button = QPushButton("Escolher cor…")
        self.choose_button.clicked.connect(self.choose_color)
        color_row.addWidget(self.choose_button)
        layout.addLayout(color_row)

        self.error_label = QLabel("Use uma cor no formato #RRGGBB.")
        self.error_label.setObjectName("customColorError")
        self.error_label.setStyleSheet(f"color: {MUTED};")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        self.save_checkbox = QCheckBox("Salvar para próximas sessões")
        self.save_checkbox.setObjectName("saveColorForFuture")
        self.save_checkbox.setChecked(save_for_future)
        layout.addWidget(self.save_checkbox)
        form = QFormLayout()
        self.name_edit = QLineEdit(name)
        self.name_edit.setObjectName("customColorName")
        self.name_edit.setAccessibleName("Nome opcional da cor")
        self.name_edit.setMaxLength(80)
        self.name_edit.setPlaceholderText("Ex.: Rosa neon")
        self.name_edit.setEnabled(save_for_future)
        form.addRow("Nome (opcional)", self.name_edit)
        layout.addLayout(form)
        self.save_checkbox.toggled.connect(self.name_edit.setEnabled)

        note = QLabel("Sem marcar essa opção, a cor ficará disponível apenas nesta sessão.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        layout.addWidget(note)

        self.buttons = QDialogButtonBox()
        self.buttons.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        self.add_button = self.buttons.addButton("Adicionar cor", QDialogButtonBox.ButtonRole.AcceptRole)
        self.add_button.setDefault(True)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.hex_edit.textChanged.connect(self._validate_color)
        self._validate_color()

    def _validate_color(self, *_args):
        try:
            value = normalize_color(self.hex_edit.text().strip())
            if value is None:
                raise ValueError("A cor precisa ter um valor RGB.")
        except ValueError:
            self.error_label.show()
            self.add_button.setEnabled(False)
            return
        self._last_valid = value
        self.preview.setStyleSheet(
            f"background: {value}; border: 1px solid {BORDER}; border-radius: 8px;"
        )
        self.error_label.hide()
        self.add_button.setEnabled(True)

    def choose_color(self):
        selected = QColorDialog.getColor(QColor(self._last_valid), self, "Escolher cor")
        if selected.isValid():
            self.hex_edit.setText(selected.name(QColor.NameFormat.HexRgb).upper())

    def color_value(self) -> str:
        value = normalize_color(self.hex_edit.text().strip())
        if value is None:
            raise ValueError("A cor precisa ter um valor RGB.")
        return value

    def save_for_future(self) -> bool:
        return self.save_checkbox.isChecked()

    def color_name(self) -> str:
        return self.name_edit.text().strip() if self.save_for_future() else ""

    def accept(self):
        try:
            self.color_value()
        except ValueError:
            self._validate_color()
            self.hex_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        super().accept()
