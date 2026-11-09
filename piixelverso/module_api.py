"""Common navigation and document capabilities of Piixel's module pages."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QPushButton, QWidget


@dataclass(frozen=True)
class ModuleHomeState:
    """Optional session information shown on the module's home card."""

    title: str
    dirty: bool


class ModulePage(QWidget):
    """A page that the application can host without knowing its implementation."""

    home_requested = Signal()
    document_accessed = Signal(str, object)
    home_button: QPushButton

    def prepare_navigation(self) -> None:
        """Finish any pending interaction before navigating to another page."""

    def set_active(self, active: bool) -> None:
        """Scope module commands to the currently visible page."""
        self._active = bool(active)

    def focus_default(self) -> None:
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def home_state(self) -> ModuleHomeState | None:
        return None

    def confirm_close(self) -> bool:
        return True

    def shutdown(self) -> None:
        """Stop background work after every module has accepted closing."""

    def attach_navigation(self, home_action: QAction, settings_action: QAction) -> None:
        """Receive application-level navigation actions once, when instantiated."""
        self.home_button.setToolTip("Voltar à tela inicial (Alt+Home)")

    def load_path(self, path: str | Path) -> bool:
        """Return whether this module successfully opened a document."""
        return False
