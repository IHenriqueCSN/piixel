"""Modelo independente de interface para uma grade de pixel art."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re

MIN_DIMENSION = 1
MAX_DIMENSION = 128
MAX_NAME_BYTES = 4096
_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")
TRANSPARENT = "#00FFFFFF"


def normalize_color(color: str | None) -> str | None:
    """Normalize uma cor RGB ou a peça transparente; ``None`` é vazio."""
    if color is None:
        return None
    if isinstance(color, str) and color.upper() == TRANSPARENT:
        return TRANSPARENT
    if not isinstance(color, str) or not _COLOR.fullmatch(color):
        raise ValueError("A cor deve estar no formato #RRGGBB ou ser uma peça transparente.")
    return color.upper()


def is_transparent(color: str | None) -> bool:
    return isinstance(color, str) and color.upper() == TRANSPARENT


def validate_name(name: str) -> None:
    if not isinstance(name, str):
        raise ValueError("O nome do design deve ser um texto.")
    try:
        encoded = name.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("O nome contém um caractere inválido.") from exc
    if len(encoded) > MAX_NAME_BYTES:
        raise ValueError(f"O nome deve ocupar no máximo {MAX_NAME_BYTES} bytes UTF-8.")


@dataclass
class PixelDesign:
    width: int = 32
    height: int = 32
    pixels: list[str | None] | None = None
    name: str = "Sem título"

    def __post_init__(self) -> None:
        self.validate_dimensions()
        validate_name(self.name)
        if self.pixels is None:
            self.pixels = [None] * (self.width * self.height)
        elif not isinstance(self.pixels, list):
            raise ValueError("Os pixels devem ser uma lista.")
        elif len(self.pixels) != self.width * self.height:
            raise ValueError("A quantidade de pixels não corresponde às dimensões da grade.")
        else:
            self.pixels = [normalize_color(color) for color in self.pixels]

    def validate_dimensions(self) -> None:
        for dimension in (self.width, self.height):
            if type(dimension) is not int or not MIN_DIMENSION <= dimension <= MAX_DIMENSION:
                raise ValueError(f"Cada dimensão deve estar entre {MIN_DIMENSION} e {MAX_DIMENSION}.")

    def validate(self) -> None:
        """Valide também alterações feitas diretamente nos atributos públicos."""
        self.validate_dimensions()
        validate_name(self.name)
        if not isinstance(self.pixels, list) or len(self.pixels) != self.width * self.height:
            raise ValueError("A quantidade de pixels não corresponde às dimensões da grade.")
        for color in self.pixels:
            normalize_color(color)

    def _index(self, x: int, y: int) -> int:
        if type(x) is not int or type(y) is not int or not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError("A célula está fora dos limites da grade.")
        return y * self.width + x

    def get_pixel(self, x: int, y: int) -> str | None:
        return self.pixels[self._index(x, y)]

    def set_pixel(self, x: int, y: int, color: str | None) -> None:
        index = self._index(x, y)
        self.pixels[index] = normalize_color(color)

    def counts(self) -> dict[str, int]:
        return dict(Counter(normalize_color(color) for color in self.pixels if color is not None))

    @property
    def filled_count(self) -> int:
        return sum(color is not None for color in self.pixels)

    @property
    def is_empty(self) -> bool:
        return not any(color is not None for color in self.pixels)

    def clone(self) -> PixelDesign:
        return PixelDesign(self.width, self.height, list(self.pixels), self.name)
