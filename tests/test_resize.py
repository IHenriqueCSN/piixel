"""Canvas changes preserve cells, placement and the original document."""
from __future__ import annotations

import unittest

from piixelverso.format import decode_design, encode_design
from piixelverso.model import PixelDesign
from piixelverso.resize import (
    ANCHOR_LABELS, count_cropped_pixels, resized_design, resize_offset,
)


RED = "#ED5598"
BLUE = "#285A78"
WHITE = "#FFFFFF"


class CanvasResizeTests(unittest.TestCase):
    def test_growing_a_rectangle_preserves_every_color_and_pads_with_empty_cells(self):
        design = PixelDesign(10, 12, name="Órbita original")
        design.set_pixel(0, 0, RED)
        design.set_pixel(9, 11, WHITE)
        design.set_pixel(4, 6, BLUE)
        original_pixels = design.pixels
        snapshot = list(design.pixels)
        enlarged = resized_design(design, 16, 20)
        self.assertEqual((enlarged.width, enlarged.height, enlarged.name), (16, 20, design.name))
        self.assertEqual(enlarged.get_pixel(3, 4), RED)
        self.assertEqual(enlarged.get_pixel(12, 15), WHITE)
        self.assertEqual(enlarged.get_pixel(7, 10), BLUE)
        self.assertIsNone(enlarged.get_pixel(0, 0))
        self.assertEqual(enlarged.counts(), design.counts())
        self.assertIs(design.pixels, original_pixels)
        self.assertEqual(design.pixels, snapshot)
        self.assertEqual((design.width, design.height), (10, 12))

    def test_all_nine_anchors_place_the_same_piece_without_scaling_it(self):
        design = PixelDesign(10, 10)
        design.set_pixel(2, 3, RED)
        expected = {
            "top_left": (0, 0), "top": (3, 0), "top_right": (6, 0),
            "left": (0, 4), "center": (3, 4), "right": (6, 4),
            "bottom_left": (0, 8), "bottom": (3, 8), "bottom_right": (6, 8),
        }
        self.assertEqual(set(ANCHOR_LABELS), set(expected))
        for anchor, offset in expected.items():
            with self.subTest(anchor=anchor):
                self.assertEqual(resize_offset(design, 16, 18, anchor), offset)
                resized = resized_design(design, 16, 18, anchor)
                self.assertEqual(resized.get_pixel(2 + offset[0], 3 + offset[1]), RED)
                self.assertEqual(resized.filled_count, 1)
                self.assertEqual(count_cropped_pixels(design, 16, 18, anchor), 0)

    def test_shrinking_keeps_the_chosen_region_and_counts_cropped_white_pieces(self):
        design = PixelDesign(14, 12, name="Peças nas bordas")
        design.set_pixel(0, 0, WHITE)
        design.set_pixel(13, 11, RED)
        design.set_pixel(4, 4, BLUE)
        original = design.clone()
        for anchor, lost, kept_position in (
            ("top_left", RED, (4, 4)),
            ("bottom_right", WHITE, (0, 2)),
        ):
            with self.subTest(anchor=anchor):
                resized = resized_design(design, 10, 10, anchor)
                self.assertNotIn(lost, resized.counts())
                self.assertEqual(resized.get_pixel(*kept_position), BLUE)
                self.assertEqual(count_cropped_pixels(design, 10, 10, anchor), 1)
        centered = resized_design(design, 10, 10)
        self.assertEqual(centered.counts(), {BLUE: 1})
        self.assertEqual(centered.get_pixel(2, 3), BLUE)
        self.assertEqual(count_cropped_pixels(design, 10, 10), 2)
        self.assertEqual(design, original)

    def test_all_anchors_crop_the_expected_edges_of_a_filled_rectangle(self):
        design = PixelDesign(14, 16, [RED] * (14 * 16))
        expected = {
            "top_left": (0, 0), "top": (-2, 0), "top_right": (-4, 0),
            "left": (0, -3), "center": (-2, -3), "right": (-4, -3),
            "bottom_left": (0, -6), "bottom": (-2, -6), "bottom_right": (-4, -6),
        }
        for anchor, offset in expected.items():
            with self.subTest(anchor=anchor):
                self.assertEqual(resize_offset(design, 10, 10, anchor), offset)
                self.assertEqual(count_cropped_pixels(design, 10, 10, anchor), 124)
                self.assertEqual(resized_design(design, 10, 10, anchor).pixels, [RED] * 100)

    def test_odd_center_changes_leave_the_extra_cell_on_the_right_and_bottom(self):
        design = PixelDesign(10, 10)
        design.set_pixel(0, 0, WHITE)
        design.set_pixel(9, 9, RED)
        for new_width, new_height, expected_offset in ((11, 13, (0, 1)), (13, 11, (1, 0))):
            with self.subTest(width=new_width, height=new_height):
                enlarged = resized_design(design, new_width, new_height)
                self.assertEqual(resize_offset(design, new_width, new_height), expected_offset)
                self.assertEqual(resized_design(enlarged, 10, 10), design)
                self.assertEqual(count_cropped_pixels(enlarged, 10, 10), 0)

    def test_growing_one_axis_and_shrinking_the_other_preserves_its_overlap(self):
        design = PixelDesign(14, 10)
        design.set_pixel(1, 0, RED)
        design.set_pixel(2, 1, BLUE)
        design.set_pixel(11, 9, WHITE)
        resized = resized_design(design, 10, 16)
        self.assertEqual(resize_offset(design, 10, 16), (-2, 3))
        self.assertEqual(resized.counts(), {BLUE: 1, WHITE: 1})
        self.assertEqual(resized.get_pixel(0, 4), BLUE)
        self.assertEqual(resized.get_pixel(9, 12), WHITE)
        self.assertEqual(count_cropped_pixels(design, 10, 16), 1)

    def test_same_size_returns_an_independent_equal_document_and_does_not_crop(self):
        design = PixelDesign(10, 12)
        design.set_pixel(9, 11, BLUE)
        for anchor in ANCHOR_LABELS:
            with self.subTest(anchor=anchor):
                result = resized_design(design, 10, 12, anchor)
                self.assertEqual(result, design)
                self.assertIsNot(result, design)
                self.assertIsNot(result.pixels, design.pixels)
                self.assertEqual(count_cropped_pixels(design, 10, 12, anchor), 0)

    def test_empty_canvas_and_maximum_size_are_supported(self):
        design = PixelDesign(10, 10)
        self.assertEqual(count_cropped_pixels(design, 128, 128), 0)
        enlarged = resized_design(design, 128, 128)
        self.assertEqual(len(enlarged.pixels), 128 * 128)
        self.assertTrue(enlarged.is_empty)
        self.assertEqual(count_cropped_pixels(enlarged, 10, 10), 0)
        self.assertEqual(resized_design(enlarged, 10, 10), design)

    def test_existing_small_designs_can_be_enlarged_without_changing_the_format_limits(self):
        legacy = PixelDesign(1, 2, [WHITE, RED], name="Design pequeno")
        resized = resized_design(legacy, 10, 10, "bottom_right")
        self.assertEqual(resized.get_pixel(9, 8), WHITE)
        self.assertEqual(resized.get_pixel(9, 9), RED)
        self.assertEqual(decode_design(encode_design(resized)), resized)
        self.assertEqual(legacy.pixels, [WHITE, RED])

    def test_invalid_dimensions_anchor_and_source_are_rejected_without_mutation(self):
        design = PixelDesign(12, 12)
        design.set_pixel(5, 5, RED)
        original = design.clone()
        for helper in (resize_offset, resized_design, count_cropped_pixels):
            for invalid in (1, 9, 129, 10.0, True, False, "10", None):
                for width, height in ((invalid, 12), (12, invalid)):
                    with self.subTest(helper=helper.__name__, width=width, height=height):
                        with self.assertRaises(ValueError):
                            helper(design, width, height)
            for anchor in ("middle", "", None, [], 0):
                with self.subTest(helper=helper.__name__, anchor=anchor):
                    with self.assertRaises(ValueError):
                        helper(design, 10, 10, anchor)
        self.assertEqual(design, original)
        design.pixels.append(None)
        with self.assertRaises(ValueError):
            resized_design(design, 10, 10)


if __name__ == "__main__":
    unittest.main()
