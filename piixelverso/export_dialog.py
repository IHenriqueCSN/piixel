"""Preview the PNG appearance before choosing a destination file."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame,
    QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout,
)

from .model import PixelDesign
from .png_export import format_mm, measurement_labels, render_png
from .preferences import validate_piece_size_mm
from .theme import BORDER, MUTED, WHITE


class ExportPngDialog(QDialog):
    """Choose visual options without changing the drawing or preferences."""

    def __init__(self, design: PixelDesign, *, piece_size_mm=5.0,
                 display_mode="squares", show_grid=True, parent=None):
        super().__init__(parent)
        if display_mode not in ("squares", "beads"):
            raise ValueError("Escolha quadradinhos ou rosquinhas para exportar.")
        self._piece_size_mm = validate_piece_size_mm(piece_size_mm)
        self._design = design.clone()
        width, height = measurement_labels(self._design, self._piece_size_mm)
        self._preview_image = QImage()
        self._preview_ready = False
        self.setWindowTitle("Exportar como PNG")
        self.setObjectName("exportPngDialog")
        self.setMinimumWidth(500)
        self.setMaximumWidth(600)
        self.resize(560, 590)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        intro = QLabel("Escolha a aparência da imagem antes de salvar.")
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {MUTED};")
        layout.addWidget(intro)

        options = QHBoxLayout()
        options.setSpacing(12)
        options.addWidget(QLabel("Peças"))
        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("exportPngMode")
        self.mode_combo.setAccessibleName("Exibição das peças no PNG")
        self.mode_combo.addItem("Quadradinhos", "squares")
        self.mode_combo.addItem("Rosquinhas (hama beads)", "beads")
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(display_mode))
        options.addWidget(self.mode_combo, 1)
        self.grid_checkbox = QCheckBox("Mostrar grade")
        self.grid_checkbox.setObjectName("exportPngGrid")
        self.grid_checkbox.setChecked(bool(show_grid))
        options.addWidget(self.grid_checkbox)
        layout.addLayout(options)

        self.dimensions_label = QLabel(f"Largura: {width}  ·  Altura: {height}")
        self.dimensions_label.setObjectName("sectionTitle")
        self.dimensions_label.setWordWrap(True)
        layout.addWidget(self.dimensions_label)

        self.piece_size_label = QLabel(
            f"{format_mm(self._piece_size_mm)} por peça · altere em Configurações"
        )
        self.piece_size_label.setWordWrap(True)
        self.piece_size_label.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        layout.addWidget(self.piece_size_label)

        preview_heading = QLabel("Prévia do PNG")
        preview_heading.setObjectName("eyebrow")
        layout.addWidget(preview_heading)

        preview_frame = QFrame()
        preview_frame.setObjectName("exportPngPreviewFrame")
        preview_frame.setStyleSheet(
            f"QFrame#exportPngPreviewFrame {{ background: {WHITE}; "
            f"border: 1px solid {BORDER}; border-radius: 8px; }}"
        )
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        self.preview_label = QLabel()
        self.preview_label.setObjectName("exportPngPreview")
        self.preview_label.setAccessibleName("Prévia da imagem PNG com medidas")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setFixedHeight(280)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.preview_label.installEventFilter(self)
        preview_layout.addWidget(self.preview_label)
        layout.addWidget(preview_frame)

        note = QLabel("As medidas vão de uma extremidade à outra do desenho, sem contar as margens vazias.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        layout.addWidget(note)

        self.error_label = QLabel()
        self.error_label.setObjectName("exportPngError")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        self.error_label.hide()
        layout.addWidget(self.error_label)
        layout.addStretch(1)

        self.buttons = QDialogButtonBox()
        self.buttons.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        self.export_button = self.buttons.addButton(
            "Escolher onde salvar…", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.export_button.setObjectName("primary")
        self.export_button.setDefault(True)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.mode_combo.currentIndexChanged.connect(self._update_preview)
        self.grid_checkbox.toggled.connect(self._update_preview)
        self._update_preview()

    def display_mode(self) -> str:
        return self.mode_combo.currentData()

    def show_grid(self) -> bool:
        return self.grid_checkbox.isChecked()

    def piece_size_mm(self) -> float:
        return self._piece_size_mm

    def _update_preview(self, *_args):
        try:
            image = render_png(
                self._design, display_mode=self.display_mode(), show_grid=self.show_grid(),
                piece_size_mm=self.piece_size_mm(),
            )
            if image.isNull():
                raise RuntimeError("A imagem está vazia.")
        except (ValueError, RuntimeError, OSError) as error:
            self._preview_ready = False
            self._preview_image = QImage()
            self.preview_label.clear()
            self.preview_label.setText("Prévia indisponível")
            self.error_label.setText(f"Não foi possível gerar a prévia.\n{error}")
            self.error_label.show()
            self.export_button.setEnabled(False)
            return

        # Keep only a small preview, even when the drawing has 128 × 128 cells.
        self._preview_image = image.scaled(
            QSize(560, 280), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_ready = True
        self.error_label.hide()
        self.export_button.setEnabled(True)
        self._fit_preview()

    def _fit_preview(self):
        if not self._preview_image.isNull():
            pixmap = QPixmap.fromImage(self._preview_image).scaled(
                self.preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.preview_label.setPixmap(pixmap)

    def eventFilter(self, watched, event):
        if watched is self.preview_label and event.type() == QEvent.Type.Resize:
            self._fit_preview()
        return super().eventFilter(watched, event)

    def accept(self):
        if self._preview_ready:
            super().accept()
