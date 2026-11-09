"""Encrypted local history survives reconnects without weakening identity pins."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid

from piixelverso.piixelfone.store import MAX_RECORD_BYTES, Store, StoreError


class PiixelfoneStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "phone" / "history.sqlite3"
        self.key = os.urandom(32)
        self.store = Store(self.path, self.key)
        self.peer = str(uuid.uuid4())

    def tearDown(self):
        self.directory.cleanup()

    def contact(self, **changes):
        record = {
            "user_id": self.peer,
            "number": "584 093",
            "public_key": base64.b64encode(bytes(range(32))).decode("ascii"),
            "state": "accepted",
            "incoming": False,
        }
        record.update(changes)
        return record

    def message(self, **changes):
        record = {
            "id": str(uuid.uuid4()),
            "peer_id": self.peer,
            "direction": "outgoing",
            "status": "queued",
            "created_at": "2026-11-09T12:00:00+00:00",
            "text": "Conteúdo privado que só as pessoas da conversa podem ver ♥",
            "filename": "meu desenho privado.pii",
            "data": base64.b64encode(b"private attachment contents").decode("ascii"),
            "payload": "opaque encrypted server envelope",
        }
        record.update(changes)
        return record

    def test_reopen_keeps_encrypted_history_and_pinned_contacts(self):
        contact = self.contact()
        message = self.message()
        self.store.put_contact(contact)
        self.store.put_message(message)
        reopened = Store(self.path, self.key)
        self.assertEqual(reopened.messages(self.peer), [message])
        contact["number"] = "584093"
        self.assertEqual(reopened.contacts(), [contact])
        raw = self.path.read_bytes()
        for private in (message["text"], message["filename"], message["data"], message["payload"], contact["public_key"]):
            self.assertNotIn(private.encode("utf-8"), raw)
        if os.name != "nt":
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)

    def test_outbox_and_pending_ack_are_durable_and_do_not_regress(self):
        outgoing = self.message()
        incoming = self.message(direction="incoming", status="received")
        self.store.put_message(outgoing)
        self.store.put_message(incoming)
        self.assertEqual(self.store.outbox(), [outgoing])
        self.assertEqual(self.store.pending_ack(), [incoming])
        self.store.set_status(outgoing["id"], "sent")
        self.assertEqual(self.store.outbox(), [])
        self.store.set_status(outgoing["id"], "delivered")
        self.store.set_status(outgoing["id"], "queued")
        self.assertEqual(self.store.message(outgoing["id"])["status"], "delivered")
        self.store.set_status(incoming["id"], "delivered")
        self.assertEqual(Store(self.path, self.key).pending_ack(), [])

    def test_message_duplicate_is_idempotent_but_cannot_replace_content(self):
        record = self.message()
        self.store.put_message(record)
        self.store.put_message(record)
        self.assertEqual(self.store.all_messages(), [record])
        for field, value in (("text", "Troca indevida"), ("peer_id", str(uuid.uuid4())),
                             ("filename", "outro.pii"), ("created_at", "2026-11-10T12:00:00Z")):
            changed = {**record, field: value}
            with self.subTest(field=field), self.assertRaises(StoreError):
                self.store.put_message(changed)
        self.assertEqual(self.store.message(record["id"]), record)
        self.store.put_message({**record, "status": "sent"})
        self.assertEqual(self.store.message(record["id"])["status"], "sent")

    def test_contact_alias_can_change_but_public_key_cannot(self):
        contact = self.contact()
        self.store.put_contact(contact)
        updated = {**contact, "number": "923456", "state": "pending", "incoming": True}
        self.store.put_contact(updated)
        self.assertEqual(self.store.contact(self.peer), updated)
        with self.assertRaisesRegex(StoreError, "chave de segurança"):
            self.store.put_contact({**updated, "public_key": base64.b64encode(os.urandom(32)).decode("ascii")})
        self.assertEqual(self.store.contact(self.peer), updated)

    def test_wrong_storage_key_does_not_reset_or_overwrite_database(self):
        record = self.message()
        self.store.put_message(record)
        with self.assertRaises(StoreError):
            Store(self.path, os.urandom(32))
        self.assertEqual(Store(self.path, self.key).message(record["id"]), record)

    def test_ciphertext_corruption_and_index_tampering_are_detected(self):
        record = self.message()
        self.store.put_message(record)
        with sqlite3.connect(self.path) as connection:
            original = connection.execute("SELECT sealed FROM messages WHERE id = ?", (record["id"],)).fetchone()[0]
            connection.execute("UPDATE messages SET sealed = ? WHERE id = ?", ("AAAA", record["id"]))
        with self.assertRaises(StoreError):
            self.store.message(record["id"])
        with sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE messages SET sealed = ?, peer_id = ? WHERE id = ?", (original, "another-peer", record["id"]))
        with self.assertRaises(StoreError):
            self.store.all_messages()

    def test_swapping_encrypted_contacts_is_detected(self):
        one = self.contact()
        two = self.contact(user_id=str(uuid.uuid4()), number="123456")
        self.store.put_contact(one)
        self.store.put_contact(two)
        with sqlite3.connect(self.path) as connection:
            sealed = connection.execute("SELECT sealed FROM contacts WHERE user_id = ?", (two["user_id"],)).fetchone()[0]
            connection.execute("UPDATE contacts SET sealed = ? WHERE user_id = ?", (sealed, one["user_id"]))
        with self.assertRaises(StoreError):
            self.store.contact(one["user_id"])

    def test_history_orders_by_timestamp_with_stable_insertion_ties(self):
        late = self.message(created_at="2026-11-09T13:00:00Z")
        early = self.message(created_at="2026-11-09T10:00:00Z")
        tied = self.message(created_at="2026-11-09T10:00:00Z")
        for record in (late, early, tied):
            self.store.put_message(record)
        self.assertEqual(self.store.messages(self.peer), [early, tied, late])

    def test_parallel_operations_use_separate_connections_without_losing_records(self):
        records = [self.message(text=f"Mensagem {index}") for index in range(24)]
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(self.store.put_message, records))
        self.assertEqual({record["id"] for record in self.store.messages(self.peer)}, {record["id"] for record in records})

    def test_record_limits_validate_before_writing(self):
        invalid = [
            self.message(text="á" * 151),
            self.message(data="x" * MAX_RECORD_BYTES),
            self.message(created_at="not-a-date"),
            self.message(direction=[]),
            self.message(status="received"),
            self.message(direction="incoming", status="queued"),
        ]
        for record in invalid:
            with self.subTest(record=record["id"]), self.assertRaises(StoreError):
                self.store.put_message(record)
        self.assertEqual(self.store.all_messages(), [])

    def test_maximum_attachment_and_its_network_envelope_fit_in_one_record(self):
        record = self.message(data=base64.b64encode(b"x" * 86000).decode("ascii"), payload="y" * 160000)
        self.store.put_message(record)
        self.assertEqual(Store(self.path, self.key).message(record["id"]), record)

    def test_bad_status_does_not_damage_existing_record(self):
        record = self.message()
        self.store.put_message(record)
        for status in ("unknown", [], "received"):
            with self.subTest(status=status), self.assertRaises(StoreError):
                self.store.set_status(record["id"], status)
        self.assertEqual(self.store.message(record["id"]), record)
        with self.assertRaises(StoreError):
            self.store.set_status("missing", "sent")

    def test_invalid_contact_never_overwrites_a_pin(self):
        contact = self.contact()
        self.store.put_contact(contact)
        for changes in ({"number": "012345"}, {"public_key": "not-a-key"},
                        {"state": []}, {"incoming": 1}):
            with self.subTest(changes=changes), self.assertRaises(StoreError):
                self.store.put_contact({**contact, **changes})
        self.assertEqual(self.store.contact(self.peer)["public_key"], contact["public_key"])


if __name__ == "__main__":
    unittest.main()
