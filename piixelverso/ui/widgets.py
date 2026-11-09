"""Small presentation helpers shared by editor views and dialogs."""
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QLabel, QPushButton

from .icons import icon
from ..theme import INK


def label(text, name=None):
    result = QLabel(text)
    if name:
        result.setObjectName(name)
    return result


def button(text, callback, name=None, symbol=None):
    result = QPushButton(text)
    if name:
        result.setObjectName(name)
    if symbol:
        result.setIcon(icon(symbol, INK))
        result.setIconSize(QSize(18, 18))
    result.clicked.connect(callback)
    return result

