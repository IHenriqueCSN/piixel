"""Start visual feedback before importing the editor or its Qt dependencies."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import threading
from contextlib import contextmanager


_SPLASH_ARGUMENT = "--piixel-startup-splash"
_PAGE_LOADING_ARGUMENT = "--piixel-page-loading"
_INSTALLER_MUTEX = "Piixel.Piixelverso.Desktop"


@contextmanager
def _installer_mutex():
    """Let the per-user Windows installer ask to close a running application.

    This does not impose a single-instance policy. The native handle simply
    remains open while this process runs; helper processes do not acquire it.
    """
    kernel = None
    handle = None
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            kernel.CreateMutexW.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle.restype = wintypes.BOOL
            handle = kernel.CreateMutexW(None, False, _INSTALLER_MUTEX)
        except (OSError, AttributeError):
            kernel = None
    try:
        yield
    finally:
        if kernel is not None and handle:
            try:
                kernel.CloseHandle(handle)
            except OSError:
                pass


class _SplashProcess:
    """A separate Qt event loop keeps the activity bar moving during startup."""

    def __init__(self, process: subprocess.Popen | None):
        self.process = process
        self._closed = process is None
        self._lock = threading.Lock()
        self._watcher = None

    @property
    def closed(self) -> bool:
        return self._closed

    @classmethod
    def launch(cls, *, page_loading: dict | None = None) -> _SplashProcess:
        env = os.environ.copy()
        arguments = [_SPLASH_ARGUMENT]
        if page_loading is not None:
            import json
            arguments = [_PAGE_LOADING_ARGUMENT, json.dumps(page_loading, ensure_ascii=False)]
        if getattr(sys, "frozen", False):
            command = [sys.executable, *arguments]
        else:
            command = [sys.executable, "-m", "piixelverso.startup", *arguments]
            # A source entry point can be opened from outside the project folder.
            package_root = str(Path(__file__).resolve().parent.parent)
            env["PYTHONPATH"] = os.pathsep.join(
                [package_root] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
            )
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except OSError:
            # Optional feedback must never prevent the actual program from opening.
            return cls(None)
        return cls(process)

    def finish(self, window) -> None:
        """Dismiss after the main window's first paint, without a minimum dwell."""
        if self._closed:
            return
        from PySide6.QtCore import QEvent, QObject, QTimer

        owner = self

        class FirstPaint(QObject):
            def eventFilter(self, watched, event):
                if event.type() == QEvent.Type.Paint:
                    watched.removeEventFilter(self)
                    # Paint finishes before the next event-loop turn.
                    QTimer.singleShot(0, owner.close)
                return False

        self._watcher = FirstPaint(window)
        window.installEventFilter(self._watcher)

    def close(self) -> None:
        """EOF closes the helper; process cleanup never blocks the GUI thread."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        process = self.process
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        threading.Thread(target=self._reap, args=(process,), daemon=True).start()

    @staticmethod
    def _reap(process: subprocess.Popen) -> None:
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                process.terminate()
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            except OSError:
                pass


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == [_SPLASH_ARGUMENT]:
        from .splash import run_splash
        return run_splash()
    if arguments and arguments[0] == _PAGE_LOADING_ARGUMENT:
        import json
        if len(arguments) != 2 or len(arguments[1]) > 4096:
            return 2
        try:
            payload = json.loads(arguments[1])
            if not isinstance(payload, dict):
                return 2
        except (ValueError, TypeError):
            return 2
        from .splash import run_splash
        return run_splash(page_loading=payload)

    # --help and argument errors should also work without a graphical session.
    parser = argparse.ArgumentParser(description="Piixel — ferramentas do Piixelverso")
    parser.add_argument("design", nargs="?", help="Arquivo .pii para abrir diretamente no Ateliê")
    parser.parse_args(arguments)
    with _installer_mutex():
        splash = _SplashProcess.launch()
        try:
            from .app import main as run_application
            return run_application(arguments, startup=splash)
        finally:
            splash.close()


if __name__ == "__main__":
    raise SystemExit(main())
