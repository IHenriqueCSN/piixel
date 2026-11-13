"""Small loading surfaces shared by page transitions and asynchronous actions."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QWindow
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

from ..theme import (
    BLUE, BORDER, CREAM, INK, PINK, apply_themed_stylesheet, theme_color,
)


class Spinner(QWidget):
    """A lightweight activity wheel, driven by the owning Qt event loop."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("loadingSpinner")
        self.setAccessibleName("Carregando")
        self.setFixedSize(40, 40)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(32)
        self._timer.timeout.connect(self._advance)

    @property
    def is_spinning(self) -> bool:
        return self._timer.isActive()

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _advance(self) -> None:
        self._angle = (self._angle + 12) % 360
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring = QRectF(self.rect()).adjusted(5, 5, -5, -5)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(theme_color("blue")), 4, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        painter.drawEllipse(ring)
        painter.setPen(QPen(QColor(theme_color("pink")), 4, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        painter.drawArc(ring, -self._angle * 16, 100 * 16)

    def hideEvent(self, event) -> None:
        self.stop()
        super().hideEvent(event)


class _LoadingCard(QFrame):
    """The same compact card is used inside the app and in the helper process."""

    def __init__(self, parent=None, flags=Qt.WindowType.Widget):
        super().__init__(parent, flags)
        self.setObjectName("loadingCard")
        self.setFixedSize(360, 132)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        apply_themed_stylesheet(self, f"""
            QFrame#loadingCard {{
                background: {CREAM}; border: 1px solid {BORDER}; border-radius: 12px;
            }}
            QLabel#loadingMessage {{
                background: transparent; color: {INK}; border: 0;
                font-family: 'DejaVu Sans', sans-serif;
                font-size: 14px; font-weight: 600;
            }}
        """)
        row = QHBoxLayout(self)
        row.setContentsMargins(24, 24, 24, 24)
        row.setSpacing(20)
        self.spinner = Spinner(self)
        row.addWidget(self.spinner)
        self.message_label = QLabel("Carregando…", self)
        self.message_label.setObjectName("loadingMessage")
        self.message_label.setTextFormat(Qt.TextFormat.PlainText)
        self.message_label.setWordWrap(True)
        self.message_label.setSizePolicy(QSizePolicy.Policy.Ignored,
                                         QSizePolicy.Policy.Preferred)
        row.addWidget(self.message_label, 1)

    def showEvent(self, event) -> None:
        self.spinner.start()
        super().showEvent(event)


class LoadingOverlay(QWidget):
    """An immediate visual/input veil over a single parent widget.

    The spinner follows this GUI's event loop. Page factories that block that
    loop can show the same card in a separate helper via create_loading_popup.
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("loadingOverlay")
        self.setAccessibleName("Carregamento em andamento")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.card = _LoadingCard(self)
        layout.addWidget(self.card, 0, Qt.AlignmentFlag.AlignCenter)
        self.spinner = self.card.spinner
        self.message_label = self.card.message_label
        self.setGeometry(parent.rect())
        parent.installEventFilter(self)
        # Qt can synchronously deliver hideEvent here, even while a stacked
        # parent is still being built, so child fields must already exist.
        self.hide()

    def show_loading(self, message: str = "Carregando…") -> None:
        self.message_label.setText(str(message))
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.layout().activate()
        self.spinner.start()
        # Paint synchronously without pumping input or causing nested navigation.
        self.repaint()
        self.card.repaint()

    def hide_loading(self) -> None:
        self.spinner.stop()
        self.hide()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.parentWidget():
            if event.type() == QEvent.Type.Resize:
                self.setGeometry(watched.rect())
            elif event.type() in (QEvent.Type.ChildAdded, QEvent.Type.LayoutRequest):
                if self.isVisible():
                    self.raise_()
        return super().eventFilter(watched, event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(41, 35, 67, 92))

    def mousePressEvent(self, event) -> None:
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        event.accept()

    def wheelEvent(self, event) -> None:
        event.accept()

    def hideEvent(self, event) -> None:
        self.spinner.stop()
        super().hideEvent(event)


def create_loading_popup(payload: dict) -> QWidget:
    """Create the helper's card at the overlay card's global logical position.

    Foreign transient parenting is supported on Windows and X11. Wayland and
    offscreen platforms keep the positioning hints without unsupported calls.
    """
    flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
             | Qt.WindowType.WindowDoesNotAcceptFocus
             | Qt.WindowType.WindowTransparentForInput)
    window = _LoadingCard(None, flags)
    window.card = window
    window.setObjectName("loadingCard")
    window.setWindowTitle("Piixel — Carregando…")
    window.setAccessibleName("Carregamento do módulo")
    window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    window.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    window.message_label.setText(str(payload.get("message", "Carregando…")))
    window.setGeometry(int(payload.get("x", 0)), int(payload.get("y", 0)),
                       int(payload.get("width", 360)), int(payload.get("height", 132)))
    platform = QGuiApplication.platformName().lower()
    if platform in ("windows", "xcb"):
        try:
            parent_id = int(payload.get("parent_id", 0))
            if parent_id > 0:
                foreign_parent = QWindow.fromWinId(parent_id)
                if foreign_parent is not None:
                    window.winId()
                    handle = window.windowHandle()
                    if handle is not None:
                        handle.setTransientParent(foreign_parent)
                        window._foreign_parent_window = foreign_parent
        except (RuntimeError, TypeError, ValueError, OverflowError):
            # Feedback is optional; an unsupported native handle must not fail
            # the actual page transition or leave an exception on screen.
            pass
    return window
