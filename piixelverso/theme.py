"""Piixelverso v3 brand colors and accessible desktop surfaces."""
from PySide6.QtGui import QColor, QPalette

INK = "#292343"
PINK = "#ED5598"
WHITE = "#FFFFFF"
BLUE = "#BDE7EE"
PEACH = "#F6A875"
LIGHT_PINK = "#FCA0BB"
YELLOW = "#FFD878"
CREAM = "#FFF8EF"
PALE_BLUE = "#DFF2F4"

# Quiet supporting surfaces keep the artwork's RGB colors easy to judge.
MUTED = "#756C83"
BORDER = "#E2DCE7"
HOVER = "#FDE9F1"
SELECTED = "#FBD5E5"
GRID = "#D9D7E3"
EMPTY_ALT = "#F4FAFB"


def apply_palette(app):
    """Brand the native controls too, including focus and checked states."""
    palette = app.palette()
    for role, color in {
        QPalette.ColorRole.Window: CREAM,
        QPalette.ColorRole.WindowText: INK,
        QPalette.ColorRole.Base: WHITE,
        QPalette.ColorRole.AlternateBase: PALE_BLUE,
        QPalette.ColorRole.Text: INK,
        QPalette.ColorRole.Button: WHITE,
        QPalette.ColorRole.ButtonText: INK,
        QPalette.ColorRole.Highlight: LIGHT_PINK,
        QPalette.ColorRole.HighlightedText: INK,
        QPalette.ColorRole.ToolTipBase: INK,
        QPalette.ColorRole.ToolTipText: WHITE,
        QPalette.ColorRole.Link: INK,
    }.items():
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(MUTED))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(MUTED))
    app.setPalette(palette)


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
QComboBox {{ border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 10px; background: {WHITE}; }}
QComboBox:hover {{ border-color: {PINK}; }}
QLineEdit, QSpinBox {{ border: 1px solid {BORDER}; border-radius: 6px; padding: 8px; background: {WHITE}; selection-background-color: {LIGHT_PINK}; selection-color: {INK}; }}
QLineEdit:focus, QSpinBox:focus {{ border-color: {PINK}; }}
QDialog {{ background: {CREAM}; }}
QToolTip {{ background: {INK}; color: {WHITE}; padding: 6px; border: 0; }}
"""
