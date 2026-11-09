"""Choose canvas dimensions and where existing pieces should stay."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QSpinBox, QVBoxLayout,
)

from .model import PixelDesign
from .resize import ANCHOR_LABELS, MAX_CANVAS_SIZE, MIN_CANVAS_SIZE, count_cropped_pixels
from .theme import INK, MUTED


class ResizeCanvasDialog(QDialog):
    def __init__(self, design: PixelDesign, parent=None):
        super().__init__(parent)
        self._design = design.clone()
        self.setWindowTitle("Redimensionar prancheta")
        self.setMinimumWidth(430)
        self.setMaximumWidth(520)
        self.resize(460, 355)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        intro = QLabel("Altere o tamanho da prancheta mantendo o tamanho de cada peça.")
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {MUTED};")
        layout.addWidget(intro)
        current = QLabel(f"Tamanho atual: {design.width} × {design.height} células")
        layout.addWidget(current)

        form = QFormLayout()
        form.setSpacing(12)
        self.width_input, self.height_input = QSpinBox(), QSpinBox()
        for field, value, name in (
            (self.width_input, design.width, "Largura da prancheta em colunas"),
            (self.height_input, design.height, "Altura da prancheta em linhas"),
        ):
            field.setRange(MIN_CANVAS_SIZE, MAX_CANVAS_SIZE)
            field.setValue(value)
            field.setKeyboardTracking(False)
            field.setAccessibleName(name)
        form.addRow("Largura (colunas)", self.width_input)
        form.addRow("Altura (linhas)", self.height_input)
        self.anchor_combo = QComboBox()
        self.anchor_combo.setAccessibleName("Posição do desenho ao redimensionar")
        for key, text in ANCHOR_LABELS.items():
            self.anchor_combo.addItem(text, key)
        self.anchor_combo.setCurrentIndex(self.anchor_combo.findData("center"))
        form.addRow("Posição do desenho", self.anchor_combo)
        layout.addLayout(form)

        self.crop_label = QLabel()
        self.crop_label.setTextFormat(Qt.TextFormat.PlainText)
        self.crop_label.setWordWrap(True)
        self.crop_label.setStyleSheet(f"color: {INK};")
        layout.addWidget(self.crop_label)
        note = QLabel("Novos espaços ficam vazios. Você poderá desfazer o redimensionamento.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        layout.addWidget(note)
        layout.addStretch(1)
        self.buttons = QDialogButtonBox()
        self.buttons.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        self.resize_button = self.buttons.addButton("Redimensionar", QDialogButtonBox.ButtonRole.AcceptRole)
        self.resize_button.setObjectName("primary")
        self.resize_button.setDefault(True)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.width_input.valueChanged.connect(self._update_summary)
        self.height_input.valueChanged.connect(self._update_summary)
        self.anchor_combo.currentIndexChanged.connect(self._update_summary)
        self._update_summary()

    def target_width(self) -> int:
        return self.width_input.value()

    def target_height(self) -> int:
        return self.height_input.value()

    def anchor(self) -> str:
        return self.anchor_combo.currentData()

    def _update_summary(self, *_args):
        count = count_cropped_pixels(self._design, self.target_width(), self.target_height(), self.anchor())
        if count:
            text = "1 peça ficará fora da nova prancheta." if count == 1 else f"{count} peças ficarão fora da nova prancheta."
        else:
            text = "Todas as peças serão preservadas."
        self.crop_label.setText(text)
        self.resize_button.setEnabled(
            (self.target_width(), self.target_height()) != (self._design.width, self._design.height)
        )

    def accept(self):
        self.width_input.interpretText()
        self.height_input.interpretText()
        self._update_summary()
        if self.resize_button.isEnabled():
            super().accept()
