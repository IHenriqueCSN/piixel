"""Presentation names and visible colors for special physical materials."""
from __future__ import annotations

from .model import is_transparent


TRANSPARENT_FILL = "#E4F3F5"
TRANSPARENT_OUTLINE = "#548DB0"


def display_color(color: str) -> str:
    return TRANSPARENT_FILL if is_transparent(color) else color


def material_reference(color: str) -> str:
    return "TRANSPARENTE" if is_transparent(color) else color
