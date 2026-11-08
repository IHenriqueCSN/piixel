"""A one-line menu and tool strip for the native pixel-art editor."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QMenuBar,
    QSizePolicy, QSlider, QToolBar, QToolButton, QWidget,
)


COMMAND_STYLE = """
QWidget#editorCommandBar { background: #FFFFFF; border-bottom: 1px solid #DDE4DD; }
QMenuBar#editorMenuBar { background: #FFFFFF; border: 0; spacing: 0; }
QMenuBar#editorMenuBar::item { padding: 7px 9px; background: transparent; color: #3D5A49; }
QMenuBar#editorMenuBar::item:selected { background: #EDF4E9; border-radius: 4px; }
QMenu { background: #FFFFFF; color: #293C37; border: 1px solid #D2DDCF; padding: 4px; }
QMenu::item { padding: 7px 28px 7px 24px; }
QMenu::item:selected { background: #EAF3E5; color: #285B49; border-radius: 3px; }
QMenu::item:disabled { color: #B2BDB5; }
QMenu::separator { height: 1px; background: #E2E8DF; margin: 4px 8px; }
QToolBar#editorToolBar { background: #FFFFFF; border: 0; spacing: 3px; padding: 0; }
QToolBar#editorToolBar::separator { background: #DFE6DC; width: 1px; margin: 6px 5px; }
QToolButton#compactCommand {
    background: transparent; color: #334D40; border: 1px solid transparent;
    border-radius: 5px; padding: 4px;
}
QToolButton#compactCommand:hover { background: #F0F5ED; border-color: #D2DFCD; }
QToolButton#compactCommand:pressed { background: #E4EEDF; }
QToolButton#compactCommand:checked { background: #EAF3E5; border-color: #8FAE91; }
QLabel#compactZoomValue { color: #61796B; font-size: 10px; }
"""


class EditorCommandBar(QWidget):
    """Shared actions in native menus and a compact, icon-only quick toolbar."""

    def __init__(self, commands: dict[str, QAction], parent=None):
        super().__init__(parent)
        self.setObjectName("editorCommandBar")
        self.setAccessibleName("Menus e ferramentas")
        self.setFixedHeight(44)
        self.setStyleSheet(COMMAND_STYLE)
        self.commands = commands
        self.buttons: dict[str, QToolButton] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(28, 3, 28, 4)
        layout.setSpacing(9)

        self.menubar = QMenuBar()
        self.menubar.setObjectName("editorMenuBar")
        self.menubar.setAccessibleName("Menus do editor")
        self.menubar.setNativeMenuBar(False)
        self.menubar.setFixedSize(184, 32)
        self.menus = {
            "file": self.menubar.addMenu("&Arquivo"),
            "edit": self.menubar.addMenu("&Editar"),
            "view": self.menubar.addMenu("E&xibir"),
        }
        for name in ("new", "open", "save", "save_as"):
            self.menus["file"].addAction(commands[name])
        for name in ("undo", "redo"):
            self.menus["edit"].addAction(commands[name])
        self.menus["edit"].addSeparator()
        for name in ("pencil", "eraser", "picker"):
            self.menus["edit"].addAction(commands[name])
        self.menus["edit"].addSeparator()
        self.menus["edit"].addAction(commands["custom_color"])
        layout.addWidget(self.menubar)

        self.toolbar = QToolBar()
        self.toolbar.setObjectName("editorToolBar")
        self.toolbar.setAccessibleName("Ferramentas rápidas")
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.toolbar.setIconSize(QSize(18, 18))
        self.toolbar.setFixedHeight(36)
        self.toolbar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.toolbar, 1)

        for name in ("undo", "redo"):
            self._add_command(name)
        self.toolbar.addSeparator()
        for name in ("pencil", "eraser", "picker", "custom_color"):
            self._add_command(name)
        self.toolbar.addSeparator()

        self.display_mode_combo = QComboBox()
        self.display_mode_combo.setObjectName("displayMode")
        self.display_mode_combo.setAccessibleName("Exibição das peças")
        self.display_mode_combo.setToolTip("Exibir como quadradinhos ou rosquinhas")
        self.display_mode_combo.addItem("Quadradinhos", "squares")
        self.display_mode_combo.addItem("Rosquinhas (hama beads)", "beads")
        self.display_mode_combo.setFixedWidth(192)
        self.toolbar.addWidget(self.display_mode_combo)

        self.grid_checkbox = QCheckBox("Grade")
        self.grid_checkbox.setObjectName("compactGrid")
        self.grid_checkbox.setAccessibleName("Mostrar grade da prancheta")
        self.grid_checkbox.setToolTip("Mostrar ou ocultar a grade")
        self.grid_checkbox.setChecked(True)
        self.toolbar.addWidget(self.grid_checkbox)
        self.toolbar.addSeparator()

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setObjectName("compactZoom")
        self.zoom_slider.setAccessibleName("Zoom da prancheta")
        self.zoom_slider.setRange(25, 250)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(90)
        self.toolbar.addWidget(self.zoom_slider)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("compactZoomValue")
        self.zoom_label.setFixedWidth(34)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toolbar.addWidget(self.zoom_label)
        self._add_command("fit")

        self._build_view_menu()

    def _add_command(self, name: str):
        action = self.commands[name]
        self.toolbar.addAction(action)
        command = self.toolbar.widgetForAction(action)
        if not isinstance(command, QToolButton):
            raise TypeError(f"O comando {name} não criou um botão de ferramenta.")
        command.setObjectName("compactCommand")
        command.setAccessibleName(action.text().replace("&", ""))
        command.setAutoRaise(True)
        command.setFixedSize(29, 29)
        self.buttons[name] = command

    def _build_view_menu(self):
        pieces = self.menus["view"].addMenu("Peças")
        self.piece_action_group = QActionGroup(self)
        self.piece_action_group.setExclusive(True)
        self.view_actions = {}
        for index in range(self.display_mode_combo.count()):
            mode = self.display_mode_combo.itemData(index)
            action = QAction(self.display_mode_combo.itemText(index), self)
            action.setCheckable(True)
            action.setChecked(index == self.display_mode_combo.currentIndex())
            self.piece_action_group.addAction(action)
            pieces.addAction(action)
            action.triggered.connect(lambda _checked=False, value=index: self.display_mode_combo.setCurrentIndex(value))
            self.view_actions[mode] = action
        self.display_mode_combo.currentIndexChanged.connect(self._sync_display_action)

        self.grid_action = QAction("Mostrar grade", self)
        self.grid_action.setCheckable(True)
        self.grid_action.setChecked(True)
        self.grid_action.toggled.connect(self.grid_checkbox.setChecked)
        self.grid_checkbox.toggled.connect(self.grid_action.setChecked)
        self.view_actions["grid"] = self.grid_action
        self.menus["view"].addAction(self.grid_action)

        zoom = self.menus["view"].addMenu("Zoom")
        for text, step in (("Diminuir", -25), ("100%", 0), ("Aumentar", 25)):
            action = QAction(text, self)
            action.triggered.connect(lambda _checked=False, delta=step: self._change_zoom(delta))
            zoom.addAction(action)
        self.menus["view"].addSeparator()
        self.menus["view"].addAction(self.commands["fit"])

    def _sync_display_action(self, index: int):
        mode = self.display_mode_combo.itemData(index)
        action = self.view_actions.get(mode)
        if action is not None:
            action.setChecked(True)

    def _change_zoom(self, delta: int):
        self.zoom_slider.setValue(self.zoom_slider.value() + delta if delta else 100)
