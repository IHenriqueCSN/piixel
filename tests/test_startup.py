"""Keep startup feedback light and close it reliably on readiness or failure."""
from __future__ import annotations

import io
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication, QWidget


ROOT = Path(__file__).resolve().parents[1]


class StartupProcessTests(unittest.TestCase):
    def probe(self, code: str):
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", PIIXEL_DATA_DIR=directory)
            result = subprocess.run(
                [sys.executable, "-c", code], cwd=ROOT, env=environment,
                capture_output=True, text=True, input="", timeout=15,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_importing_startup_and_splash_does_not_load_qt_or_the_editor(self):
        self.probe("""
import sys
import piixelverso.startup
import piixelverso.splash
assert not any(name == 'PySide6' or name.startswith('PySide6.') for name in sys.modules)
assert 'piixelverso.app' not in sys.modules
assert 'piixelverso.atelier' not in sys.modules
""")

    def test_help_does_not_launch_a_window_or_import_qt(self):
        result = self.probe("""
import sys
from piixelverso.startup import main
try:
    main(['--help'])
except SystemExit as error:
    assert error.code == 0
else:
    raise AssertionError('--help deve encerrar sem iniciar o aplicativo')
assert 'PySide6' not in sys.modules
assert 'piixelverso.app' not in sys.modules
""")
        self.assertIn("Piixel", result.stdout)

    def test_helper_exits_if_the_parent_pipe_is_already_closed(self):
        self.probe("""
from piixelverso.splash import run_splash
raise SystemExit(run_splash())
""")

    def test_visible_helper_exits_when_its_parent_closes_the_pipe(self):
        code = """
import piixelverso.splash as splash
original = splash.create_splash
def observed_splash():
    from PySide6.QtCore import QEvent, QObject
    window = original()
    class FirstPaint(QObject):
        reported = False
        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.Paint and not self.reported:
                self.reported = True
                print('PIIXEL_PAINTED', flush=True)
            return False
    watcher = FirstPaint(window)
    window.installEventFilter(watcher)
    window._test_paint_watcher = watcher
    return window
splash.create_splash = observed_splash
raise SystemExit(splash.run_splash())
"""
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", PIIXEL_DATA_DIR=directory)
            process = subprocess.Popen(
                [sys.executable, "-c", code], cwd=ROOT, env=environment,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
            )
            output = queue.Queue()
            reader = threading.Thread(
                target=lambda: output.put(process.stdout.readline()), daemon=True,
            )
            reader.start()
            try:
                self.assertEqual(output.get(timeout=15).strip(), "PIIXEL_PAINTED")
                self.assertIsNone(process.poll(), "A tela deve continuar aberta durante o carregamento")
                process.stdin.close()
                process.stdin = None
                _stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, stderr)
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=10)


class StartupControllerTests(unittest.TestCase):
    def test_parent_starts_feedback_before_the_app_and_propagates_its_exit_code(self):
        from piixelverso import startup

        calls = []
        handle = SimpleNamespace(close=lambda: calls.append("close"))

        def launch():
            calls.append("launch")
            return handle

        def run_app(argv, *, startup):
            calls.append("app")
            self.assertIs(startup, handle)
            self.assertEqual(argv, ["design com espaços.pii"])
            self.assertEqual(calls, ["launch", "app"])
            return 7

        with patch.object(startup._SplashProcess, "launch", side_effect=launch), patch.dict(
            sys.modules, {"piixelverso.app": SimpleNamespace(main=run_app)}
        ):
            self.assertEqual(startup.main(["design com espaços.pii"]), 7)
        self.assertEqual(calls, ["launch", "app", "close"])

    def test_app_initialization_failure_closes_feedback(self):
        from piixelverso import startup

        calls = []
        handle = SimpleNamespace(close=lambda: calls.append("close"))

        def fail(argv, *, startup):
            self.assertIs(startup, handle)
            raise RuntimeError("Falha simulada ao iniciar")

        with patch.object(startup._SplashProcess, "launch", return_value=handle), patch.dict(
            sys.modules, {"piixelverso.app": SimpleNamespace(main=fail)}
        ):
            with self.assertRaisesRegex(RuntimeError, "Falha simulada"):
                startup.main([])
        self.assertEqual(calls, ["close"])

    def test_unavailable_helper_does_not_prevent_the_main_app_from_starting(self):
        from piixelverso import startup

        def run_app(argv, *, startup):
            self.assertTrue(startup.closed)
            self.assertIsNone(startup.process)
            return 0

        with patch("piixelverso.startup.subprocess.Popen", side_effect=OSError("Sem helper")), patch.dict(
            sys.modules, {"piixelverso.app": SimpleNamespace(main=run_app)}
        ):
            self.assertEqual(startup.main([]), 0)


class SplashWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")

    def test_splash_has_the_mascot_activity_bar_and_requested_text(self):
        from piixelverso.splash import create_splash

        window = create_splash()
        try:
            self.assertEqual(window.loading_label.text(), "Carregando…")
            self.assertEqual(window.credit_label.text(), "Desenvolvido por Piixelverso")
            self.assertIn("Pii", window.mascot_label.accessibleName())
            self.assertFalse(window.mascot_label.pixmap().isNull())
            self.assertEqual((window.progress.minimum(), window.progress.maximum()), (0, 0))
            self.assertLessEqual(window.width(), 480)
            self.assertLessEqual(window.height(), 340)
            self.assertTrue(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
            window.show()
            self.app.processEvents()
            self.assertFalse(window.grab().isNull())
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_main_window_first_paint_closes_the_pipe_without_waiting_for_a_dwell_time(self):
        from piixelverso.startup import _SplashProcess

        reaped = threading.Event()

        def wait(timeout=None):
            reaped.set()
            return 0

        stream = io.BytesIO()
        handle = _SplashProcess(SimpleNamespace(stdin=stream, wait=wait))
        window = QWidget()
        try:
            handle.finish(window)
            QApplication.sendEvent(window, QEvent(QEvent.Type.Show))
            self.app.processEvents()
            self.assertFalse(handle.closed, "Uma notificação de show ainda não é uma pintura")
            self.assertFalse(stream.closed)

            window.show()
            for _ in range(3):
                self.app.processEvents()
            self.assertTrue(handle.closed)
            self.assertTrue(stream.closed)
            self.assertTrue(reaped.wait(timeout=2))
            handle.close()
            self.assertTrue(handle.closed, "Fechar novamente deve ser inofensivo")
        finally:
            handle.close()
            window.close()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
