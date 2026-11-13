"""Official brand assets and bundled typography for source and packaged runs."""
from __future__ import annotations

from pathlib import Path
import weakref

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QFontDatabase, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


_ASSET_DIR = Path(__file__).resolve().parent / "assets" / "brand"
_FONT_FILES = ("DejaVuSans-Latin.ttf", "DejaVuSans-Bold-Latin.ttf")
_font_app: weakref.ReferenceType | None = None
_font_ids: tuple[int, ...] = ()


def asset_path(name: str) -> Path:
    """Resolve one bundled brand file without depending on the working folder."""
    path = (_ASSET_DIR / name).resolve()
    if path.parent != _ASSET_DIR.resolve():
        raise ValueError("O recurso deve estar na pasta de identidade visual.")
    if not path.is_file():
        raise FileNotFoundError(f"Recurso da identidade visual não encontrado: {name}")
    return path


def ensure_fonts() -> None:
    """Register the supplied regular and bold fonts once per Qt application."""
    global _font_app, _font_ids
    app = QGuiApplication.instance()
    if app is None:
        raise RuntimeError("Crie a aplicação Qt antes de carregar as fontes do Piixelverso.")
    if _font_app is not None and _font_app() is app:
        return
    loaded = []
    try:
        for filename in _FONT_FILES:
            font_id = QFontDatabase.addApplicationFont(str(asset_path(filename)))
            if font_id < 0:
                raise RuntimeError(f"Não foi possível carregar a fonte da marca: {filename}")
            loaded.append(font_id)
            if "DejaVu Sans" not in QFontDatabase.applicationFontFamilies(font_id):
                raise RuntimeError(f"A fonte da marca não contém a família DejaVu Sans: {filename}")
    except Exception:
        for font_id in loaded:
            QFontDatabase.removeApplicationFont(font_id)
        raise
    _font_ids = tuple(loaded)
    _font_app = weakref.ref(app)


def _render_svg(name: str, width: int, height: int, margin: float = 0,
                foreground: str | None = None) -> QPixmap:
    app = QGuiApplication.instance()
    if app is None:
        raise RuntimeError("Crie a aplicação Qt antes de carregar os símbolos do Piixelverso.")
    if width < 1 or height < 1:
        raise ValueError("A imagem da marca precisa ter dimensões positivas.")
    path = asset_path(name)
    if foreground is None:
        renderer = QSvgRenderer(str(path))
    else:
        source_data = path.read_bytes().replace(b"#292343", foreground.encode("ascii"))
        renderer = QSvgRenderer(QByteArray(source_data))
    if not renderer.isValid():
        raise RuntimeError(f"O SVG da marca não pôde ser carregado: {name}")
    source = renderer.defaultSize()
    available_width, available_height = width - 2 * margin, height - 2 * margin
    scale = min(available_width / source.width(), available_height / source.height())
    rendered_width, rendered_height = source.width() * scale, source.height() * scale
    target = QRectF((width - rendered_width) / 2, (height - rendered_height) / 2,
                    rendered_width, rendered_height)
    screen = app.primaryScreen()
    ratio = max(1.0, screen.devicePixelRatio()) if screen is not None else 1.0
    pixmap = QPixmap(round(width * ratio), round(height * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, target)
    painter.end()
    return pixmap


def svg_pixmap(name: str, width: int, height: int) -> QPixmap:
    """Rasterize an official SVG into a transparent canvas, retaining its ratio."""
    foreground = None
    if name == "wordmark.svg":
        # Imported lazily to keep startup's brand module independent of theme
        # until Qt has created the application.
        from .theme import current_resolved_mode, theme_color
        if current_resolved_mode() == "dark":
            foreground = theme_color("ink")
    return _render_svg(name, width, height, foreground=foreground)


def app_icon() -> QIcon:
    """Provide the pixel mascot at common icon sizes with transparent clearance."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        # The cropped source is 44 modules wide: two modules of space per side.
        icon.addPixmap(_render_svg("symbol.svg", size, size, margin=size / 24))
    return icon
