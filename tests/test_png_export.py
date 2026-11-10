"""Verify exported artwork, measured annotations, and safe PNG file writes."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSaveFile
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from piixelverso.materials import TRANSPARENT_FILL, TRANSPARENT_OUTLINE
from piixelverso.model import TRANSPARENT, PixelDesign
from piixelverso.png_export import (
    CELL_SIZE, GRID_COLOR, export_layout, format_mm, measurement_labels, occupied_bounds,
    render_png, save_png,
)


RED = "#E7794B"
BLUE = "#285A78"
WHITE = "#FFFFFF"
BLACK = "#000000"


class PNGExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")

    def pixel(self, image, x, y):
        return image.pixelColor(x, y).name().upper()

    def has_black(self, image, rect):
        return any(self.pixel(image, x, y) == BLACK
                   for y in range(rect.top(), rect.bottom() + 1)
                   for x in range(rect.left(), rect.right() + 1))

    def test_measurements_use_the_painted_span_and_configured_piece_size(self):
        design = PixelDesign(32, 16)
        design.set_pixel(0, 0, RED)
        design.set_pixel(31, 15, BLUE)
        self.assertEqual(measurement_labels(design), ("160 mm", "80 mm"))
        self.assertEqual(measurement_labels(design, 2.6), ("83,2 mm", "41,6 mm"))
        self.assertEqual(format_mm(12.5), "12,5 mm")
        self.assertEqual(format_mm(20.0), "20 mm")
        self.assertEqual(format_mm(0.1), "0,1 mm")

    def test_empty_outer_borders_are_excluded_but_gaps_and_white_pieces_count(self):
        design = PixelDesign(15, 12)
        design.set_pixel(3, 2, RED)
        design.set_pixel(8, 6, BLUE)
        design.set_pixel(10, 8, WHITE)
        original = design.clone()
        self.assertEqual(occupied_bounds(design), (3, 2, 11, 9))
        self.assertEqual(measurement_labels(design), ("40 mm", "35 mm"))
        self.assertEqual(measurement_labels(design, 2.6), ("20,8 mm", "18,2 mm"))
        self.assertEqual(design.filled_count, 3)
        self.assertIsNone(design.get_pixel(6, 5))
        self.assertEqual(design, original)

    def test_one_piece_measures_one_cell_even_far_from_the_grid_origin(self):
        for color in (RED, WHITE):
            with self.subTest(color=color):
                design = PixelDesign(128, 128)
                design.set_pixel(123, 117, color)
                self.assertEqual(occupied_bounds(design), (123, 117, 124, 118))
                self.assertEqual(measurement_labels(design), ("5 mm", "5 mm"))
                self.assertEqual(measurement_labels(design, 2.6), ("2,6 mm", "2,6 mm"))

    def test_an_empty_design_measures_zero_and_has_no_dimension_arrows(self):
        design = PixelDesign(7, 6)
        self.assertIsNone(occupied_bounds(design))
        self.assertEqual(measurement_labels(design), ("0 mm", "0 mm"))
        layout = export_layout(design)
        self.assertEqual((layout.design_width, layout.design_height), (0, 0))
        image = render_png(design, show_grid=True)
        for x in range(layout.grid_left, layout.grid_left + layout.grid_width + 1):
            self.assertEqual(self.pixel(image, x, layout.horizontal_arrow_y), WHITE)
        for y in range(layout.grid_top, layout.grid_top + layout.grid_height + 1):
            self.assertEqual(self.pixel(image, layout.vertical_arrow_x, y), WHITE)
        self.assertTrue(self.has_black(image, layout.horizontal_label_rect))
        self.assertTrue(self.has_black(image, layout.vertical_label_rect))

    def test_squares_keep_exact_colors_and_empty_cells_are_white_without_mutation(self):
        design = PixelDesign(3, 2, [RED, BLUE, None, WHITE, None, RED])
        original = design.clone()
        layout = export_layout(design)
        image = render_png(design, show_grid=False)
        self.assertEqual(image.size(), layout.image_size)
        for row in range(2):
            for column in range(3):
                self.assertEqual(
                    self.pixel(image, layout.grid_left + column * CELL_SIZE + 16,
                               layout.grid_top + row * CELL_SIZE + 16),
                    design.get_pixel(column, row) or WHITE,
                )
        self.assertEqual(design, original)

    def test_beads_have_white_holes_and_gaps_but_preserve_the_rgb_ring(self):
        design = PixelDesign(2, 1, [RED, None])
        layout = export_layout(design)
        beads = render_png(design, display_mode="beads", show_grid=False)
        squares = render_png(design, display_mode="squares", show_grid=False)
        x, y = layout.grid_left, layout.grid_top
        self.assertEqual(self.pixel(beads, x + 16, y + 16), WHITE)
        self.assertEqual(self.pixel(squares, x + 16, y + 16), RED)
        self.assertEqual(self.pixel(beads, x + 16, y + 6), RED)
        self.assertEqual(self.pixel(beads, x + 1, y + 1), WHITE)
        self.assertEqual(self.pixel(beads, x + CELL_SIZE + 16, y + 16), WHITE)

    def test_transparent_beads_are_visible_counted_and_measured_in_both_modes(self):
        design = PixelDesign(4, 3)
        design.set_pixel(2, 1, TRANSPARENT)
        self.assertEqual(design.counts(), {TRANSPARENT: 1})
        self.assertEqual(occupied_bounds(design), (2, 1, 3, 2))
        self.assertEqual(measurement_labels(design), ("5 mm", "5 mm"))
        layout = export_layout(design)
        left = layout.grid_left + 2 * CELL_SIZE
        top = layout.grid_top + CELL_SIZE

        squares = render_png(design, display_mode="squares", show_grid=False)
        self.assertEqual(self.pixel(squares, left + 16, top + 16), TRANSPARENT_FILL)
        self.assertEqual(self.pixel(squares, left + 1, top + 10), TRANSPARENT_OUTLINE)

        beads = render_png(design, display_mode="beads", show_grid=False)
        self.assertEqual(self.pixel(beads, left + 16, top + 16), WHITE)
        self.assertNotEqual(self.pixel(beads, left + 16, top + 5), WHITE)
        self.assertEqual(self.pixel(beads, layout.grid_left + 16, layout.grid_top + 16), WHITE)

    def test_grid_switch_changes_boundaries_in_both_display_modes(self):
        design = PixelDesign(2, 2, [RED, RED, RED, RED])
        layout = export_layout(design)
        for mode in ("squares", "beads"):
            with self.subTest(mode=mode):
                with_grid = render_png(design, display_mode=mode, show_grid=True)
                without_grid = render_png(design, display_mode=mode, show_grid=False)
                x, y = layout.grid_left + CELL_SIZE, layout.grid_top + 16
                self.assertEqual(self.pixel(with_grid, x, y), GRID_COLOR)
                self.assertEqual(self.pixel(without_grid, x, y), RED if mode == "squares" else WHITE)
                # Turning the grid off also removes the outer cell boundary.
                self.assertEqual(self.pixel(with_grid, layout.grid_left, y), GRID_COLOR)
                self.assertEqual(self.pixel(without_grid, layout.grid_left, y),
                                 RED if mode == "squares" else WHITE)

    def test_dimension_arrows_and_text_are_black_above_and_left_of_the_grid(self):
        design = PixelDesign(4, 3)
        design.set_pixel(3, 0, RED)
        design.set_pixel(0, 2, BLUE)
        layout = export_layout(design)
        image = render_png(design, show_grid=False)
        self.assertEqual(layout.width_label, "20 mm")
        self.assertEqual(layout.height_label, "15 mm")
        x0, y0 = layout.grid_left, layout.grid_top
        x1, y1 = x0 + layout.grid_width, y0 + layout.grid_height
        for x in (x0, x0 + 3, x0 + layout.grid_width // 2, x1 - 3, x1):
            self.assertEqual(self.pixel(image, x, layout.horizontal_arrow_y), BLACK)
        for y in (y0, y0 + 3, y0 + layout.grid_height // 2, y1 - 3, y1):
            self.assertEqual(self.pixel(image, layout.vertical_arrow_x, y), BLACK)
        # Heads extend to either side of each arrow's stem.
        self.assertEqual(self.pixel(image, x0 + 6, layout.horizontal_arrow_y - 2), BLACK)
        self.assertEqual(self.pixel(image, layout.vertical_arrow_x - 2, y0 + 6), BLACK)
        self.assertTrue(self.has_black(image, layout.horizontal_label_rect))
        self.assertTrue(self.has_black(image, layout.vertical_label_rect))
        self.assertLess(layout.horizontal_label_rect.bottom(), y0)
        self.assertLess(layout.vertical_label_rect.right(), x0)
        self.assertEqual(self.pixel(image, x0 + 16, y0 + 16), WHITE)

    def test_arrows_span_only_the_design_extremes_in_both_piece_display_modes(self):
        design = PixelDesign(11, 10)
        design.set_pixel(3, 2, RED)
        design.set_pixel(8, 6, BLUE)
        original = design.clone()
        layout = export_layout(design)
        self.assertEqual((layout.width_label, layout.height_label), ("30 mm", "25 mm"))
        self.assertEqual(layout.design_left, layout.grid_left + 3 * CELL_SIZE)
        self.assertEqual(layout.design_top, layout.grid_top + 2 * CELL_SIZE)
        self.assertEqual((layout.design_width, layout.design_height), (6 * CELL_SIZE, 5 * CELL_SIZE))
        x0, y0 = layout.design_left, layout.design_top
        x1, y1 = x0 + layout.design_width, y0 + layout.design_height
        self.assertLessEqual(abs(layout.horizontal_label_rect.center().x() - (x0 + x1) / 2), 1)
        self.assertLessEqual(abs(layout.vertical_label_rect.center().y() - (y0 + y1) / 2), 1)
        for mode in ("squares", "beads"):
            with self.subTest(mode=mode):
                image = render_png(design, display_mode=mode, show_grid=False)
                self.assertEqual(image.size(), layout.image_size)
                for x in (x0, x0 + 3, (x0 + x1) // 2, x1 - 3, x1):
                    self.assertEqual(self.pixel(image, x, layout.horizontal_arrow_y), BLACK)
                for y in (y0, y0 + 3, (y0 + y1) // 2, y1 - 3, y1):
                    self.assertEqual(self.pixel(image, layout.vertical_arrow_x, y), BLACK)
                self.assertEqual(self.pixel(image, x0 + 6, layout.horizontal_arrow_y - 2), BLACK)
                self.assertEqual(self.pixel(image, layout.vertical_arrow_x - 2, y0 + 6), BLACK)
                for x in (layout.grid_left, x0 - 8, x1 + 8,
                          layout.grid_left + layout.grid_width):
                    self.assertEqual(self.pixel(image, x, layout.horizontal_arrow_y), WHITE)
                for y in (layout.grid_top, y0 - 8, y1 + 8,
                          layout.grid_top + layout.grid_height):
                    self.assertEqual(self.pixel(image, layout.vertical_arrow_x, y), WHITE)
                self.assertEqual(self.pixel(image, layout.grid_left + 5 * CELL_SIZE + 16,
                                           layout.grid_top + 4 * CELL_SIZE + 16), WHITE)
        self.assertEqual(design, original)

    def test_tiny_and_narrow_grids_have_room_for_the_complete_labels(self):
        for columns, rows in ((1, 1), (1, 128), (128, 1), (128, 128)):
            for mm in (0.1, 5, 100):
                with self.subTest(columns=columns, rows=rows, mm=mm):
                    design = PixelDesign(columns, rows)
                    design.set_pixel(0, 0, RED)
                    design.set_pixel(columns - 1, rows - 1, BLUE)
                    layout = export_layout(design, mm)
                    for rect in (layout.horizontal_label_rect, layout.vertical_label_rect,
                                 layout.grid_rect):
                        self.assertGreaterEqual(rect.left(), 0)
                        self.assertGreaterEqual(rect.top(), 0)
                        self.assertLess(rect.right(), layout.image_width)
                        self.assertLess(rect.bottom(), layout.image_height)
                    self.assertLessEqual(layout.image_width, 4300)
                    self.assertLessEqual(layout.image_height, 4300)
        tiny = PixelDesign(1, 1, [RED])
        image = render_png(tiny, piece_size_mm=100)
        layout = export_layout(tiny, 100)
        self.assertTrue(self.has_black(image, layout.horizontal_label_rect))
        self.assertTrue(self.has_black(image, layout.vertical_label_rect))

    def test_maximum_grid_renders_and_png_density_matches_the_physical_cell_size(self):
        design = PixelDesign(128, 128)
        design.set_pixel(127, 127, BLUE)
        image = render_png(design, show_grid=False)
        layout = export_layout(design)
        self.assertEqual(image.size(), layout.image_size)
        self.assertEqual(image.dotsPerMeterX(), 6400)
        self.assertEqual(image.dotsPerMeterY(), 6400)
        self.assertEqual(self.pixel(image, layout.grid_left + 127 * CELL_SIZE + 16,
                                   layout.grid_top + 127 * CELL_SIZE + 16), BLUE)
        small = render_png(PixelDesign(1, 1), piece_size_mm=2.5)
        self.assertEqual(small.dotsPerMeterX(), 12800)
        self.assertEqual(small.dotsPerMeterY(), 12800)

    def test_real_png_roundtrip_preserves_artwork_and_density(self):
        design = PixelDesign(2, 1, [RED, BLUE], name="Cores do ateliê")
        original = design.clone()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "minha criação.png"
            save_png(design, target, display_mode="beads", show_grid=True, piece_size_mm=2.6)
            self.assertEqual(target.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            restored = QImage(str(target))
            expected = render_png(design, display_mode="beads", show_grid=True, piece_size_mm=2.6)
            self.assertFalse(restored.isNull())
            self.assertEqual(restored.size(), expected.size())
            self.assertEqual(restored.dotsPerMeterX(), expected.dotsPerMeterX())
            self.assertEqual(restored.convertToFormat(QImage.Format.Format_ARGB32),
                             expected.convertToFormat(QImage.Format.Format_ARGB32))
            self.assertEqual(list(Path(directory).iterdir()), [target])
        self.assertEqual(design, original)

    def test_commit_failure_keeps_the_previous_image_and_cleans_temporary_files(self):
        class FailedCommit(QSaveFile):
            def commit(self):
                return False

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "imagem.png"
            save_png(PixelDesign(1, 1, [RED]), target)
            original = target.read_bytes()
            with patch("piixelverso.png_export.QSaveFile", FailedCommit):
                with self.assertRaisesRegex(OSError, "concluir"):
                    save_png(PixelDesign(1, 1, [BLUE]), target)
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_invalid_options_or_missing_folder_fail_without_mutating_the_design(self):
        design = PixelDesign(1, 1, [RED])
        original = design.clone()
        for size in (0, -1, True, float("inf"), float("nan"), 101, "5"):
            with self.subTest(piece_size_mm=size), self.assertRaises(ValueError):
                render_png(design, piece_size_mm=size)
        with self.assertRaises(ValueError):
            render_png(design, display_mode="triangle")
        with self.assertRaises(ValueError):
            render_png(design, show_grid="sim")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(OSError):
                save_png(design, Path(directory) / "inexistente" / "imagem.png")
        self.assertEqual(design, original)


if __name__ == "__main__":
    unittest.main()
