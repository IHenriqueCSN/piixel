"""Exercise the native editor through real Qt mouse events, without a display."""
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

from piixelverso.atelier import AtelierModule as MainWindow, STYLE
from piixelverso.counts import ColorCountsView
from piixelverso.format import save_design
from piixelverso.model import PixelDesign
from piixelverso.preferences import PreferencesStore


class EditorTests(unittest.TestCase):
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
        self.window._replace_design(PixelDesign(8, 8, name="Pequeno universo"))
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
        self._preferences_directory.cleanup()

    def click_cell(self, x, y, button=Qt.MouseButton.LeftButton):
        QTest.mouseClick(self.window.canvas, button,
                         pos=self.window.canvas.cell_center(x, y))
        self.app.processEvents()

    def drag(self, start, end):
        canvas = self.window.canvas
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton,
                         pos=canvas.cell_center(*start))
        QTest.mouseMove(canvas, canvas.cell_center(*end))
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton,
                           pos=canvas.cell_center(*end))
        self.app.processEvents()

    def test_paint_counts_repaint_and_undo(self):
        self.window.select_color("#E7794B")
        self.click_cell(2, 3)
        self.assertEqual(self.window.design.get_pixel(2, 3), "#E7794B")
        self.assertEqual(self.window.design.counts(), {"#E7794B": 1})
        self.assertEqual(self.window.total_label.text(), "1")
        self.assertEqual(self.window.color_total.text(), "1 cor usada")
        self.assertFalse(self.window.history.isClean())
        self.assertIn(" *", self.window.windowTitle())
        self.window.select_color("#245448")
        self.click_cell(2, 3)
        self.assertEqual(self.window.design.counts(), {"#245448": 1})
        self.window.undo()
        self.assertEqual(self.window.design.counts(), {"#E7794B": 1})

    def test_fast_drag_has_no_gaps_and_one_undo_step(self):
        self.drag((0, 2), (7, 2))
        self.assertEqual(self.window.design.filled_count, 8)
        for x in range(8):
            self.assertEqual(self.window.design.get_pixel(x, 2), "#E7794B")
        self.assertEqual(self.window.history.count(), 1)
        self.window.undo()
        self.assertTrue(self.window.design.is_empty)
        self.assertTrue(self.window.history.isClean())
        self.window.redo()
        self.assertEqual(self.window.design.filled_count, 8)
        self.assertFalse(self.window.history.isClean())

    def test_fast_diagonal_drag_is_continuous(self):
        self.drag((0, 0), (7, 7))
        self.assertEqual(self.window.design.filled_count, 8)
        for value in range(8):
            self.assertEqual(self.window.design.get_pixel(value, value), "#E7794B")

    def test_eraser_and_right_button_are_undoable(self):
        self.drag((0, 0), (3, 0))
        self.click_cell(0, 0, Qt.MouseButton.RightButton)
        self.assertIsNone(self.window.design.get_pixel(0, 0))
        self.assertEqual(self.window.design.filled_count, 3)
        self.window.undo()
        self.assertEqual(self.window.design.filled_count, 4)
        self.window.select_tool("eraser")
        self.click_cell(1, 0)
        self.assertIsNone(self.window.design.get_pixel(1, 0))
        self.assertEqual(self.window.design.filled_count, 3)
        self.window.undo()
        self.assertEqual(self.window.design.filled_count, 4)

    def test_picker_selects_color_and_returns_to_pencil(self):
        self.window.select_color("#123456")
        self.click_cell(4, 4)
        self.window.select_color("#ABCDEF")
        self.window.select_tool("picker")
        history_count = self.window.history.count()
        self.click_cell(4, 4)
        self.assertEqual(self.window.canvas.color, "#123456")
        self.assertEqual(self.window.canvas.tool, "pencil")
        self.assertTrue(self.window.tool_buttons["pencil"].isChecked())
        self.assertEqual(self.window.history.count(), history_count)
        self.click_cell(5, 4)
        self.assertEqual(self.window.design.get_pixel(5, 4), "#123456")

    def test_repainting_same_color_is_not_an_undo_step(self):
        self.click_cell(3, 3)
        self.click_cell(3, 3)
        self.assertEqual(self.window.history.count(), 1)
        self.window.undo()
        self.assertTrue(self.window.design.is_empty)
        self.window.select_tool("eraser")
        self.click_cell(3, 3)
        self.assertEqual(self.window.history.index(), 0)
        self.assertTrue(self.window.history.isClean())

    def test_save_reopen_preserves_document_and_clean_state(self):
        self.window.select_color("#548DB0")
        self.drag((1, 1), (6, 1))
        self.window.name_edit.setText("Criação — João 🌱")
        self.window.rename_design()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "meu-design.pii"
            self.assertTrue(self.window._save_path(path))
            self.assertTrue(self.window.history.isClean())
            self.assertNotIn(" *", self.window.windowTitle())
            before = self.window.design.clone()
            self.window._replace_design(PixelDesign(12, 4, name="Outro"))
            self.assertTrue(self.window.load_path(path))
            self.assertEqual(self.window.design, before)
            self.assertEqual(self.window.file_path, path)
            self.assertEqual(self.window.total_label.text(), "6")
            self.assertTrue(self.window.history.isClean())
            self.click_cell(7, 7)
            self.assertFalse(self.window.history.isClean())
            self.window.undo()
            self.assertTrue(self.window.history.isClean())

    def test_invalid_file_keeps_current_work(self):
        self.click_cell(5, 6)
        before = self.window.design.clone()
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "invalid.pii"
            invalid.write_bytes(b"not a design")
            with patch("piixelverso.atelier.QMessageBox.warning") as warning:
                self.assertFalse(self.window.load_path(invalid))
                warning.assert_called_once()
        self.assertEqual(self.window.design, before)
        self.assertFalse(self.window.history.isClean())

    def test_cancel_open_keeps_unsaved_work(self):
        self.click_cell(5, 6)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "saved.pii"
            self.assertTrue(self.window._save_path(path))
            self.click_cell(1, 1)
            before = self.window.design.clone()
            with patch.object(self.window, "confirm_discard", return_value=False):
                self.assertFalse(self.window.load_path(path))
            self.assertEqual(self.window.design, before)
            self.assertFalse(self.window.history.isClean())

    def test_long_imported_name_remains_unchanged_without_editing(self):
        name = "  " + "Um universo de pequenos quadrados " * 8 + "  "
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nome-longo.pii"
            save_design(PixelDesign(8, 8, name=name), path)
            self.assertTrue(self.window.load_path(path))
            self.assertEqual(self.window.name_edit.text(), name)
            with patch("piixelverso.atelier.QMessageBox.exec", side_effect=AssertionError("Documento sem edição não deve pedir para salvar")):
                self.assertTrue(self.window.confirm_discard())
            self.assertEqual(self.window.design.name, name)
            self.assertTrue(self.window.history.isClean())

    def test_rename_undo_returns_to_saved_document(self):
        self.click_cell(2, 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nome.pii"
            original_name = self.window.design.name
            self.assertTrue(self.window._save_path(path))
            self.window.name_edit.setText("Bosque do João")
            self.window.rename_design()
            self.assertFalse(self.window.history.isClean())
            self.assertEqual(self.window.design.name, "Bosque do João")
            self.window.undo()
            self.assertEqual(self.window.design.name, original_name)
            self.assertEqual(self.window.name_edit.text(), original_name)
            self.assertTrue(self.window.history.isClean())
            self.window.redo()
            self.assertEqual(self.window.design.name, "Bosque do João")
            self.assertFalse(self.window.history.isClean())

    def test_maximum_palette_all_colors_remain_available(self):
        colors = [f"#{value:06X}" for value in range(128 * 128)]
        self.window._replace_design(PixelDesign(128, 128, colors, name="Paleta completa"))
        self.app.processEvents()
        view = self.window.findChild(ColorCountsView)
        self.assertIsNotNone(view)
        model = view.model()
        self.assertEqual(model.rowCount(), 16384)
        self.assertEqual(self.window.total_label.text(), "16.384")
        self.assertEqual(self.window.color_total.text(), "16384 cores usadas")
        final = model.index(16383, 0)
        self.assertEqual(final.data(Qt.ItemDataRole.UserRole)[0], "#003FFF")
        self.window.select_tool("picker")
        view.scrollTo(final)
        self.app.processEvents()
        rectangle = view.visualRect(final)
        self.assertTrue(view.viewport().rect().intersects(rectangle))
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=rectangle.center())
        self.app.processEvents()
        self.assertEqual(self.window.canvas.color, "#003FFF")
        self.assertEqual(self.window.canvas.tool, "pencil")

    def test_failed_save_retains_dirty_work_and_original_file(self):
        self.click_cell(1, 1)
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original.pii"
            self.assertTrue(self.window._save_path(original))
            previous_data = original.read_bytes()
            self.click_cell(2, 1)
            before = self.window.design.clone()
            with patch("piixelverso.atelier.save_design", side_effect=OSError("Permissão negada")):
                with patch("piixelverso.atelier.QMessageBox.warning") as warning:
                    self.assertFalse(self.window._save_path(Path(directory) / "outro.pii"))
                    warning.assert_called_once()
            self.assertEqual(self.window.file_path, original)
            self.assertEqual(original.read_bytes(), previous_data)
            self.assertEqual(self.window.design, before)
            self.assertFalse(self.window.history.isClean())


if __name__ == "__main__":
    unittest.main()
