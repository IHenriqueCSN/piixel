"""Choose a drawing-wide color replacement without changing the design."""
from __future__ import annotations

from collections.abc import Mapping
from html import escape

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QLabel, QSizePolicy, QVBoxLayout,
)

from .materials import TRANSPARENT_OUTLINE, display_color, material_reference
from .model import PixelDesign, is_transparent, normalize_color
from .theme import BORDER, MUTED, PINK


class ReplaceColorDialog(QDialog):
    """Collect palette materials; the editor applies replacement after acceptance."""

    def __init__(self, design: PixelDesign, color_names: Mapping[str, str],
                 initial_target: str, parent=None, *,
                 target_colors: Mapping[str, str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Substituir cor")
        self.setObjectName("replaceColorDialog")
        self.setMinimumWidth(440)
        self.setMaximumWidth(600)
        self.resize(480, 300)
        self._design = design
        self._color_names = color_names
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
            suffix = f"{material_reference(color)} · {quantity}"
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
        self.target_combo = QComboBox()
        self.target_combo.setObjectName("replacementTarget")
        self.target_combo.setAccessibleName("Nova cor para substituir")
        self.target_combo.setIconSize(QSize(18, 18))
        self.target_combo.setMinimumContentsLength(20)
        self.target_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.target_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.target_combo.view().setTextElideMode(Qt.TextElideMode.ElideRight)
        self.target_combo.setPlaceholderText("Selecione uma cor")
        self.target_combo.addItem("Escolher cor personalizada…", None)
        for color, name in (target_colors if target_colors is not None else color_names).items():
            value = normalize_color(color)
            if value is not None:
                self._add_target_color(value, name)
        if initial_target:
            index = self._add_target_color(initial_target, color_names.get(initial_target, "Personalizada"))
            self.target_combo.setCurrentIndex(index)
        elif self.target_combo.count() > 1:
            self.target_combo.setCurrentIndex(0)
        else:
            self.target_combo.setCurrentIndex(-1)
        layout.addWidget(self.target_combo)

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
        self.target_combo.currentIndexChanged.connect(self._validate)
        self.target_combo.activated.connect(self._target_activated)
        self._validate()

    def _add_target_color(self, color: str, name: str) -> int:
        """Insert before the custom-color action, reusing matching materials."""
        existing = self.target_combo.findData(color)
        if existing >= 0:
            return existing
        name = name.strip()
        short_name = self.target_combo.fontMetrics().elidedText(
            name, Qt.TextElideMode.ElideRight, 240
        )
        reference = material_reference(color)
        text = f"{short_name} · {reference}" if name else reference
        full_text = f"{name} · {reference}" if name else reference
        index = self.target_combo.count() - 1
        self.target_combo.insertItem(index, self._color_icon(color), text, color)
        self.target_combo.setItemData(
            index, f"<p>{escape(full_text)}</p>", Qt.ItemDataRole.ToolTipRole
        )
        return index

    def _target_activated(self, _index: int):
        if self.target_combo.currentData() is None:
            self.choose_color()

    @staticmethod
    def _color_icon(color: str) -> QIcon:
        pixmap = QPixmap(18, 18)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(
            TRANSPARENT_OUTLINE if is_transparent(color) else BORDER
        ), 2 if is_transparent(color) else 1))
        painter.setBrush(QColor(display_color(color)))
        painter.drawRoundedRect(1, 1, 16, 16, 4, 4)
        painter.end()
        return QIcon(pixmap)

    def source_color(self) -> str:
        value = normalize_color(self.source_combo.currentData())
        if value is None or self._design.counts().get(value, 0) == 0:
            raise ValueError("Selecione uma cor utilizada no desenho.")
        return value

    def target_color(self) -> str:
        value = normalize_color(self.target_combo.currentData())
        if value is None:
            raise ValueError("Selecione uma nova cor ou escolha uma cor personalizada.")
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

        if source is None:
            error = "Não há peças da cor selecionada para substituir."
        elif target is None:
            error = "Selecione uma nova cor ou escolha uma cor personalizada."
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
        self.target_combo.setToolTip(
            self.target_combo.currentData(Qt.ItemDataRole.ToolTipRole) or ""
        )
        return not error

    def choose_color(self):
        initial = QColor(display_color(self._last_valid))
        selected = QColorDialog.getColor(initial, self, "Escolher nova cor")
        if selected.isValid():
            value = selected.name(QColor.NameFormat.HexRgb).upper()
            index = self._add_target_color(value, self._color_names.get(value, "Personalizada"))
        else:
            index = self.target_combo.findData(self._last_valid)
        self.target_combo.setCurrentIndex(index)

    def accept(self):
        if not self._validate():
            self.target_combo.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        super().accept()
