"""Exercise Piixelfone's native workflow without a network or real credentials."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from piixelverso.piixelfone.page import PiixelfoneModule, SETUP_MESSAGE
from piixelverso.preferences import PreferencesStore


class FakeService:
    def __init__(self, *, configured=False, existing=False):
        self.config = SimpleNamespace(url="https://example.supabase.co", public_key="")
        self.configured = configured
        self.has_vault = existing
        self.calls = []
        self.thread_ids = []
        self.value = {
            "number": "584093", "user_id": "me", "connected": True,
            "status": "Conectado.", "fingerprint": "OWN CODE",
            "contacts": [], "messages": [],
        }

    def record(self, name, *args):
        self.calls.append((name, *args))
        self.thread_ids.append(threading.get_ident())

    def configure(self, url, key):
        self.record("configure", url, key)
        if key == "sb_secret_invalid":
            raise ValueError("Informe apenas a chave pública.")
        self.config = SimpleNamespace(url=url, public_key=key)
        self.configured = True

    def unlock(self, password):
        self.record("unlock", password)
        self.has_vault = True
        return self.snapshot()

    def snapshot(self):
        return deepcopy(self.value)

    def sync(self):
        self.record("sync")
        return self.snapshot()

    def request_contact(self, number):
        self.record("request_contact", number)
        return self.snapshot()

    def accept_contact(self, peer):
        self.record("accept_contact", peer)
        self.value["contacts"][0]["state"] = "accepted"
        return self.snapshot()

    def decline_contact(self, peer):
        self.record("decline_contact", peer)
        self.value["contacts"][0]["state"] = "declined"
        return self.snapshot()

    def send_text(self, peer, text):
        self.record("send_text", peer, text)
        self.value["messages"].append({
            "id": "text1", "peer_id": peer, "direction": "outgoing", "status": "queued",
            "created_at": "2026-11-09T10:00:00Z", "type": "text", "text": text,
        })
        return self.snapshot()

    def send_file(self, peer, path):
        self.record("send_file", peer, path)
        return self.snapshot()

    def attachment(self, identifier):
        self.record("attachment", identifier)
        return "piece.pii", b"validated pii bytes"

    def regenerate_number(self):
        self.record("regenerate_number")
        self.value["number"] = "123456"
        return self.snapshot()


class PiixelfoneUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.preferences = PreferencesStore(Path(self.directory.name) / "preferences.json")
        self.pages = []

    def tearDown(self):
        for page in self.pages:
            page.shutdown()
            page.close()
            page.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def page(self, service):
        page = PiixelfoneModule(preferences=self.preferences, service=service)
        page.resize(1120, 750)
        page.show()
        self.pages.append(page)
        self.app.processEvents()
        return page

    def wait_idle(self, page):
        deadline = time.monotonic() + 3
        while page._busy and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(5)
        self.app.processEvents()
        self.assertFalse(page._busy, "A tarefa em background não concluiu")

    def unlocked(self, *, contact_state="accepted", incoming=False):
        service = FakeService(configured=True, existing=True)
        service.value["contacts"] = [{
            "user_id": "friend", "number": "987654", "public_key": "pinned key",
            "state": contact_state, "incoming": incoming, "fingerprint": "FRIEND CODE",
        }]
        page = self.page(service)
        page.password_input.setText("local password")
        page._unlock()
        self.wait_idle(page)
        page.contacts_list.setCurrentRow(0)
        self.app.processEvents()
        return page, service

    def test_first_access_shows_admin_guidance_and_public_key_configuration(self):
        service = FakeService()
        page = self.page(service)
        self.assertEqual(page.stage.currentIndex(), 0)
        labels = [label.text() for label in page.findChildren(type(page.status_label))]
        self.assertIn(SETUP_MESSAGE, labels)
        self.assertEqual(page.url_input.text(), service.config.url)
        self.assertFalse(page.config_back_button.isVisible())
        page.key_input.setText("sb_publishable_public")
        page.configure_button.click()
        self.wait_idle(page)
        self.assertEqual(page.stage.currentIndex(), 1)
        self.assertTrue(page.confirm_password_input.isVisible())
        self.assertEqual(service.calls[0][0], "configure")
        self.assertNotEqual(service.thread_ids[0], threading.get_ident())

    def test_new_identity_requires_matching_eight_character_local_password(self):
        service = FakeService(configured=True)
        page = self.page(service)
        page.password_input.setText("short")
        page.confirm_password_input.setText("short")
        page._unlock()
        self.assertIn("8 caracteres", page.status_label.text())
        self.assertEqual(service.calls, [])
        page.password_input.setText("local password")
        page.confirm_password_input.setText("different password")
        page._unlock()
        self.assertIn("não coincidem", page.status_label.text())
        page.confirm_password_input.setText("local password")
        page._unlock()
        self.assertEqual(page.password_input.text(), "")
        self.assertEqual(page.confirm_password_input.text(), "")
        self.wait_idle(page)
        self.assertEqual(page.stage.currentIndex(), 2)
        self.assertTrue(page.poll_timer.isActive())
        self.assertEqual(page.number_label.text(), "584 093")

    def test_existing_identity_does_not_offer_password_replacement(self):
        page = self.page(FakeService(configured=True, existing=True))
        self.assertEqual(page.stage.currentIndex(), 1)
        self.assertFalse(page.confirm_password_input.isVisible())
        self.assertEqual(page.unlock_button.text(), "Desbloquear")

    def test_unicode_limit_counts_characters_and_sends_literal_text(self):
        page, service = self.unlocked()
        page.message_input.setPlainText("😀" * 150)
        self.assertEqual(page.counter_label.text(), "150 / 150")
        self.assertEqual(len(page.message_input.toPlainText()), 150)
        page.message_input.insertPlainText("extra")
        self.assertEqual(len(page.message_input.toPlainText()), 150)
        text = "<b>Olá</b> & uma nova arte!"
        page.message_input.setPlainText(text)
        page.send_button.click()
        self.wait_idle(page)
        self.assertIn(("send_text", "friend", text), service.calls)
        self.assertEqual(page.message_input.toPlainText(), "")
        self.assertIn(text, page.messages_list.item(0).text())
        self.assertIn("Na fila", page.messages_list.item(0).text())

    def test_incoming_invitation_disables_send_until_accepted(self):
        page, service = self.unlocked(contact_state="pending", incoming=True)
        self.assertTrue(page.accept_button.isVisible())
        self.assertTrue(page.decline_button.isVisible())
        self.assertFalse(page.message_input.isEnabled())
        self.assertFalse(page.attachment_button.isEnabled())
        page.accept_button.click()
        self.wait_idle(page)
        self.assertIn(("accept_contact", "friend"), service.calls)
        self.assertTrue(page.message_input.isEnabled())
        self.assertFalse(page.accept_button.isVisible())

    def test_invite_normalizes_spaces_and_rejects_non_ascii_or_short_codes(self):
        page, service = self.unlocked()
        for number in ("123", "１２３４５６", "abc123"):
            page.number_input.setText(number)
            page._request_contact()
            self.assertIn("6 dígitos", page.status_label.text())
        page.number_input.setText("584 093")
        page._request_contact()
        self.wait_idle(page)
        self.assertIn(("request_contact", "584093"), service.calls)

    def test_file_send_and_received_save_use_explicit_file_choosers(self):
        page, service = self.unlocked()
        with patch("piixelverso.piixelfone.page.QFileDialog.getOpenFileName",
                   return_value=("/chosen/art.pii", "")) as picker:
            page._send_file()
        self.wait_idle(page)
        picker.assert_called_once()
        self.assertIn(("send_file", "friend", "/chosen/art.pii"), service.calls)
        service.value["messages"] = [{
            "id": "file1", "peer_id": "friend", "direction": "incoming", "status": "received",
            "created_at": "2026-11-09T10:00:00Z", "type": "file", "filename": "<b>piece.pii</b>",
        }]
        page._apply_snapshot(service.snapshot())
        page.messages_list.setCurrentRow(0)
        self.assertTrue(page.save_attachment_button.isEnabled())
        self.assertIn("<b>piece.pii</b>", page.messages_list.item(0).text())
        destination = Path(self.directory.name) / "copied.pii"
        with patch("piixelverso.piixelfone.page.QFileDialog.getSaveFileName",
                   return_value=(str(destination), "")):
            page._save_selected_attachment()
        self.wait_idle(page)
        self.assertEqual(destination.read_bytes(), b"validated pii bytes")
        self.assertIn(("attachment", "file1"), service.calls)
        self.assertFalse(list(destination.parent.glob("*.tmp")))

    def test_background_poll_survives_navigation_and_shutdown_stops_it(self):
        page, service = self.unlocked()
        page.set_active(False)
        self.assertTrue(page.poll_timer.isActive())
        page._poll()
        self.wait_idle(page)
        self.assertIn(("sync",), service.calls)
        page.shutdown()
        self.assertFalse(page.poll_timer.isActive())
        before = len(service.calls)
        page._poll()
        self.app.processEvents()
        self.assertEqual(len(service.calls), before)

    def test_busy_worker_serializes_operations_without_gui_work(self):
        page, service = self.unlocked()
        entered, release = threading.Event(), threading.Event()
        original = service.sync
        def delayed():
            entered.set()
            release.wait(2)
            return original()
        service.sync = delayed
        page._poll()
        self.assertTrue(entered.wait(1))
        self.assertFalse(page._submit("regenerate_number"))
        self.assertFalse(page.send_button.isEnabled())
        release.set()
        self.wait_idle(page)
        self.assertNotIn(("regenerate_number",), service.calls)
        self.assertTrue(all(identifier != threading.get_ident() for identifier in service.thread_ids))

    def test_regeneration_is_explicit_and_preserves_existing_chat_view(self):
        page, service = self.unlocked()
        with patch("piixelverso.piixelfone.page.QMessageBox") as dialog_type:
            dialog = dialog_type.return_value
            confirm, cancel = object(), object()
            dialog.addButton.side_effect = [confirm, cancel]
            dialog.clickedButton.return_value = confirm
            page._regenerate()
        self.wait_idle(page)
        self.assertIn(("regenerate_number",), service.calls)
        self.assertEqual(page.number_label.text(), "123 456")
        self.assertEqual(page._selected_peer, "friend")
        self.assertIn("mantidos", dialog.setInformativeText.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
