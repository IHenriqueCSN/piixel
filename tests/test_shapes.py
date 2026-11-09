"""Integer geometry stays predictable independently of Qt and the canvas."""
from __future__ import annotations

import unittest

from piixelverso.shapes import SHAPE_TOOLS, shape_cells


class ShapeCellsTests(unittest.TestCase):
    def assert_connected(self, cells):
        pending = [next(iter(cells))]
        visited = set(pending)
        while pending:
            x, y = pending.pop()
            for offset_x in (-1, 0, 1):
                for offset_y in (-1, 0, 1):
                    neighbor = (x + offset_x, y + offset_y)
                    if neighbor in cells and neighbor not in visited:
                        visited.add(neighbor)
                        pending.append(neighbor)
        self.assertEqual(visited, cells, "A forma deve ser ligada por lados ou diagonais")

    def test_line_draws_horizontal_vertical_and_diagonal_endpoints(self):
        self.assertEqual(shape_cells("line", (2, 3), (6, 3)),
                         {(x, 3) for x in range(2, 7)})
        self.assertEqual(shape_cells("line", (2, 3), (2, -1)),
                         {(2, y) for y in range(-1, 4)})
        self.assertEqual(shape_cells("line", (1, 5), (5, 1)),
                         {(1, 5), (2, 4), (3, 3), (4, 2), (5, 1)})

    def test_sloped_lines_are_connected_single_width_and_reversible(self):
        for start, end in (((0, 0), (6, 3)), ((0, 0), (3, 6)),
                           ((4, 0), (0, 7)), ((-5, 8), (11, -3)),
                           ((0, 0), (30, 127)), ((127, 30), (0, 0))):
            with self.subTest(start=start, end=end):
                cells = shape_cells("line", start, end)
                self.assertEqual(cells, shape_cells("line", end, start))
                self.assertEqual(cells, shape_cells("line", start, end, filled=True))
                self.assertIn(start, cells)
                self.assertIn(end, cells)
                self.assertEqual(len(cells), max(abs(end[0] - start[0]), abs(end[1] - start[1])) + 1)
                self.assert_connected(cells)

    def test_rectangle_has_an_inclusive_perimeter_or_solid_interior(self):
        outline = shape_cells("rectangle", (2, 3), (5, 6))
        self.assertEqual(outline, {
            (2, 3), (3, 3), (4, 3), (5, 3),
            (2, 4), (5, 4), (2, 5), (5, 5),
            (2, 6), (3, 6), (4, 6), (5, 6),
        })
        filled = shape_cells("rectangle", (2, 3), (5, 6), filled=True)
        self.assertEqual(filled, {(x, y) for y in range(3, 7) for x in range(2, 6)})
        self.assertTrue(outline < filled)

    def test_box_tools_support_dragging_from_any_corner(self):
        for tool in ("rectangle", "ellipse"):
            for filled in (False, True):
                expected = shape_cells(tool, (2, 3), (9, 8), filled)
                for start, end in (((9, 8), (2, 3)), ((9, 3), (2, 8)), ((2, 8), (9, 3))):
                    with self.subTest(tool=tool, filled=filled, start=start):
                        self.assertEqual(shape_cells(tool, start, end, filled), expected)

    def test_click_and_degenerate_row_or_column_have_no_gaps(self):
        for tool in SHAPE_TOOLS:
            for filled in (False, True):
                with self.subTest(tool=tool, filled=filled):
                    self.assertEqual(shape_cells(tool, (7, 9), (7, 9), filled), {(7, 9)})
                    self.assertEqual(shape_cells(tool, (7, 9), (7, 4), filled),
                                     {(7, y) for y in range(4, 10)})
                    self.assertEqual(shape_cells(tool, (7, 9), (2, 9), filled),
                                     {(x, 9) for x in range(2, 8)})

    def test_small_ellipse_has_a_round_perimeter_and_a_filled_center(self):
        outline = shape_cells("ellipse", (0, 0), (4, 4))
        expected = ({(x, y) for y in (0, 4) for x in (1, 2, 3)}
                    | {(x, y) for x in (0, 4) for y in (1, 2, 3)})
        self.assertEqual(outline, expected)
        self.assertNotIn((2, 2), outline)
        self.assertNotIn((0, 0), outline)
        filled = shape_cells("ellipse", (0, 0), (4, 4), True)
        self.assertTrue(outline < filled)
        self.assertIn((2, 2), filled)
        self.assertEqual(len(filled), 21)

    def test_ellipses_keep_symmetry_extremes_and_connected_narrow_tips(self):
        for width, height in ((2, 2), (2, 3), (2, 128), (3, 2), (3, 8), (3, 127),
                              (4, 4), (4, 15), (15, 4), (7, 10), (10, 7),
                              (32, 33), (33, 32), (127, 128), (128, 127)):
            with self.subTest(width=width, height=height):
                left, top = -7, 3
                right, bottom = left + width - 1, top + height - 1
                cells = shape_cells("ellipse", (left, top), (right, bottom))
                self.assertEqual(cells, {(left + right - x, y) for x, y in cells})
                self.assertEqual(cells, {(x, top + bottom - y) for x, y in cells})
                self.assertTrue(all(left <= x <= right and top <= y <= bottom for x, y in cells))
                self.assertEqual({x for x, y in cells}, set(range(left, right + 1)))
                self.assertEqual({y for x, y in cells}, set(range(top, bottom + 1)))
                self.assert_connected(cells)

    def test_filled_ellipses_contain_the_outline_and_have_no_internal_holes(self):
        for width, height in ((2, 128), (3, 8), (8, 3), (8, 8), (31, 18), (128, 128)):
            with self.subTest(width=width, height=height):
                start, end = (0, 0), (width - 1, height - 1)
                outline = shape_cells("ellipse", start, end)
                filled = shape_cells("ellipse", start, end, True)
                self.assertTrue(outline <= filled)
                for y in range(height):
                    columns = {x for x, row in filled if row == y}
                    self.assertTrue(columns)
                    self.assertEqual(columns, set(range(min(columns), max(columns) + 1)))
                self.assert_connected(filled)

    def test_maximum_canvas_shapes_are_bounded_without_recursion(self):
        for tool in SHAPE_TOOLS:
            for filled in (False, True):
                with self.subTest(tool=tool, filled=filled):
                    cells = shape_cells(tool, (0, 0), (127, 127), filled)
                    self.assertLessEqual(len(cells), 128 * 128)
                    self.assertTrue(all(0 <= x < 128 and 0 <= y < 128 for x, y in cells))
        self.assertEqual(len(shape_cells("rectangle", (0, 0), (127, 127), True)), 128 * 128)

    def test_translations_and_input_lists_preserve_their_coordinates(self):
        start, end = [2, 3], [9, 10]
        for tool in SHAPE_TOOLS:
            for filled in (False, True):
                cells = shape_cells(tool, start, end, filled)
                translated = shape_cells(tool, (-8, -17), (-1, -10), filled)
                self.assertEqual(translated, {(x - 10, y - 20) for x, y in cells})
        self.assertEqual(start, [2, 3])
        self.assertEqual(end, [9, 10])

    def test_invalid_shape_points_and_fill_flags_are_rejected(self):
        for tool in (None, "circle", "LINE", "", [], 1):
            with self.subTest(tool=tool), self.assertRaises(ValueError):
                shape_cells(tool, (0, 0), (2, 2))
        for point in (None, (), (1,), (1, 2, 3), (True, 2), (1, False), (1.5, 2), "12"):
            for start, end in ((point, (2, 2)), ((0, 0), point)):
                with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                    shape_cells("rectangle", start, end)
        for filled in (None, 0, 1, "true"):
            with self.subTest(filled=filled), self.assertRaises(ValueError):
                shape_cells("ellipse", (0, 0), (2, 2), filled)


if __name__ == "__main__":
    unittest.main()
