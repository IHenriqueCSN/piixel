"""Ateliê: the pixel-art editor module hosted by Piixel."""
from __future__ import annotations

from pathlib import Path
from html import escape

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QApplication, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLayout, QLineEdit, QMenu, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

from .canvas import PixelCanvas
from .counts import ColorCountsView
from .format import DesignFormatError, load_design, save_design
from .model import PixelDesign, normalize_color, validate_name
from .operations import replace_color_changes
from .replace import ReplaceColorDialog
from .export_dialog import ExportPngDialog
from .png_export import save_png
from .colors import CustomColorDialog
from .preferences import PreferencesError, PreferencesStore
from .commands import EditorCommandBar
from .brand import app_icon, ensure_fonts, svg_pixmap
from .theme import APP_STYLE, BORDER, INK, PINK, apply_palette


PALETTE = [
    ("Carvão", "#293C37"), ("Ardósia", "#66766F"), ("Névoa", "#B5BFB7"), ("Neve", "#FFFFFF"),
    ("Terracota", "#C75B40"), ("Coral", "#E7794B"), ("Pêssego", "#F4AE87"), ("Areia", "#F4D8B2"),
    ("Mostarda", "#D5A039"), ("Sol", "#F0C65B"), ("Lima", "#B6CD70"), ("Creme", "#F8EFCA"),
    ("Floresta", "#245448"), ("Musgo", "#54856A"), ("Folha", "#85B48D"), ("Menta", "#BCDCC6"),
    ("Oceano", "#285A78"), ("Azul", "#548DB0"), ("Céu", "#9DC4D5"), ("Gelo", "#D3E8EA"),
    ("Ameixa", "#734E70"), ("Lavanda", "#A58CB4"), ("Rosa", "#D792A5"), ("Blush", "#EECBD2"),
]
COLOR_NAMES = {color: name for name, color in PALETTE}

STYLE = APP_STYLE


def icon(kind: str, color=INK) -> QIcon:
    if kind == "brand":
        return app_icon()
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
    elif kind == "bucket":
        p.drawPolygon([QPoint(x, y) for x, y in [(4, 11), (11, 4), (18, 11), (11, 18)]])
        p.drawLine(8, 3, 15, 10); p.drawLine(4, 11, 18, 11)
        p.drawLine(20, 13, 18, 17); p.drawLine(18, 17, 18, 19)
        p.drawArc(18, 17, 4, 4, 180 * 16, 180 * 16); p.drawLine(22, 19, 20, 13)
    elif kind == "replace_color":
        p.drawRoundedRect(3, 4, 7, 7, 1, 1)
        p.drawRoundedRect(14, 13, 7, 7, 1, 1)
        p.drawLine(13, 6, 20, 6); p.drawLine(20, 6, 17, 3)
        p.drawLine(20, 6, 17, 9)
        p.drawLine(11, 18, 4, 18); p.drawLine(4, 18, 7, 15)
        p.drawLine(4, 18, 7, 21)
    elif kind == "picker":
        p.drawLine(7, 14, 16, 5); p.drawLine(11, 18, 20, 9)
        p.drawLine(16, 5, 20, 9); p.drawLine(7, 14, 6, 20)
        p.drawLine(6, 20, 11, 18); p.drawLine(13, 5, 20, 12)
    elif kind in ("undo", "redo"):
        if kind == "redo":
            p.translate(24, 0); p.scale(-1, 1)
        p.drawArc(6, 7, 14, 14, -60 * 16, 240 * 16)
        p.drawLine(6, 7, 6, 13); p.drawLine(6, 13, 12, 13)
    elif kind in ("save", "save_as"):
        p.drawRoundedRect(4, 4, 16, 16, 2, 2)
        p.drawRect(8, 4, 8, 6); p.drawRect(8, 14, 8, 6)
        if kind == "save_as":
            p.drawLine(15, 19, 21, 13); p.drawLine(18, 13, 21, 16)
    elif kind == "palette":
        p.drawEllipse(3, 3, 18, 18)
        for x, y in [(8, 7), (14, 6), (17, 12), (8, 14)]:
            p.drawEllipse(x - 1, y - 1, 2, 2)
    elif kind == "folder":
        p.drawLine(3, 8, 3, 19); p.drawLine(3, 19, 21, 19)
        p.drawLine(21, 19, 21, 8); p.drawLine(21, 8, 12, 8)
        p.drawLine(12, 8, 10, 5); p.drawLine(10, 5, 3, 5); p.drawLine(3, 5, 3, 8)
    elif kind == "plus":
        p.drawLine(12, 5, 12, 19); p.drawLine(5, 12, 19, 12)
    elif kind == "fit":
        for x, y, sx, sy in [(4, 4, 1, 1), (20, 4, -1, 1), (4, 20, 1, -1), (20, 20, -1, -1)]:
            p.drawLine(x, y, x + 5 * sx, y); p.drawLine(x, y, x, y + 5 * sy)
    elif kind == "settings":
        p.drawEllipse(6, 6, 12, 12); p.drawEllipse(10, 10, 4, 4)
        for x, y, ex, ey in [(12, 3, 12, 6), (12, 18, 12, 21), (3, 12, 6, 12),
                             (18, 12, 21, 12), (5, 5, 8, 8), (16, 16, 19, 19),
                             (5, 19, 8, 16), (16, 8, 19, 5)]:
            p.drawLine(x, y, ex, ey)
    elif kind == "export_png":
        p.drawRoundedRect(3, 4, 18, 15, 2, 2)
        p.drawEllipse(6, 7, 3, 3)
        p.drawLine(4, 17, 10, 11); p.drawLine(10, 11, 14, 15)
        p.drawLine(14, 15, 17, 12); p.drawLine(17, 12, 20, 15)
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
        result.setIcon(icon(symbol, INK))
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


class AtelierModule(QWidget):
    home_requested = Signal()
    document_accessed = Signal(str, object)

    def __init__(self, parent=None, preferences: PreferencesStore | None = None):
        super().__init__(parent)
        self.setObjectName("atelierModule")
        self._active = True
        self.preferences = preferences if preferences is not None else PreferencesStore()
        self.color_names = dict(COLOR_NAMES)
        self._custom_color_names: dict[str, str] = {}
        self._saved_colors = {}
        ensure_fonts()
        apply_palette(QApplication.instance())
        self.design = PixelDesign(name="Meu primeiro design")
        self.file_path: Path | None = None
        self.history = QUndoStack(self)
        self.history.setUndoLimit(300)
        self.setWindowIcon(app_icon())
        self.setMinimumSize(1120, 750)
        self.resize(1380, 900)
        self._swatches = {}
        self._custom_colors: list[str] = []
        self._counts_timer = QTimer(self)
        self._counts_timer.setSingleShot(True)
        self._counts_timer.timeout.connect(self.refresh_counts)
        self._create_actions()
        self._build()
        self._load_saved_colors()
        self._connect_command_bar()
        self.history.indexChanged.connect(self._history_changed)
        self.refresh_design()
        self.select_color("#E7794B")
        self._history_changed()
        QTimer.singleShot(0, self.fit_canvas)

    def _build(self):
        root = QWidget()
        root.setObjectName("root")
        host = QVBoxLayout(self)
        host.setContentsMargins(0, 0, 0, 0)
        host.setSpacing(0)
        host.addWidget(root)
        layout = QVBoxLayout(root)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        topbar = QFrame(objectName="topbar")
        topbar.setFixedHeight(44)
        top = QHBoxLayout(topbar)
        top.setContentsMargins(28, 0, 28, 0)
        logo = QLabel()
        logo.setPixmap(svg_pixmap("symbol.svg", 44, 38))
        logo.setAccessibleName("Gatinho e planeta do Piixelverso")
        top.addWidget(logo)
        wordmark = QLabel()
        wordmark.setObjectName("brand")
        wordmark.setPixmap(svg_pixmap("wordmark.svg", 142, 25))
        wordmark.setAccessibleName("Piixelverso")
        top.addWidget(wordmark)
        top.addSpacing(16)
        top.addWidget(label("PIIXEL / ATELIÊ", "edition"))
        top.addStretch()
        self.home_button = QPushButton("← Início")
        self.home_button.setObjectName("homeButton")
        self.home_button.setAccessibleName("Voltar à tela inicial")
        self.home_button.setToolTip("Voltar à tela inicial (Alt+Home)")
        self.home_button.setFixedHeight(28)
        self.home_button.clicked.connect(self.home_requested.emit)
        top.addWidget(self.home_button)
        badge = label("Feito à mão, pixel por pixel.", "localBadge")
        badge.setMaximumHeight(29)
        top.addWidget(badge)
        layout.addWidget(topbar)

        self.command_bar = EditorCommandBar(self.command_actions)
        layout.addWidget(self.command_bar)
        self.tool_buttons = {key: self.command_bar.buttons[key] for key in ("pencil", "bucket", "eraser", "picker")}
        self.undo_button = self.command_bar.buttons["undo"]
        self.redo_button = self.command_bar.buttons["redo"]
        self.display_mode_combo = self.command_bar.display_mode_combo
        self.zoom = self.command_bar.zoom_slider
        self.zoom_label = self.command_bar.zoom_label

        project_bar = QWidget(objectName="projectBar")
        project = QHBoxLayout(project_bar)
        project.setContentsMargins(28, 8, 28, 8)
        title = QVBoxLayout()
        title.setSpacing(3)
        self.name_edit = QLineEdit(self.design.name)
        self.name_edit.setObjectName("designName")
        self.name_edit.setMaxLength(4096)
        self.name_edit.setToolTip("Clique para renomear o design")
        self.name_edit.setAccessibleName("Nome do design")
        self.name_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.name_edit.editingFinished.connect(self.rename_design)
        title.addWidget(self.name_edit)
        project.addLayout(title, 1)
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
        bottom.addWidget(label("PIIXEL / ATELIÊ · VERSÃO 0.1", "status"))
        layout.addLayout(bottom)

    def _left_panel(self):
        pane = QFrame(objectName="card")
        pane.setFixedWidth(215)
        outer = QVBoxLayout(pane)
        outer.setContentsMargins(1, 1, 1, 1)
        scroll = QScrollArea()
        self.palette_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget(objectName="paletteBody")
        contents = QVBoxLayout(body)
        contents.setContentsMargins(16, 20, 16, 17)
        contents.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        contents.setSpacing(10)
        contents.addWidget(label("Paleta de cores", "sectionTitle"))
        contents.addWidget(label("Um universo de possibilidades.", "tiny"))
        self.palette_grid = QGridLayout()
        self.palette_grid.setHorizontalSpacing(8)
        self.palette_grid.setVerticalSpacing(8)
        for i, (name, color) in enumerate(PALETTE):
            self._add_swatch(color, name, i)
        contents.addLayout(self.palette_grid)
        contents.addSpacing(4)
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
        self.active_color_name = label("", "tiny")
        self.active_color_name.setTextFormat(Qt.TextFormat.PlainText)
        self.active_color_name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.active_color_name.setMinimumWidth(0)
        self.active_color_name.setWordWrap(True)
        self.active_color_name.hide()
        text.addWidget(self.active_color_name)
        active_layout.addLayout(text)
        contents.addWidget(active)
        contents.addStretch()
        tip = label("DICA DO ATELIÊ\n\nArraste para desenhar. Use o botão direito para apagar.", "hint")
        tip.setWordWrap(True)
        contents.addWidget(tip)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        return pane

    def _add_swatch(self, color, name, index):
        swatch = QPushButton()
        swatch.setObjectName("swatch")
        swatch.setFixedSize(36, 29)
        swatch.setToolTip(f"{name} · {color}")
        swatch.setAccessibleName(f"Selecionar cor {color}")
        swatch.clicked.connect(lambda checked=False, value=color: self.select_color(value))
        swatch.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        swatch.customContextMenuRequested.connect(
            lambda position, value=color: self._show_color_menu(value, position)
        )
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
        toolbar.addWidget(label("1 célula = 1 peça", "tiny"))
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
        self.canvas_view_label = label("Quadradinhos · 100%", "muted")
        controls.addWidget(self.canvas_view_label)
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
        self.count_view = ColorCountsView(self.color_names)
        self.count_view.color_selected.connect(self.pick_color)
        contents.addWidget(self.count_view, 1)
        note = label("Cada quadradinho pintado conta como uma peça. Células vazias ficam fora da contagem.", "hint")
        note.setWordWrap(True)
        contents.addWidget(note)
        return pane

    def _create_actions(self):
        """One QAction per command powers menus, toolbar and global shortcuts."""
        standard = QKeySequence.StandardKey
        specs = [
            ("new", "Novo", "plus", self.new_design, standard.New),
            ("open", "Abrir", "folder", self.open_design, standard.Open),
            ("save", "Salvar", "save", self.save, standard.Save),
            ("save_as", "Salvar como", "save_as", self.save_as, standard.SaveAs),
            ("export_png", "Exportar como PNG…", "export_png", self.export_png, "Ctrl+Shift+E"),
            ("undo", "Desfazer", "undo", self.undo, standard.Undo),
            ("redo", "Refazer", "redo", self.redo, standard.Redo),
            ("pencil", "Lápis", "pencil", lambda: self.select_tool("pencil"), "B"),
            ("bucket", "Balde de tinta", "bucket", lambda: self.select_tool("bucket"), "G"),
            ("eraser", "Borracha", "eraser", lambda: self.select_tool("eraser"), "E"),
            ("picker", "Conta-gotas", "picker", lambda: self.select_tool("picker"), "I"),
            ("replace_color", "Substituir cor…", "replace_color", self.show_replace_color_dialog, "Ctrl+H"),
            ("custom_color", "Cor personalizada", "palette", self.custom_color, None),
            ("fit", "Ajustar à janela", "fit", self.fit_canvas, None),
        ]
        self.command_actions = {}
        self.tool_action_group = QActionGroup(self)
        self.tool_action_group.setExclusive(True)
        for key, text, symbol, callback, shortcut in specs:
            action = QAction(icon(symbol), text, self)
            action.setObjectName(f"action_{key}")
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            sequences = []
            if isinstance(shortcut, QKeySequence.StandardKey):
                sequences = QKeySequence.keyBindings(shortcut)
            elif shortcut:
                sequences = [QKeySequence(shortcut)]
            if key == "redo":
                sequences.extend([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
            unique = {s.toString(QKeySequence.SequenceFormat.PortableText): s for s in sequences}
            action.setShortcuts(list(unique.values()))
            hints = " / ".join(s.toString(QKeySequence.SequenceFormat.NativeText) for s in unique.values())
            action.setToolTip(f"{text} ({hints})" if hints else text)
            action.triggered.connect(lambda _checked=False, handler=callback: handler())
            if key in ("pencil", "bucket", "eraser", "picker"):
                action.setCheckable(True)
                self.tool_action_group.addAction(action)
            self.command_actions[key] = action
            self.addAction(action)
        self.command_actions["pencil"].setChecked(True)

    def _connect_command_bar(self):
        self.display_mode_combo.currentIndexChanged.connect(self.change_display_mode)
        self.command_bar.grid_checkbox.toggled.connect(self.toggle_grid)
        self.zoom.valueChanged.connect(self.set_zoom)

    def select_tool(self, tool):
        self.canvas.finish_stroke()
        self.canvas.tool = tool
        self.command_actions[tool].setChecked(True)

    def select_color(self, color):
        self.canvas.color = color.upper()
        self.active_hex.setText(color.upper())
        name = self._custom_color_names.get(color.upper(), "")
        self.active_color_name.setText(name)
        self.active_color_name.setToolTip(f"<p>{escape(name)}</p>" if name else "")
        self.active_color_name.setVisible(bool(name))
        self.active_swatch.setStyleSheet(f"background: {color}; border: 1px solid {BORDER}; border-radius: 5px;")
        for value, swatch in self._swatches.items():
            border = f"2px solid {INK}" if value == color.upper() else f"1px solid {BORDER}"
            swatch.setStyleSheet(f"QPushButton {{ background: {value}; border: {border}; border-radius: 5px; }} QPushButton:hover {{ border: 2px solid {PINK}; }}")

    def pick_color(self, color):
        self.select_color(color)
        self.select_tool("pencil")

    def custom_color(self):
        self._edit_custom_color(self.canvas.color)

    def show_replace_color_dialog(self):
        self.canvas.finish_stroke()
        if not self.design.counts():
            return
        target_colors = dict(COLOR_NAMES)
        for item in self.preferences.saved_colors():
            target_colors[item.color] = item.name or COLOR_NAMES.get(item.color, "Personalizada")
        dialog = ReplaceColorDialog(
            self.design, self.color_names, self.canvas.color, self.window(),
            target_colors=target_colors,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.replace_color(dialog.source_color(), dialog.target_color())

    def replace_color(self, source: str, target: str) -> int:
        """Replace every occurrence with one undo step; keep new colors in this session."""
        self.canvas.finish_stroke()
        after = replace_color_changes(self.design, source, target)
        if not after:
            return 0
        before = {index: self.design.pixels[index] for index in after}
        self.history.push(PixelCommand(self, before, after, "Substituir cor"))
        self.add_custom_color(next(iter(after.values())))
        return len(after)

    def _edit_custom_color(self, color, *, save_for_future=False):
        dialog = CustomColorDialog(
            color, self.window(), name=self._custom_color_names.get(color, ""),
            save_for_future=save_for_future,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.add_custom_color(dialog.color_value(), dialog.color_name(), dialog.save_for_future())

    def _load_saved_colors(self):
        for item in self.preferences.saved_colors():
            self._saved_colors[item.color] = item
            self._remember_custom_color(item.color, item.name)

    def _remember_custom_color(self, color, name="", *, replace_name=False):
        if name:
            self._custom_color_names[color] = name
            self.color_names[color] = name
        elif replace_name:
            self._custom_color_names.pop(color, None)
            self.color_names[color] = COLOR_NAMES.get(color, "Personalizada")
        else:
            self.color_names.setdefault(color, "Personalizada")
        if color not in self._swatches:
            self._add_swatch(color, self.color_names[color], len(PALETTE) + len(self._custom_colors))
            self._custom_colors.append(color)
        self._refresh_color_tooltip(color)

    def _refresh_color_tooltip(self, color):
        name = self.color_names.get(color, "Personalizada")
        if color in self._saved_colors:
            note = "Salva para próximas sessões"
        else:
            note = "Cor da paleta inicial" if color in COLOR_NAMES else "Disponível nesta sessão"
        self._swatches[color].setToolTip(f"<p>{escape(name)} · {color}<br>{note}</p>")

    def add_custom_color(self, color: str, name: str = "", persist: bool = False) -> None:
        value = normalize_color(color)
        if value is None:
            raise ValueError("A cor precisa ter um valor RGB.")
        if (not isinstance(name, str) or len(name.strip()) > 80
                or any(ord(char) < 32 for char in name)):
            raise ValueError("O nome da cor deve ter até 80 caracteres, em uma linha.")
        name = name.strip()
        self._remember_custom_color(value, name, replace_name=bool(persist))
        error = None
        if persist:
            try:
                self.preferences.save_color(value, name)
            except (PreferencesError, OSError, ValueError) as exc:
                error = exc
            else:
                self._saved_colors = {item.color: item for item in self.preferences.saved_colors()}
        self._refresh_color_tooltip(value)
        self.select_color(value)
        self.refresh_counts()
        QTimer.singleShot(0, self, lambda: self._reveal_color(value))
        if error is not None:
            QMessageBox.warning(
                self.window(), "Cor adicionada nesta sessão",
                "A cor foi adicionada à sessão, mas não foi possível salvá-la para próximas sessões."
                f"\n\n{error}",
            )

    def _reveal_color(self, color):
        body = self.palette_scroll.widget()
        body.layout().activate()
        body.adjustSize()
        self.palette_scroll.ensureWidgetVisible(self._swatches[color], 0, 8)

    def forget_saved_color(self, color: str) -> None:
        value = normalize_color(color)
        if value is None or value not in self._saved_colors:
            return
        try:
            self.preferences.remove_color(value)
        except (PreferencesError, OSError, ValueError) as error:
            QMessageBox.warning(self.window(), "Não foi possível remover a cor salva", str(error))
            return
        self._saved_colors.pop(value, None)
        self._refresh_color_tooltip(value)

    def _show_color_menu(self, color, position):
        menu = QMenu(self)
        save = menu.addAction("Editar cor salva…" if color in self._saved_colors else "Salvar cor…")
        save.triggered.connect(lambda _checked=False: self._edit_custom_color(color, save_for_future=True))
        if color in self._saved_colors:
            forget = menu.addAction("Remover das cores salvas")
            forget.triggered.connect(lambda _checked=False: self.forget_saved_color(color))
        menu.exec(self._swatches[color].mapToGlobal(position))
        menu.deleteLater()

    def toggle_grid(self, checked):
        self.canvas.show_grid = checked
        self.canvas.update()

    def change_display_mode(self, index):
        self.canvas.finish_stroke()
        self.canvas.set_display_mode(self.display_mode_combo.itemData(index))
        self._update_view_status()

    def set_zoom(self, percent):
        self.canvas.set_zoom(percent)
        self.zoom_label.setText(f"{round(self.canvas.cell_size / 16 * 100)}%")
        self._update_view_status()

    def _update_view_status(self):
        self.canvas_view_label.setText(f"{self.display_mode_combo.currentText()} · {self.zoom_label.text()}")

    def fit_canvas(self):
        available = self.viewport.viewport().size()
        cell = min((available.width() - 2 * self.canvas.MARGIN - 18) // self.design.width,
                   (available.height() - 2 * self.canvas.MARGIN - 18) // self.design.height)
        self.zoom.setValue(max(25, min(250, int(cell / 16 * 100))))

    def _canvas_changed(self):
        self._counts_timer.start(0)
        self._update_title()

    def _commit_stroke(self, before, after):
        text = "Apagar pixels" if self.canvas._erase else (
            "Preencher área" if self.canvas.tool == "bucket" else "Pintar pixels")
        self.history.push(PixelCommand(self, before, after, text))

    def prepare_navigation(self):
        """Commit the current gesture and name before leaving this module."""
        self.canvas.finish_stroke()
        self.rename_design()

    def set_active(self, active: bool):
        """Keep editor commands scoped to the visible module."""
        self._active = bool(active)
        for action in self.command_actions.values():
            action.setEnabled(self._active)
        self._history_changed()

    def _history_changed(self, *args):
        self.command_actions["undo"].setEnabled(self._active and self.history.canUndo())
        self.command_actions["redo"].setEnabled(self._active and self.history.canRedo())
        self.command_actions["replace_color"].setEnabled(self._active and self.design.filled_count > 0)
        self._update_title()

    def undo(self):
        self.canvas.finish_stroke()
        self.history.undo()

    def redo(self):
        self.canvas.finish_stroke()
        self.history.redo()

    def _update_title(self):
        dirty = not self.history.isClean() or bool(self.canvas._before)
        self.setWindowTitle(f"{self.design.name}{' *' if dirty else ''} — Ateliê · Piixel")
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
        self.command_actions["replace_color"].setEnabled(self._active and bool(counts))
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
            QMessageBox.warning(self.window(), "Nome muito longo", str(error))
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
        dialog = QMessageBox(self.window())
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
        dialog = NewDesignDialog(self.window())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not self.confirm_discard():
            return
        self._replace_design(PixelDesign(dialog.width_input.value(), dialog.height_input.value(),
                                        name=dialog.name.text().strip() or "Sem título"))

    def open_design(self):
        path, _ = QFileDialog.getOpenFileName(self.window(), "Abrir design", "", "Design Piixelverso (*.pii)")
        if path:
            self.load_path(path)

    def load_path(self, path):
        try:
            design = load_design(path)
        except FileNotFoundError:
            QMessageBox.warning(
                self.window(), "Arquivo não encontrado",
                "Arquivo não encontrado. Verifique se o arquivo foi movido ou apagado.",
            )
            return False
        except (OSError, DesignFormatError, ValueError) as error:
            QMessageBox.warning(self.window(), "Não foi possível abrir", f"O arquivo não pôde ser aberto.\n\n{error}")
            return False
        if not self.confirm_discard():
            return False
        self._replace_design(design, path)
        self.document_accessed.emit(str(self.file_path), self.design.clone())
        return True

    def save(self):
        self.canvas.finish_stroke()
        self.rename_design()
        return self._save_path(self.file_path) if self.file_path else self.save_as()

    def save_as(self):
        self.canvas.finish_stroke()
        self.rename_design()
        name = self.file_path.name if self.file_path else "meu-design.pii"
        path, _ = QFileDialog.getSaveFileName(self.window(), "Salvar design", str(self.file_path or name), "Design Piixelverso (*.pii)")
        if not path:
            return False
        target = Path(path)
        if target.suffix.lower() != ".pii":
            target = Path(str(target) + ".pii")
            if target.exists():
                reply = QMessageBox.question(self.window(), "Substituir arquivo?", f"{target.name} já existe. Deseja substituí-lo?",
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                             QMessageBox.StandardButton.No)
                if reply != QMessageBox.StandardButton.Yes:
                    return False
        return self._save_path(target)

    def export_png(self):
        self.rename_design()
        self.canvas.finish_stroke()
        try:
            dialog = ExportPngDialog(
                self.design, piece_size_mm=self.preferences.piece_size_mm(),
                display_mode=self.canvas.display_mode, show_grid=self.canvas.show_grid,
                parent=self.window(),
            )
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self.window(), "Não foi possível exportar o PNG", str(error))
            return False
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        initial_path = self.file_path.with_suffix(".png") if self.file_path else Path("meu-design.png")
        chosen, _ = QFileDialog.getSaveFileName(
            self.window(), "Exportar como PNG", str(initial_path), "Imagem PNG (*.png)"
        )
        if not chosen:
            return False
        target = Path(chosen)
        if target.suffix.lower() != ".png":
            target = Path(str(target) + ".png")
            if target.exists():
                answer = QMessageBox.question(
                    self.window(), "Substituir imagem?",
                    f"{target.name} já existe. Deseja substituir a imagem?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return False
        return self.export_png_path(
            target, display_mode=dialog.display_mode(), show_grid=dialog.show_grid(),
            piece_size_mm=dialog.piece_size_mm(),
        )

    def export_png_path(self, path, *, display_mode=None, show_grid=None, piece_size_mm=None) -> bool:
        """Write an image while keeping the open document and its save state."""
        self.rename_design()
        self.canvas.finish_stroke()
        target = Path(path)
        try:
            save_png(
                self.design, target,
                display_mode=self.canvas.display_mode if display_mode is None else display_mode,
                show_grid=self.canvas.show_grid if show_grid is None else show_grid,
                piece_size_mm=self.preferences.piece_size_mm() if piece_size_mm is None else piece_size_mm,
            )
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.warning(
                self.window(), "Não foi possível exportar o PNG",
                f"A imagem não pôde ser salva.\n\n{error}",
            )
            return False
        self.status_text.setText(f"Imagem PNG exportada para {target.name}.")
        return True

    def _save_path(self, path):
        try:
            save_design(self.design, path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self.window(), "Não foi possível salvar", f"Seu design continua aberto. Tente salvar em outra pasta.\n\n{error}")
            return False
        self.file_path = Path(path)
        self.history.setClean()
        self._update_title()
        self.document_accessed.emit(str(self.file_path), self.design.clone())
        return True

    def closeEvent(self, event):
        if self.confirm_discard():
            event.accept()
        else:
            event.ignore()

