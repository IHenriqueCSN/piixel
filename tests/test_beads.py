"""Exercise bead rendering and editing through the native canvas and controls."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from piixelverso.atelier import AtelierModule as MainWindow, STYLE
from piixelverso.format import encode_design, save_design
from piixelverso.model import PixelDesign
from piixelverso.preferences import PreferencesStore


class BeadViewTests(unittest.TestCase):
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
        design = PixelDesign(4, 4, name="Peças de teste")
        design.set_pixel(1, 1, "#E7794B")
        design.set_pixel(2, 1, "#FFFFFF")
        self.window._replace_design(design)
        self.app.processEvents()
        self.window.zoom.setValue(200)
        self.app.processEvents()

    def tearDown(self):
        self.window.canvas.finish_stroke()
        self.window.name_edit.setText(self.window.design.name)
        self.window.history.setClean()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self._preferences_directory.cleanup()

    def set_mode(self, mode):
        combo = self.window.display_mode_combo
        index = combo.findData(mode)
        self.assertGreaterEqual(index, 0, f"Modo ausente do seletor: {mode}")
        combo.setCurrentIndex(index)
        self.app.processEvents()

    def click_cell(self, x, y, button=Qt.MouseButton.LeftButton):
        QTest.mouseClick(self.window.canvas, button,
                         pos=self.window.canvas.cell_center(x, y))
        self.app.processEvents()

    def test_display_toggle_preserves_design_history_and_saved_bytes(self):
        self.assertEqual(self.window.canvas.display_mode, "squares")
        self.assertEqual(self.window.display_mode_combo.currentData(), "squares")
        self.click_cell(0, 0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contagem.pii"
            self.assertTrue(self.window._save_path(path))
            before = self.window.design.clone()
            before_bytes = path.read_bytes()
            before_history = (self.window.history.count(), self.window.history.index(),
                              self.window.history.isClean())
            before_total = self.window.total_label.text()
            for mode in ("beads", "squares", "beads"):
                self.set_mode(mode)
                self.assertEqual(self.window.canvas.display_mode, mode)
                self.assertEqual(self.window.design, before)
                self.assertEqual(encode_design(self.window.design), before_bytes)
                self.assertEqual(path.read_bytes(), before_bytes)
                self.assertEqual(self.window.design.counts(), before.counts())
                self.assertEqual(self.window.total_label.text(), before_total)
                self.assertEqual((self.window.history.count(), self.window.history.index(),
                                  self.window.history.isClean()), before_history)
                self.assertNotIn(" *", self.window.windowTitle())
        self.window.undo()
        self.assertIsNone(self.window.design.get_pixel(0, 0))
        self.assertEqual(self.window.design.filled_count, 2)

    def test_bead_has_a_visible_hole_colored_ring_and_empty_corners(self):
        canvas = self.window.canvas
        self.window.toggle_grid(False)
        center = canvas.cell_center(1, 1)
        square = canvas.grab().toImage()
        self.assertEqual(square.pixelColor(center), QColor("#E7794B"))
        self.set_mode("beads")
        beads = canvas.grab().toImage()
        empty_background = beads.pixelColor(canvas.cell_center(3, 3))
        self.assertEqual(beads.pixelColor(center), empty_background)
        self.assertNotEqual(beads.pixelColor(center), square.pixelColor(center))
        ring_point = center + QPoint(canvas.cell_size // 4, 0)
        ring = beads.pixelColor(ring_point)
        source = QColor("#E7794B")
        self.assertLess(sum(abs(a - b) for a, b in zip(ring.getRgb()[:3], source.getRgb()[:3])), 110)
        self.assertGreater(ring.red(), ring.green())
        self.assertGreater(ring.green(), ring.blue())
        corner = center - QPoint(canvas.cell_size // 2 - 1, canvas.cell_size // 2 - 1)
        self.assertEqual(beads.pixelColor(corner), empty_background)

    def test_white_bead_is_visible_and_counts_as_one_piece(self):
        self.set_mode("beads")
        self.window.toggle_grid(False)
        canvas = self.window.canvas
        image = canvas.grab().toImage()
        white_center = canvas.cell_center(2, 1)
        empty = image.pixelColor(canvas.cell_center(0, 1))
        self.assertEqual(image.pixelColor(white_center), empty)
        ring = white_center + QPoint(canvas.cell_size // 4, 0)
        self.assertNotEqual(image.pixelColor(ring), empty)
        self.assertEqual(self.window.design.counts()["#FFFFFF"], 1)
        self.assertEqual(self.window.design.filled_count, 2)

    def test_hole_center_remains_editable_and_erasable_with_undo(self):
        self.set_mode("beads")
        self.window.select_color("#245448")
        self.click_cell(0, 0)
        self.assertEqual(self.window.design.get_pixel(0, 0), "#245448")
        self.assertEqual(self.window.design.filled_count, 3)
        self.click_cell(0, 0, Qt.MouseButton.RightButton)
        self.assertIsNone(self.window.design.get_pixel(0, 0))
        self.assertEqual(self.window.design.filled_count, 2)
        self.window.undo()
        self.assertEqual(self.window.design.get_pixel(0, 0), "#245448")
        self.window.redo()
        self.assertIsNone(self.window.design.get_pixel(0, 0))
        self.assertEqual(self.window.canvas.display_mode, "beads")

    def test_display_preference_survives_new_and_open_design(self):
        self.set_mode("beads")
        with tempfile.TemporaryDirectory() as directory:
            saved = PixelDesign(6, 3, name="Design reaberto")
            saved.set_pixel(4, 1, "#548DB0")
            path = Path(directory) / "reabrir.pii"
            save_design(saved, path)
            self.window._replace_design(PixelDesign(5, 2, name="Design novo"))
            self.app.processEvents()
            self.assertEqual(self.window.canvas.display_mode, "beads")
            self.assertEqual(self.window.display_mode_combo.currentData(), "beads")
            self.assertTrue(self.window.load_path(path))
            self.app.processEvents()
            self.assertEqual(self.window.design, saved)
            self.assertEqual(self.window.canvas.display_mode, "beads")
            self.assertEqual(self.window.display_mode_combo.currentData(), "beads")
            self.assertTrue(self.window.history.isClean())

    def test_zoom_grid_and_cell_selection_work_in_bead_mode(self):
        self.set_mode("beads")
        before = self.window.design.clone()
        for percent in (25, 100, 250):
            self.window.zoom.setValue(percent)
            self.app.processEvents()
            for visible in (False, True):
                self.window.toggle_grid(visible)
                self.app.processEvents()
                self.assertFalse(self.window.canvas.grab().isNull())
                for cell in ((0, 0), (3, 3)):
                    self.assertEqual(self.window.canvas.cell_at(self.window.canvas.cell_center(*cell)), cell)
                self.assertEqual(self.window.design, before)
        self.window.zoom.setValue(25)
        self.app.processEvents()
        self.click_cell(3, 3)
        self.assertEqual(self.window.design.get_pixel(3, 3), self.window.canvas.color)

    def test_invalid_display_mode_does_not_replace_current_mode(self):
        self.set_mode("beads")
        before = encode_design(self.window.design)
        with self.assertRaises(ValueError):
            self.window.canvas.set_display_mode("unknown")
        self.assertEqual(self.window.canvas.display_mode, "beads")
        self.assertEqual(encode_design(self.window.design), before)


if __name__ == "__main__":
    unittest.main()
