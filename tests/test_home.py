"""Exercise Piixel's home page and the persistent Ateliê module session."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from piixelverso.app import MainWindow, STYLE
from piixelverso.format import encode_design, load_design, save_design
from piixelverso.model import PixelDesign
from piixelverso.preferences import PreferencesStore
from piixelverso.modules import MODULES


class HomeNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self._preferences_directory = tempfile.TemporaryDirectory()
        self.preferences = PreferencesStore(Path(self._preferences_directory.name) / "preferences.json")
        self.window = MainWindow(preferences=self.preferences)
        self.window.show()
        self.window.activateWindow()
        self.app.processEvents()

    def tearDown(self):
        popup = QApplication.activePopupWidget()
        while popup is not None:
            popup.close()
            self.app.processEvents()
            popup = QApplication.activePopupWidget()
        for module in self.window.module_pages.values():
            if hasattr(module, "history"):
                module.canvas.finish_stroke()
                module.name_edit.setText(module.design.name)
                module.history.setClean()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self._preferences_directory.cleanup()

    def open_atelier(self):
        module = self.window.open_module("atelier")
        self.app.processEvents()
        module.zoom.setValue(100)
        self.app.processEvents()
        return module

    def paint_cell(self, atelier, x=1, y=1):
        QTest.mouseClick(atelier.canvas, Qt.MouseButton.LeftButton,
                         pos=atelier.canvas.cell_center(x, y))
        self.app.processEvents()

    def key(self, widget, key, modifiers=Qt.KeyboardModifier.NoModifier):
        self.window.activateWindow()
        widget.setFocus()
        self.app.processEvents()
        QTest.keyClick(widget, key, modifiers)
        self.app.processEvents()

    def test_startup_shows_only_atelier_without_constructing_it(self):
        self.assertIsNone(self.window.current_module)
        self.assertIs(self.window.pages.currentWidget(), self.window.home_page)
        self.assertTrue(self.window.home_page.isVisible())
        self.assertEqual(self.window.module_pages, {})
        self.assertEqual(set(self.window.home_page.module_buttons), {"atelier"})
        self.assertEqual({definition.id for definition in MODULES}, {"atelier"})
        self.assertIn("Piixel", self.window.windowTitle())
        self.assertIn("Início", self.window.windowTitle())

    def test_launcher_home_button_and_home_shortcut_reuse_one_module(self):
        launch = self.window.home_page.module_buttons["atelier"]
        QTest.mouseClick(launch, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        atelier = self.window.module_pages["atelier"]
        self.assertEqual(self.window.current_module, "atelier")
        self.assertIs(self.window.pages.currentWidget(), atelier)
        self.assertIn("Ateliê", self.window.windowTitle())
        self.assertIn("Piixel", self.window.windowTitle())
        QTest.mouseClick(atelier.home_button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertIsNone(self.window.current_module)
        self.assertIs(self.window.pages.currentWidget(), self.window.home_page)
        QTest.mouseClick(launch, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertIs(self.window.module_pages["atelier"], atelier)
        self.key(atelier.canvas, Qt.Key.Key_Home, Qt.KeyboardModifier.AltModifier)
        self.assertIsNone(self.window.current_module)
        self.assertIs(self.window.pages.currentWidget(), self.window.home_page)

    def test_navigation_preserves_design_history_path_and_view_preferences(self):
        atelier = self.open_atelier()
        atelier._replace_design(PixelDesign(8, 8, name="Órbita do João"))
        self.app.processEvents()
        atelier.select_color("#245448")
        self.paint_cell(atelier)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orbita.pii"
            self.assertTrue(atelier._save_path(path))
            atelier.select_color("#ED5598")
            self.paint_cell(atelier, 2, 1)
            atelier.select_color("#BDE7EE")
            atelier.select_tool("eraser")
            atelier.display_mode_combo.setCurrentIndex(1)
            atelier.zoom.setValue(180)
            atelier.name_edit.setText("Órbita de peças")
            atelier.rename_design()
            self.app.processEvents()
            before = encode_design(atelier.design)
            history = (atelier.history.count(), atelier.history.index(), atelier.history.isClean())
            zoom = atelier.zoom.value()
            self.window.show_home()
            self.app.processEvents()
            self.assertEqual(encode_design(atelier.design), before)
            self.assertFalse(atelier.history.isClean())
            resumed = self.window.open_module("atelier")
            self.app.processEvents()
            self.assertIs(resumed, atelier)
            self.assertEqual(encode_design(atelier.design), before)
            self.assertEqual((atelier.history.count(), atelier.history.index(), atelier.history.isClean()), history)
            self.assertEqual(atelier.file_path, path)
            self.assertEqual(atelier.zoom.value(), zoom)
            self.assertEqual(atelier.canvas.display_mode, "beads")
            self.assertEqual(atelier.canvas.color, "#BDE7EE")
            self.assertEqual(atelier.canvas.tool, "eraser")
            self.assertTrue(atelier.command_actions["eraser"].isChecked())
            self.assertIn(" *", self.window.windowTitle())
            atelier.undo()
            self.assertEqual(atelier.design.name, "Órbita do João")
            atelier.undo()
            self.assertIsNone(atelier.design.get_pixel(2, 1))
            self.assertEqual(atelier.design.get_pixel(1, 1), "#245448")
            self.assertTrue(atelier.history.isClean())

    def test_editor_shortcuts_are_inactive_on_home_and_restore_on_return(self):
        atelier = self.open_atelier()
        self.paint_cell(atelier)
        atelier.select_tool("eraser")
        before = encode_design(atelier.design)
        history = (atelier.history.count(), atelier.history.index())
        self.window.show_home()
        self.app.processEvents()
        self.assertTrue(all(not action.isEnabled() for action in atelier.command_actions.values()))
        target = self.window.home_page.module_buttons["atelier"]
        with patch("piixelverso.atelier.QFileDialog.getSaveFileName",
                   side_effect=AssertionError("A tela inicial não deve abrir o diálogo do editor")):
            self.key(target, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
            self.key(target, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
            self.key(target, Qt.Key.Key_B)
        self.assertEqual(encode_design(atelier.design), before)
        self.assertEqual((atelier.history.count(), atelier.history.index()), history)
        self.assertEqual(atelier.canvas.tool, "eraser")
        self.window.open_module("atelier")
        self.app.processEvents()
        self.assertTrue(atelier.command_actions["save"].isEnabled())
        self.assertTrue(atelier.command_actions["undo"].isEnabled())
        self.key(atelier.canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(atelier.design.is_empty)

    def test_opening_a_design_from_home_selects_atelier(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "aberto-diretamente.pii"
            design = PixelDesign(9, 3, name="Um novo universo")
            design.set_pixel(4, 1, "#BDE7EE")
            design.set_pixel(5, 1, "#ED5598")
            save_design(design, path)
            self.assertTrue(self.window.open_design_path(path))
            self.app.processEvents()
            atelier = self.window.module_pages["atelier"]
            self.assertEqual(self.window.current_module, "atelier")
            self.assertIs(self.window.pages.currentWidget(), atelier)
            self.assertEqual(atelier.design, design)
            self.assertEqual(atelier.file_path, path)
            self.assertTrue(atelier.history.isClean())
            self.assertIn(design.name, self.window.windowTitle())

    def test_invalid_design_on_home_preserves_route_and_unsaved_editor(self):
        atelier = self.open_atelier()
        self.paint_cell(atelier)
        before = encode_design(atelier.design)
        history = (atelier.history.count(), atelier.history.index())
        self.window.show_home()
        self.app.processEvents()
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "corrompido.pii"
            invalid.write_bytes(b"this is not a pii design")
            with patch("piixelverso.atelier.QMessageBox.warning") as warning:
                with patch.object(atelier, "confirm_discard",
                                  side_effect=AssertionError("Um arquivo inválido não deve descartar o design aberto")):
                    self.assertFalse(self.window.open_design_path(invalid))
                warning.assert_called_once()
                self.assertIs(warning.call_args.args[0], self.window)
        self.assertIsNone(self.window.current_module)
        self.assertIs(self.window.pages.currentWidget(), self.window.home_page)
        self.assertIn("Início", self.window.windowTitle())
        self.assertEqual(encode_design(atelier.design), before)
        self.assertEqual((atelier.history.count(), atelier.history.index()), history)
        self.assertTrue(all(not action.isEnabled() for action in atelier.command_actions.values()))

    def test_closing_home_checks_the_unsaved_atelier(self):
        atelier = self.open_atelier()
        self.paint_cell(atelier)
        before = encode_design(atelier.design)
        self.window.show_home()
        self.app.processEvents()
        with patch.object(atelier, "confirm_discard", return_value=False) as confirm:
            self.assertFalse(self.window.close())
            confirm.assert_called_once()
        self.assertTrue(self.window.isVisible())
        self.assertIsNone(self.window.current_module)
        self.assertEqual(encode_design(atelier.design), before)
        self.assertFalse(atelier.history.isClean())
        # Accepting Save from the home page must still persist the hidden editor.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "salvo-ao-sair.pii"
            with patch("piixelverso.atelier.QMessageBox") as message_box:
                dialog = message_box.return_value
                buttons = {}

                def add_button(text, *_args):
                    buttons[text] = object()
                    return buttons[text]

                dialog.addButton.side_effect = add_button
                dialog.clickedButton.side_effect = lambda: buttons["Salvar"]
                with patch("piixelverso.atelier.QFileDialog.getSaveFileName",
                           return_value=(str(path), "Design Piixelverso (*.pii)")):
                    self.assertTrue(self.window.close())
                message_box.assert_called_once_with(self.window)
                self.assertEqual(load_design(path), atelier.design)
                self.assertTrue(atelier.history.isClean())
        self.assertFalse(self.window.isVisible())

    def test_unknown_module_does_not_change_the_current_route(self):
        for module_id in ("estoque", "financeiro"):
            before = self.window.pages.currentWidget()
            current = self.window.current_module
            with self.assertRaises(ValueError):
                self.window.open_module(module_id)
            self.assertIs(self.window.pages.currentWidget(), before)
            self.assertEqual(self.window.current_module, current)
            if current is None:
                self.assertEqual(self.window.module_pages, {})
                self.open_atelier()


if __name__ == "__main__":
    unittest.main()
