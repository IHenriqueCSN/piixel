"""Prepare the Windows executable's icon and metadata from the project sources."""
from __future__ import annotations

import os
from pathlib import Path
import re
import struct
import tomllib


ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def read_version(root: Path) -> str:
    with (Path(root) / "pyproject.toml").open("rb") as stream:
        version = tomllib.load(stream)["project"]["version"]
    if (not isinstance(version, str) or not re.fullmatch(r"(?:0|[1-9][0-9]{0,4})(?:\.(?:0|[1-9][0-9]{0,4})){2}", version)
            or any(int(part) > 65535 for part in version.split("."))):
        raise ValueError("A versão do instalador deve conter três números de 0 a 65535, como 0.1.0.")
    return version


def create_windows_assets(root: Path) -> dict:
    root = Path(root).resolve()
    version = read_version(root)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    # Keep a strong reference throughout rendering, including when no GUI is
    # running (the normal build-script case).
    application = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(root / "piixelverso" / "assets" / "brand" / "symbol.svg"))
    if not renderer.isValid():
        raise ValueError("O símbolo oficial do Piixelverso não pôde ser lido.")
    source = renderer.defaultSize()
    png_images = []
    for size in ICON_SIZES:
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        margin = size / 24
        scale = min((size - 2 * margin) / source.width(), (size - 2 * margin) / source.height())
        width, height = source.width() * scale, source.height() * scale
        painter = QPainter(image)
        renderer.render(painter, QRectF((size - width) / 2, (size - height) / 2, width, height))
        painter.end()
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, "PNG"):
            raise OSError("Não foi possível gerar o ícone do Piixel.")
        png_images.append(bytes(buffer.data()))
        buffer.close()

    directory = root / "build" / "windows"
    directory.mkdir(parents=True, exist_ok=True)
    offset = 6 + 16 * len(ICON_SIZES)
    entries = []
    for size, png in zip(ICON_SIZES, png_images):
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), offset))
        offset += len(png)
    icon = directory / "piixel.ico"
    icon.write_bytes(struct.pack("<HHH", 0, 1, len(entries)) + b"".join(entries) + b"".join(png_images))

    numbers = (*map(int, version.split(".")), 0)
    version_file = directory / "version_info.txt"
    version_file.write_text(f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers!r}, prodvers={numbers!r},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041604B0', [
      StringStruct('CompanyName', 'Piixelverso'),
      StringStruct('FileDescription', 'Piixel - ferramentas do Piixelverso'),
      StringStruct('FileVersion', {version!r}),
      StringStruct('InternalName', 'Piixel'),
      StringStruct('OriginalFilename', 'Piixel.exe'),
      StringStruct('ProductName', 'Piixel'),
      StringStruct('ProductVersion', {version!r})])]),
    VarFileInfo([VarStruct('Translation', [0x0416, 1200])])])
""", encoding="utf-8")
    return {"version": version, "icon": icon, "version_file": version_file}
