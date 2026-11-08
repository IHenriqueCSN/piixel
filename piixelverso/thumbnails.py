"""Small file previews rendered from the design data, without changing it."""
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen

from .model import PixelDesign
from .theme import BORDER, EMPTY_ALT, WHITE


def thumbnail_png(design: PixelDesign, width: int = 96, height: int = 72) -> bytes:
    if not (16 <= width <= 256 and 16 <= height <= 256):
        raise ValueError("A miniatura deve ter de 16 a 256 pixels por dimensão.")
    design.validate()
    artwork = QImage(design.width, design.height, QImage.Format.Format_ARGB32)
    for y in range(design.height):
        for x in range(design.width):
            color = design.pixels[y * design.width + x]
            artwork.setPixelColor(x, y, QColor(color or (WHITE if (x + y) % 2 == 0 else EMPTY_ALT)))
    preview = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    preview.fill(QColor(WHITE))
    scaled = artwork.scaled(width - 12, height - 12,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.FastTransformation)
    painter = QPainter(preview)
    painter.drawImage((width - scaled.width()) // 2, (height - scaled.height()) // 2, scaled)
    painter.setPen(QPen(QColor(BORDER), 1))
    painter.drawRect(0, 0, width - 1, height - 1)
    painter.end()
    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly) or not preview.save(buffer, "PNG"):
        raise RuntimeError("Não foi possível criar a miniatura do design.")
    data = bytes(buffer.data())
    buffer.close()
    return data
