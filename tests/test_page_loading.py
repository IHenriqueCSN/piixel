"""Loading feedback stays visible through page work and closes on readiness."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QVBoxLayout

from piixelverso.module_api import ModulePage
from piixelverso.modules import ModuleDefinition
from piixelverso.preferences import PreferencesStore
from piixelverso.ui.loading import Spinner, create_loading_popup


ROOT = Path(__file__).resolve().parents[1]


class ExampleModule(ModulePage):
    def __init__(self, parent=None, preferences=None):
        super().__init__(parent)
        self.preferences = preferences
        self.allow_close = True
        self.setWindowTitle("Piixel — Página de teste")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Página pronta"))
        self.home_button = QPushButton("Início")
        self.home_button.clicked.connect(self.home_requested.emit)
        layout.addWidget(self.home_button)

    def confirm_close(self):
        return self.allow_close


class PageLoadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.preferences = PreferencesStore(Path(self.directory.name) / "preferences.json")
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            for module in window.module_pages.values():
                module.allow_close = True
            window.close()
            window.deleteLater()
        self.drain()
        self.directory.cleanup()

    def drain(self):
        for _ in range(6):
            self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def shell(self, *definitions):
        from piixelverso.app import MainWindow
        definitions = definitions or (
            ModuleDefinition("example", "Exemplo", "Página de teste", "pencil", ExampleModule),
        )
        with patch("piixelverso.app.MODULES", definitions):
            window = MainWindow(preferences=self.preferences)
        self.windows.append(window)
        window.show()
        self.drain()
        return window

    def test_cold_factory_sees_feedback_before_work_and_first_paint_dismisses_it(self):
        observations = []
        window = None

        def factory(**kwargs):
            observations.append((window.loading.active,
                                 window.loading.overlay.isVisible(),
                                 window.loading.overlay.message_label.text()))
            return ExampleModule(**kwargs)

        window = self.shell(ModuleDefinition("example", "Exemplo", "Teste", "pencil", factory))
        page = window.open_module("example")
        self.assertEqual(len(observations), 1)
        self.assertTrue(observations[0][0])
        self.assertTrue(observations[0][1])
        self.assertIn("Exemplo", observations[0][2])
        self.assertIs(window.pages.currentWidget(), page)
        self.assertTrue(window.loading.active, "Mostrar a página ainda não significa que ela foi pintada")
        self.drain()
        self.assertFalse(window.loading.active)
        self.assertFalse(window.loading.overlay.isVisible())
        self.assertFalse(window.loading.overlay.spinner.is_spinning)

    def test_cached_page_is_reused_without_showing_another_loading_surface(self):
        window = self.shell()
        page = window.open_module("example")
        self.drain()
        window.show_home()
        self.drain()
        with patch.object(window.loading.overlay, "show_loading") as show:
            again = window.open_module("example")
        self.assertIs(again, page)
        show.assert_not_called()
        self.assertFalse(window.loading.active)

    def test_rapid_navigation_to_a_cached_page_clears_the_cold_page_indicator(self):
        window = self.shell(
            ModuleDefinition("example", "Exemplo", "Teste", "pencil", ExampleModule),
            ModuleDefinition("other", "Outra página", "Teste", "pencil", ExampleModule),
        )
        first = window.open_module("example")
        self.drain()
        window.show_home()
        self.drain()
        window.open_module("other")
        self.assertTrue(window.loading.active)
        self.assertIs(window.open_module("example"), first)
        self.assertFalse(window.loading.active)
        self.drain()
        self.assertIs(window.pages.currentWidget(), first)
        self.assertFalse(window.loading.overlay.isVisible())

    def test_an_old_first_paint_callback_cannot_close_a_new_loading_operation(self):
        window = self.shell()
        page = window.open_module("example")
        # A synchronous paint queues the first completion, but its callback has
        # not run yet. The next operation must own a different generation.
        page.repaint()
        with window.loading.operation("Carregando outra etapa…"):
            self.drain()
            self.assertTrue(window.loading.active)
            self.assertTrue(window.loading.overlay.isVisible())
        self.drain()
        self.assertFalse(window.loading.active)

    def test_failed_factory_removes_feedback_and_keeps_the_previous_page(self):
        def fail(**_kwargs):
            raise RuntimeError("Falha de construção simulada")

        window = self.shell(
            ModuleDefinition("example", "Exemplo", "Teste", "pencil", ExampleModule),
            ModuleDefinition("broken", "Página indisponível", "Teste", "pencil", fail),
        )
        page = window.open_module("example")
        self.drain()
        with self.assertRaisesRegex(RuntimeError, "simulada"):
            window.open_module("broken")
        self.assertFalse(window.loading.active)
        self.assertFalse(window.loading.overlay.isVisible())
        self.assertIs(window.pages.currentWidget(), page)
        self.assertEqual(window.current_module, "example")
        self.assertNotIn("broken", window.module_pages)

    def test_unknown_page_does_not_start_loading(self):
        window = self.shell()
        with patch.object(window.loading.overlay, "show_loading") as show:
            with self.assertRaises(ValueError):
                window.open_module("unknown")
        show.assert_not_called()
        self.assertFalse(window.loading.active)

    def test_home_refresh_has_feedback_during_file_work(self):
        window = self.shell()
        window.open_module("example")
        self.drain()
        observations = []

        def refresh():
            observations.append(window.loading.overlay.isVisible())

        with patch.object(window, "refresh_recent_files", side_effect=refresh):
            window.show_home()
        self.assertEqual(observations, [True])
        self.drain()
        self.assertFalse(window.loading.active)
        self.assertIsNone(window.current_module)

    def test_file_route_removes_cold_page_feedback_before_document_dialogs(self):
        seen = []
        window = None

        class DocumentModule(ExampleModule):
            def load_path(self, _path):
                seen.append(window.loading.active)
                return False

        window = self.shell(ModuleDefinition("atelier", "Ateliê", "Teste", "pencil", DocumentModule))
        self.assertFalse(window.open_design_path("arquivo.pii"))
        self.assertEqual(seen, [False])
        self.assertFalse(window.loading.active)
        self.assertIsNone(window.current_module)

    def test_nested_work_keeps_one_indicator_and_an_error_cleans_it(self):
        window = self.shell()
        overlay = window.loading.overlay
        with patch.object(overlay, "show_loading", wraps=overlay.show_loading) as show:
            with self.assertRaisesRegex(ValueError, "teste"):
                with window.loading.operation("Preparando página…"):
                    self.assertTrue(window.loading.active)
                    with window.loading.operation("Carregando detalhe…"):
                        self.assertTrue(window.loading.active)
                        raise ValueError("erro de teste")
        self.assertEqual(show.call_count, 1)
        self.assertFalse(window.loading.active)
        self.assertFalse(overlay.isVisible())

    def test_modal_dialog_is_never_covered_by_loading_feedback(self):
        window = self.shell()
        dialog = QDialog(window)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        try:
            with window.loading.operation("Preparando página…"):
                self.assertTrue(window.loading.active)
                dialog.show()
                self.drain()
                self.assertFalse(window.loading.active)
                self.assertFalse(window.loading.overlay.isVisible())
        finally:
            dialog.close()
            dialog.deleteLater()
            self.drain()

    def test_close_clears_feedback_even_when_an_unsaved_module_vetoes_closing(self):
        window = self.shell()
        page = window.open_module("example")
        self.drain()
        page.allow_close = False
        with window.loading.operation("Carregando…"):
            self.assertTrue(window.loading.active)
            self.assertFalse(window.close())
            self.assertFalse(window.loading.active)
        self.assertTrue(window.isVisible())

    def test_popup_is_compact_literal_and_does_not_steal_focus_or_become_topmost(self):
        # A Tool popup belongs to an already running application. Keep a normal
        # owner window alive, as in production, instead of inheriting a pending
        # quit from the preceding test's last normal-window closure.
        window = self.shell()
        window.activateWindow()
        focus = window.home_page.module_buttons["example"]
        focus.setFocus()
        self.drain()
        self.assertIs(self.app.focusWidget(), focus)
        popup = create_loading_popup({"x": 100, "y": 80, "width": 360, "height": 132,
                                      "message": "<b>Carregando…</b>", "parent_id": int(window.winId())})
        try:
            self.assertEqual(popup.pos(), QPoint(100, 80))
            self.assertEqual((popup.width(), popup.height()), (360, 132))
            self.assertEqual(popup.message_label.text(), "<b>Carregando…</b>")
            self.assertEqual(popup.message_label.textFormat(), Qt.TextFormat.PlainText)
            self.assertTrue(popup.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))
            self.assertTrue(popup.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus)
            self.assertFalse(popup.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
            popup.show()
            self.drain()
            first = popup.spinner._angle
            QTest.qWait(90)
            self.assertTrue(popup.spinner.is_spinning)
            self.assertNotEqual(popup.spinner._angle, first)
        finally:
            popup.close()
            popup.deleteLater()
            self.drain()


class PageLoadingProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_helper_animation_continues_while_parent_gui_does_not_process_events(self):
        code = r'''
import piixelverso.ui.loading as loading
from piixelverso.splash import run_splash
original = loading.Spinner.paintEvent
def observed_paint(self, event):
    original(self, event)
    print("FRAME " + str(self._angle), flush=True)
loading.Spinner.paintEvent = observed_paint
raise SystemExit(run_splash(page_loading={"x": 0, "y": 0, "width": 360,
    "height": 132, "message": "Carregando teste…", "parent_id": 0}))
'''
        parent_window = QDialog()
        parent_window.resize(200, 100)
        parent_spinner = Spinner(parent_window)
        parent_window.show()
        parent_spinner.start()
        self.app.processEvents()
        environment = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        process = subprocess.Popen(
            [sys.executable, "-c", code], cwd=ROOT, env=environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
        )
        frames = queue.Queue()

        def read_frames():
            for line in process.stdout:
                if line.startswith("FRAME "):
                    frames.put(int(line[6:].strip()))

        reader = threading.Thread(target=read_frames, daemon=True)
        reader.start()
        try:
            first = frames.get(timeout=15)
            parent_angle = parent_spinner._angle
            # Intentionally do not pump the parent's Qt event loop. The helper
            # owns another process/event loop and must keep rendering itself.
            time.sleep(0.3)
            available = []
            while not frames.empty():
                available.append(frames.get_nowait())
            self.assertGreaterEqual(len(available), 2)
            self.assertTrue(any(angle != first for angle in available))
            self.assertEqual(parent_spinner._angle, parent_angle,
                             "O event loop do pai deve permanecer intencionalmente bloqueado")
            self.assertIsNone(process.poll())
            process.stdin.close()
            process.stdin = None
            reader.join(timeout=5)
            _stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stderr)
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)
            parent_window.close()
            parent_window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
