"""Exercise canvas resizing without losing the editor session or undo history."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from piixelverso.app import MainWindow, STYLE
from piixelverso.format import encode_design, load_design
from piixelverso.model import PixelDesign
from piixelverso.preferences import PreferencesStore


CORAL = "#E7794B"
FOREST = "#245448"
WHITE = "#FFFFFF"


class CanvasResizeUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.preferences = PreferencesStore(self.root / "preferences.json")
        self.window = MainWindow(preferences=self.preferences)
        self.window.show()
        self.window.activateWindow()
        self.atelier = self.window.open_module("atelier")
        self.source_path = self.root / "prancheta original.pii"
        design = PixelDesign(12, 11, name="Prancheta do João")
        design.set_pixel(0, 0, CORAL)
        design.set_pixel(5, 4, FOREST)
        design.set_pixel(11, 10, WHITE)
        self.set_design(design)

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
        self.directory.cleanup()

    def set_design(self, design):
        self.atelier._replace_design(design)
        self.assertTrue(self.atelier._save_path(self.source_path))
        self.app.processEvents()
        self.atelier.zoom.setValue(100)
        self.app.processEvents()

    def state(self):
        return (
            encode_design(self.atelier.design), self.atelier.file_path,
            self.atelier.history.count(), self.atelier.history.index(),
            self.atelier.history.isClean(), self.source_path.read_bytes(),
            self.preferences.path.read_bytes(),
            self.atelier.canvas.display_mode, self.atelier.canvas.show_grid,
            self.atelier.canvas.color, self.atelier.canvas.tool,
            self.atelier.zoom.value(),
        )

    def key_resize(self):
        self.window.activateWindow()
        self.atelier.canvas.setFocus()
        self.app.processEvents()
        QTest.keyClick(self.atelier.canvas, Qt.Key.Key_C,
                       Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
        self.app.processEvents()

    def click_resize_menu(self):
        bar = self.atelier.command_bar.menubar
        menu = self.atelier.command_bar.menus["edit"]
        QTest.mouseClick(bar, Qt.MouseButton.LeftButton,
                         pos=bar.actionGeometry(menu.menuAction()).center())
        self.app.processEvents()
        self.assertTrue(menu.isVisible())
        action = self.atelier.command_actions["resize_canvas"]
        self.assertIn(action, menu.actions())
        QTest.mouseClick(menu, Qt.MouseButton.LeftButton,
                         pos=menu.actionGeometry(action).center())
        self.app.processEvents()

    def accept_resize(self, width, height, anchor="center", inspect=None):
        def accept(dialog):
            dialog.show()
            self.app.processEvents()
            for field in (dialog.width_input, dialog.height_input):
                self.assertEqual((field.minimum(), field.maximum()), (10, 128))
            self.assertEqual(dialog.anchor_combo.currentData(), "center")
            self.assertEqual(dialog.anchor_combo.count(), 9)
            self.assertFalse(dialog.resize_button.isEnabled())
            dialog.width_input.setValue(width)
            dialog.height_input.setValue(height)
            index = dialog.anchor_combo.findData(anchor)
            self.assertGreaterEqual(index, 0)
            dialog.anchor_combo.setCurrentIndex(index)
            self.app.processEvents()
            self.assertEqual(dialog.target_width(), width)
            self.assertEqual(dialog.target_height(), height)
            self.assertEqual(dialog.anchor(), anchor)
            self.assertTrue(dialog.resize_button.isEnabled())
            if inspect is not None:
                inspect(dialog)
            QTest.mouseClick(dialog.resize_button, Qt.MouseButton.LeftButton)
            self.app.processEvents()
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
            return dialog.result()
        return accept

    def test_growing_preserves_pixels_model_identity_and_session_with_one_undo_step(self):
        self.atelier.add_custom_color("#123ABC", name="Minha cor", persist=True)
        self.atelier.select_tool("bucket")
        self.atelier.display_mode_combo.setCurrentIndex(1)
        self.atelier.command_bar.grid_checkbox.setChecked(False)
        self.atelier.zoom.setValue(125)
        self.app.processEvents()
        original = self.atelier.design.clone()
        identity = self.atelier.design
        source = self.source_path.read_bytes()
        preferences = self.preferences.path.read_bytes()
        view = self.state()[-5:]

        self.assertTrue(self.atelier.resize_canvas(16, 15))
        self.app.processEvents()
        self.assertIs(self.atelier.design, identity)
        self.assertIs(self.atelier.canvas.design, identity)
        self.assertEqual((identity.width, identity.height), (16, 15))
        self.assertEqual(identity.get_pixel(2, 2), CORAL)
        self.assertEqual(identity.get_pixel(7, 6), FOREST)
        self.assertEqual(identity.get_pixel(13, 12), WHITE)
        self.assertIsNone(identity.get_pixel(0, 0))
        self.assertEqual(identity.counts(), original.counts())
        self.assertEqual(self.atelier.total_label.text(), "3")
        self.assertEqual(self.atelier.dimensions.text(), "16 × 15")
        self.assertEqual(self.atelier.canvas.width(), 16 * self.atelier.canvas.cell_size + 52)
        self.assertEqual(self.atelier.canvas.height(), 15 * self.atelier.canvas.cell_size + 52)
        self.assertEqual(self.atelier.history.count(), 1)
        self.assertFalse(self.atelier.history.isClean())
        self.assertEqual(self.atelier.file_path, self.source_path)
        self.assertEqual(self.state()[-5:], view)
        self.assertEqual(self.source_path.read_bytes(), source)
        self.assertEqual(self.preferences.path.read_bytes(), preferences)
        resized = identity.clone()

        self.atelier.undo()
        self.app.processEvents()
        self.assertIs(self.atelier.design, identity)
        self.assertEqual(identity, original)
        self.assertTrue(self.atelier.history.isClean())
        self.atelier.redo()
        self.app.processEvents()
        self.assertEqual(identity, resized)
        self.assertEqual(self.state()[-5:], view)
        self.assertEqual(self.preferences.path.read_bytes(), preferences)

    def test_paint_commands_keep_their_original_coordinates_across_resize_undo_redo(self):
        original = self.atelier.design.clone()
        self.atelier.select_color("#ED5598")
        QTest.mouseClick(self.atelier.canvas, Qt.MouseButton.LeftButton,
                         pos=self.atelier.canvas.cell_center(3, 2))
        self.app.processEvents()
        painted = self.atelier.design.clone()
        self.assertTrue(self.atelier.resize_canvas(10, 10, "top_left"))
        self.assertEqual(self.atelier.design.get_pixel(3, 2), "#ED5598")
        self.assertEqual(self.atelier.design.counts(), {CORAL: 1, FOREST: 1, "#ED5598": 1})
        self.assertEqual(self.atelier.history.count(), 2)
        self.atelier.undo()
        self.assertEqual(self.atelier.design, painted)
        self.atelier.undo()
        self.assertEqual(self.atelier.design, original)
        self.assertTrue(self.atelier.history.isClean())
        self.atelier.redo()
        self.atelier.redo()
        self.assertEqual((self.atelier.design.width, self.atelier.design.height), (10, 10))
        self.assertEqual(self.atelier.design.get_pixel(3, 2), "#ED5598")
        self.assertEqual(self.atelier.total_label.text(), "3")

    def test_noop_and_invalid_sizes_leave_history_and_document_untouched(self):
        before = self.state()
        self.assertFalse(self.atelier.resize_canvas(12, 11))
        for width, height in ((9, 10), (10, 129), (True, 10), (12.0, 11)):
            with self.subTest(width=width, height=height):
                with self.assertRaises(ValueError):
                    self.atelier.resize_canvas(width, height)
                self.assertEqual(self.state(), before)

    def test_menu_and_keyboard_open_the_real_dialog_without_expanding_the_toolbar(self):
        callbacks = [(self.click_resize_menu, 16, 14), (self.key_resize, 14, 16)]
        for invoke, width, height in callbacks:
            with self.subTest(width=width, height=height):
                with patch("piixelverso.atelier.ResizeCanvasDialog.exec",
                           new=self.accept_resize(width, height)), patch(
                    "piixelverso.atelier.QMessageBox.question",
                    side_effect=AssertionError("Aumentar a prancheta não pode cortar peças"),
                ):
                    invoke()
                self.assertEqual((self.atelier.design.width, self.atelier.design.height), (width, height))
                self.assertLessEqual(self.atelier.command_bar.height(), 44)
                self.atelier.undo()

    def test_crop_warning_can_cancel_or_confirm_without_losing_the_original_for_undo(self):
        original = self.atelier.design.clone()
        before = self.state()
        def inspect(dialog):
            self.assertIn("1", dialog.crop_label.text())

        for answer in (QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes):
            with self.subTest(answer=answer), patch(
                "piixelverso.atelier.ResizeCanvasDialog.exec",
                new=self.accept_resize(10, 10, "top_left", inspect),
            ), patch("piixelverso.atelier.QMessageBox.question", return_value=answer) as warning:
                self.atelier.show_resize_canvas_dialog()
                warning.assert_called_once()
                self.assertIs(warning.call_args.args[0], self.window)
                self.assertEqual(warning.call_args.args[-1], QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.No:
                self.assertEqual(self.state(), before)
            else:
                self.assertEqual((self.atelier.design.width, self.atelier.design.height), (10, 10))
                self.assertEqual(self.atelier.design.counts(), {CORAL: 1, FOREST: 1})
                self.atelier.undo()
                self.assertEqual(self.atelier.design, original)
                self.assertTrue(self.atelier.history.isClean())

    def test_reducing_empty_margins_needs_no_crop_confirmation(self):
        design = PixelDesign(12, 12, name="Margens vazias")
        design.set_pixel(5, 5, CORAL)
        self.set_design(design)
        with patch("piixelverso.atelier.ResizeCanvasDialog.exec",
                   new=self.accept_resize(10, 10)), patch(
            "piixelverso.atelier.QMessageBox.question",
            side_effect=AssertionError("Somente margens vazias serão removidas"),
        ):
            self.atelier.show_resize_canvas_dialog()
        self.assertEqual(self.atelier.design.get_pixel(4, 4), CORAL)
        self.assertEqual(self.atelier.design.filled_count, 1)

    def test_canceling_the_dialog_and_the_home_shortcut_do_not_change_the_design(self):
        before = self.state()
        def cancel(dialog):
            dialog.show()
            dialog.width_input.setValue(128)
            dialog.height_input.setValue(10)
            self.app.processEvents()
            QTest.keyClick(dialog, Qt.Key.Key_Escape)
            return dialog.result()
        with patch("piixelverso.atelier.ResizeCanvasDialog.exec", new=cancel):
            self.key_resize()
        self.assertEqual(self.state(), before)
        self.window.show_home()
        self.app.processEvents()
        self.assertFalse(self.atelier.command_actions["resize_canvas"].isEnabled())
        target = self.window.home_page.module_buttons["atelier"]
        target.setFocus()
        with patch("piixelverso.atelier.ResizeCanvasDialog.exec",
                   side_effect=AssertionError("Redimensionar não deve abrir na tela inicial")):
            QTest.keyClick(target, Qt.Key.Key_C,
                           Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
            self.app.processEvents()
        self.assertEqual(self.state(), before)

    def test_resized_design_saves_and_reopens_and_exports_with_the_preserved_piece_scale(self):
        from piixelverso.png_export import export_layout, measurement_labels

        self.assertTrue(self.atelier.resize_canvas(18, 16))
        current = self.atelier.design.clone()
        self.assertEqual(measurement_labels(current), ("60 mm", "55 mm"))
        png_path = self.root / "prancheta ampliada.png"
        self.assertTrue(self.atelier.export_png_path(png_path, display_mode="squares", show_grid=False))
        image = QImage(str(png_path))
        self.assertFalse(image.isNull())
        self.assertEqual(image.size(), export_layout(current).image_size)
        self.assertEqual(image.dotsPerMeterX(), 6400)
        self.assertFalse(self.atelier.history.isClean(), "PNG não salva o documento .pii")
        self.assertTrue(self.atelier._save_path(self.source_path))
        self.assertEqual(load_design(self.source_path), current)
        self.assertTrue(self.atelier.history.isClean())
        self.atelier.undo()
        self.assertFalse(self.atelier.history.isClean())
        self.atelier.redo()
        self.assertTrue(self.atelier.history.isClean())

    def test_pending_paint_and_name_are_committed_before_the_resize_snapshot(self):
        self.atelier.name_edit.setText("Nome durante o redimensionamento")
        self.atelier.select_color("#ED5598")
        QTest.mousePress(self.atelier.canvas, Qt.MouseButton.LeftButton,
                         pos=self.atelier.canvas.cell_center(3, 2))
        self.assertTrue(self.atelier.resize_canvas(14, 13))
        QTest.mouseRelease(self.atelier.canvas, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(self.atelier.design.name, "Nome durante o redimensionamento")
        self.assertEqual(self.atelier.design.get_pixel(4, 3), "#ED5598")
        self.atelier.undo()
        self.assertEqual((self.atelier.design.width, self.atelier.design.height), (12, 11))
        self.assertEqual(self.atelier.design.get_pixel(3, 2), "#ED5598")
        self.assertEqual(self.atelier.design.name, "Nome durante o redimensionamento")

    def test_an_older_small_design_can_grow_to_the_new_minimum(self):
        self.set_design(PixelDesign(3, 4, [WHITE] + [None] * 11, name="Arquivo antigo"))

        def accept(dialog):
            dialog.show()
            self.app.processEvents()
            self.assertEqual((dialog.target_width(), dialog.target_height()), (10, 10))
            self.assertTrue(dialog.resize_button.isEnabled())
            QTest.mouseClick(dialog.resize_button, Qt.MouseButton.LeftButton)
            return dialog.result()

        with patch("piixelverso.atelier.ResizeCanvasDialog.exec", new=accept), patch(
            "piixelverso.atelier.QMessageBox.question",
            side_effect=AssertionError("Ampliar o arquivo antigo não corta peças"),
        ):
            self.assertTrue(self.atelier.show_resize_canvas_dialog())
        self.assertEqual((self.atelier.design.width, self.atelier.design.height), (10, 10))
        self.assertEqual(self.atelier.design.get_pixel(3, 3), WHITE)
        self.assertEqual(self.atelier.design.filled_count, 1)
        self.atelier.undo()
        self.assertEqual((self.atelier.design.width, self.atelier.design.height), (3, 4))
        self.assertEqual(self.atelier.design.get_pixel(0, 0), WHITE)


if __name__ == "__main__":
    unittest.main()
