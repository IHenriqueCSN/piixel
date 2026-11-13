"""Physical piece sizes persist without changing drawings, colors or recents."""
from __future__ import annotations

import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from piixelverso.preferences import (
    DEFAULT_PIECE_SIZE_MM, PreferencesError, PreferencesStore, validate_piece_size_mm,
)
from piixelverso.settings import SettingsModule
from piixelverso.theme import APP_STYLE, ensure_theme_controller


class PieceSizePreferencesTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.path = self.root / "preferences.json"
        self.store = PreferencesStore(self.path)

    def tearDown(self):
        self.directory.cleanup()

    def test_default_and_legacy_preferences_use_five_mm_without_rewriting_files(self):
        self.assertEqual(self.store.piece_size_mm(), DEFAULT_PIECE_SIZE_MM)
        self.assertFalse(self.path.exists())
        legacy = {
            "version": 1, "recent_files": [],
            "saved_colors": [{"color": "#ED5598", "name": "Rosa"}],
        }
        self.path.write_text(json.dumps(legacy))
        original = self.path.read_bytes()
        reopened = PreferencesStore(self.path)
        self.assertIsNone(reopened.load_error)
        self.assertEqual(reopened.piece_size_mm(), 5.0)
        self.assertEqual(reopened.saved_colors()[0].name, "Rosa")
        self.assertEqual(self.path.read_bytes(), original)

    def test_size_and_all_other_preference_writes_preserve_each_other(self):
        design = self.root / "desenho.pii"
        design.write_bytes(b"design")
        self.store.record_file(design, b"preview")
        self.store.save_color("#ED5598", "Rosa")
        recent = self.store.recent_files()
        colors = self.store.saved_colors()
        self.store.set_piece_size_mm(2.6)
        self.assertEqual(self.store.recent_files(), recent)
        self.assertEqual(self.store.saved_colors(), colors)

        self.store.save_color("#292343", "Tinta")
        self.store.remove_color("#ED5598")
        self.store.record_file(design, b"updated preview")
        reopened = PreferencesStore(self.path)
        self.assertEqual(reopened.piece_size_mm(), 2.6)
        self.assertEqual(reopened.saved_colors()[0].name, "Tinta")
        self.assertEqual(reopened.recent_files()[0].thumbnail, b"updated preview")
        self.assertEqual(json.loads(self.path.read_text())["version"], 1)

    def test_invalid_values_cannot_change_memory_or_disk(self):
        self.store.set_piece_size_mm(5.0)
        original = self.path.read_bytes()
        invalid = [True, False, None, "5", 0, -1, 0.09, 100.01,
                   float("nan"), float("inf"), float("-inf"), 10 ** 1000]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_piece_size_mm(value)
                with self.assertRaises(PreferencesError):
                    self.store.set_piece_size_mm(value)
                self.assertEqual(self.store.piece_size_mm(), 5.0)
                self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(validate_piece_size_mm(0.1), 0.1)
        self.assertEqual(validate_piece_size_mm(100), 100.0)

    def test_failed_atomic_save_keeps_size_and_preferences_unchanged(self):
        self.store.save_color("#ED5598", "Rosa")
        self.store.set_piece_size_mm(2.6)
        original = self.path.read_bytes()
        with patch("piixelverso.preferences.os.replace", side_effect=OSError("Disco cheio")):
            with self.assertRaises(PreferencesError):
                self.store.set_piece_size_mm(10)
        self.assertEqual(self.store.piece_size_mm(), 2.6)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.store.saved_colors()[0].name, "Rosa")
        self.assertEqual(list(self.root.glob(".*.tmp")), [])

    def test_invalid_stored_size_reports_error_and_leaves_the_file_intact(self):
        for value in (None, True, "5", 0, 101, float("nan")):
            with self.subTest(value=value):
                payload = {"version": 1, "recent_files": [], "saved_colors": [], "piece_size_mm": value}
                self.path.write_text(json.dumps(payload))
                original = self.path.read_bytes()
                reopened = PreferencesStore(self.path)
                self.assertTrue(reopened.load_error)
                self.assertEqual(reopened.piece_size_mm(), 5.0)
                self.assertEqual(self.path.read_bytes(), original)


class SettingsModuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(APP_STYLE)

    def setUp(self):
        self.theme = ensure_theme_controller(self.app, "light")
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "preferences.json"
        self.preferences = PreferencesStore(self.path)
        self.module = SettingsModule(preferences=self.preferences)
        self.module.resize(1120, 750)
        self.module.show()
        self.app.processEvents()

    def tearDown(self):
        self.theme.set_mode("light")
        self.module.close()
        self.module.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def test_default_can_be_changed_and_saved_for_a_new_session(self):
        self.assertEqual(self.module.piece_size_input.value(), 5.0)
        self.assertEqual(self.module.piece_size_input.locale().decimalPoint(), ",")
        self.module.piece_size_input.setValue(2.6)
        self.assertEqual(self.preferences.piece_size_mm(), 5.0)
        self.assertFalse(self.path.exists())
        QTest.mouseClick(self.module.save_button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(self.preferences.piece_size_mm(), 2.6)
        self.assertEqual(PreferencesStore(self.path).piece_size_mm(), 2.6)
        self.assertEqual(self.module.status_label.text(), "Configurações salvas.")

    def test_appearance_previews_immediately_and_persists_only_on_save(self):
        self.assertEqual(self.module.appearance_input.currentData(), "system")
        index = self.module.appearance_input.findData("dark")
        self.module.appearance_input.setCurrentIndex(index)
        self.app.processEvents()
        self.assertEqual(self.theme.resolved_mode, "dark")
        self.assertEqual(self.preferences.appearance_mode(), "system")
        self.assertFalse(self.path.exists())
        self.assertEqual(self.module.status_label.text(), "Alteração ainda não salva.")

        QTest.mouseClick(self.module.save_button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(PreferencesStore(self.path).appearance_mode(), "dark")
        self.assertEqual(self.module.status_label.text(), "Configurações salvas.")

    def test_navigation_keeps_draft_until_explicit_save_and_home_signal_works(self):
        homes = []
        self.module.home_requested.connect(lambda: homes.append(True))
        self.module.piece_size_input.setValue(10.5)
        self.module.prepare_navigation()
        self.module.set_active(False)
        self.assertFalse(self.module.piece_size_input.isEnabled())
        self.assertFalse(self.module.save_button.isEnabled())
        self.module.set_active(True)
        self.assertEqual(self.module.piece_size_input.value(), 10.5)
        self.assertEqual(self.preferences.piece_size_mm(), 5.0)
        self.assertFalse(self.path.exists())
        QTest.mouseClick(self.module.home_button, Qt.MouseButton.LeftButton)
        self.assertEqual(homes, [True])

    def test_save_failure_reports_the_problem_and_keeps_the_saved_value(self):
        self.preferences.set_piece_size_mm(5)
        original = self.path.read_bytes()
        self.module.piece_size_input.setValue(2.6)
        with patch.object(self.preferences, "set_settings", side_effect=PreferencesError("Sem espaço")), \
             patch("piixelverso.settings.QMessageBox.warning") as warning:
            self.assertFalse(self.module.save_settings())
            warning.assert_called_once()
        self.assertEqual(self.preferences.piece_size_mm(), 5.0)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.module.piece_size_input.value(), 2.6)
        self.assertIn("Não foi possível salvar", self.module.status_label.text())


if __name__ == "__main__":
    unittest.main()
