"""User operations show animated feedback without interrupting mailbox polling."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import threading
import time
import unittest

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from piixelverso.piixelfone.page import PiixelfoneModule
from piixelverso.preferences import PreferencesStore
from tests.test_piixelfone_ui import FakeService


class PiixelfoneLoadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.pages = []
        self.releases = []

    def tearDown(self):
        for release in self.releases:
            release.set()
        for page in self.pages:
            page.shutdown()
            page.close()
            page.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def page(self, service):
        preferences = PreferencesStore(Path(self.directory.name) / "preferences.json")
        page = PiixelfoneModule(preferences=preferences, service=service)
        page.resize(1120, 750)
        page.show()
        page.activateWindow()
        self.pages.append(page)
        self.app.processEvents()
        return page

    def delay(self, service, method_name, *, error=None):
        entered, release = threading.Event(), threading.Event()
        self.releases.append(release)
        original = getattr(service, method_name)

        def delayed(*args):
            entered.set()
            release.wait(3)
            if error is not None:
                raise error
            return original(*args)

        setattr(service, method_name, delayed)
        return entered, release

    def wait_idle(self, page):
        deadline = time.monotonic() + 3
        while page._busy and time.monotonic() < deadline:
            QTest.qWait(5)
        self.app.processEvents()
        self.assertFalse(page._busy, "A operação não terminou")

    def unlocked(self):
        service = FakeService(configured=True, existing=True)
        service.value["contacts"] = [{
            "user_id": "friend", "number": "987654", "public_key": "pinned key",
            "state": "accepted", "incoming": False, "fingerprint": "FRIEND CODE",
        }]
        page = self.page(service)
        page.password_input.setText("local password")
        page._unlock()
        self.wait_idle(page)
        page.poll_timer.stop()
        page.contacts_list.setCurrentRow(0)
        self.app.processEvents()
        return page, service

    def test_unlock_shows_moving_spinner_before_the_worker_completes(self):
        service = FakeService(configured=True, existing=True)
        entered, release = self.delay(service, "unlock")
        page = self.page(service)
        page.password_input.setText("local password")
        page._unlock()
        self.assertTrue(entered.wait(1))
        overlay = page.loading_overlay
        self.assertTrue(overlay.isVisible())
        self.assertTrue(overlay.spinner.is_spinning)
        self.assertIn("conversas", overlay.message_label.text())
        self.assertFalse(page.stage.currentWidget().isEnabled())
        self.assertTrue(page.home_button.isEnabled())
        self.assertEqual(page.password_input.text(), "")
        before = overlay.spinner.grab().toImage()
        QTest.qWait(115)
        self.assertNotEqual(before, overlay.spinner.grab().toImage())
        self.assertFalse(page._submit("regenerate_number"))
        self.assertIn("conversas", overlay.message_label.text())
        release.set()
        self.wait_idle(page)
        self.assertFalse(overlay.isVisible())
        self.assertFalse(overlay.spinner.is_spinning)
        self.assertEqual(page.stage.currentIndex(), 2)
        self.assertTrue(page.stage.currentWidget().isEnabled())

    def test_failed_configuration_hides_feedback_and_restores_input(self):
        service = FakeService()
        entered, release = self.delay(service, "configure", error=ValueError("Conexão inválida de teste."))
        page = self.page(service)
        page.key_input.setText("public key")
        page.key_input.setFocus()
        page._configure()
        self.assertTrue(entered.wait(1))
        self.assertTrue(page.loading_overlay.isVisible())
        self.assertFalse(page.key_input.isEnabled())
        release.set()
        self.wait_idle(page)
        self.assertEqual(page.stage.currentIndex(), 0)
        self.assertEqual(page.status_label.text(), "Conexão inválida de teste.")
        self.assertTrue(page.key_input.isEnabled())
        self.assertFalse(page.loading_overlay.isVisible())
        self.assertFalse(page.loading_overlay.spinner.is_spinning)
        self.assertIs(QApplication.focusWidget(), page.key_input)

    def test_periodic_sync_never_covers_the_chat_with_an_overlay(self):
        page, service = self.unlocked()
        entered, release = self.delay(service, "sync")
        page.message_input.setPlainText("Um rascunho em andamento")
        page._poll()
        self.assertTrue(entered.wait(1))
        self.assertFalse(page.loading_overlay.isVisible())
        self.assertFalse(page.loading_overlay.spinner.is_spinning)
        self.assertTrue(page.message_input.isEnabled())
        page.message_input.insertPlainText(".")
        release.set()
        self.wait_idle(page)
        self.assertIn("rascunho", page.message_input.toPlainText())
        self.assertFalse(page.loading_overlay.isVisible())

    def test_send_can_complete_while_the_module_is_hidden_without_leaving_a_veil(self):
        page, service = self.unlocked()
        entered, release = self.delay(service, "send_text")
        page.message_input.setPlainText("Uma mensagem")
        page._send_text()
        self.assertTrue(entered.wait(1))
        self.assertTrue(page.loading_overlay.isVisible())
        self.assertIn("mensagem", page.loading_overlay.message_label.text())
        page.set_active(False)
        page.hide()
        self.app.processEvents()
        self.assertFalse(page.loading_overlay.spinner.is_spinning)
        page.set_active(True)
        page.show()
        self.app.processEvents()
        self.assertTrue(page.loading_overlay.isVisible())
        self.assertTrue(page.loading_overlay.spinner.is_spinning)
        page.set_active(False)
        page.hide()
        release.set()
        self.wait_idle(page)
        page.set_active(True)
        page.show()
        self.app.processEvents()
        self.assertFalse(page.loading_overlay.isVisible())
        self.assertFalse(page.loading_overlay.spinner.is_spinning)
        self.assertTrue(page.stage.currentWidget().isEnabled())
        self.assertEqual(page.message_input.toPlainText(), "")

    def test_shutdown_stops_feedback_even_when_a_user_job_is_still_waiting(self):
        page, service = self.unlocked()
        entered, release = self.delay(service, "regenerate_number")
        page._submit("regenerate_number")
        self.assertTrue(entered.wait(1))
        self.assertTrue(page.loading_overlay.isVisible())
        page.shutdown()
        self.assertFalse(page.loading_overlay.isVisible())
        self.assertFalse(page.loading_overlay.spinner.is_spinning)
        self.assertTrue(page.stage.currentWidget().isEnabled())
        self.assertFalse(page._submit("request_contact", "584093"))
        release.set()


if __name__ == "__main__":
    unittest.main()
