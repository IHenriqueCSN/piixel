"""A compact native ribbon backed by the editor's shared QAction commands."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QSlider,
    QStackedWidget, QTabBar, QToolButton, QVBoxLayout, QWidget,
)


RIBBON_STYLE = """
QWidget#editorRibbon { background: #FFFFFF; border-bottom: 1px solid #DDE4DD; }
QTabBar#ribbonTabs { background: #FAFCF9; }
QTabBar#ribbonTabs::tab {
    color: #607568; background: #FAFCF9; border: 0;
    border-bottom: 3px solid transparent; padding: 6px 22px; min-width: 60px;
}
QTabBar#ribbonTabs::tab:selected {
    color: #285B49; background: #FFFFFF; border-bottom-color: #285B49; font-weight: 700;
}
QTabBar#ribbonTabs::tab:hover { color: #285B49; background: #EFF5ED; }
QStackedWidget#ribbonPages { background: #FFFFFF; border: 0; }
QFrame#ribbonGroup { background: #FFFFFF; border: 0; }
QFrame#ribbonSeparator { background: #E2E8DF; border: 0; }
QLabel#ribbonCaption { color: #809087; font-size: 10px; }
QLabel#ribbonShortcut { color: #8A968E; font-size: 9px; background: transparent; }
QLabel#ribbonZoomValue { color: #61796B; font-size: 11px; }
QToolButton#ribbonCommand {
    color: #334D40; background: transparent; border: 1px solid transparent;
    border-radius: 5px; padding: 3px 5px; font-size: 11px;
}
QToolButton#ribbonCommand:hover { background: #F0F5ED; border-color: #D2DFCD; }
QToolButton#ribbonCommand:pressed { background: #E4EEDF; }
QToolButton#ribbonCommand:checked { background: #EAF3E5; border-color: #8FAE91; color: #285B49; }
QToolButton#ribbonCommand:disabled { color: #B2BDB5; }
"""


class EditorRibbon(QWidget):
    """Command tabs; actions stay owned by MainWindow for global shortcuts."""

    def __init__(self, commands: dict[str, QAction], parent=None):
        super().__init__(parent)
        self.setObjectName("editorRibbon")
        self.setAccessibleName("Faixa de opções")
        self.setStyleSheet(RIBBON_STYLE)
        self.setFixedHeight(136)
        self.commands = commands
        self.buttons: dict[str, QToolButton] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 0, 28, 1)
        layout.setSpacing(0)
        self.tabs = QTabBar()
        self.tabs.setObjectName("ribbonTabs")
        self.tabs.setAccessibleName("Abas da faixa de opções")
        self.tabs.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.tabs.setFixedHeight(32)
        for title in ("&Arquivo", "&Início", "E&xibir"):
            self.tabs.addTab(title)
        self.tabs.setTabToolTip(0, "Arquivo (Alt+A)")
        self.tabs.setTabToolTip(1, "Início (Alt+I)")
        self.tabs.setTabToolTip(2, "Exibir (Alt+X)")
        layout.addWidget(self.tabs)

        self.pages = QStackedWidget()
        self.pages.setObjectName("ribbonPages")
        self.stack = self.pages
        layout.addWidget(self.pages, 1)

        file_page, file_layout = self._page()
        document = self._group(file_layout, "Documento")
        for name in ("new", "open", "save", "save_as"):
            document.addWidget(self._command(name))
        file_layout.addStretch()
        self.pages.addWidget(file_page)

        home_page, home_layout = self._page()
        history = self._group(home_layout, "Histórico")
        for name in ("undo", "redo"):
            history.addWidget(self._command(name))
        self._separator(home_layout)
        tools = self._group(home_layout, "Ferramentas")
        for name in ("pencil", "eraser", "picker"):
            tools.addWidget(self._command(name))
        self._separator(home_layout)
        colors = self._group(home_layout, "Cores")
        colors.addWidget(self._command("custom_color"))
        home_layout.addStretch()
        self.pages.addWidget(home_page)

        view_page, view_layout = self._page()
        pieces = self._group(view_layout, "Peças")
        self.display_mode_combo = QComboBox()
        self.display_mode_combo.setObjectName("displayMode")
        self.display_mode_combo.setAccessibleName("Exibição das peças")
        self.display_mode_combo.setToolTip("Escolha a aparência das peças na prancheta")
        self.display_mode_combo.addItem("Quadradinhos", "squares")
        self.display_mode_combo.addItem("Rosquinhas (hama beads)", "beads")
        self.display_mode_combo.setMinimumWidth(210)
        pieces.addWidget(self.display_mode_combo, 0, Qt.AlignmentFlag.AlignVCenter)
        self._separator(view_layout)
        grid = self._group(view_layout, "Grade")
        self.grid_checkbox = QCheckBox("Mostrar grade")
        self.grid_checkbox.setObjectName("ribbonGrid")
        self.grid_checkbox.setAccessibleName("Mostrar grade da prancheta")
        self.grid_checkbox.setChecked(True)
        grid.addWidget(self.grid_checkbox, 0, Qt.AlignmentFlag.AlignVCenter)
        self._separator(view_layout)
        zoom = self._group(view_layout, "Zoom")
        zoom.setSpacing(10)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setObjectName("ribbonZoom")
        self.zoom_slider.setAccessibleName("Zoom da prancheta")
        self.zoom_slider.setRange(25, 250)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(140)
        zoom.addWidget(self.zoom_slider, 0, Qt.AlignmentFlag.AlignVCenter)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("ribbonZoomValue")
        self.zoom_label.setFixedWidth(40)
        zoom.addWidget(self.zoom_label, 0, Qt.AlignmentFlag.AlignVCenter)
        zoom.addWidget(self._command("fit"))
        view_layout.addStretch()
        self.pages.addWidget(view_page)

        self.tabs.currentChanged.connect(self.pages.setCurrentIndex)
        self.tabs.setCurrentIndex(0)
        self.pages.setCurrentIndex(0)

    @staticmethod
    def _page():
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        return page, layout

    @staticmethod
    def _group(page_layout: QHBoxLayout, title: str) -> QHBoxLayout:
        frame = QFrame()
        frame.setObjectName("ribbonGroup")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 4, 10, 3)
        layout.setSpacing(1)
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(4)
        layout.addLayout(controls, 1)
        caption = QLabel(title)
        caption.setObjectName("ribbonCaption")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setFixedHeight(15)
        layout.addWidget(caption)
        page_layout.addWidget(frame)
        return controls

    @staticmethod
    def _separator(page_layout: QHBoxLayout):
        line = QFrame()
        line.setObjectName("ribbonSeparator")
        line.setFixedWidth(1)
        line.setFixedHeight(80)
        page_layout.addWidget(line, 0, Qt.AlignmentFlag.AlignVCenter)

    def _command(self, name: str) -> QWidget:
        action = self.commands[name]
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        command = QToolButton()
        command.setObjectName("ribbonCommand")
        command.setDefaultAction(action)
        command.setAccessibleName(action.text().replace("&", ""))
        command.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        command.setIconSize(QSize(26, 26))
        command.setMinimumWidth(108 if name == "custom_color" else 78)
        command.setFixedHeight(55)
        self.buttons[name] = command
        layout.addWidget(command)
        shortcut = QLabel()
        shortcut.setObjectName("ribbonShortcut")
        shortcut.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shortcut.setFixedHeight(14)

        def update_shortcut():
            keys = action.shortcuts()
            shortcut.setText(keys[0].toString(QKeySequence.SequenceFormat.NativeText) if keys else "")

        update_shortcut()
        action.changed.connect(update_shortcut)
        layout.addWidget(shortcut)
        return container
