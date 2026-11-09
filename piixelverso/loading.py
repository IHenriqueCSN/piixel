"""Page loading feedback that survives blocking GUI imports and constructors."""
from __future__ import annotations

from contextlib import contextmanager

from PySide6.QtCore import QEvent, QObject, QPoint, QTimer
from PySide6.QtWidgets import QApplication, QWidget

from .startup import _SplashProcess
from .ui.loading import LoadingOverlay


_INPUT_EVENTS = {
    QEvent.Type.ShortcutOverride, QEvent.Type.Shortcut,
    QEvent.Type.KeyPress, QEvent.Type.KeyRelease,
    QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
    QEvent.Type.MouseButtonDblClick, QEvent.Type.Wheel,
}


class PageLoadingController(QObject):
    """Paint immediately, then animate the same card in an independent helper.

    Widgets stay on the GUI thread. The helper has its own Qt event loop, so an
    import or page constructor cannot freeze the visible wheel. EOF/reaping is
    shared with the startup splash; finishing never waits for a child process.
    """

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.overlay = LoadingOverlay(window.centralWidget())
        self._active = False
        self._depth = 0
        self._generation = 0
        self._waiting_for_paint = False
        self._target = None
        self._helper = None
        self._filter_installed = False
        window.destroyed.connect(lambda *_args: self.close())

    @property
    def active(self) -> bool:
        return self._active

    @contextmanager
    def operation(self, message: str = "Carregando…", *, enabled: bool = True):
        if not enabled or not self.window.isVisible():
            if self._depth == 0 and self._active:
                self.close()
            yield
            return
        if self._depth == 0:
            self._begin(message)
        self._depth += 1
        try:
            yield
        except BaseException:
            self.close()
            raise
        finally:
            self._depth -= 1
            if self._depth == 0 and self._active:
                self._finish_after_paint()

    def _begin(self, message: str):
        self.close()
        self._generation += 1
        self._active = True
        QApplication.instance().installEventFilter(self)
        self._filter_installed = True
        self.overlay.show_loading(message)
        # Offscreen/minimal have no native surface to overlay. Widget feedback
        # remains testable there; the helper is also tested directly via a pipe.
        if QApplication.platformName().lower() in ("offscreen", "minimal"):
            return
        position = self.overlay.card.mapToGlobal(QPoint(0, 0))
        payload = {
            "message": message, "x": position.x(), "y": position.y(),
            "width": self.overlay.card.width(), "height": self.overlay.card.height(),
            "parent_id": int(self.window.winId()),
        }
        self._helper = _SplashProcess.launch(page_loading=payload)

    def _finish_after_paint(self):
        pages = self.window.centralWidget()
        self._target = pages.currentWidget() if hasattr(pages, "currentWidget") else pages
        if self._target is None or not self._target.isVisible():
            generation = self._generation
            QTimer.singleShot(0, lambda: self._close_generation(generation))
            return
        self._waiting_for_paint = True
        self._target.update()
        # Complete a real paint now, without pumping queued input. The zero-delay
        # completion is then already queued when normal event processing resumes,
        # so a ready page does not lose its first click behind the veil.
        self._target.repaint()

    def _close_generation(self, generation):
        if generation == self._generation:
            self.close()

    def close(self):
        self._generation += 1
        self._active = False
        self._waiting_for_paint = False
        self._target = None
        if self._filter_installed:
            self._filter_installed = False
            try:
                QApplication.instance().removeEventFilter(self)
            except RuntimeError:
                pass
        helper, self._helper = self._helper, None
        if helper is not None:
            helper.close()
        try:
            self.overlay.hide_loading()
        except RuntimeError:
            # QObject destruction can run after the overlay's native widget.
            pass

    def eventFilter(self, watched, event):
        if not self._active:
            return False
        kind = event.type()
        if watched is self.window and kind in (QEvent.Type.Hide, QEvent.Type.Close):
            self.close()
            return False
        if isinstance(watched, QWidget):
            if kind == QEvent.Type.Show and watched.isWindow() and watched.isModal():
                # Error/confirmation dialogs must remain visible and interactive.
                self.close()
                return False
            if watched.window() is self.window and kind in _INPUT_EVENTS:
                event.accept()
                return True
            if self._waiting_for_paint and kind == QEvent.Type.Paint:
                target = self._target
                if target is not None and (watched is target or target.isAncestorOf(watched)):
                    # Exclude the veil: only the destination's actual paint is
                    # evidence of readiness. Close after that paint completes.
                    if watched is not self.overlay and not self.overlay.isAncestorOf(watched):
                        self._waiting_for_paint = False
                        generation = self._generation
                        QTimer.singleShot(0, lambda: self._close_generation(generation))
        return False
