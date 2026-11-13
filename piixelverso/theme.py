"""Piixelverso colors and live application appearance management."""
from __future__ import annotations

from dataclasses import dataclass
import weakref

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QWidget


# These public constants remain the light colors used by artwork surfaces.
# PixelCanvas imports them once, so its grid never changes with the app theme.
INK = "#292343"
PINK = "#ED5598"
WHITE = "#FFFFFF"
BLUE = "#BDE7EE"
PEACH = "#F6A875"
LIGHT_PINK = "#FCA0BB"
YELLOW = "#FFD878"
CREAM = "#FFF8EF"
PALE_BLUE = "#DFF2F4"
MUTED = "#756C83"
BORDER = "#E2DCE7"
HOVER = "#FDE9F1"
SELECTED = "#FBD5E5"
GRID = "#D9D7E3"
EMPTY_ALT = "#F4FAFB"

APPEARANCE_MODES = ("system", "light", "dark")


@dataclass(frozen=True)
class ThemeColors:
    ink: str
    pink: str
    white: str
    blue: str
    light_pink: str
    cream: str
    pale_blue: str
    muted: str
    border: str
    hover: str
    selected: str


LIGHT_COLORS = ThemeColors(
    ink=INK, pink=PINK, white=WHITE, blue=BLUE, light_pink=LIGHT_PINK,
    cream=CREAM, pale_blue=PALE_BLUE, muted=MUTED, border=BORDER,
    hover=HOVER, selected=SELECTED,
)

# Warm off-black surfaces and a quieter rose preserve the brand. None of these
# values are used to render the artboard itself.
DARK_COLORS = ThemeColors(
    ink="#F5EDF3",
    pink="#D86C9B",
    white="#242128",
    blue="#31474C",
    light_pink="#B96588",
    cream="#18161B",
    pale_blue="#222D31",
    muted="#B8ADB9",
    border="#454049",
    hover="#33252E",
    selected="#49303D",
)


def validate_appearance_mode(mode: object) -> str:
    if not isinstance(mode, str) or mode not in APPEARANCE_MODES:
        raise ValueError("A aparência deve ser sistema, clara ou escura.")
    return mode


def colors_for(resolved_mode: str) -> ThemeColors:
    return DARK_COLORS if resolved_mode == "dark" else LIGHT_COLORS


_LIGHT_TO_FIELD = {
    INK: "ink", PINK: "pink", WHITE: "white", BLUE: "blue",
    LIGHT_PINK: "light_pink", CREAM: "cream", PALE_BLUE: "pale_blue",
    MUTED: "muted", BORDER: "border", HOVER: "hover", SELECTED: "selected",
}


def themed_stylesheet(light_style: str, resolved_mode: str | None = None) -> str:
    """Translate a static light stylesheet without touching artwork colors."""
    mode = resolved_mode or current_resolved_mode()
    if mode != "dark":
        return light_style
    result = light_style
    for light, field in _LIGHT_TO_FIELD.items():
        result = result.replace(light, getattr(DARK_COLORS, field))
    return result


def current_resolved_mode() -> str:
    controller = theme_controller()
    return controller.resolved_mode if controller is not None else "light"


def theme_color(name: str) -> str:
    return getattr(colors_for(current_resolved_mode()), name)


def apply_themed_stylesheet(widget: QWidget, light_style: str) -> None:
    """Register a component stylesheet so live theme changes can reapply it."""
    widget.setProperty("_piixelLightStyle", light_style)
    widget.setStyleSheet(themed_stylesheet(light_style))


def _apply_palette(app: QApplication, resolved_mode: str) -> None:
    colors = colors_for(resolved_mode)
    palette = app.style().standardPalette()
    for role, color in {
        QPalette.ColorRole.Window: colors.cream,
        QPalette.ColorRole.WindowText: colors.ink,
        QPalette.ColorRole.Base: colors.white,
        QPalette.ColorRole.AlternateBase: colors.pale_blue,
        QPalette.ColorRole.Text: colors.ink,
        QPalette.ColorRole.Button: colors.white,
        QPalette.ColorRole.ButtonText: colors.ink,
        QPalette.ColorRole.Highlight: colors.light_pink,
        QPalette.ColorRole.HighlightedText: colors.ink,
        QPalette.ColorRole.ToolTipBase: colors.ink,
        QPalette.ColorRole.ToolTipText: colors.white,
        QPalette.ColorRole.Link: colors.pink,
        QPalette.ColorRole.PlaceholderText: colors.muted,
    }.items():
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(colors.muted))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(colors.muted))
    app.setPalette(palette)


def apply_palette(app, resolved_mode: str | None = None):
    """Compatibility helper for standalone editor tests and older callers."""
    _apply_palette(app, resolved_mode or current_resolved_mode())


APP_STYLE = f"""
QWidget {{ color: {INK}; font-family: 'DejaVu Sans', sans-serif; font-size: 12px; }}
QMainWindow, #root {{ background: {CREAM}; }}
#topbar {{ background: {CREAM}; border-bottom: 1px solid {BORDER}; }}
#edition {{ color: {MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 2px; }}
#localBadge {{ color: {INK}; background: {PALE_BLUE}; border-radius: 12px; padding: 6px 12px; font-size: 11px; }}
#projectBar {{ background: {CREAM}; }}
#eyebrow {{ color: {MUTED}; font-size: 9px; font-weight: 700; letter-spacing: 2px; }}
#designName {{ background: transparent; border: 0; border-radius: 4px; padding: 1px 0; font-size: 23px; font-weight: 700; }}
#designName:focus {{ background: {WHITE}; border-bottom: 1px solid {PINK}; }}
#card, #editorCard {{ background: {WHITE}; border: 1px solid {BORDER}; border-radius: 12px; }}
#sectionTitle {{ font-weight: 700; font-size: 13px; }}
#muted {{ color: {MUTED}; font-size: 11px; }}
#tiny {{ color: {MUTED}; font-size: 10px; }}
#canvasStage {{ background: {PALE_BLUE}; border: 0; }}
#editorHeading {{ font-weight: 700; font-size: 12px; }}
#canvasFooter {{ background: {WHITE}; border-top: 1px solid {BORDER}; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; }}
QPushButton {{ background: {WHITE}; border: 1px solid {BORDER}; border-radius: 7px; padding: 9px 13px; font-weight: 600; }}
QPushButton:hover {{ background: {HOVER}; border-color: {PINK}; }}
QPushButton:pressed {{ background: {SELECTED}; }}
QPushButton:disabled {{ color: {MUTED}; border-color: {BORDER}; }}
QPushButton#primary {{ color: {INK}; background: {LIGHT_PINK}; border-color: {PINK}; }}
QPushButton#primary:hover {{ background: {SELECTED}; }}
QPushButton#swatch {{ padding: 0; border-radius: 5px; }}
#activeColor {{ border: 1px solid {BORDER}; border-radius: 8px; background: {CREAM}; }}
#paletteBody {{ background: {WHITE}; }}
#bigNumber {{ font-size: 44px; font-weight: 700; letter-spacing: -2px; }}
#statBox {{ background: {PALE_BLUE}; border-radius: 10px; }}
#hint {{ color: {MUTED}; background: {CREAM}; border-radius: 8px; padding: 12px; font-size: 11px; }}
#status {{ color: {MUTED}; font-size: 10px; }}
QScrollArea {{ border: 0; background: transparent; }}
QScrollBar:vertical {{ background: {CREAM}; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {LIGHT_PINK}; border-radius: 3px; min-height: 25px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QSlider::groove:horizontal {{ background: {BLUE}; height: 4px; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {PINK}; width: 12px; margin: -4px 0; border-radius: 6px; }}
QCheckBox {{ color: {INK}; font-size: 11px; spacing: 6px; }}
QComboBox {{ color: {INK}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 10px; background: {WHITE}; }}
QComboBox:hover {{ border-color: {PINK}; }}
QComboBox QAbstractItemView {{ color: {INK}; background: {WHITE}; selection-background-color: {SELECTED}; selection-color: {INK}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QListWidget {{ color: {INK}; border: 1px solid {BORDER}; border-radius: 6px; padding: 8px; background: {WHITE}; selection-background-color: {LIGHT_PINK}; selection-color: {INK}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{ border-color: {PINK}; }}
QDialog {{ background: {CREAM}; }}
QToolTip {{ background: {INK}; color: {WHITE}; padding: 6px; border: 0; }}
"""


_controller_ref: weakref.ReferenceType | None = None


def theme_controller() -> "ThemeController | None":
    return _controller_ref() if _controller_ref is not None else None


class ThemeController(QObject):
    """Resolve the preference and update every registered Qt surface."""

    changed = Signal(str, str)

    def __init__(self, app: QApplication, mode: str = "system"):
        super().__init__(app)
        global _controller_ref
        _controller_ref = weakref.ref(self)
        self.app = app
        self.mode = validate_appearance_mode(mode)
        self.resolved_mode = self._resolve_mode(self.mode)
        hints = QGuiApplication.styleHints()
        signal = getattr(hints, "colorSchemeChanged", None)
        if signal is not None:
            signal.connect(self._system_scheme_changed)
        self.apply(emit=False)

    @staticmethod
    def _resolve_mode(mode: str) -> str:
        if mode != "system":
            return mode
        scheme = QGuiApplication.styleHints().colorScheme()
        return "dark" if scheme == Qt.ColorScheme.Dark else "light"

    def set_mode(self, mode: str) -> None:
        mode = validate_appearance_mode(mode)
        resolved = self._resolve_mode(mode)
        if mode == self.mode and resolved == self.resolved_mode:
            return
        self.mode = mode
        self.resolved_mode = resolved
        self.apply()

    def _system_scheme_changed(self, _scheme) -> None:
        if self.mode != "system":
            return
        resolved = self._resolve_mode(self.mode)
        if resolved != self.resolved_mode:
            self.resolved_mode = resolved
            self.apply()

    def apply(self, *, emit: bool = True) -> None:
        _apply_palette(self.app, self.resolved_mode)
        self.app.setStyleSheet(themed_stylesheet(APP_STYLE, self.resolved_mode))
        for widget in self.app.allWidgets():
            source = widget.property("_piixelLightStyle")
            if isinstance(source, str) and source:
                widget.setStyleSheet(themed_stylesheet(source, self.resolved_mode))
            widget.update()
        if emit:
            self.changed.emit(self.mode, self.resolved_mode)


def ensure_theme_controller(app: QApplication, mode: str = "system") -> ThemeController:
    current = theme_controller()
    if current is not None and current.app is app:
        current.set_mode(mode)
        return current
    return ThemeController(app, mode)
