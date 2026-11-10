"""Exercise selection, copy, cut, paste and move through native Qt input."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from piixelverso.app import MainWindow, STYLE
from piixelverso.model import PixelDesign, TRANSPARENT
from piixelverso.preferences import PreferencesStore


RED = "#ED5598"
BLUE = "#245448"


class SelectionUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.window = MainWindow(
            preferences=PreferencesStore(Path(self.directory.name) / "preferences.json")
        )
        self.window.show()
        self.window.activateWindow()
        self.atelier = self.window.open_module("atelier")
        self.atelier._replace_design(PixelDesign(8, 8, name="Seleção do João"))
        self.app.processEvents()
        self.atelier.zoom.setValue(100)
        self.app.processEvents()

    def tearDown(self):
        self.atelier.canvas.cancel_stroke()
        self.atelier.canvas.finish_stroke()
        self.atelier.name_edit.setText(self.atelier.design.name)
        self.atelier.history.setClean()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def drag(self, start, end):
        canvas = self.atelier.canvas
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=canvas.cell_center(*start))
        QTest.mouseMove(canvas, canvas.cell_center(*end))
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=canvas.cell_center(*end))
        self.app.processEvents()

    def key(self, key, modifiers=Qt.KeyboardModifier.NoModifier, widget=None):
        self.window.activateWindow()
        target = widget or self.atelier.canvas
        target.setFocus()
        self.app.processEvents()
        QTest.keyClick(target, key, modifiers)
        self.app.processEvents()

    def select(self, start, end):
        self.atelier.select_tool("selection")
        self.drag(start, end)

    def test_copy_and_paste_preserve_materials_empty_cells_and_history(self):
        self.atelier.design.set_pixel(1, 1, RED)
        self.atelier.design.set_pixel(2, 1, TRANSPARENT)
        self.atelier.design.set_pixel(2, 2, BLUE)
        self.atelier.refresh_design()
        self.select((1, 1), (2, 2))
        self.assertEqual(self.atelier.canvas.selection_tuple(), (1, 1, 2, 2))
        self.assertTrue(self.atelier.command_actions["copy"].isEnabled())
        self.key(Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.atelier.command_actions["paste"].isEnabled())
        self.assertEqual(self.atelier.history.count(), 0)

        self.key(Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.atelier.canvas.selection_tuple(), (2, 2, 2, 2))
        self.assertEqual(self.atelier.design.get_pixel(2, 2), RED)
        self.assertEqual(self.atelier.design.get_pixel(3, 2), TRANSPARENT)
        self.assertIsNone(self.atelier.design.get_pixel(2, 3))
        self.assertEqual(self.atelier.design.get_pixel(3, 3), BLUE)
        self.assertEqual(self.atelier.history.count(), 1)
        self.assertEqual(self.atelier.history.undoText(), "Colar seleção")
        self.atelier.undo()
        self.assertEqual(self.atelier.design.get_pixel(2, 2), BLUE)
        self.assertIsNone(self.atelier.design.get_pixel(3, 2))
        self.atelier.redo()
        self.assertEqual(self.atelier.design.get_pixel(3, 3), BLUE)

    def test_cut_is_one_undoable_step_and_keeps_payload_for_paste(self):
        self.atelier.design.set_pixel(0, 0, RED)
        self.atelier.design.set_pixel(1, 1, BLUE)
        self.atelier.refresh_design()
        self.select((0, 0), (1, 1))
        self.key(Qt.Key.Key_X, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.atelier.design.is_empty)
        self.assertEqual(self.atelier.history.count(), 1)
        self.assertEqual(self.atelier.history.undoText(), "Recortar seleção")
        self.atelier.undo()
        self.assertEqual(self.atelier.design.get_pixel(0, 0), RED)
        self.assertEqual(self.atelier.design.get_pixel(1, 1), BLUE)
        self.key(Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.atelier.design.get_pixel(1, 1), RED)
        self.assertEqual(self.atelier.design.get_pixel(2, 2), BLUE)

    def test_dragging_inside_selection_moves_it_in_one_history_step(self):
        self.atelier.design.set_pixel(1, 1, RED)
        self.atelier.design.set_pixel(2, 2, BLUE)
        self.atelier.refresh_design()
        self.select((1, 1), (2, 2))
        self.drag((1, 1), (4, 3))
        self.assertEqual(self.atelier.canvas.selection_tuple(), (4, 3, 2, 2))
        self.assertIsNone(self.atelier.design.get_pixel(1, 1))
        self.assertIsNone(self.atelier.design.get_pixel(2, 2))
        self.assertEqual(self.atelier.design.get_pixel(4, 3), RED)
        self.assertEqual(self.atelier.design.get_pixel(5, 4), BLUE)
        self.assertEqual(self.atelier.history.count(), 1)
        self.assertEqual(self.atelier.history.undoText(), "Mover seleção")
        self.atelier.undo()
        self.assertEqual(self.atelier.design.get_pixel(1, 1), RED)
        self.assertEqual(self.atelier.design.get_pixel(2, 2), BLUE)
        self.assertIsNone(self.atelier.design.get_pixel(4, 3))

    def test_escape_and_right_click_clear_selection_without_editing(self):
        self.atelier.design.set_pixel(3, 3, RED)
        self.select((2, 2), (4, 4))
        self.key(Qt.Key.Key_Escape)
        self.assertFalse(self.atelier.canvas.has_selection)
        self.assertFalse(self.atelier.command_actions["copy"].isEnabled())
        self.select((2, 2), (4, 4))
        QTest.mouseClick(
            self.atelier.canvas, Qt.MouseButton.RightButton,
            pos=self.atelier.canvas.cell_center(3, 3),
        )
        self.app.processEvents()
        self.assertFalse(self.atelier.canvas.has_selection)
        self.assertEqual(self.atelier.design.get_pixel(3, 3), RED)
        self.assertEqual(self.atelier.history.count(), 0)

    def test_text_copy_does_not_trigger_the_canvas_clipboard(self):
        self.select((0, 0), (1, 1))
        self.atelier.name_edit.setFocus()
        self.atelier.name_edit.selectAll()
        self.app.processEvents()
        QTest.keyClick(
            self.atelier.name_edit, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier
        )
        self.app.processEvents()
        self.assertIsNone(self.atelier._selection_clipboard)
        self.assertEqual(QApplication.clipboard().text(), "Seleção do João")

    def test_selection_commands_are_scoped_to_the_visible_atelier(self):
        self.select((0, 0), (2, 2))
        self.key(Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.window.show_home()
        self.app.processEvents()
        for key in ("selection", "cut", "copy", "paste"):
            self.assertFalse(self.atelier.command_actions[key].isEnabled())
        self.window.open_module("atelier")
        self.app.processEvents()
        for key in ("selection", "cut", "copy", "paste"):
            self.assertTrue(self.atelier.command_actions[key].isEnabled())


if __name__ == "__main__":
    unittest.main()
