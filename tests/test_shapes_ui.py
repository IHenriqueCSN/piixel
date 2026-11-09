"""Exercise shape previews and commits through the native editing controls."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from piixelverso.app import MainWindow, STYLE
from piixelverso.format import encode_design, load_design
from piixelverso.model import PixelDesign
from piixelverso.preferences import PreferencesStore


COLOR = "#ED5598"
OTHER = "#245448"


class GeometricToolsUiTests(unittest.TestCase):
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
        self.set_design()
        self.atelier.select_color(COLOR)

    def tearDown(self):
        popup = QApplication.activePopupWidget()
        while popup is not None:
            popup.close()
            self.app.processEvents()
            popup = QApplication.activePopupWidget()
        for module in self.window.module_pages.values():
            if hasattr(module, "history"):
                module.canvas.cancel_stroke()
                module.canvas.finish_stroke()
                module.name_edit.setText(module.design.name)
                module.history.setClean()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def set_design(self, design=None):
        self.atelier._replace_design(design or PixelDesign(12, 12, name="Formas do João"))
        self.app.processEvents()
        self.atelier.zoom.setValue(100)
        self.app.processEvents()

    def choose(self, tool, *, filled=False):
        self.atelier.select_tool(tool)
        self.atelier.set_shape_fill(filled)
        self.atelier.canvas.setFocus()
        self.app.processEvents()

    def press(self, cell, button=Qt.MouseButton.LeftButton):
        QTest.mousePress(self.atelier.canvas, button,
                         pos=self.atelier.canvas.cell_center(*cell))
        self.app.processEvents()

    def move(self, cell):
        QTest.mouseMove(self.atelier.canvas, self.atelier.canvas.cell_center(*cell))
        self.app.processEvents()

    def release(self, cell, button=Qt.MouseButton.LeftButton):
        QTest.mouseRelease(self.atelier.canvas, button,
                           pos=self.atelier.canvas.cell_center(*cell))
        self.app.processEvents()

    def drag(self, start, end, button=Qt.MouseButton.LeftButton):
        self.press(start, button)
        self.move(end)
        self.release(end, button)

    def key(self, key, modifiers=Qt.KeyboardModifier.NoModifier):
        self.window.activateWindow()
        self.atelier.canvas.setFocus()
        self.app.processEvents()
        QTest.keyClick(self.atelier.canvas, key, modifiers)
        self.app.processEvents()

    def assert_counts(self, expected):
        self.assertEqual(self.atelier.design.counts(), expected)
        self.assertEqual(self.atelier.total_label.text(), str(sum(expected.values())))
        displayed = {}
        model = self.atelier.count_view.model()
        for row in range(model.rowCount()):
            color, count, _name = model.index(row, 0).data(Qt.ItemDataRole.UserRole)
            displayed[color] = count
        self.assertEqual(displayed, expected)

    def test_line_preview_moves_without_touching_the_document_then_commits_one_undo_step(self):
        self.choose("line")
        before = encode_design(self.atelier.design)
        self.press((2, 2))
        self.move((7, 2))
        self.assertEqual(encode_design(self.atelier.design), before)
        self.assertEqual(self.atelier.history.count(), 0)
        self.assertTrue(self.atelier.history.isClean())
        self.assert_counts({})
        self.assertNotIn(" *", self.atelier.windowTitle())
        preview = self.atelier.canvas.grab().toImage()
        center = self.atelier.canvas.cell_center(7, 2)
        self.assertEqual(preview.pixelColor(center).name().upper(), COLOR)

        self.move((4, 2))
        preview = self.atelier.canvas.grab().toImage()
        self.assertNotEqual(preview.pixelColor(center).name().upper(), COLOR)
        self.assertEqual(encode_design(self.atelier.design), before)
        self.release((4, 2))
        self.assert_counts({COLOR: 3})
        self.assertEqual(self.atelier.history.count(), 1)
        self.assertFalse(self.atelier.history.isClean())
        self.assertEqual(self.atelier.canvas._shape_preview, {})
        self.atelier.undo()
        self.assertEqual(encode_design(self.atelier.design), before)
        self.assert_counts({})
        self.assertTrue(self.atelier.history.isClean())
        self.atelier.redo()
        self.assert_counts({COLOR: 3})

    def test_rectangle_outline_preserves_the_interior_while_fill_replaces_it(self):
        design = PixelDesign(12, 12)
        design.set_pixel(4, 4, OTHER)
        self.set_design(design)
        original = self.atelier.design.clone()
        self.choose("rectangle")
        self.drag((2, 2), (6, 6))
        self.assert_counts({COLOR: 16, OTHER: 1})
        self.assertEqual(self.atelier.design.get_pixel(4, 4), OTHER)
        self.assertIsNone(self.atelier.design.get_pixel(3, 3))
        self.atelier.undo()
        self.assertEqual(self.atelier.design, original)

        self.choose("rectangle", filled=True)
        self.drag((6, 6), (2, 2))
        self.assert_counts({COLOR: 25})
        self.assertEqual(self.atelier.design.get_pixel(4, 4), COLOR)
        self.assertEqual(self.atelier.history.count(), 1)
        self.atelier.undo()
        self.assertEqual(self.atelier.design, original)

    def test_ellipse_preview_and_pixels_use_the_selected_color_in_both_display_modes(self):
        for mode in ("squares", "beads"):
            with self.subTest(mode=mode):
                self.set_design()
                self.atelier.display_mode_combo.setCurrentIndex(
                    self.atelier.display_mode_combo.findData(mode)
                )
                self.choose("ellipse", filled=True)
                self.press((1, 1))
                self.move((7, 5))
                self.assertTrue(self.atelier.design.is_empty)
                self.assert_counts({})
                self.assertIn(3 * self.atelier.design.width + 4,
                              self.atelier.canvas._shape_preview)
                self.release((7, 5))
                self.assertEqual(self.atelier.design.get_pixel(4, 3), COLOR)
                self.assertEqual(self.atelier.design.get_pixel(4, 1), COLOR)
                self.assertEqual(self.atelier.design.get_pixel(1, 3), COLOR)
                self.assertIsNone(self.atelier.design.get_pixel(1, 1))
                self.assertEqual(set(self.atelier.design.counts()), {COLOR})
                self.assertEqual(self.atelier.history.count(), 1)
                self.atelier.undo()
                self.assertTrue(self.atelier.design.is_empty)

    def test_single_cell_click_is_one_piece_for_each_geometric_tool(self):
        for tool in ("line", "rectangle", "ellipse"):
            with self.subTest(tool=tool):
                self.set_design()
                self.choose(tool)
                self.press((5, 5))
                self.assertTrue(self.atelier.design.is_empty)
                self.release((5, 5))
                self.assert_counts({COLOR: 1})
                self.assertEqual(self.atelier.history.count(), 1)
                self.assertEqual(self.atelier.design.get_pixel(5, 5), COLOR)

    def test_mouse_release_position_finishes_a_line_even_without_a_move_event(self):
        self.choose("line")
        self.press((1, 1))
        self.release((6, 1))
        self.assert_counts({COLOR: 6})
        self.assertEqual(self.atelier.design.get_pixel(6, 1), COLOR)
        self.assertEqual(self.atelier.history.count(), 1)

    def test_dragging_beyond_either_edge_clips_to_the_canvas(self):
        canvas = self.atelier.canvas
        for start, point, corner in (
            ((9, 9), QPoint(canvas.width() + 100, canvas.height() + 100), (11, 11)),
            ((2, 2), QPoint(-100, -100), (0, 0)),
        ):
            with self.subTest(corner=corner):
                self.set_design()
                self.choose("rectangle", filled=True)
                self.press(start)
                QTest.mouseMove(canvas, point)
                QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=point)
                self.app.processEvents()
                self.assert_counts({COLOR: 9})
                self.assertEqual(self.atelier.design.get_pixel(*corner), COLOR)
                self.assertEqual(self.atelier.history.count(), 1)

    def test_escape_cancels_the_preview_and_later_release_does_not_paint(self):
        self.choose("rectangle", filled=True)
        before = encode_design(self.atelier.design)
        self.press((1, 1))
        self.move((8, 7))
        self.assertTrue(self.atelier.canvas._shape_preview)
        self.key(Qt.Key.Key_Escape)
        self.assertEqual(self.atelier.canvas._shape_preview, {})
        self.assertFalse(self.atelier.canvas._drawing)
        self.release((8, 7))
        self.assertEqual(encode_design(self.atelier.design), before)
        self.assert_counts({})
        self.assertEqual(self.atelier.history.count(), 0)
        self.assertTrue(self.atelier.history.isClean())

    def test_changing_tool_commits_the_pending_shape_before_starting_another_tool(self):
        self.choose("line")
        self.press((1, 4))
        self.move((5, 4))
        self.assertTrue(self.atelier.design.is_empty)
        self.atelier.select_tool("pencil")
        self.app.processEvents()
        self.assert_counts({COLOR: 5})
        self.assertEqual(self.atelier.canvas._shape_preview, {})
        self.assertEqual(self.atelier.canvas.tool, "pencil")
        self.assertEqual(self.atelier.history.count(), 1)
        self.atelier.undo()
        self.assertTrue(self.atelier.design.is_empty)

    def test_right_button_still_erases_a_freehand_stroke_with_a_shape_selected(self):
        design = PixelDesign(12, 12)
        for x in range(2, 5):
            design.set_pixel(x, 2, COLOR)
        design.set_pixel(2, 3, OTHER)
        self.set_design(design)
        original = self.atelier.design.clone()
        self.choose("ellipse", filled=True)
        self.drag((2, 2), (4, 2), Qt.MouseButton.RightButton)
        self.assert_counts({OTHER: 1})
        self.assertEqual(self.atelier.design.get_pixel(2, 3), OTHER)
        self.assertEqual(self.atelier.canvas.tool, "ellipse")
        self.assertEqual(self.atelier.history.count(), 1)
        self.atelier.undo()
        self.assertEqual(self.atelier.design, original)

    def test_redrawing_the_same_shape_does_not_dirty_or_add_a_history_step(self):
        design = PixelDesign(12, 12)
        for x in range(1, 6):
            design.set_pixel(x, 3, COLOR)
        self.set_design(design)
        self.choose("line")
        original = encode_design(self.atelier.design)
        self.drag((1, 3), (5, 3))
        self.assertEqual(encode_design(self.atelier.design), original)
        self.assertEqual(self.atelier.history.count(), 0)
        self.assertTrue(self.atelier.history.isClean())
        self.assert_counts({COLOR: 5})

    def test_menu_shortcuts_and_shape_button_share_exclusive_tools_and_fill_state(self):
        bar = self.atelier.command_bar
        for key, tool in ((Qt.Key.Key_L, "line"), (Qt.Key.Key_R, "rectangle"),
                          (Qt.Key.Key_O, "ellipse")):
            with self.subTest(tool=tool):
                self.key(key)
                self.assertEqual(self.atelier.canvas.tool, tool)
                checked = [name for name in ("pencil", "bucket", "eraser", "picker",
                                              "line", "rectangle", "ellipse")
                           if self.atelier.command_actions[name].isChecked()]
                self.assertEqual(checked, [tool])
                self.assertIs(bar.shape_button.defaultAction(), self.atelier.command_actions[tool])
                self.assertEqual(bar.fill_checkbox.isEnabled(), tool != "line")

        menu = bar.shape_button.menu()
        self.assertIn(self.atelier.command_actions["rectangle"], menu.actions())
        menu.popup(bar.shape_button.mapToGlobal(QPoint(0, bar.shape_button.height())))
        self.app.processEvents()
        QTest.mouseClick(menu, Qt.MouseButton.LeftButton,
                         pos=menu.actionGeometry(self.atelier.command_actions["rectangle"]).center())
        self.app.processEvents()
        self.assertEqual(self.atelier.canvas.tool, "rectangle")
        QTest.mouseClick(bar.fill_checkbox, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertTrue(self.atelier.canvas.shape_filled)
        self.assertTrue(self.atelier.command_actions["shape_fill"].isChecked())
        self.key(Qt.Key.Key_B)
        self.assertFalse(bar.fill_checkbox.isEnabled())
        QTest.mouseClick(bar.shape_button, Qt.MouseButton.LeftButton, pos=QPoint(8, 14))
        self.app.processEvents()
        self.assertEqual(self.atelier.canvas.tool, "rectangle")
        self.assertTrue(bar.fill_checkbox.isChecked())

        self.atelier.name_edit.setFocus()
        self.atelier.name_edit.selectAll()
        self.app.processEvents()
        QTest.keyClicks(self.atelier.name_edit, "LRO")
        self.app.processEvents()
        self.assertEqual(self.atelier.name_edit.text(), "LRO")
        self.assertEqual(self.atelier.canvas.tool, "rectangle")

    def test_navigation_commits_a_pending_shape_and_disables_its_commands_on_home(self):
        self.choose("line")
        self.press((2, 5))
        self.move((6, 5))
        self.window.show_home()
        self.app.processEvents()
        self.assert_counts({COLOR: 5})
        for name in ("line", "rectangle", "ellipse", "shape_fill"):
            self.assertFalse(self.atelier.command_actions[name].isEnabled())
        self.assertFalse(self.atelier.command_bar.fill_checkbox.isEnabled())
        self.assertEqual(self.atelier.history.count(), 1)
        self.assertIs(self.window.open_module("atelier"), self.atelier)
        self.app.processEvents()
        self.assertEqual(self.atelier.canvas.tool, "line")
        self.atelier.undo()
        self.assertTrue(self.atelier.design.is_empty)

    def test_shape_history_survives_resize_and_roundtrips_through_pii_and_png(self):
        from piixelverso.png_export import CELL_SIZE, export_layout

        self.choose("rectangle", filled=True)
        self.drag((2, 2), (5, 5))
        shaped = self.atelier.design.clone()
        self.assertTrue(self.atelier.resize_canvas(16, 14, "top_left"))
        resized = self.atelier.design.clone()
        self.atelier.undo()
        self.assertEqual(self.atelier.design, shaped)
        self.atelier.undo()
        self.assertTrue(self.atelier.design.is_empty)
        self.atelier.redo()
        self.atelier.redo()
        self.assertEqual(self.atelier.design, resized)
        path = self.root / "formas.pii"
        self.assertTrue(self.atelier._save_path(path))
        self.assertEqual(load_design(path), resized)
        image_path = self.root / "formas.png"
        self.assertTrue(self.atelier.export_png_path(image_path, display_mode="squares", show_grid=False))
        image = QImage(str(image_path))
        self.assertFalse(image.isNull())
        layout = export_layout(resized)
        self.assertEqual((layout.width_label, layout.height_label), ("20 mm", "20 mm"))
        self.assertEqual(image.pixelColor(layout.grid_left + 3 * CELL_SIZE + 16,
                                          layout.grid_top + 3 * CELL_SIZE + 16).name().upper(), COLOR)
        self.assertTrue(self.atelier.history.isClean())

    def test_shape_controls_fit_the_compact_toolbar_at_the_minimum_window_size(self):
        self.window.resize(1120, 750)
        self.app.processEvents()
        bar = self.atelier.command_bar
        self.assertLessEqual(bar.height(), 44)
        controls = list(bar.buttons.values()) + [
            bar.shape_button, bar.fill_checkbox, bar.display_mode_combo,
            bar.grid_checkbox, bar.zoom_slider, bar.zoom_label,
        ]
        for control in controls:
            with self.subTest(control=control.accessibleName() or control.objectName()):
                self.assertTrue(control.isVisible())
                bounds = QRect(control.mapTo(bar, QPoint(0, 0)), control.size())
                self.assertTrue(bar.rect().contains(bounds), f"Controle fora da barra: {bounds}")


if __name__ == "__main__":
    unittest.main()
