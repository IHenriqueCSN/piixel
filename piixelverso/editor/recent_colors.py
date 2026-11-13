"""Compact numbered color slots; ordering belongs to the editor coordinator."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..materials import TRANSPARENT_OUTLINE, display_color, material_reference
from ..model import is_transparent, normalize_color
from ..theme import (
    BORDER, CREAM, INK, MUTED, PINK, apply_themed_stylesheet, theme_color,
)


def _number_color(color: QColor) -> str:
    """Choose the higher WCAG contrast ratio between black and white."""
    channels = (color.redF(), color.greenF(), color.blueF())
    linear = [value / 12.92 if value <= 0.04045
              else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    luminance = sum(channel * weight for channel, weight in
                    zip(linear, (0.2126, 0.7152, 0.0722)))
    black = (luminance + 0.05) / 0.05
    white = 1.05 / (luminance + 0.05)
    return "#000000" if black >= white else "#FFFFFF"


class RecentColorsWidget(QWidget):
    """Nine visible session color slots, activated by click or external shortcuts."""

    color_selected = Signal(int)

    def __init__(self, color_names: Mapping[str, str], parent=None):
        super().__init__(parent)
        self.setObjectName("recentColors")
        self.setAccessibleName("Cores recentes, atalhos de 1 a 9")
        self._color_names = color_names
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        heading = QLabel("Recentes · teclas 1–9")
        heading.setObjectName("recentColorsTitle")
        heading.setTextFormat(Qt.TextFormat.PlainText)
        apply_themed_stylesheet(
            heading, f"color: {MUTED}; font-size: 10px; font-weight: 700;"
        )
        layout.addWidget(heading)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        grid.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.buttons: list[QPushButton] = []
        for index in range(9):
            button = QPushButton(str(index + 1))
            button.setObjectName(f"recentColor{index + 1}")
            button.setFixedSize(30, 28)
            button.clicked.connect(
                lambda _checked=False, slot=index: self.color_selected.emit(slot)
            )
            grid.addWidget(button, index // 5, index % 5)
            self.buttons.append(button)
        layout.addLayout(grid)
        self.set_colors((), "")

    def set_colors(self, colors: Sequence[str], active_color: str) -> None:
        self._last_colors = tuple(colors[:9])
        self._last_active_color = active_color
        values = [normalize_color(value) for value in colors[:9]]
        if any(value is None for value in values):
            raise ValueError("Cor recente inválida.")
        parsed = [QColor(display_color(value)) for value in values]
        active = normalize_color(active_color) if active_color else None
        for index, button in enumerate(self.buttons):
            number = index + 1
            if index >= len(parsed):
                button.setProperty("color", None)
                button.setEnabled(False)
                button.setAccessibleName(f"Cor recente {number}, ainda vazia")
                button.setToolTip("Selecione uma cor na paleta para adicioná-la às recentes.")
                button.setStyleSheet(
                    f"QPushButton {{ background: {theme_color('cream')}; "
                    f"color: {theme_color('muted')}; border: 1px solid {theme_color('border')}; "
                    f"border-radius: 5px; padding: 0; "
                    "font-size: 11px; font-weight: 600; }"
                )
                continue
            color = parsed[index]
            value = values[index]
            name = self._color_names.get(value, "")
            reference = material_reference(value)
            description = f"{name} · {reference}" if name else reference
            button.setProperty("color", value)
            button.setEnabled(True)
            button.setAccessibleName(f"Cor recente {number}: {description}")
            button.setToolTip(
                f"<p>{escape(description)}<br>Selecionar com a tecla {number}</p>"
            )
            inactive_border = (
                TRANSPARENT_OUTLINE if is_transparent(value) else theme_color("border")
            )
            border = (
                f"2px solid {theme_color('ink')}"
                if value == active else f"1px solid {inactive_border}"
            )
            button.setStyleSheet(
                f"QPushButton {{ background: {display_color(value)}; color: {_number_color(color)}; "
                f"border: {border}; border-radius: 5px; padding: 0; "
                "font-size: 11px; font-weight: 700; } "
                f"QPushButton:hover {{ border: 2px solid {theme_color('pink')}; }} "
                f"QPushButton:focus {{ border: 2px solid {theme_color('ink')}; }}"
            )

    def refresh_theme(self) -> None:
        self.set_colors(self._last_colors, self._last_active_color)
