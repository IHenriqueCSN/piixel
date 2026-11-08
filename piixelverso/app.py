"""Piixelverso: a local, native Qt pixel-art workshop."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QColorDialog, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from .canvas import PixelCanvas
from .counts import ColorCountsView
from .format import DesignFormatError, load_design, save_design
from .model import PixelDesign, validate_name


PALETTE = [
    ("Carvão", "#293C37"), ("Ardósia", "#66766F"), ("Névoa", "#B5BFB7"), ("Neve", "#FFFFFF"),
    ("Terracota", "#C75B40"), ("Coral", "#E7794B"), ("Pêssego", "#F4AE87"), ("Areia", "#F4D8B2"),
    ("Mostarda", "#D5A039"), ("Sol", "#F0C65B"), ("Lima", "#B6CD70"), ("Creme", "#F8EFCA"),
    ("Floresta", "#245448"), ("Musgo", "#54856A"), ("Folha", "#85B48D"), ("Menta", "#BCDCC6"),
    ("Oceano", "#285A78"), ("Azul", "#548DB0"), ("Céu", "#9DC4D5"), ("Gelo", "#D3E8EA"),
    ("Ameixa", "#734E70"), ("Lavanda", "#A58CB4"), ("Rosa", "#D792A5"), ("Blush", "#EECBD2"),
]
COLOR_NAMES = {color: name for name, color in PALETTE}

STYLE = """
QWidget { color: #293C37; font-family: 'Segoe UI', 'DejaVu Sans', sans-serif; font-size: 12px; }
QMainWindow, #root { background: #F2F4F1; }
#topbar { background: #FFFFFF; border-bottom: 1px solid #DFE5DF; }
#brand { font-size: 23px; font-weight: 800; letter-spacing: -1px; }
#edition { color: #7F8C84; font-size: 10px; font-weight: 700; letter-spacing: 2px; }
#localBadge { color: #477362; background: #EFF5F0; border-radius: 12px; padding: 6px 12px; font-size: 11px; }
#projectBar { background: #F2F4F1; }
#eyebrow { color: #8A968E; font-size: 9px; font-weight: 700; letter-spacing: 2px; }
#designName { background: transparent; border: 0; border-radius: 4px; padding: 1px 0; font-size: 23px; font-weight: 650; }
#designName:focus { background: #FFFFFF; }
#card, #editorCard { background: #FFFFFF; border: 1px solid #DDE4DD; border-radius: 12px; }
#sectionTitle { font-weight: 700; font-size: 13px; }
#muted { color: #849088; font-size: 11px; }
#tiny { color: #8A968E; font-size: 10px; }
#canvasStage { background: #E9EEE8; border: 0; }
#editorHeading { font-weight: 650; font-size: 12px; }
#canvasFooter { background: #FAFBF9; border-top: 1px solid #E3E8E1; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; }
QPushButton { background: #FFFFFF; border: 1px solid #DCE3DC; border-radius: 7px; padding: 9px 13px; font-weight: 600; }
QPushButton:hover { background: #F3F6F1; border-color: #ADBDB0; }
QPushButton:pressed { background: #E8EFE7; }
QPushButton:disabled { color: #B9C1BB; border-color: #E9EDE7; }
QPushButton#primary { color: #FFFFFF; background: #285B49; border-color: #285B49; }
QPushButton#primary:hover { background: #1D4939; }
QPushButton#tool { text-align: left; padding: 10px 12px; font-weight: 500; }
QPushButton#tool:checked { background: #EEF4EC; color: #285B49; border: 1px solid #88AB92; font-weight: 700; }
QPushButton#iconButton { padding: 5px; border: 0; background: transparent; }
QPushButton#iconButton:hover { background: #EDF2EA; }
QPushButton#swatch { padding: 0; border-radius: 5px; }
#activeColor { border: 1px solid #DDE4DD; border-radius: 8px; background: #FAFBF8; }
#bigNumber { font-size: 44px; font-weight: 700; letter-spacing: -2px; }
#statBox { background: #F1F6EF; border-radius: 10px; }
#hint { color: #78887E; background: #F6F8F3; border-radius: 8px; padding: 12px; font-size: 11px; }
#status { color: #7D8B82; font-size: 10px; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { background: #F1F4EE; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: #C4CEC2; border-radius: 3px; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSlider::groove:horizontal { background: #DCE5D9; height: 4px; border-radius: 2px; }
QSlider::handle:horizontal { background: #285B49; width: 12px; margin: -4px 0; border-radius: 6px; }
QCheckBox { color: #718078; font-size: 11px; spacing: 6px; }
QLineEdit, QSpinBox { border: 1px solid #D0DACE; border-radius: 6px; padding: 8px; background: white; }
QDialog { background: #F8FAF5; }
QToolTip { background: #293C37; color: white; padding: 6px; border: 0; }
"""


def icon(kind: str, color="#52685B") -> QIcon:
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if kind == "pencil":
        p.drawPolygon([QPoint(x, y) for x, y in [(5, 19), (7, 13), (16, 4), (20, 8), (11, 17)]])
        p.drawLine(14, 6, 18, 10)
    elif kind == "eraser":
        p.drawLine(5, 16, 14, 5); p.drawLine(14, 5, 20, 10)
        p.drawLine(20, 10, 12, 20); p.drawLine(12, 20, 8, 20); p.drawLine(8, 20, 5, 16)
        p.drawLine(9, 12, 16, 17); p.drawLine(12, 20, 21, 20)
    elif kind == "picker":
        p.drawLine(7, 14, 16, 5); p.drawLine(11, 18, 20, 9)
        p.drawLine(16, 5, 20, 9); p.drawLine(7, 14, 6, 20)
        p.drawLine(6, 20, 11, 18); p.drawLine(13, 5, 20, 12)
    elif kind in ("undo", "redo"):
        if kind == "redo":
            p.translate(24, 0); p.scale(-1, 1)
        p.drawArc(6, 7, 14, 14, -60 * 16, 240 * 16)
        p.drawLine(6, 7, 6, 13); p.drawLine(6, 13, 12, 13)
    elif kind == "save":
        p.drawRoundedRect(4, 4, 16, 16, 2, 2)
        p.drawRect(8, 4, 8, 6); p.drawRect(8, 14, 8, 6)
    elif kind == "folder":
        p.drawLine(3, 8, 3, 19); p.drawLine(3, 19, 21, 19)
        p.drawLine(21, 19, 21, 8); p.drawLine(21, 8, 12, 8)
        p.drawLine(12, 8, 10, 5); p.drawLine(10, 5, 3, 5); p.drawLine(3, 5, 3, 8)
    elif kind == "plus":
        p.drawLine(12, 5, 12, 19); p.drawLine(5, 12, 19, 12)
    elif kind == "fit":
        for x, y, sx, sy in [(4, 4, 1, 1), (20, 4, -1, 1), (4, 20, 1, -1), (20, 20, -1, -1)]:
            p.drawLine(x, y, x + 5 * sx, y); p.drawLine(x, y, x, y + 5 * sy)
    elif kind == "brand":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#E7794B"))
        for x, y in [(0, 0), (1, 0), (2, 0), (0, 1), (2, 1), (0, 2), (1, 2), (0, 3)]:
            p.drawRoundedRect(3 + x * 5, 2 + y * 5, 4, 4, 0.7, 0.7)
    p.end()
    return QIcon(pixmap)


def label(text, name=None):
    result = QLabel(text)
    if name:
        result.setObjectName(name)
    return result


def button(text, callback, name=None, symbol=None):
    result = QPushButton(text)
    if name:
        result.setObjectName(name)
    if symbol:
        result.setIcon(icon(symbol, "#FFFFFF" if name == "primary" else "#52685B"))
        result.setIconSize(QSize(18, 18))
    result.clicked.connect(callback)
    return result


class PixelCommand(QUndoCommand):
    def __init__(self, window, before, after, text="Pintar pixels"):
        super().__init__(text)
        self.window, self.before, self.after = window, before, after

    def apply(self, values):
        for index, color in values.items():
            self.window.design.pixels[index] = color
        self.window.refresh_design()

    def redo(self):
        self.apply(self.after)

    def undo(self):
        self.apply(self.before)


class RenameCommand(QUndoCommand):
    def __init__(self, window, name):
        super().__init__("Renomear design")
        self.window, self.before, self.after = window, window.design.name, name

    def redo(self):
        self.window.design.name = self.after
        self.window.refresh_design()

    def undo(self):
        self.window.design.name = self.before
        self.window.refresh_design()


class NewDesignDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Novo design")
        self.setMinimumWidth(360)
        form = QFormLayout(self)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(14)
        self.name = QLineEdit("Meu novo design")
        self.name.setMaxLength(120)
        self.width_input, self.height_input = QSpinBox(), QSpinBox()
        for field in (self.width_input, self.height_input):
            field.setRange(1, 128)
            field.setValue(32)
        form.addRow("Nome", self.name)
        form.addRow("Colunas", self.width_input)
        form.addRow("Linhas", self.height_input)
        note = label("Cada célula da grade corresponde a uma peça.", "muted")
        note.setWordWrap(True)
        form.addRow(note)
        buttons = QDialogButtonBox()
        buttons.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.addButton("Criar design", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.design = PixelDesign(name="Meu primeiro design")
        self.file_path: Path | None = None
        self.history = QUndoStack(self)
        self.history.setUndoLimit(300)
        self.setWindowIcon(icon("brand"))
        self.setMinimumSize(1120, 750)
        self.resize(1380, 900)
        self._swatches = {}
        self._custom_colors: list[str] = []
        self._counts_timer = QTimer(self)
        self._counts_timer.setSingleShot(True)
        self._counts_timer.timeout.connect(self.refresh_counts)
        self._build()
        self.history.indexChanged.connect(self._history_changed)
        self._shortcuts()
        self.refresh_design()
        self.select_color("#E7794B")
        self._history_changed()
        QTimer.singleShot(0, self.fit_canvas)

    def _build(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        topbar = QFrame(objectName="topbar")
        topbar.setFixedHeight(70)
        top = QHBoxLayout(topbar)
        top.setContentsMargins(28, 0, 28, 0)
        logo = QLabel()
        logo.setPixmap(icon("brand").pixmap(38, 38))
        top.addWidget(logo)
        top.addWidget(label("piixelverso", "brand"))
        top.addSpacing(16)
        top.addWidget(label("ATELIÊ DIGITAL", "edition"))
        top.addStretch()
        badge = label("●  Feito pixel por pixel", "localBadge")
        badge.setMaximumHeight(29)
        top.addWidget(badge)
        layout.addWidget(topbar)

        project_bar = QWidget(objectName="projectBar")
        project = QHBoxLayout(project_bar)
        project.setContentsMargins(28, 19, 28, 19)
        title = QVBoxLayout()
        title.setSpacing(3)
        title.addWidget(label("SEU ESPAÇO DE CRIAÇÃO", "eyebrow"))
        self.name_edit = QLineEdit(self.design.name)
        self.name_edit.setObjectName("designName")
        self.name_edit.setMaxLength(4096)
        self.name_edit.setToolTip("Clique para renomear o design")
        self.name_edit.setAccessibleName("Nome do design")
        self.name_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.name_edit.editingFinished.connect(self.rename_design)
        title.addWidget(self.name_edit)
        project.addLayout(title, 1)
        project.addSpacing(20)
        project.addWidget(button("Novo", self.new_design, symbol="plus"))
        project.addWidget(button("Abrir .pii", self.open_design, symbol="folder"))
        self.save_button = button("Salvar design", self.save, "primary", "save")
        self.save_button.setToolTip("Salvar design (Ctrl+S)")
        project.addWidget(self.save_button)
        layout.addWidget(project_bar)

        workspace = QHBoxLayout()
        workspace.setContentsMargins(28, 0, 28, 0)
        workspace.setSpacing(18)
        workspace.addWidget(self._left_panel())
        workspace.addWidget(self._editor(), 1)
        workspace.addWidget(self._materials())
        layout.addLayout(workspace, 1)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(29, 11, 29, 12)
        self.status_text = label("Tudo pronto para criar.", "status")
        bottom.addWidget(self.status_text)
        bottom.addStretch()
        bottom.addWidget(label("PIIXELVERSO  /  VERSÃO 0.1", "status"))
        layout.addLayout(bottom)

    def _left_panel(self):
        pane = QFrame(objectName="card")
        pane.setFixedWidth(215)
        contents = QVBoxLayout(pane)
        contents.setContentsMargins(17, 21, 17, 18)
        contents.setSpacing(10)
        contents.addWidget(label("Ferramentas", "sectionTitle"))
        contents.addSpacing(3)
        group = QButtonGroup(self)
        self.tool_buttons = {}
        for key, name, shortcut in [("pencil", "Lápis", "B"), ("eraser", "Borracha", "E"), ("picker", "Conta-gotas", "I")]:
            tool = button(f"{name}    {shortcut}", lambda checked=False, value=key: self.select_tool(value), "tool", key)
            tool.setCheckable(True)
            tool.setToolTip(f"{name} ({shortcut})")
            group.addButton(tool)
            self.tool_buttons[key] = tool
            contents.addWidget(tool)
        self.tool_buttons["pencil"].setChecked(True)
        contents.addSpacing(17)
        contents.addWidget(label("Paleta de cores", "sectionTitle"))
        contents.addWidget(label("Um universo de possibilidades.", "tiny"))
        self.palette_grid = QGridLayout()
        self.palette_grid.setHorizontalSpacing(8)
        self.palette_grid.setVerticalSpacing(8)
        for i, (name, color) in enumerate(PALETTE):
            self._add_swatch(color, name, i)
        contents.addLayout(self.palette_grid)
        contents.addSpacing(4)
        contents.addWidget(button("+  Cor personalizada", self.custom_color))
        active = QFrame(objectName="activeColor")
        active_layout = QHBoxLayout(active)
        active_layout.setContentsMargins(10, 10, 8, 10)
        self.active_swatch = QLabel()
        self.active_swatch.setFixedSize(30, 30)
        active_layout.addWidget(self.active_swatch)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(label("COR ATIVA", "eyebrow"))
        self.active_hex = label("#E7794B", "sectionTitle")
        text.addWidget(self.active_hex)
        active_layout.addLayout(text)
        contents.addWidget(active)
        contents.addStretch()
        tip = label("DICA DO ATELIÊ\n\nArraste para desenhar. Use o botão direito para apagar.", "hint")
        tip.setWordWrap(True)
        contents.addWidget(tip)
        return pane

    def _add_swatch(self, color, name, index):
        swatch = QPushButton()
        swatch.setObjectName("swatch")
        swatch.setFixedSize(36, 29)
        swatch.setToolTip(f"{name} · {color}")
        swatch.setAccessibleName(f"Selecionar cor {color}")
        swatch.clicked.connect(lambda checked=False, value=color: self.select_color(value))
        self._swatches[color] = swatch
        self.palette_grid.addWidget(swatch, index // 4, index % 4)

    def _editor(self):
        card = QFrame(objectName="editorCard")
        content = QVBoxLayout(card)
        content.setSpacing(0)
        content.setContentsMargins(1, 1, 1, 1)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(18, 12, 14, 12)
        toolbar.addWidget(label("Prancheta", "editorHeading"))
        self.dimensions = label("32 × 32", "muted")
        toolbar.addSpacing(8)
        toolbar.addWidget(self.dimensions)
        toolbar.addStretch()
        self.undo_button = button("", self.undo, "iconButton", "undo")
        self.undo_button.setToolTip("Desfazer (Ctrl+Z)")
        self.undo_button.setAccessibleName("Desfazer")
        self.redo_button = button("", self.redo, "iconButton", "redo")
        self.redo_button.setToolTip("Refazer (Ctrl+Shift+Z / Ctrl+Y)")
        self.redo_button.setAccessibleName("Refazer")
        toolbar.addWidget(self.undo_button)
        toolbar.addWidget(self.redo_button)
        content.addLayout(toolbar)
        self.canvas = PixelCanvas(self.design)
        self.canvas.changed.connect(self._canvas_changed)
        self.canvas.stroke_finished.connect(self._commit_stroke)
        self.canvas.color_picked.connect(self.pick_color)
        self.canvas.hovered.connect(lambda x, y: self.position_label.setText(f"COL {x+1:02d}   LIN {y+1:02d}"))
        self.viewport = QScrollArea()
        self.viewport.setObjectName("canvasStage")
        self.viewport.setWidget(self.canvas)
        self.canvas.setAutoFillBackground(False)
        self.viewport.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(self.viewport, 1)
        footer = QWidget(objectName="canvasFooter")
        controls = QHBoxLayout(footer)
        controls.setContentsMargins(15, 12, 15, 12)
        self.position_label = label("COL —   LIN —", "tiny")
        controls.addWidget(self.position_label)
        controls.addStretch()
        grid = QCheckBox("Grade")
        grid.setChecked(True)
        grid.toggled.connect(self.toggle_grid)
        controls.addWidget(grid)
        controls.addSpacing(9)
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(25, 250)
        self.zoom.setValue(100)
        self.zoom.setFixedWidth(85)
        self.zoom.setAccessibleName("Zoom da prancheta")
        self.zoom.valueChanged.connect(self.set_zoom)
        controls.addWidget(self.zoom)
        self.zoom_label = label("100%", "muted")
        self.zoom_label.setFixedWidth(36)
        controls.addWidget(self.zoom_label)
        fit = button("", self.fit_canvas, "iconButton", "fit")
        fit.setToolTip("Ajustar prancheta à janela")
        fit.setAccessibleName("Ajustar prancheta à janela")
        controls.addWidget(fit)
        content.addWidget(footer)
        return card

    def _materials(self):
        pane = QFrame(objectName="card")
        pane.setFixedWidth(258)
        contents = QVBoxLayout(pane)
        contents.setContentsMargins(19, 21, 19, 18)
        contents.setSpacing(13)
        contents.addWidget(label("Seu design em números", "sectionTitle"))
        contents.addWidget(label("Planeje cada peça da sua criação.", "tiny"))
        stat = QFrame(objectName="statBox")
        stat_layout = QVBoxLayout(stat)
        stat_layout.setContentsMargins(17, 13, 17, 16)
        stat_layout.setSpacing(0)
        self.total_label = label("0", "bigNumber")
        stat_layout.addWidget(self.total_label)
        stat_layout.addWidget(label("peças no design", "muted"))
        contents.addWidget(stat)
        summary = QHBoxLayout()
        self.color_total = label("0 cores usadas", "muted")
        self.empty_total = label("1.024 vazios", "muted")
        summary.addWidget(self.color_total)
        summary.addStretch()
        summary.addWidget(self.empty_total)
        contents.addLayout(summary)
        contents.addSpacing(4)
        columns = QHBoxLayout()
        columns.addWidget(label("COR / REFERÊNCIA", "eyebrow"))
        columns.addStretch()
        columns.addWidget(label("QTD.", "eyebrow"))
        contents.addLayout(columns)
        self.count_view = ColorCountsView(COLOR_NAMES)
        self.count_view.color_selected.connect(self.pick_color)
        contents.addWidget(self.count_view, 1)
        note = label("Cada quadradinho pintado conta como uma peça. Células vazias ficam fora da contagem.", "hint")
        note.setWordWrap(True)
        contents.addWidget(note)
        return pane

    def _shortcuts(self):
        for shortcut, callback in [
            (QKeySequence.StandardKey.New, self.new_design),
            (QKeySequence.StandardKey.Open, self.open_design),
            (QKeySequence.StandardKey.Save, self.save),
            (QKeySequence.StandardKey.SaveAs, self.save_as),
            (QKeySequence.StandardKey.Undo, self.undo),
            (QKeySequence.StandardKey.Redo, self.redo),
            ("Ctrl+Shift+Z", self.redo),
            ("B", lambda: self.select_tool("pencil")),
            ("E", lambda: self.select_tool("eraser")),
            ("I", lambda: self.select_tool("picker")),
        ]:
            action = QAction(self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback)
            self.addAction(action)

    def select_tool(self, tool):
        self.canvas.finish_stroke()
        self.canvas.tool = tool
        self.tool_buttons[tool].setChecked(True)

    def select_color(self, color):
        self.canvas.color = color.upper()
        self.active_hex.setText(color.upper())
        self.active_swatch.setStyleSheet(f"background: {color}; border: 1px solid #CAD4C8; border-radius: 5px;")
        for value, swatch in self._swatches.items():
            border = "2px solid #293C37" if value == color.upper() else "1px solid #CED7CB"
            swatch.setStyleSheet(f"QPushButton {{ background: {value}; border: {border}; border-radius: 5px; }} QPushButton:hover {{ border: 2px solid #293C37; }}")

    def pick_color(self, color):
        self.select_color(color)
        self.select_tool("pencil")

    def custom_color(self):
        color = QColorDialog.getColor(QColor(self.canvas.color), self, "Escolher cor")
        if color.isValid():
            value = color.name().upper()
            if value not in self._swatches and len(self._custom_colors) < 8:
                self._add_swatch(value, "Personalizada", len(PALETTE) + len(self._custom_colors))
                self._custom_colors.append(value)
            self.select_color(value)

    def toggle_grid(self, checked):
        self.canvas.show_grid = checked
        self.canvas.update()

    def set_zoom(self, percent):
        self.canvas.set_zoom(percent)
        self.zoom_label.setText(f"{round(self.canvas.cell_size / 16 * 100)}%")

    def fit_canvas(self):
        available = self.viewport.viewport().size()
        cell = min((available.width() - 2 * self.canvas.MARGIN - 18) // self.design.width,
                   (available.height() - 2 * self.canvas.MARGIN - 18) // self.design.height)
        self.zoom.setValue(max(25, min(250, int(cell / 16 * 100))))

    def _canvas_changed(self):
        self._counts_timer.start(0)
        self._update_title()

    def _commit_stroke(self, before, after):
        self.history.push(PixelCommand(self, before, after, "Apagar pixels" if self.canvas._erase else "Pintar pixels"))

    def _history_changed(self, *args):
        self.undo_button.setEnabled(self.history.canUndo())
        self.redo_button.setEnabled(self.history.canRedo())
        self._update_title()

    def undo(self):
        self.canvas.finish_stroke()
        self.history.undo()

    def redo(self):
        self.canvas.finish_stroke()
        self.history.redo()

    def _update_title(self):
        dirty = not self.history.isClean() or bool(self.canvas._before)
        self.setWindowTitle(f"{self.design.name}{' *' if dirty else ''} — Piixelverso")
        self.status_text.setText("●  Alterações não salvas" if dirty else (
            f"Salvo em {self.file_path.name}" if self.file_path else "Tudo pronto para criar. Seu design fica no seu computador."))

    def refresh_design(self):
        self.canvas.update()
        self.name_edit.setText(self.design.name)
        self.dimensions.setText(f"{self.design.width} × {self.design.height}")
        self.refresh_counts()
        self._update_title()

    def refresh_counts(self):
        counts = self.design.counts()
        total = sum(counts.values())
        number = lambda value: f"{value:,}".replace(",", ".")
        self.total_label.setText(number(total))
        self.color_total.setText(f"{len(counts)} {'cor usada' if len(counts) == 1 else 'cores usadas'}")
        self.empty_total.setText(f"{number(self.design.width * self.design.height - total)} vazios")
        self.count_view.set_counts(counts)

    def rename_design(self):
        if self.name_edit.text() == self.design.name:
            return
        name = self.name_edit.text().strip() or "Sem título"
        try:
            validate_name(name)
        except ValueError as error:
            self.name_edit.setText(self.design.name)
            QMessageBox.warning(self, "Nome muito longo", str(error))
            return
        if name != self.design.name:
            self.canvas.finish_stroke()
            self.history.push(RenameCommand(self, name))
        else:
            self.name_edit.setText(name)

    def confirm_discard(self):
        self.canvas.finish_stroke()
        self.rename_design()
        if self.history.isClean():
            return True
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle("Salvar seu design?")
        dialog.setText("Seu design tem alterações não salvas.")
        dialog.setInformativeText("Salve para continuar criando de onde parou.")
        save_button = dialog.addButton("Salvar", QMessageBox.ButtonRole.AcceptRole)
        discard_button = dialog.addButton("Descartar alterações", QMessageBox.ButtonRole.DestructiveRole)
        dialog.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(save_button)
        dialog.exec()
        if dialog.clickedButton() == save_button:
            return self.save()
        return dialog.clickedButton() == discard_button

    def _replace_design(self, design, path=None):
        self.canvas.finish_stroke()
        self.design = design
        self.canvas.set_design(design)
        self.file_path = Path(path) if path else None
        self.history.clear()
        self.history.setClean()
        self.refresh_design()
        QTimer.singleShot(0, self.fit_canvas)

    def new_design(self):
        dialog = NewDesignDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not self.confirm_discard():
            return
        self._replace_design(PixelDesign(dialog.width_input.value(), dialog.height_input.value(),
                                        name=dialog.name.text().strip() or "Sem título"))

    def open_design(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir design", "", "Design Piixelverso (*.pii)")
        if path:
            self.load_path(path)

    def load_path(self, path):
        try:
            design = load_design(path)
        except (OSError, DesignFormatError, ValueError) as error:
            QMessageBox.warning(self, "Não foi possível abrir", f"O arquivo não pôde ser aberto.\n\n{error}")
            return False
        if not self.confirm_discard():
            return False
        self._replace_design(design, path)
        return True

    def save(self):
        self.canvas.finish_stroke()
        self.rename_design()
        return self._save_path(self.file_path) if self.file_path else self.save_as()

    def save_as(self):
        self.canvas.finish_stroke()
        self.rename_design()
        name = self.file_path.name if self.file_path else "meu-design.pii"
        path, _ = QFileDialog.getSaveFileName(self, "Salvar design", str(self.file_path or name), "Design Piixelverso (*.pii)")
        if not path:
            return False
        target = Path(path)
        if target.suffix.lower() != ".pii":
            target = Path(str(target) + ".pii")
            if target.exists():
                reply = QMessageBox.question(self, "Substituir arquivo?", f"{target.name} já existe. Deseja substituí-lo?",
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                             QMessageBox.StandardButton.No)
                if reply != QMessageBox.StandardButton.Yes:
                    return False
        return self._save_path(target)

    def _save_path(self, path):
        try:
            save_design(self.design, path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Não foi possível salvar", f"Seu design continua aberto. Tente salvar em outra pasta.\n\n{error}")
            return False
        self.file_path = Path(path)
        self.history.setClean()
        self._update_title()
        return True

    def closeEvent(self, event):
        if self.confirm_discard():
            event.accept()
        else:
            event.ignore()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Piixelverso — seu ateliê de pixel art")
    parser.add_argument("design", nargs="?", help="Caminho de um arquivo .pii")
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Piixelverso")
    app.setOrganizationName("Piixelverso")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setFont(QFont("Segoe UI" if sys.platform == "win32" else "DejaVu Sans", 10))
    window = MainWindow()
    window.show()
    if args.design:
        QTimer.singleShot(0, lambda: window.load_path(args.design))
    return app.exec()
