"""Compact numbered color slots; ordering belongs to the editor coordinator."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..theme import BORDER, CREAM, INK, MUTED, PINK


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
        heading.setStyleSheet(f"color: {MUTED}; font-size: 10px; font-weight: 700;")
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
        parsed = [QColor(value) for value in colors[:9]]
        if any(not color.isValid() for color in parsed):
            raise ValueError("Cor recente inválida.")
        active = active_color.upper()
        for index, button in enumerate(self.buttons):
            number = index + 1
            if index >= len(parsed):
                button.setProperty("color", None)
                button.setEnabled(False)
                button.setAccessibleName(f"Cor recente {number}, ainda vazia")
                button.setToolTip("Selecione uma cor na paleta para adicioná-la às recentes.")
                button.setStyleSheet(
                    f"QPushButton {{ background: {CREAM}; color: {MUTED}; "
                    f"border: 1px solid {BORDER}; border-radius: 5px; padding: 0; "
                    "font-size: 11px; font-weight: 600; }"
                )
                continue
            color = parsed[index]
            value = color.name(QColor.NameFormat.HexRgb).upper()
            name = self._color_names.get(value, "")
            description = f"{name} · {value}" if name else value
            button.setProperty("color", value)
            button.setEnabled(True)
            button.setAccessibleName(f"Cor recente {number}: {description}")
            button.setToolTip(
                f"<p>{escape(description)}<br>Selecionar com a tecla {number}</p>"
            )
            border = f"2px solid {INK}" if value == active else f"1px solid {BORDER}"
            button.setStyleSheet(
                f"QPushButton {{ background: {value}; color: {_number_color(color)}; "
                f"border: {border}; border-radius: 5px; padding: 0; "
                "font-size: 11px; font-weight: 700; } "
                f"QPushButton:hover {{ border: 2px solid {PINK}; }} "
                f"QPushButton:focus {{ border: 2px solid {INK}; }}"
            )
