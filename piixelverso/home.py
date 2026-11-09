"""Piixel's module launcher, independent of the editor's document state."""
from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QStyle, QVBoxLayout, QWidget,
)

from .brand import svg_pixmap
from .modules import MODULES, ModuleDefinition
from .recents import RecentFilesPanel
from .theme import BORDER, CREAM, HOVER, INK, LIGHT_PINK, MUTED, PALE_BLUE, PINK, WHITE


HOME_STYLE = f"""
QWidget#homePage, QWidget#homeScrollBody {{ background: {CREAM}; }}
QFrame#homeHeader {{ background: {CREAM}; border-bottom: 1px solid {BORDER}; }}
QLabel#homeEdition {{ color: {MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 2px; }}
QLabel#homeTagline {{ background: {PALE_BLUE}; color: {INK}; border-radius: 12px; padding: 6px 12px; font-size: 11px; }}
QLabel#homeEyebrow {{ color: {MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 2px; }}
QLabel#homeTitle {{ color: {INK}; font-size: 42px; font-weight: 700; letter-spacing: -1px; }}
QLabel#homeSubtitle {{ color: {MUTED}; font-size: 15px; }}
QLabel#homeSectionTitle {{ color: {INK}; font-size: 16px; font-weight: 700; }}
QFrame#homeMascot {{ background: {PALE_BLUE}; border-radius: 28px; }}
QFrame#moduleCard {{ background: {WHITE}; border: 1px solid {BORDER}; border-radius: 15px; }}
QLabel#moduleIcon {{ background: {PALE_BLUE}; border-radius: 18px; }}
QLabel#moduleTitle {{ color: {INK}; font-size: 24px; font-weight: 700; }}
QLabel#moduleDescription {{ color: {MUTED}; font-size: 13px; }}
QLabel#moduleState {{ color: {MUTED}; font-size: 11px; }}
QLabel#moduleDirty {{ color: {INK}; background: {HOVER}; border-radius: 5px; padding: 4px 7px; font-size: 10px; }}
QPushButton#openModule {{ color: {INK}; background: {LIGHT_PINK}; border: 1px solid {PINK}; border-radius: 8px; padding: 11px 18px; font-size: 12px; font-weight: 700; }}
QPushButton#openModule:hover {{ background: {HOVER}; border-color: {PINK}; }}
QPushButton#openModule:focus {{ border: 2px solid {INK}; padding: 10px 17px; }}
QLabel#homeFootnote {{ color: {MUTED}; font-size: 11px; }}
"""


class HomePage(QWidget):
    module_requested = Signal(str)
    recent_file_requested = Signal(str)

    def __init__(self, modules: Sequence[ModuleDefinition] = MODULES,
                 module_icons: dict[str, QIcon] | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("homePage")
        self.setAccessibleName("Tela inicial do Piixel")
        self.setStyleSheet(HOME_STYLE)
        self._definitions = {module.id: module for module in modules}
        self.module_buttons: dict[str, QPushButton] = {}
        self._state_labels: dict[str, QLabel] = {}
        self._dirty_labels: dict[str, QLabel] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget(objectName="homeScrollBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(40, 36, 40, 30)
        body_layout.setSpacing(0)
        centered = QHBoxLayout()
        centered.setContentsMargins(0, 0, 0, 0)
        centered.addStretch()
        content = QWidget()
        content.setMaximumWidth(1240)
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        columns = QHBoxLayout(content)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(28)
        left = QWidget()
        left.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        contents = QVBoxLayout(left)
        contents.setContentsMargins(0, 0, 0, 0)
        contents.setSpacing(24)
        contents.addWidget(self._hero())
        contents.addWidget(self._label("Módulos", "homeSectionTitle"))
        for module in modules:
            supplied = (module_icons or {}).get(module.id)
            module_icon = supplied or self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
            contents.addWidget(self._module_card(module, module_icon))
        contents.addStretch(1)
        footnote = self._label("Cada criação começa com um pixel.", "homeFootnote")
        contents.addWidget(footnote)
        columns.addWidget(left, 1)
        self.recent_panel = RecentFilesPanel()
        self.recent_panel.setFixedWidth(390)
        self.recent_panel.setMinimumHeight(520)
        self.recent_panel.file_requested.connect(self.recent_file_requested.emit)
        columns.addWidget(self.recent_panel)
        centered.addWidget(content, 1)
        centered.addStretch()
        body_layout.addLayout(centered, 1)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

    @staticmethod
    def _label(text: str, name: str) -> QLabel:
        result = QLabel(text)
        result.setObjectName(name)
        result.setTextFormat(Qt.TextFormat.PlainText)
        return result

    def _header(self) -> QWidget:
        header = QFrame(objectName="homeHeader")
        header.setFixedHeight(44)
        row = QHBoxLayout(header)
        row.setContentsMargins(28, 0, 28, 0)
        symbol = QLabel()
        symbol.setPixmap(svg_pixmap("symbol.svg", 44, 38))
        symbol.setAccessibleName("Gatinho e planeta do Piixelverso")
        row.addWidget(symbol)
        wordmark = QLabel()
        wordmark.setPixmap(svg_pixmap("wordmark.svg", 142, 25))
        wordmark.setAccessibleName("Piixelverso")
        row.addWidget(wordmark)
        row.addSpacing(16)
        row.addWidget(self._label("PIIXEL", "homeEdition"))
        row.addStretch()
        tagline = self._label("Feito à mão, pixel por pixel.", "homeTagline")
        tagline.setMaximumHeight(29)
        row.addWidget(tagline)
        return header

    def _hero(self) -> QWidget:
        hero = QWidget()
        row = QHBoxLayout(hero)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(24)
        words = QVBoxLayout()
        words.setSpacing(11)
        words.addStretch()
        words.addWidget(self._label("BEM-VINDO AO SEU ESPAÇO CRIATIVO", "homeEyebrow"))
        words.addWidget(self._label("Piixel", "homeTitle"))
        subtitle = self._label("Escolha um módulo para começar.", "homeSubtitle")
        subtitle.setWordWrap(True)
        words.addWidget(subtitle)
        words.addStretch()
        row.addLayout(words, 1)
        mascot = QFrame(objectName="homeMascot")
        mascot.setFixedSize(140, 140)
        mascot_layout = QVBoxLayout(mascot)
        mascot_layout.setContentsMargins(14, 22, 14, 22)
        artwork = QLabel()
        artwork.setAlignment(Qt.AlignmentFlag.AlignCenter)
        artwork.setPixmap(svg_pixmap("symbol.svg", 112, 96))
        artwork.setAccessibleName("Mascote do Piixelverso")
        mascot_layout.addWidget(artwork)
        row.addWidget(mascot)
        return hero

    def _module_card(self, module: ModuleDefinition, module_icon: QIcon) -> QWidget:
        card = QFrame(objectName="moduleCard")
        compact = module.id in ("settings", "piixelfone")
        card.setMinimumHeight(180 if compact else 250)
        content = QVBoxLayout(card)
        content.setContentsMargins(25, 20 if compact else 24, 25, 20 if compact else 24)
        content.setSpacing(12)
        row = QHBoxLayout()
        row.setSpacing(16)
        illustration = QLabel()
        illustration.setObjectName("moduleIcon")
        illustration.setFixedSize(44 if compact else 60, 44 if compact else 60)
        illustration.setAlignment(Qt.AlignmentFlag.AlignCenter)
        illustration.setPixmap(module_icon.pixmap(36, 36))
        row.addWidget(illustration)
        row.addWidget(self._label(module.title, "moduleTitle"), 1)
        content.addLayout(row)
        description = self._label(module.description, "moduleDescription")
        description.setWordWrap(True)
        content.addWidget(description)
        state = self._label("", "moduleState")
        state.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        state.hide()
        content.addWidget(state)
        dirty = self._label("Alterações não salvas", "moduleDirty")
        dirty.hide()
        content.addWidget(dirty, 0, Qt.AlignmentFlag.AlignLeft)
        content.addStretch(1)

        launch = QPushButton(f"Abrir {module.title}")
        launch.setObjectName("openModule")
        launch.setAccessibleName(f"Abrir módulo {module.title}")
        launch.setMinimumWidth(180)
        launch.setAutoDefault(True)
        launch.setDefault(not self.module_buttons)
        launch.clicked.connect(lambda _checked=False, identifier=module.id: self.module_requested.emit(identifier))
        content.addWidget(launch, 0, Qt.AlignmentFlag.AlignLeft)
        self.module_buttons[module.id] = launch
        self._state_labels[module.id] = state
        self._dirty_labels[module.id] = dirty
        return card

    def set_module_state(self, module_id: str, title: str, dirty: bool) -> None:
        """Expose the in-memory module session without implying an automatic save."""
        definition = self._definitions[module_id]
        self.module_buttons[module_id].setText(f"Continuar no {definition.title}")
        state = self._state_labels[module_id]
        visible_title = state.fontMetrics().elidedText(title or "Sem título", Qt.TextElideMode.ElideRight, 370)
        state.setText(f"Design aberto: {visible_title}")
        state.setToolTip(title or "Sem título")
        state.show()
        self._dirty_labels[module_id].setVisible(bool(dirty))

    def focus_default_module(self) -> None:
        if self.module_buttons:
            next(iter(self.module_buttons.values())).setFocus(Qt.FocusReason.OtherFocusReason)

    def set_recent_files(self, entries) -> None:
        self.recent_panel.set_files(entries)
