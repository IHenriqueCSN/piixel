import unittest

from piixelverso.model import PixelDesign
from piixelverso.operations import flood_fill_changes, replace_color_changes


RED = "#FF0000"
BLUE = "#0000FF"
WHITE = "#FFFFFF"


class FloodFillTests(unittest.TestCase):
    def test_fills_connected_region_without_crossing_border(self):
        design = PixelDesign(4, 3, [
            RED, RED, BLUE, RED,
            RED, BLUE, BLUE, RED,
            RED, RED, BLUE, RED,
        ])
        self.assertEqual(flood_fill_changes(design, 0, 0, WHITE), {
            0: WHITE, 1: WHITE, 4: WHITE, 8: WHITE, 9: WHITE,
        })

    def test_diagonal_cells_and_opposite_row_edges_are_not_connected(self):
        design = PixelDesign(3, 3, [
            RED, BLUE, RED,
            BLUE, RED, BLUE,
            RED, BLUE, RED,
        ])
        self.assertEqual(flood_fill_changes(design, 1, 1, WHITE), {4: WHITE})
        # Adjacent list positions at the end and start of rows are not neighbors.
        design = PixelDesign(3, 2, [BLUE, BLUE, RED, RED, BLUE, BLUE])
        self.assertEqual(flood_fill_changes(design, 2, 0, WHITE), {2: WHITE})

    def test_empty_cells_are_distinct_from_white_and_can_be_filled_or_cleared(self):
        design = PixelDesign(3, 2, [None, WHITE, None, None, WHITE, WHITE])
        self.assertEqual(flood_fill_changes(design, 0, 0, RED), {0: RED, 3: RED})
        self.assertEqual(flood_fill_changes(design, 1, 0, None), {
            1: None, 4: None, 5: None,
        })
        self.assertEqual(flood_fill_changes(design, 2, 0, RED), {2: RED})

    def test_handles_single_cell_and_narrow_grids(self):
        for width, height in ((1, 1), (1, 4), (4, 1)):
            with self.subTest(width=width, height=height):
                design = PixelDesign(width, height)
                self.assertEqual(flood_fill_changes(design, width - 1, height - 1, RED),
                                 dict.fromkeys(range(width * height), RED))

    def test_normalizes_comparisons_and_destination_without_mutating_input(self):
        design = PixelDesign(3, 1, [RED, RED, BLUE], "Original")
        design.pixels[0] = "#ff0000"
        original_pixels = design.pixels
        snapshot = list(design.pixels)
        self.assertEqual(flood_fill_changes(design, 0, 0, "#aabbcc"), {
            0: "#AABBCC", 1: "#AABBCC",
        })
        self.assertIs(design.pixels, original_pixels)
        self.assertEqual(design.pixels, snapshot)
        self.assertEqual((design.width, design.height, design.name), (3, 1, "Original"))

    def test_same_color_and_already_empty_are_noops(self):
        design = PixelDesign(2, 1, [RED, None])
        self.assertEqual(flood_fill_changes(design, 0, 0, "#ff0000"), {})
        self.assertEqual(flood_fill_changes(design, 1, 0, None), {})

    def test_rejects_invalid_colors_and_coordinates(self):
        design = PixelDesign(2, 2)
        for color in ("red", "#FFF", "#123456\n", 123, "#GGFFFF"):
            with self.subTest(color=color), self.assertRaises(ValueError):
                flood_fill_changes(design, 0, 0, color)
        for position in ((-1, 0), (2, 0), (0, -1), (0, 2), (True, 0), (0, 1.0)):
            with self.subTest(position=position), self.assertRaises(IndexError):
                flood_fill_changes(design, *position, RED)
        self.assertEqual(design.pixels, [None] * 4)

    def test_fills_maximum_grid_without_recursion_or_mutation(self):
        design = PixelDesign(128, 128)
        changes = flood_fill_changes(design, 127, 127, RED)
        self.assertEqual(changes, dict.fromkeys(range(128 * 128), RED))
        self.assertTrue(design.is_empty)


class ReplaceColorTests(unittest.TestCase):
    def test_replaces_all_islands_while_preserving_other_colors_and_empty_cells(self):
        design = PixelDesign(3, 3, [
            RED, BLUE, RED,
            None, WHITE, BLUE,
            RED, BLUE, RED,
        ])
        self.assertEqual(replace_color_changes(design, RED, BLUE), {
            0: BLUE, 2: BLUE, 6: BLUE, 8: BLUE,
        })
        self.assertEqual(design.counts(), {RED: 4, BLUE: 3, WHITE: 1})

    def test_normalizes_comparisons_and_destination_without_mutating_input(self):
        design = PixelDesign(3, 1, [RED, RED, None], "Original")
        design.pixels[0] = "#ff0000"
        original_pixels = design.pixels
        snapshot = list(design.pixels)
        self.assertEqual(replace_color_changes(design, "#ff0000", "#aabbcc"), {
            0: "#AABBCC", 1: "#AABBCC",
        })
        self.assertIs(design.pixels, original_pixels)
        self.assertEqual(design.pixels, snapshot)
        self.assertEqual((design.width, design.height, design.name), (3, 1, "Original"))

    def test_same_color_or_absent_source_are_noops(self):
        design = PixelDesign(2, 1, [RED, None])
        self.assertEqual(replace_color_changes(design, "#ff0000", RED), {})
        self.assertEqual(replace_color_changes(design, BLUE, WHITE), {})

    def test_white_replacement_does_not_replace_empty_cells(self):
        design = PixelDesign(3, 1, [None, WHITE, None])
        self.assertEqual(replace_color_changes(design, WHITE, BLUE), {1: BLUE})

    def test_rejects_missing_or_invalid_colors(self):
        design = PixelDesign(1, 1, [RED])
        for invalid in (None, "red", "#FFF", "#123456\n", 123, "#GGFFFF"):
            for source, target in ((invalid, BLUE), (RED, invalid)):
                with self.subTest(source=source, target=target), self.assertRaises(ValueError):
                    replace_color_changes(design, source, target)
        self.assertEqual(design.pixels, [RED])


if __name__ == "__main__":
    unittest.main()
