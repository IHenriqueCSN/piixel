import unittest

from piixelverso.model import PixelDesign


class ModelTests(unittest.TestCase):
    def test_empty_grid(self):
        design = PixelDesign()
        self.assertEqual(len(design.pixels), 1024)
        self.assertEqual(design.counts(), {})
        self.assertEqual(design.filled_count, 0)
        self.assertTrue(design.is_empty)

    def test_counts_and_row_major(self):
        design = PixelDesign(3, 2)
        design.set_pixel(2, 1, "#aabbcc")
        design.set_pixel(0, 0, "#AABBCC")
        design.set_pixel(1, 1, "#000000")
        self.assertEqual(design.pixels[5], "#AABBCC")
        self.assertEqual(design.counts(), {"#AABBCC": 2, "#000000": 1})
        self.assertEqual(design.filled_count, 3)
        design.set_pixel(0, 0, None)
        self.assertEqual(design.counts(), {"#AABBCC": 1, "#000000": 1})
        self.assertFalse(design.is_empty)

    def test_clone_is_independent(self):
        original = PixelDesign(1, 1, ["#00ff00"], "Coração ♥")
        clone = original.clone()
        clone.set_pixel(0, 0, None)
        self.assertEqual(original.get_pixel(0, 0), "#00FF00")
        self.assertEqual(clone.name, "Coração ♥")

    def test_counts_normalize_public_list_mutations(self):
        design = PixelDesign(2, 1, ["#AABBCC", None])
        design.pixels[1] = "#aabbcc"
        self.assertEqual(design.counts(), {"#AABBCC": 2})

    def test_invalid_dimensions(self):
        for value in (0, -1, 129, True, 1.5, "3"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                PixelDesign(value, 1)

    def test_invalid_coordinates(self):
        design = PixelDesign(2, 2)
        for position in ((-1, 0), (2, 0), (0, -1), (0, 2), (True, 0)):
            with self.subTest(position=position), self.assertRaises(IndexError):
                design.set_pixel(*position, "#000000")

    def test_invalid_colors(self):
        design = PixelDesign(1, 1)
        for color in ("red", "#FFF", "#123456\n", 123, "#GGFFFF"):
            with self.subTest(color=color), self.assertRaises(ValueError):
                design.set_pixel(0, 0, color)

    def test_shape_and_name_validation(self):
        for pixels in ([], [None, None], (None,)):
            with self.subTest(pixels=pixels), self.assertRaises(ValueError):
                PixelDesign(1, 1, pixels)
        for name in (None, "a" * 4097, "\ud800"):
            with self.subTest(name=repr(name)), self.assertRaises(ValueError):
                PixelDesign(name=name)


if __name__ == "__main__":
    unittest.main()
