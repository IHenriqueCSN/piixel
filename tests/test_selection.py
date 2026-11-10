"""Selection payload transformations without constructing the editor UI."""
from __future__ import annotations

import unittest

from piixelverso.model import PixelDesign, TRANSPARENT
from piixelverso.selection import (
    capture_selection, cut_selection_changes, move_selection_changes,
    paste_selection_changes,
)


class SelectionOperationsTests(unittest.TestCase):
    def test_capture_and_paste_preserve_empty_and_transparent_cells(self):
        design = PixelDesign(5, 4)
        design.set_pixel(1, 1, "#ED5598")
        design.set_pixel(2, 1, TRANSPARENT)
        design.set_pixel(2, 2, "#245448")
        payload = capture_selection(design, (1, 1, 2, 2))
        self.assertEqual(payload.pixels, ("#ED5598", TRANSPARENT, None, "#245448"))

        design.set_pixel(0, 3, "#FFFFFF")
        changes = paste_selection_changes(design, payload, 0, 2)
        self.assertEqual(changes[2 * design.width], "#ED5598")
        self.assertEqual(changes[2 * design.width + 1], TRANSPARENT)
        self.assertIsNone(changes[3 * design.width])
        self.assertEqual(changes[3 * design.width + 1], "#245448")

    def test_cut_only_changes_filled_cells_and_move_handles_overlap(self):
        design = PixelDesign(6, 2)
        for x, color in enumerate(("#111111", "#222222", "#333333")):
            design.set_pixel(x, 0, color)
        self.assertEqual(cut_selection_changes(design, (0, 0, 3, 2)), {0: None, 1: None, 2: None})
        changes = move_selection_changes(design, (0, 0, 3, 1), 1, 0)
        self.assertEqual(changes, {0: None, 1: "#111111", 2: "#222222", 3: "#333333"})

    def test_invalid_or_out_of_bounds_rectangles_are_rejected(self):
        design = PixelDesign(4, 4)
        for rect in ((-1, 0, 2, 2), (0, 0, 0, 1), (3, 3, 2, 2)):
            with self.subTest(rect=rect), self.assertRaises(ValueError):
                capture_selection(design, rect)
        with self.assertRaises(ValueError):
            move_selection_changes(design, (0, 0, 2, 2), 3, 3)


if __name__ == "__main__":
    unittest.main()
