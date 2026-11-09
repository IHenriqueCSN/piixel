"""Discrete geometric shapes, independent of the interface and document state."""
from __future__ import annotations


SHAPE_TOOLS = frozenset({"line", "rectangle", "ellipse"})


def _point(value) -> tuple[int, int]:
    if (not isinstance(value, (tuple, list)) or len(value) != 2
            or any(type(coordinate) is not int for coordinate in value)):
        raise ValueError("As extremidades precisam conter duas coordenadas inteiras.")
    return value[0], value[1]


def _line(start: tuple[int, int], end: tuple[int, int]) -> set[tuple[int, int]]:
    # A fixed direction makes the choice at a half-cell identical on reversed drags.
    (x, y), (end_x, end_y) = sorted((start, end))
    distance_x, distance_y = abs(end_x - x), -abs(end_y - y)
    step_x, step_y = (1 if x < end_x else -1), (1 if y < end_y else -1)
    error = distance_x + distance_y
    cells = set()
    while True:
        cells.add((x, y))
        if (x, y) == (end_x, end_y):
            return cells
        doubled = 2 * error
        if doubled >= distance_y:
            error += distance_y
            x += step_x
        if doubled <= distance_x:
            error += distance_x
            y += step_y


def _ellipse(left: int, top: int, right: int, bottom: int) -> set[tuple[int, int]]:
    """Trace the four symmetric quadrants using integer midpoint decisions."""
    if left == right or top == bottom:
        return _line((left, top), (right, bottom))
    width, height = right - left, bottom - top
    odd_height = height & 1
    delta_x = 4 * (1 - width) * height * height
    delta_y = 4 * (odd_height + 1) * width * width
    error = delta_x + delta_y + odd_height * width * width
    y_low = top + (height + 1) // 2
    y_high = y_low - odd_height
    x_low, x_high = left, right
    step_y, step_x = 8 * width * width, 8 * height * height
    cells = set()
    while x_low <= x_high:
        cells.update(((x_high, y_low), (x_low, y_low),
                      (x_low, y_high), (x_high, y_high)))
        doubled = 2 * error
        if doubled <= delta_y:
            y_low += 1
            y_high -= 1
            delta_y += step_y
            error += delta_y
        if doubled >= delta_x or 2 * error > delta_y:
            x_low += 1
            x_high -= 1
            delta_x += step_x
            error += delta_x
    # Complete narrow tips when the horizontal radius reaches zero first.
    while y_low - y_high <= height:
        cells.update(((x_low - 1, y_low), (x_high + 1, y_low),
                      (x_low - 1, y_high), (x_high + 1, y_high)))
        y_low += 1
        y_high -= 1
    return cells


def shape_cells(
    tool: str, start: tuple[int, int], end: tuple[int, int], filled: bool = False,
) -> set[tuple[int, int]]:
    """Return occupied cells; both endpoints define an inclusive bounding box."""
    if not isinstance(tool, str) or tool not in SHAPE_TOOLS:
        raise ValueError("Escolha linha, retângulo ou elipse.")
    if type(filled) is not bool:
        raise ValueError("A opção de preenchimento precisa ser verdadeira ou falsa.")
    start, end = _point(start), _point(end)
    if tool == "line":
        return _line(start, end)
    left, right = sorted((start[0], end[0]))
    top, bottom = sorted((start[1], end[1]))
    if tool == "rectangle":
        if filled:
            return {(x, y) for y in range(top, bottom + 1) for x in range(left, right + 1)}
        return ({(x, y) for y in (top, bottom) for x in range(left, right + 1)}
                | {(x, y) for x in (left, right) for y in range(top, bottom + 1)})
    outline = _ellipse(left, top, right, bottom)
    if not filled:
        return outline
    rows: dict[int, list[int]] = {}
    for x, y in outline:
        rows.setdefault(y, []).append(x)
    return {(x, y) for y, columns in rows.items()
            for x in range(min(columns), max(columns) + 1)}
