"""The editor's shared command catalog and native Qt action bindings."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PySide6.QtWidgets import QWidget


TOOL_KEYS = ("pencil", "bucket", "eraser", "picker", "selection", "line", "rectangle", "ellipse")


@dataclass(frozen=True)
class CommandDefinition:
    key: str
    text: str
    symbol: str
    shortcut: QKeySequence.StandardKey | str | None = None


_STANDARD = QKeySequence.StandardKey
COMMANDS = (
    CommandDefinition("new", "Novo", "plus", _STANDARD.New),
    CommandDefinition("open", "Abrir", "folder", _STANDARD.Open),
    CommandDefinition("save", "Salvar", "save", _STANDARD.Save),
    CommandDefinition("save_as", "Salvar como", "save_as", _STANDARD.SaveAs),
    CommandDefinition("export_png", "Exportar como PNG…", "export_png", "Ctrl+Shift+E"),
    CommandDefinition("resize_canvas", "Redimensionar prancheta…", "fit", "Ctrl+Alt+C"),
    CommandDefinition("undo", "Desfazer", "undo", _STANDARD.Undo),
    CommandDefinition("redo", "Refazer", "redo", _STANDARD.Redo),
    CommandDefinition("cut", "Recortar", "cut", _STANDARD.Cut),
    CommandDefinition("copy", "Copiar", "copy", _STANDARD.Copy),
    CommandDefinition("paste", "Colar", "paste", _STANDARD.Paste),
    CommandDefinition("pencil", "Lápis", "pencil", "B"),
    CommandDefinition("bucket", "Balde de tinta", "bucket", "G"),
    CommandDefinition("eraser", "Borracha", "eraser", "E"),
    CommandDefinition("picker", "Conta-gotas", "picker", "I"),
    CommandDefinition("selection", "Seleção", "selection", "S"),
    CommandDefinition("line", "Linha reta", "line", "L"),
    CommandDefinition("rectangle", "Retângulo", "rectangle", "R"),
    CommandDefinition("ellipse", "Elipse", "ellipse", "O"),
    CommandDefinition("shape_fill", "Preencher formas", "shape_fill"),
    CommandDefinition("replace_color", "Substituir cor…", "replace_color", "Ctrl+H"),
    CommandDefinition("custom_color", "Cor personalizada", "palette"),
    CommandDefinition("reference_panel", "Imagem de referência", "reference", "Ctrl+Shift+R"),
    CommandDefinition("fit", "Ajustar à janela", "fit"),
)


class EditorActions:
    """One QAction per command, shared by menus, controls, and shortcuts.

    Callbacks are supplied by the editor coordinator. This component knows
    command metadata and Qt bindings, without depending on its document or UI.
    """

    def __init__(
        self, parent: QWidget, *, handlers: Mapping[str, Callable[[], None]],
        select_tool: Callable[[str], None], set_shape_fill: Callable[[bool], None],
        icon_factory: Callable[[str], QIcon] | None = None,
        select_recent_color: Callable[[int], None] | None = None,
    ):
        if icon_factory is None:
            from ..ui.icons import icon
            icon_factory = icon
        self.commands: dict[str, QAction] = {}
        self.tool_group = QActionGroup(parent)
        self.tool_group.setExclusive(True)
        for definition in COMMANDS:
            key = definition.key
            action = QAction(icon_factory(definition.symbol), definition.text, parent)
            action.setObjectName(f"action_{key}")
            action.setShortcutContext(
                Qt.ShortcutContext.WidgetShortcut
                if key in ("cut", "copy", "paste") else Qt.ShortcutContext.WindowShortcut
            )
            sequences = []
            if isinstance(definition.shortcut, QKeySequence.StandardKey):
                sequences = QKeySequence.keyBindings(definition.shortcut)
            elif definition.shortcut:
                sequences = [QKeySequence(definition.shortcut)]
            if key == "redo":
                sequences.extend([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
            unique = {
                sequence.toString(QKeySequence.SequenceFormat.PortableText): sequence
                for sequence in sequences
            }
            action.setShortcuts(list(unique.values()))
            hints = " / ".join(
                sequence.toString(QKeySequence.SequenceFormat.NativeText)
                for sequence in unique.values()
            )
            action.setToolTip(f"{definition.text} ({hints})" if hints else definition.text)
            if key == "shape_fill":
                action.setCheckable(True)
                action.toggled.connect(set_shape_fill)
                action.setEnabled(False)
            else:
                if key in TOOL_KEYS:
                    callback = lambda tool=key: select_tool(tool)
                else:
                    callback = handlers[key]
                action.triggered.connect(lambda _checked=False, handler=callback: handler())
            if key in TOOL_KEYS:
                action.setCheckable(True)
                self.tool_group.addAction(action)
            self.commands[key] = action
            parent.addAction(action)
        self.commands["pencil"].setChecked(True)
        self.recent_color_actions: list[QAction] = []
        if select_recent_color is not None:
            for index in range(9):
                action = QAction(f"Cor recente {index + 1}", parent)
                action.setObjectName(f"action_recent_color_{index + 1}")
                action.setShortcut(QKeySequence(str(index + 1)))
                action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
                action.setEnabled(False)
                action.triggered.connect(
                    lambda _checked=False, slot=index: select_recent_color(slot)
                )
                parent.addAction(action)
                self.recent_color_actions.append(action)
