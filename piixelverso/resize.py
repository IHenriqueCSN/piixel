"""Resize the logical canvas without scaling or mutating the artwork."""
from __future__ import annotations

from .model import PixelDesign


MIN_CANVAS_SIZE = 10
MAX_CANVAS_SIZE = 128

ANCHOR_LABELS = {
    "top_left": "Superior esquerdo",
    "top": "Superior central",
    "top_right": "Superior direito",
    "left": "Centro esquerdo",
    "center": "Centro",
    "right": "Centro direito",
    "bottom_left": "Inferior esquerdo",
    "bottom": "Inferior central",
    "bottom_right": "Inferior direito",
}

_ANCHOR_AXES = {
    "top_left": (0, 0),
    "top": (1, 0),
    "top_right": (2, 0),
    "left": (0, 1),
    "center": (1, 1),
    "right": (2, 1),
    "bottom_left": (0, 2),
    "bottom": (1, 2),
    "bottom_right": (2, 2),
}


def _axis_offset(difference: int, alignment: int) -> int:
    if alignment == 0:
        return 0
    if alignment == 2:
        return difference
    # Leave an odd extra cell on the right/bottom, for both grow and shrink.
    return difference // 2 if difference >= 0 else -((-difference) // 2)


def resize_offset(
    design: PixelDesign, width: int, height: int, anchor: str = "center",
) -> tuple[int, int]:
    """Return the old canvas origin's position within the new canvas."""
    design.validate()
    for dimension in (width, height):
        if type(dimension) is not int or not MIN_CANVAS_SIZE <= dimension <= MAX_CANVAS_SIZE:
            raise ValueError(
                f"A largura e a altura devem estar entre {MIN_CANVAS_SIZE} e {MAX_CANVAS_SIZE} células."
            )
    if not isinstance(anchor, str) or anchor not in _ANCHOR_AXES:
        raise ValueError("Escolha uma posição de ancoragem válida para o desenho.")
    horizontal, vertical = _ANCHOR_AXES[anchor]
    return (
        _axis_offset(width - design.width, horizontal),
        _axis_offset(height - design.height, vertical),
    )


def count_cropped_pixels(
    design: PixelDesign, width: int, height: int, anchor: str = "center",
) -> int:
    """Count painted pieces that the new canvas would leave outside its edges."""
    offset_x, offset_y = resize_offset(design, width, height, anchor)
    cropped = 0
    for index, color in enumerate(design.pixels):
        if color is None:
            continue
        y, x = divmod(index, design.width)
        if not (0 <= x + offset_x < width and 0 <= y + offset_y < height):
            cropped += 1
    return cropped


def resized_design(
    design: PixelDesign, width: int, height: int, anchor: str = "center",
) -> PixelDesign:
    """Copy the overlapping cells, adding empty cells and cropping the rest."""
    offset_x, offset_y = resize_offset(design, width, height, anchor)
    pixels = [None] * (width * height)
    for row in range(design.height):
        destination_y = row + offset_y
        if not 0 <= destination_y < height:
            continue
        for column in range(design.width):
            destination_x = column + offset_x
            if 0 <= destination_x < width:
                pixels[destination_y * width + destination_x] = design.pixels[row * design.width + column]
    return PixelDesign(width, height, pixels, design.name)
