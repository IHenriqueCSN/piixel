"""The shell hosts module capabilities without editor-specific widget access."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QPushButton

from piixelverso.module_api import ModuleHomeState, ModulePage
from piixelverso.modules import MODULES, ModuleDefinition
from piixelverso.preferences import PreferencesStore
from piixelverso.model import PixelDesign
from piixelverso.format import save_design


class DocumentModule(ModulePage):
    """A minimal document module deliberately lacking canvas/design/history fields."""

    def __init__(self, parent=None, preferences=None):
        super().__init__(parent)
        self.preferences = preferences
        self.home_button = QPushButton("Início", self)
        self.home_button.clicked.connect(self.home_requested.emit)
        self.setWindowTitle("Documento — Piixel")
        self.active_events = []
        self.navigation_count = 0
        self.focus_count = 0
        self.allow_close = True
        self.opened_path = None

    def set_active(self, active):
        self.active_events.append(active)

    def prepare_navigation(self):
        self.navigation_count += 1

    def focus_default(self):
        self.focus_count += 1

    def home_state(self):
        return ModuleHomeState("Documento da sessão", True)

    def confirm_close(self):
        return self.allow_close

    def load_path(self, path):
        self.opened_path = Path(path)
        self.document_accessed.emit(str(path), PixelDesign(2, 2, ["#ED5598", None, None, None]))
        return True


class ModuleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.preferences = PreferencesStore(Path(self.directory.name) / "preferences.json")
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            for module in window.module_pages.values():
                module.allow_close = True
            window.close()
            window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def shell(self, definitions=MODULES):
        from piixelverso.app import MainWindow
        with patch("piixelverso.app.MODULES", definitions):
            window = MainWindow(preferences=self.preferences)
        self.windows.append(window)
        window.show()
        self.app.processEvents()
        return window

    def test_registry_can_be_imported_without_qt_or_module_implementations(self):
        result = subprocess.run(
            [sys.executable, "-c", """
import sys
from piixelverso.modules import MODULES
assert all(module.factory is not None for module in MODULES)
assert 'PySide6' not in sys.modules
assert 'piixelverso.atelier' not in sys.modules
assert 'piixelverso.settings' not in sys.modules
"""], capture_output=True, text=True, timeout=15,
            cwd=Path(__file__).resolve().parents[1],
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_importing_shell_does_not_import_concrete_modules(self):
        result = subprocess.run(
            [sys.executable, "-c", """
import sys
from piixelverso.app import MainWindow
assert 'piixelverso.atelier' not in sys.modules
assert 'piixelverso.settings' not in sys.modules
"""], capture_output=True, text=True, timeout=15,
            cwd=Path(__file__).resolve().parents[1],
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_registered_page_uses_only_the_shared_navigation_and_state_contract(self):
        calls = []

        def factory(**kwargs):
            calls.append(kwargs)
            return DocumentModule(**kwargs)

        definition = ModuleDefinition("document", "Documento", "Sessão de exemplo", "pencil", factory)
        window = self.shell((*MODULES, definition))
        self.assertEqual(window.module_pages, {})
        module = window.open_module("document")
        self.app.processEvents()
        self.assertEqual(len(calls), 1)
        self.assertIs(module.preferences, self.preferences)
        self.assertEqual(module.active_events, [False, True])
        self.assertGreaterEqual(module.focus_count, 1)
        self.assertIn("Alt+Home", module.home_button.toolTip())
        self.assertEqual(window.windowTitle(), "Documento — Piixel")
        self.assertIn("Documento da sessão", window.home_page._state_labels["document"].text())
        self.assertFalse(window.home_page._dirty_labels["document"].isHidden())
        self.assertFalse(hasattr(module, "canvas"))
        self.assertFalse(hasattr(module, "history"))

        module.home_requested.emit()
        self.app.processEvents()
        self.assertIsNone(window.current_module)
        self.assertEqual(module.navigation_count, 1)
        self.assertEqual(module.active_events[-1], False)
        self.assertTrue(window.home_page._dirty_labels["document"].isVisible())
        self.assertIs(window.open_module("document"), module)
        self.assertEqual(len(calls), 1)

    def test_hidden_registered_module_can_veto_application_close(self):
        definition = ModuleDefinition("document", "Documento", "Sessão de exemplo", "pencil", DocumentModule)
        window = self.shell((*MODULES, definition))
        module = window.open_module("document")
        self.app.processEvents()
        window.show_home()
        module.allow_close = False
        self.assertFalse(window.close())
        self.assertTrue(window.isVisible())
        module.allow_close = True
        self.assertTrue(window.close())

    def test_file_route_and_recent_notification_use_the_document_capability(self):
        window = self.shell()
        window._factories["atelier"] = DocumentModule
        path = Path(self.directory.name) / "documento.pii"
        save_design(PixelDesign(2, 2), path)
        self.assertTrue(window.open_design_path(path))
        module = window.module_pages["atelier"]
        self.assertIsInstance(module, DocumentModule)
        self.assertEqual(module.opened_path, path)
        self.assertEqual(window.current_module, "atelier")
        self.assertEqual(self.preferences.recent_files()[0].path, str(path))
        self.assertTrue(self.preferences.recent_files()[0].thumbnail)


if __name__ == "__main__":
    unittest.main()
