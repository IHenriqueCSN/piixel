"""Exercise ribbon commands and window shortcuts through real Qt events."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from piixelverso.app import MainWindow, STYLE
from piixelverso.format import encode_design, load_design, save_design
from piixelverso.model import PixelDesign


class RibbonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.window._replace_design(PixelDesign(8, 8, name="Ateliê com ribbon"))
        self.window.activateWindow()
        self.app.processEvents()
        self.window.zoom.setValue(100)
        self.app.processEvents()

    def tearDown(self):
        self.window.canvas.finish_stroke()
        self.window.name_edit.setText(self.window.design.name)
        self.window.history.setClean()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def key(self, key, modifiers=Qt.KeyboardModifier.NoModifier):
        # A window shortcut must also work when its ribbon page is hidden.
        self.window.ribbon.tabs.setFocus()
        self.app.processEvents()
        QTest.keyClick(self.window.ribbon.tabs, key, modifiers)
        self.app.processEvents()

    def click_command(self, command):
        QTest.mouseClick(self.window.ribbon.buttons[command], Qt.MouseButton.LeftButton)
        self.app.processEvents()

    def paint_cell(self, x=2, y=3):
        QTest.mouseClick(self.window.canvas, Qt.MouseButton.LeftButton,
                         pos=self.window.canvas.cell_center(x, y))
        self.app.processEvents()

    def test_file_ribbon_open_loads_a_real_design(self):
        self.assertEqual(self.window.ribbon.tabs.currentIndex(), 0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "aberto-pelo-ribbon.pii"
            design = PixelDesign(5, 3, name="Bosque reaberto")
            design.set_pixel(3, 1, "#245448")
            save_design(design, path)
            with patch("piixelverso.app.QFileDialog.getOpenFileName",
                       return_value=(str(path), "Design Piixelverso (*.pii)")) as picker:
                self.click_command("open")
                picker.assert_called_once()
            self.assertEqual(self.window.design, design)
            self.assertEqual(self.window.file_path, path)
            self.assertEqual(self.window.total_label.text(), "1")
            self.assertTrue(self.window.history.isClean())

    def test_file_shortcuts_work_while_file_page_is_hidden(self):
        self.window.ribbon.tabs.setCurrentIndex(2)
        self.app.processEvents()
        with patch("piixelverso.app.NewDesignDialog.exec",
                   return_value=QDialog.DialogCode.Rejected) as new_dialog:
            self.key(Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)
            new_dialog.assert_called_once()
        self.paint_cell()
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "atalho-salvar.pii"
            duplicate = Path(directory) / "atalho-salvar-como.pii"
            with patch("piixelverso.app.QFileDialog.getSaveFileName",
                       return_value=(str(original), "Design Piixelverso (*.pii)")) as picker:
                self.key(Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
                picker.assert_called_once()
            self.assertEqual(load_design(original), self.window.design)
            self.assertEqual(self.window.file_path, original)
            self.assertTrue(self.window.history.isClean())
            self.paint_cell(4, 5)
            with patch("piixelverso.app.QFileDialog.getSaveFileName",
                       side_effect=AssertionError("Salvar um arquivo conhecido não deve perguntar o caminho")):
                self.key(Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
            self.assertEqual(load_design(original), self.window.design)
            with patch("piixelverso.app.QFileDialog.getSaveFileName",
                       return_value=(str(duplicate), "Design Piixelverso (*.pii)")) as picker:
                self.key(Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
                picker.assert_called_once()
            self.assertEqual(load_design(duplicate), self.window.design)
            self.assertEqual(self.window.file_path, duplicate)
            with patch("piixelverso.app.QFileDialog.getOpenFileName",
                       return_value=(str(original), "Design Piixelverso (*.pii)")) as picker:
                self.key(Qt.Key.Key_O, Qt.KeyboardModifier.ControlModifier)
                picker.assert_called_once()
            self.assertEqual(self.window.file_path, original)
            self.assertEqual(self.window.design, load_design(original))
            self.assertEqual(self.window.ribbon.tabs.currentIndex(), 2)

    def test_history_buttons_and_keyboard_share_state_and_redo_bindings(self):
        self.assertFalse(self.window.command_actions["undo"].isEnabled())
        self.assertFalse(self.window.command_actions["redo"].isEnabled())
        self.paint_cell()
        painted = self.window.design.clone()
        self.assertTrue(self.window.command_actions["undo"].isEnabled())
        self.assertTrue(self.window.ribbon.buttons["undo"].isEnabled())
        self.key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.window.design.is_empty)
        self.assertFalse(self.window.command_actions["undo"].isEnabled())
        self.assertTrue(self.window.command_actions["redo"].isEnabled())
        self.window.ribbon.tabs.setCurrentIndex(1)
        self.app.processEvents()
        self.click_command("redo")
        self.assertEqual(self.window.design, painted)
        self.assertFalse(self.window.ribbon.buttons["redo"].isEnabled())
        self.key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(self.window.design, painted)
        self.key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.key(Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.window.design, painted)

    def test_tool_buttons_and_shortcuts_stay_exclusive_without_stealing_text(self):
        self.window.ribbon.tabs.setCurrentIndex(1)
        self.app.processEvents()
        self.click_command("eraser")
        self.assertEqual(self.window.canvas.tool, "eraser")
        self.assertTrue(self.window.command_actions["eraser"].isChecked())
        for key, tool in [(Qt.Key.Key_B, "pencil"), (Qt.Key.Key_E, "eraser"), (Qt.Key.Key_I, "picker")]:
            self.key(key)
            self.assertEqual(self.window.canvas.tool, tool)
            self.assertTrue(self.window.ribbon.buttons[tool].isChecked())
            checked = [name for name in ("pencil", "eraser", "picker")
                       if self.window.command_actions[name].isChecked()]
            self.assertEqual(checked, [tool])
        self.click_command("eraser")
        self.window.name_edit.setFocus()
        self.window.name_edit.selectAll()
        self.app.processEvents()
        QTest.keyClicks(self.window.name_edit, "B")
        self.app.processEvents()
        self.assertEqual(self.window.name_edit.text(), "B")
        self.assertEqual(self.window.canvas.tool, "eraser")
        self.assertTrue(self.window.command_actions["eraser"].isChecked())

    def test_tab_mnemonics_navigate_the_ribbon(self):
        self.window.ribbon.tabs.setCurrentIndex(2)
        for key, expected in [(Qt.Key.Key_A, 0), (Qt.Key.Key_I, 1), (Qt.Key.Key_X, 2)]:
            self.key(key, Qt.KeyboardModifier.AltModifier)
            self.assertEqual(self.window.ribbon.tabs.currentIndex(), expected)

    def test_view_controls_change_the_preview_without_editing_the_design(self):
        self.paint_cell()
        before = encode_design(self.window.design)
        history = (self.window.history.count(), self.window.history.index())
        self.window.ribbon.tabs.setCurrentIndex(2)
        self.app.processEvents()
        combo = self.window.ribbon.display_mode_combo
        combo.setFocus()
        QTest.keyClick(combo, Qt.Key.Key_End)
        self.app.processEvents()
        self.assertEqual(self.window.canvas.display_mode, "beads")
        self.assertTrue(self.window.canvas.show_grid)
        QTest.mouseClick(self.window.ribbon.grid_checkbox, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertFalse(self.window.canvas.show_grid)
        slider = self.window.ribbon.zoom_slider
        slider.setFocus()
        QTest.keyClick(slider, Qt.Key.Key_Home)
        self.app.processEvents()
        self.assertEqual(self.window.canvas.cell_size, 4)
        QTest.keyClick(slider, Qt.Key.Key_End)
        self.app.processEvents()
        self.assertEqual(self.window.canvas.cell_size, 40)
        self.click_command("fit")
        self.assertEqual(encode_design(self.window.design), before)
        self.assertEqual((self.window.history.count(), self.window.history.index()), history)


if __name__ == "__main__":
    unittest.main()
