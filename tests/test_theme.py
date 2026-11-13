"""Exercise live appearance changes without recoloring the artboard."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QWidget

from piixelverso.canvas import PixelCanvas
from piixelverso.model import PixelDesign
from piixelverso.theme import (
    DARK_COLORS, LIGHT_COLORS, apply_themed_stylesheet, ensure_theme_controller,
)


class ThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")

    def setUp(self):
        self.theme = ensure_theme_controller(self.app, "light")

    def tearDown(self):
        self.theme.set_mode("light")
        self.app.processEvents()

    def test_registered_component_and_native_palette_change_live(self):
        widget = QWidget()
        apply_themed_stylesheet(
            widget, f"QWidget {{ background: {LIGHT_COLORS.white}; color: {LIGHT_COLORS.ink}; }}"
        )
        self.theme.set_mode("dark")
        self.assertIn(DARK_COLORS.white, widget.styleSheet())
        self.assertIn(DARK_COLORS.ink, widget.styleSheet())
        self.assertEqual(
            self.app.palette().window().color().name().upper(), DARK_COLORS.cream
        )
        self.theme.set_mode("light")
        self.assertIn(LIGHT_COLORS.white, widget.styleSheet())
        widget.deleteLater()

    def test_artboard_grid_pixels_are_identical_in_light_and_dark_modes(self):
        design = PixelDesign(4, 3, pixels=[
            "#ED5598", None, "#245448", "#BDE7EE",
            None, "#F6A875", None, "#292343",
            "#FFD878", None, "#FFFFFF", None,
        ])
        canvas = PixelCanvas(design)
        canvas.show()
        self.app.processEvents()
        area = QRect(
            canvas.MARGIN, canvas.MARGIN,
            design.width * canvas.cell_size + 1,
            design.height * canvas.cell_size + 1,
        )
        light = canvas.grab().toImage().copy(area)
        self.theme.set_mode("dark")
        self.app.processEvents()
        dark = canvas.grab().toImage().copy(area)
        self.assertEqual(light, dark)
        canvas.close()
        canvas.deleteLater()


if __name__ == "__main__":
    unittest.main()
