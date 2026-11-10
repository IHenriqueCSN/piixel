"""Rectangular pixel selections and clipboard transformations."""
from __future__ import annotations

from dataclasses import dataclass

from .model import PixelDesign


@dataclass(frozen=True)
class SelectionPayload:
    width: int
    height: int
    pixels: tuple[str | None, ...]

    def __post_init__(self):
        if self.width < 1 or self.height < 1 or len(self.pixels) != self.width * self.height:
            raise ValueError("A seleção copiada é inválida.")


def _bounded_rect(design: PixelDesign, rect: tuple[int, int, int, int]):
    left, top, width, height = rect
    if width < 1 or height < 1:
        raise ValueError("A seleção deve conter pelo menos uma célula.")
    if left < 0 or top < 0 or left + width > design.width or top + height > design.height:
        raise ValueError("A seleção precisa ficar dentro da prancheta.")
    return left, top, width, height


def capture_selection(design: PixelDesign, rect: tuple[int, int, int, int]) -> SelectionPayload:
    left, top, width, height = _bounded_rect(design, rect)
    pixels = tuple(
        design.get_pixel(left + x, top + y)
        for y in range(height) for x in range(width)
    )
    return SelectionPayload(width, height, pixels)


def cut_selection_changes(design: PixelDesign, rect: tuple[int, int, int, int]):
    left, top, width, height = _bounded_rect(design, rect)
    return {
        (top + y) * design.width + left + x: None
        for y in range(height) for x in range(width)
        if design.get_pixel(left + x, top + y) is not None
    }


def paste_selection_changes(design: PixelDesign, payload: SelectionPayload,
                            left: int, top: int):
    changes = {}
    for y in range(payload.height):
        target_y = top + y
        if not 0 <= target_y < design.height:
            continue
        for x in range(payload.width):
            target_x = left + x
            if not 0 <= target_x < design.width:
                continue
            index = target_y * design.width + target_x
            color = payload.pixels[y * payload.width + x]
            if design.pixels[index] != color:
                changes[index] = color
    return changes


def move_selection_changes(design: PixelDesign, rect: tuple[int, int, int, int],
                           left: int, top: int):
    source_left, source_top, width, height = _bounded_rect(design, rect)
    if left < 0 or top < 0 or left + width > design.width or top + height > design.height:
        raise ValueError("O destino da seleção precisa ficar dentro da prancheta.")
    payload = capture_selection(design, rect)
    desired = {
        (source_top + y) * design.width + source_left + x: None
        for y in range(height) for x in range(width)
    }
    for y in range(payload.height):
        for x in range(payload.width):
            index = (top + y) * design.width + left + x
            desired[index] = payload.pixels[y * payload.width + x]
    return {index: color for index, color in desired.items()
            if design.pixels[index] != color}
