"""Undoable document changes, independent of editor widgets."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand

from ..model import PixelDesign

if TYPE_CHECKING:
    from .session import EditorSession


class PixelCommand(QUndoCommand):
    def __init__(self, session: EditorSession, before, after, text="Pintar pixels"):
        super().__init__(text)
        self.session, self.before, self.after = session, before, after

    def apply(self, values):
        for index, color in values.items():
            self.session.design.pixels[index] = color
        self.session.changed.emit()

    def redo(self):
        self.apply(self.after)

    def undo(self):
        self.apply(self.before)


class RenameCommand(QUndoCommand):
    def __init__(self, session: EditorSession, name: str):
        super().__init__("Renomear design")
        self.session, self.before, self.after = session, session.design.name, name

    def redo(self):
        self.session.design.name = self.after
        self.session.changed.emit()

    def undo(self):
        self.session.design.name = self.before
        self.session.changed.emit()


class ResizeCanvasCommand(QUndoCommand):
    def __init__(self, session: EditorSession, before: PixelDesign, after: PixelDesign):
        super().__init__("Redimensionar prancheta")
        self.session, self.before, self.after = session, before, after

    def apply(self, snapshot: PixelDesign):
        # Earlier pixel commands keep their original indexes and document identity.
        design = self.session.design
        design.width, design.height = snapshot.width, snapshot.height
        design.pixels = list(snapshot.pixels)
        self.session.geometry_changed.emit()
        self.session.changed.emit()

    def redo(self):
        self.apply(self.after)

    def undo(self):
        self.apply(self.before)
