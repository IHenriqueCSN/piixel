"""A small, independent startup window with no editor imports."""
from __future__ import annotations

import os
import sys
import threading


def create_splash():
    """Build the branded window after the caller has created QApplication."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget

    from .brand import svg_pixmap
    from .theme import BLUE, BORDER, CREAM, INK, MUTED, PINK

    window = QWidget(
        None, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint
    )
    window.setObjectName("startupSplash")
    window.setWindowTitle("Piixel — Carregando…")
    window.setAccessibleName("Inicialização do Piixel")
    window.setFixedSize(400, 300)
    window.setStyleSheet(f"""
        QWidget#startupSplash {{ background: {CREAM}; border: 1px solid {BORDER}; }}
        QLabel {{ color: {INK}; background: transparent; border: 0; }}
        QLabel#startupLoading {{ font-size: 16px; font-weight: 600; }}
        QLabel#startupCredit {{ color: {MUTED}; font-size: 11px; }}
        QProgressBar {{ background: {BLUE}; border: 0; border-radius: 4px; }}
        QProgressBar::chunk {{ background: {PINK}; border-radius: 4px; width: 72px; }}
    """)

    layout = QVBoxLayout(window)
    layout.setContentsMargins(32, 22, 32, 22)
    layout.setSpacing(12)
    layout.addStretch(1)

    window.mascot_label = QLabel()
    window.mascot_label.setAccessibleName("Pii, o mascote do Piixelverso")
    window.mascot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window.mascot_label.setPixmap(svg_pixmap("symbol.svg", 144, 124))
    layout.addWidget(window.mascot_label)

    window.loading_label = QLabel("Carregando…")
    window.loading_label.setObjectName("startupLoading")
    window.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(window.loading_label)

    window.progress = QProgressBar()
    window.progress.setAccessibleName("Carregando o Piixel")
    window.progress.setRange(0, 0)
    window.progress.setTextVisible(False)
    window.progress.setFixedHeight(8)
    layout.addWidget(window.progress)

    window.credit_label = QLabel("Desenvolvido por Piixelverso")
    window.credit_label.setObjectName("startupCredit")
    window.credit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(window.credit_label)
    layout.addStretch(1)

    screen = QApplication.primaryScreen()
    if screen is not None:
        window.move(screen.availableGeometry().center() - window.rect().center())
    return window


def _control_stream():
    """Keep the inherited pipe usable in Windows builds without a console."""
    if sys.stdin is not None:
        return getattr(sys.stdin, "buffer", sys.stdin)
    if os.name == "nt":
        import ctypes
        import msvcrt

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetStdHandle.argtypes = [ctypes.c_uint32]
        kernel.GetStdHandle.restype = ctypes.c_void_p
        handle = kernel.GetStdHandle(ctypes.c_uint32(-10))  # STD_INPUT_HANDLE
        if not handle or handle == ctypes.c_void_p(-1).value:
            raise OSError("O canal de inicialização não está disponível.")
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        return os.fdopen(descriptor, "rb", buffering=0)
    return os.fdopen(0, "rb", closefd=False)


def run_splash() -> int:
    """Animate until the main process closes its pipe, including on failure."""
    finished = threading.Event()

    def watch_parent():
        try:
            stream = _control_stream()
            # A raw descriptor avoids holding Python's buffered stdin lock if
            # the user closes the splash while the application is still loading.
            while os.read(stream.fileno(), 4096):
                pass
        except (OSError, ValueError):
            pass
        finally:
            finished.set()

    # Watch for an already-finished parent before importing the GUI toolkit.
    threading.Thread(target=watch_parent, name="PiixelStartupPipe", daemon=True).start()
    if finished.is_set():
        return 0

    app = None
    window = None
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        if finished.is_set():
            return 0
        app = QApplication.instance() or QApplication(sys.argv[:1])
        app.setApplicationName("Piixel")
        app.setOrganizationName("Piixelverso")
        app.setQuitOnLastWindowClosed(True)
        window = create_splash()
        if finished.is_set():
            return 0

        timer = QTimer(window)
        timer.setInterval(12)

        def close_if_ready():
            if finished.is_set():
                window.close()
                app.quit()

        timer.timeout.connect(close_if_ready)
        timer.start()
        window.show()
        return app.exec()
    except Exception:
        if sys.stderr is not None:
            import traceback
            traceback.print_exc()
        return 1
    finally:
        if window is not None:
            window.close()

