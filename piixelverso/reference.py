"""Session-only reference images for the Ateliê."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QImage, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .theme import (
    BORDER, CREAM, INK, MUTED, PALE_BLUE, PINK, WHITE, apply_themed_stylesheet,
)


MAX_REFERENCE_FILE_BYTES = 100 * 1024 * 1024
MAX_REFERENCE_PIXELS = 64 * 1024 * 1024
REFERENCE_FILTER = "Imagens (*.png *.jpg *.jpeg *.webp);;Todos os arquivos (*)"


def validate_reference_image(image: QImage) -> QImage:
    if not isinstance(image, QImage) or image.isNull():
        raise ValueError("A imagem de referência está vazia ou não pôde ser lida.")
    if image.width() < 1 or image.height() < 1:
        raise ValueError("A imagem de referência tem dimensões inválidas.")
    if image.width() * image.height() > MAX_REFERENCE_PIXELS:
        raise ValueError("A imagem de referência é grande demais para ser aberta com segurança.")
    return image.copy()


def load_reference_image(path: str | Path) -> QImage:
    source = Path(path).expanduser()
    try:
        if not source.is_file():
            raise ValueError("O arquivo de referência não foi encontrado.")
        if source.stat().st_size > MAX_REFERENCE_FILE_BYTES:
            raise ValueError("A imagem de referência excede o limite de 100 MB.")
    except OSError as error:
        raise ValueError(f"Não foi possível acessar a imagem de referência: {error}") from error

    reader = QImageReader(str(source))
    reader.setAutoTransform(True)
    size = reader.size()
    if not size.isValid():
        raise ValueError("O formato da imagem de referência não é compatível.")
    if size.width() * size.height() > MAX_REFERENCE_PIXELS:
        raise ValueError("A imagem de referência é grande demais para ser aberta com segurança.")
    image = reader.read()
    if image.isNull():
        detail = reader.errorString().strip()
        raise ValueError(
            "Não foi possível ler a imagem de referência."
            + (f"\n\n{detail}" if detail else "")
        )
    return validate_reference_image(image)


REFERENCE_STYLE = f"""
QFrame#referencePanel {{ background: {WHITE}; border: 1px solid {BORDER}; border-radius: 12px; }}
QLabel#referenceTitle {{ color: {INK}; font-size: 14px; font-weight: 700; }}
QLabel#referenceSource {{ color: {MUTED}; font-size: 10px; }}
QLabel#referenceEmpty {{ color: {MUTED}; background: {PALE_BLUE}; border: 1px dashed {BORDER}; border-radius: 9px; padding: 18px; }}
QGraphicsView#referenceView {{ background: {PALE_BLUE}; border: 1px solid {BORDER}; border-radius: 9px; }}
QPushButton#referenceCompact {{ padding: 5px 8px; font-size: 10px; }}
QPushButton#referenceRemove {{ color: {MUTED}; background: {CREAM}; padding: 5px 8px; font-size: 10px; }}
"""


class ReferenceGraphicsView(QGraphicsView):
    """A compact viewer with wheel zoom and hand panning."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("referenceView")
        self.setAccessibleName("Imagem de referência")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._item: QGraphicsPixmapItem | None = None
        self._fit = True

    @property
    def has_image(self) -> bool:
        return self._item is not None

    def set_image(self, image: QImage) -> None:
        self._scene.clear()
        self._item = self._scene.addPixmap(QPixmap.fromImage(image))
        self._item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._item.setTransformOriginPoint(self._item.boundingRect().center())
        self._scene.setSceneRect(self._item.sceneBoundingRect())
        self.fit_image()

    def clear_image(self) -> None:
        self._scene.clear()
        self._item = None
        self.resetTransform()
        self._fit = True

    def fit_image(self) -> None:
        if self._item is None:
            return
        self._fit = True
        self.resetTransform()
        self.fitInView(self._item.sceneBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def zoom_by(self, factor: float) -> None:
        if self._item is None or factor <= 0:
            return
        current = self.transform().m11()
        target = max(0.05, min(20.0, current * factor))
        self._fit = False
        self.scale(target / current, target / current)

    def rotate_by(self, degrees: int) -> None:
        if self._item is None:
            return
        self._item.setRotation((self._item.rotation() + degrees) % 360)
        self._scene.setSceneRect(self._item.sceneBoundingRect())
        if self._fit:
            self.fit_image()

    def wheelEvent(self, event) -> None:
        if self._item is None:
            super().wheelEvent(event)
            return
        self.zoom_by(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
        event.accept()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit:
            self.fit_image()


class ReferencePanel(QFrame):
    """The right-side reference surface; image bytes remain session-only."""

    open_requested = Signal()
    paste_requested = Signal()
    file_dropped = Signal(str)
    image_dropped = Signal(object)
    removed = Signal()
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("referencePanel")
        self.setAccessibleName("Painel de imagem de referência")
        self.setAcceptDrops(True)
        apply_themed_stylesheet(self, REFERENCE_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel("Imagem de referência")
        title.setObjectName("referenceTitle")
        header.addWidget(title, 1)
        close = QPushButton("← Contagem")
        close.setObjectName("referenceCompact")
        close.setAccessibleName("Voltar à contagem de materiais")
        close.clicked.connect(self.close_requested.emit)
        header.addWidget(close)
        layout.addLayout(header)

        self.source_label = QLabel("Nenhuma imagem carregada")
        self.source_label.setObjectName("referenceSource")
        self.source_label.setTextFormat(Qt.TextFormat.PlainText)
        self.source_label.setWordWrap(True)
        layout.addWidget(self.source_label)

        self.content = QStackedWidget()
        self.empty_label = QLabel(
            "Abra, cole ou arraste uma imagem para cá.\n\n"
            "A referência fica somente nesta sessão e não entra no arquivo .pii."
        )
        self.empty_label.setObjectName("referenceEmpty")
        self.empty_label.setTextFormat(Qt.TextFormat.PlainText)
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content.addWidget(self.empty_label)
        self.viewer = ReferenceGraphicsView()
        self.content.addWidget(self.viewer)
        layout.addWidget(self.content, 1)

        # QGraphicsView and its viewport receive drag events before their parent.
        # Filtering every visible drop surface keeps file-manager drags working
        # consistently on X11, Wayland and Windows.
        for drop_surface in (
            self.empty_label, self.viewer, self.viewer.viewport(),
        ):
            drop_surface.setAcceptDrops(True)
            drop_surface.installEventFilter(self)

        controls = QHBoxLayout()
        controls.setSpacing(5)
        for text, accessible, callback in (
            ("−", "Diminuir referência", lambda: self.viewer.zoom_by(1 / 1.2)),
            ("+", "Aumentar referência", lambda: self.viewer.zoom_by(1.2)),
            ("Ajustar", "Ajustar referência ao painel", self.viewer.fit_image),
            ("↶", "Girar referência à esquerda", lambda: self.viewer.rotate_by(-90)),
            ("↷", "Girar referência à direita", lambda: self.viewer.rotate_by(90)),
        ):
            button = QPushButton(text)
            button.setObjectName("referenceCompact")
            button.setAccessibleName(accessible)
            button.clicked.connect(callback)
            controls.addWidget(button)
        layout.addLayout(controls)

        actions = QHBoxLayout()
        self.open_button = QPushButton("Abrir imagem…")
        self.open_button.setObjectName("primary")
        self.open_button.clicked.connect(self.open_requested.emit)
        actions.addWidget(self.open_button)
        self.paste_button = QPushButton("Colar")
        self.paste_button.setObjectName("referenceCompact")
        self.paste_button.clicked.connect(self.paste_requested.emit)
        actions.addWidget(self.paste_button)
        layout.addLayout(actions)
        self.remove_button = QPushButton("Remover referência")
        self.remove_button.setObjectName("referenceRemove")
        self.remove_button.clicked.connect(self.removed.emit)
        self.remove_button.hide()
        layout.addWidget(self.remove_button)

    @property
    def has_image(self) -> bool:
        return self.viewer.has_image

    def set_image(self, image: QImage, source: str) -> None:
        self.viewer.set_image(image)
        self.source_label.setText(source)
        self.source_label.setToolTip(source)
        self.content.setCurrentIndex(1)
        self.remove_button.show()

    def clear_image(self) -> None:
        self.viewer.clear_image()
        self.source_label.setText("Nenhuma imagem carregada")
        self.source_label.setToolTip("")
        self.content.setCurrentIndex(0)
        self.remove_button.hide()

    @staticmethod
    def _local_image_path(mime) -> str | None:
        for url in mime.urls() if mime.hasUrls() else []:
            if url.isLocalFile():
                return url.toLocalFile()
        return None

    def dragEnterEvent(self, event) -> None:
        if self._accepts_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        if self._handle_drop(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def eventFilter(self, watched, event) -> bool:
        if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
            if self._accepts_mime(event.mimeData()):
                event.acceptProposedAction()
                return True
            return False
        if event.type() == QEvent.Type.Drop:
            if self._handle_drop(event.mimeData()):
                event.acceptProposedAction()
                return True
            return False
        return super().eventFilter(watched, event)

    def _accepts_mime(self, mime) -> bool:
        return bool(mime.hasImage() or self._local_image_path(mime))

    def _handle_drop(self, mime) -> bool:
        path = self._local_image_path(mime)
        if path:
            self.file_dropped.emit(path)
            return True
        if mime.hasImage():
            payload = mime.imageData()
            image = payload.toImage() if isinstance(payload, QPixmap) else payload
            if isinstance(image, QImage) and not image.isNull():
                self.image_dropped.emit(image)
                return True
        return False
