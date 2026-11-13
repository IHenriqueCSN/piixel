"""Presentation names and visible colors for special physical materials."""
from __future__ import annotations

from .model import is_transparent, normalize_color


TRANSPARENT_FILL = "#E4F3F5"
TRANSPARENT_OUTLINE = "#548DB0"
LIGHT_MATERIAL_OUTLINE = "#AAA5B2"


def needs_light_outline(color: str | None) -> bool:
    """Return whether a real RGB material needs contrast on the pale grid."""
    if color is None or is_transparent(color):
        return False
    normalized = normalize_color(color)
    channels = [int(normalized[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045
        else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    luminance = sum(value * weight for value, weight in zip(
        linear, (0.2126, 0.7152, 0.0722)
    ))
    return luminance >= 0.82


def display_color(color: str) -> str:
    return TRANSPARENT_FILL if is_transparent(color) else color


def material_reference(color: str) -> str:
    return "TRANSPARENTE" if is_transparent(color) else color
