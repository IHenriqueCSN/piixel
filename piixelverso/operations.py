"""Operações de pintura que calculam alterações sem modificar o design."""
from __future__ import annotations

from .model import PixelDesign, normalize_color


def flood_fill_changes(
    design: PixelDesign, x: int, y: int, color: str | None
) -> dict[int, str | None]:
    """Preencha a região ligada por lados à célula, preservando o original."""
    target = normalize_color(color)
    design.validate()
    source = normalize_color(design.get_pixel(x, y))
    if source == target:
        return {}

    width = design.width
    size = len(design.pixels)
    start = y * width + x
    pending = [start]
    visited = bytearray(size)
    visited[start] = 1
    changes: dict[int, str | None] = {}

    while pending:
        index = pending.pop()
        changes[index] = target
        column = index % width
        neighbors = (
            index - width,
            index + width,
            index - 1 if column > 0 else -1,
            index + 1 if column < width - 1 else -1,
        )
        for neighbor in neighbors:
            if 0 <= neighbor < size and not visited[neighbor]:
                visited[neighbor] = 1
                if normalize_color(design.pixels[neighbor]) == source:
                    pending.append(neighbor)

    return changes


def replace_color_changes(
    design: PixelDesign, source: str, target: str
) -> dict[int, str]:
    """Substitua uma cor em toda a grade, inclusive em regiões separadas."""
    source = normalize_color(source)
    target = normalize_color(target)
    if source is None or target is None:
        raise ValueError("Escolha materiais válidos para a origem e o destino.")
    design.validate()
    if source == target:
        return {}
    return {
        index: target
        for index, color in enumerate(design.pixels)
        if normalize_color(color) == source
    }
