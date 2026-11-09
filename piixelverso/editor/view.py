"""Ateliê presentation: widgets, layout, and UI intent signals only."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ..brand import svg_pixmap
from ..canvas import PixelCanvas
from ..commands import EditorCommandBar
from ..counts import ColorCountsView
from ..ui.widgets import label
from .palette import PALETTE
from .recent_colors import RecentColorsWidget


# Explicit facade fields retained by AtelierModule for its existing public UI API.
VIEW_ATTRIBUTES = (
    "home_button", "command_bar", "tool_buttons", "undo_button", "redo_button",
    "display_mode_combo", "zoom", "zoom_label", "name_edit", "status_text",
    "palette_scroll", "palette_grid", "active_swatch", "active_hex",
    "active_color_name", "canvas", "viewport", "position_label", "dimensions",
    "canvas_view_label", "total_label", "color_total", "empty_total", "count_view",
    "recent_colors_widget",
)


class AtelierView(QWidget):
    home_requested = Signal()
    rename_requested = Signal()
    color_selected = Signal(str)
    color_picked = Signal(str)
    color_context_requested = Signal(str, object)
    recent_color_selected = Signal(int)

    def __init__(self, design, color_names, command_actions, parent=None):
        super().__init__(parent)
        self.setObjectName("root")
        self.color_names = color_names
        self.command_actions = command_actions
        self.swatches = {}
        self._build(design)

    def _build(self, design):
        layout = QVBoxLayout(self)
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
        self.name_edit = QLineEdit(design.name)
        self.name_edit.setObjectName("designName")
        self.name_edit.setMaxLength(4096)
        self.name_edit.setToolTip("Clique para renomear o design")
        self.name_edit.setAccessibleName("Nome do design")
        self.name_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.name_edit.editingFinished.connect(self.rename_requested.emit)
        title.addWidget(self.name_edit)
        project.addLayout(title, 1)
        layout.addWidget(project_bar)

        workspace = QHBoxLayout()
        workspace.setContentsMargins(28, 0, 28, 0)
        workspace.setSpacing(18)
        workspace.addWidget(self._left_panel())
        workspace.addWidget(self._editor(design), 1)
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
        outer.setSpacing(0)
        recent_panel = QWidget()
        recent_layout = QVBoxLayout(recent_panel)
        recent_layout.setContentsMargins(16, 14, 16, 8)
        self.recent_colors_widget = RecentColorsWidget(self.color_names)
        self.recent_colors_widget.color_selected.connect(self.recent_color_selected.emit)
        recent_layout.addWidget(self.recent_colors_widget)
        outer.addWidget(recent_panel)
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
            self.add_swatch(color, name, i)
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
        outer.addWidget(scroll, 1)
        return pane

    def add_swatch(self, color, name, index):
        swatch = QPushButton()
        swatch.setObjectName("swatch")
        swatch.setFixedSize(36, 29)
        swatch.setToolTip(f"{name} · {color}")
        swatch.setAccessibleName(f"Selecionar cor {color}")
        swatch.clicked.connect(lambda checked=False, value=color: self.color_selected.emit(value))
        swatch.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        swatch.customContextMenuRequested.connect(
            lambda position, value=color: self.color_context_requested.emit(value, position)
        )
        self.swatches[color] = swatch
        self.palette_grid.addWidget(swatch, index // 4, index % 4)

    def _editor(self, design):
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
        self.canvas = PixelCanvas(design)
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
        self.count_view.color_selected.connect(self.color_picked.emit)
        contents.addWidget(self.count_view, 1)
        note = label("Cada quadradinho pintado conta como uma peça. Células vazias ficam fora da contagem.", "hint")
        note.setWordWrap(True)
        contents.addWidget(note)
        return pane

