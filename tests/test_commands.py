"""Exercise compact menus, shared commands and window shortcuts through Qt."""
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


class CommandBarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.window._replace_design(PixelDesign(8, 8, name="Ateliê compacto"))
        self.window.activateWindow()
        self.app.processEvents()
        self.window.zoom.setValue(100)
        self.app.processEvents()

    def tearDown(self):
        self.close_popup()
        self.window.canvas.finish_stroke()
        self.window.name_edit.setText(self.window.design.name)
        self.window.history.setClean()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def close_popup(self):
        popup = QApplication.activePopupWidget()
        while popup is not None:
            popup.close()
            self.app.processEvents()
            popup = QApplication.activePopupWidget()

    def key(self, key, modifiers=Qt.KeyboardModifier.NoModifier):
        self.close_popup()
        self.window.activateWindow()
        self.window.canvas.setFocus()
        self.app.processEvents()
        QTest.keyClick(self.window.canvas, key, modifiers)
        self.app.processEvents()

    def click_command(self, command):
        QTest.mouseClick(self.window.command_bar.buttons[command], Qt.MouseButton.LeftButton)
        self.app.processEvents()

    def click_menu_command(self, menu_name, command):
        self.close_popup()
        bar = self.window.command_bar.menubar
        menu = self.window.command_bar.menus[menu_name]
        QTest.mouseClick(bar, Qt.MouseButton.LeftButton,
                         pos=bar.actionGeometry(menu.menuAction()).center())
        self.app.processEvents()
        self.assertTrue(menu.isVisible(), f"Menu não abriu: {menu_name}")
        action = self.window.command_actions[command]
        QTest.mouseClick(menu, Qt.MouseButton.LeftButton,
                         pos=menu.actionGeometry(action).center())
        self.app.processEvents()

    def paint_cell(self, x=2, y=3):
        QTest.mouseClick(self.window.canvas, Qt.MouseButton.LeftButton,
                         pos=self.window.canvas.cell_center(x, y))
        self.app.processEvents()

    def test_compact_controls_reclaim_vertical_drawing_space(self):
        self.window.resize(1380, 900)
        self.app.processEvents()
        self.assertLessEqual(self.window.command_bar.height(), 44)
        # The former 136 px ribbon left less than 600 px for the drawing viewport
        # at this window size. Keep the recovered space available to the design.
        self.assertGreaterEqual(self.window.viewport.viewport().height(), 600)

    def test_file_menu_opens_and_saves_a_real_design(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "aberto-pelo-menu.pii"
            design = PixelDesign(5, 3, name="Bosque reaberto")
            design.set_pixel(3, 1, "#245448")
            save_design(design, path)
            with patch("piixelverso.app.QFileDialog.getOpenFileName",
                       return_value=(str(path), "Design Piixelverso (*.pii)")) as picker:
                self.click_menu_command("file", "open")
                picker.assert_called_once()
            self.assertEqual(self.window.design, design)
            self.assertEqual(self.window.file_path, path)
            self.assertEqual(self.window.total_label.text(), "1")
            self.assertTrue(self.window.history.isClean())
            self.paint_cell(0, 0)
            with patch("piixelverso.app.QFileDialog.getSaveFileName",
                       side_effect=AssertionError("Um arquivo conhecido deve ser salvo sem novo diálogo")):
                self.click_menu_command("file", "save")
            self.assertEqual(load_design(path), self.window.design)
            self.assertTrue(self.window.history.isClean())

    def test_file_shortcuts_work_without_opening_a_menu(self):
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
            self.assertIsNone(QApplication.activePopupWidget())

    def test_history_buttons_and_keyboard_share_state_and_redo_bindings(self):
        self.assertFalse(self.window.command_actions["undo"].isEnabled())
        self.assertFalse(self.window.command_actions["redo"].isEnabled())
        self.paint_cell()
        painted = self.window.design.clone()
        self.assertTrue(self.window.command_actions["undo"].isEnabled())
        self.assertTrue(self.window.command_bar.buttons["undo"].isEnabled())
        self.key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.window.design.is_empty)
        self.assertFalse(self.window.command_actions["undo"].isEnabled())
        self.assertTrue(self.window.command_actions["redo"].isEnabled())
        self.click_command("redo")
        self.assertEqual(self.window.design, painted)
        self.assertFalse(self.window.command_bar.buttons["redo"].isEnabled())
        self.key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(self.window.design, painted)
        self.key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.key(Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.window.design, painted)

    def test_tool_buttons_and_shortcuts_stay_exclusive_without_stealing_text(self):
        self.click_command("eraser")
        self.assertEqual(self.window.canvas.tool, "eraser")
        self.assertTrue(self.window.command_actions["eraser"].isChecked())
        for key, tool in [(Qt.Key.Key_B, "pencil"), (Qt.Key.Key_E, "eraser"), (Qt.Key.Key_I, "picker")]:
            self.key(key)
            self.assertEqual(self.window.canvas.tool, tool)
            self.assertTrue(self.window.command_bar.buttons[tool].isChecked())
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

    def test_menu_mnemonics_open_file_edit_and_view(self):
        for key, name in [(Qt.Key.Key_A, "file"), (Qt.Key.Key_E, "edit"), (Qt.Key.Key_X, "view")]:
            self.key(key, Qt.KeyboardModifier.AltModifier)
            self.assertIs(QApplication.activePopupWidget(), self.window.command_bar.menus[name])
            QTest.keyClick(QApplication.activePopupWidget(), Qt.Key.Key_Escape)
            self.app.processEvents()
            self.assertIsNone(QApplication.activePopupWidget())

    def test_menu_and_quick_view_controls_stay_synchronized_without_editing(self):
        self.paint_cell()
        bar = self.window.command_bar
        before = encode_design(self.window.design)
        history = (self.window.history.count(), self.window.history.index())
        bar.view_actions["beads"].trigger()
        self.app.processEvents()
        self.assertEqual(bar.display_mode_combo.currentData(), "beads")
        self.assertEqual(self.window.canvas.display_mode, "beads")
        self.assertTrue(bar.view_actions["beads"].isChecked())
        self.assertFalse(bar.view_actions["squares"].isChecked())
        bar.display_mode_combo.setCurrentIndex(bar.display_mode_combo.findData("squares"))
        self.app.processEvents()
        self.assertTrue(bar.view_actions["squares"].isChecked())
        self.assertFalse(bar.view_actions["beads"].isChecked())
        self.assertEqual(self.window.canvas.display_mode, "squares")
        QTest.mouseClick(bar.grid_checkbox, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertFalse(bar.view_actions["grid"].isChecked())
        self.assertFalse(self.window.canvas.show_grid)
        bar.view_actions["grid"].trigger()
        self.app.processEvents()
        self.assertTrue(bar.grid_checkbox.isChecked())
        self.assertTrue(self.window.canvas.show_grid)
        self.assertEqual(encode_design(self.window.design), before)
        self.assertEqual((self.window.history.count(), self.window.history.index()), history)

    def test_zoom_controls_change_preview_without_editing_the_design(self):
        self.paint_cell()
        before = encode_design(self.window.design)
        history = (self.window.history.count(), self.window.history.index())
        slider = self.window.command_bar.zoom_slider
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
