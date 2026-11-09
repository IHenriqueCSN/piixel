"""The open document and its undo history, without user-interface workflows."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoStack

from ..model import PixelDesign
from .history import PixelCommand, RenameCommand, ResizeCanvasCommand


class EditorSession(QObject):
    changed = Signal()
    geometry_changed = Signal()

    def __init__(self, parent: QObject | None = None, *, design: PixelDesign | None = None):
        super().__init__(parent)
        self.design = design if design is not None else PixelDesign(name="Meu primeiro design")
        self.file_path: Path | None = None
        self.history = QUndoStack(self)
        self.history.setUndoLimit(300)

    def commit_pixels(self, before, after, text="Pintar pixels") -> None:
        self.history.push(PixelCommand(self, before, after, text))

    def rename(self, name: str) -> None:
        self.history.push(RenameCommand(self, name))

    def resize(self, after: PixelDesign) -> None:
        self.history.push(ResizeCanvasCommand(self, self.design.clone(), after))

    def replace(self, design: PixelDesign, path: str | Path | None = None) -> None:
        self.design = design
        self.file_path = Path(path) if path else None
        self.geometry_changed.emit()
        self.history.clear()
        self.history.setClean()
        self.changed.emit()

    def save(self, path: str | Path, *, writer: Callable[[PixelDesign, str | Path], None]) -> None:
        """Update the save state only after the supplied writer succeeds."""
        writer(self.design, path)
        self.file_path = Path(path)
        self.history.setClean()
