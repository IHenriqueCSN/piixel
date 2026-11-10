"""Two-client use-case tests with real crypto and a deterministic fake mailbox.

The fake models RPC responses and network failure, not PostgreSQL/RLS security.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from pathlib import Path
import tempfile
import time
import unittest
from uuid import UUID, uuid4

from piixelverso.format import MAX_FILE_SIZE, encode_design
from piixelverso.model import TRANSPARENT, PixelDesign
from piixelverso.piixelfone.config import DEFAULT_URL
from piixelverso.piixelfone.crypto import Identity, seal, unseal
from piixelverso.piixelfone.service import PhoneError, PhoneService
from piixelverso.piixelfone.transport import TransportError


PASSWORD = "uma senha local de teste"
PUBLIC_KEY = "sb_publishable_piixelfone_test_key_123456789"
NOW = "2026-11-09T15:00:00+00:00"


class FakeMailbox:
    """Durable server state shared by independent local app installations."""

    def __init__(self):
        self.profiles = {}
        self.relations = {}
        self.messages = {}
        self.offline = set()
        self.fail_send_after_commit = set()
        self.fail_ack_after_commit = set()
        self.fail_ack_before_commit = set()
        self.reserved_numbers = set()
        self.next_identity = 1
        self.next_number = 584093
        self.signups = 0
        self.calls = []

    def factory(self, config):
        return FakeTransport(self, config)

    def new_number(self):
        number = str(self.next_number)
        self.next_number += 1
        self.reserved_numbers.add(number)
        return number

    def auth(self, user_id):
        return {"access_token": "access-" + user_id, "refresh_token": "refresh-" + user_id,
                "user": {"id": user_id}, "expires_at": int(time.time()) + 3600}

    def rpc(self, user_id, name, params):
        self.calls.append((user_id, name, deepcopy(params)))
        if user_id in self.offline:
            raise TransportError("Sem conexão de teste.")
        if name == "pii_register":
            if user_id not in self.profiles:
                self.profiles[user_id] = {"user_id": user_id, "number": self.new_number(),
                                          "public_key": params["p_public_key"]}
            return deepcopy(self.profiles[user_id])
        if name == "pii_lookup":
            return next((deepcopy(row) for row in self.profiles.values()
                         if row["number"] == params["p_number"]), None)
        if name == "pii_regenerate":
            self.profiles[user_id]["number"] = self.new_number()
            return deepcopy(self.profiles[user_id])
        if name == "pii_contacts":
            result = []
            for relation in self.relations.values():
                if user_id not in (relation["sender"], relation["recipient"]):
                    continue
                peer_id = relation["recipient"] if user_id == relation["sender"] else relation["sender"]
                result.append(dict(self.profiles[peer_id], state=relation["state"],
                                   incoming=user_id == relation["recipient"]))
            return deepcopy(result)
        if name == "pii_request":
            peer = params["p_peer"]
            pair = tuple(sorted((peer, user_id)))
            if pair not in self.relations:
                self.relations[pair] = {"sender": user_id, "recipient": peer, "state": "pending"}
            return None
        if name in ("pii_accept", "pii_decline"):
            relation = self.relations[tuple(sorted((params["p_peer"], user_id)))]
            if name == "pii_accept" and relation["recipient"] != user_id:
                raise AssertionError("Only the invited contact accepts")
            relation["state"] = "accepted" if name == "pii_accept" else "declined"
            return None
        if name == "pii_send":
            relation = self.relations[tuple(sorted((params["p_recipient"], user_id)))]
            if relation["state"] != "accepted":
                raise AssertionError("Fake mailbox requires accepted contact")
            message_id = params["p_id"]
            if message_id not in self.messages:
                self.messages[message_id] = {"id": message_id, "sender": user_id,
                    "recipient": params["p_recipient"], "payload": params["p_payload"],
                    "created_at": NOW, "delivered_at": None, "rejected_at": None}
            elif self.messages[message_id]["payload"] != params["p_payload"]:
                raise AssertionError("Same message UUID cannot carry different content")
            if user_id in self.fail_send_after_commit:
                self.fail_send_after_commit.remove(user_id)
                raise TransportError("A resposta do envio se perdeu.")
            return None
        if name == "pii_inbox":
            return deepcopy([row for row in self.messages.values() if row["recipient"] == user_id
                             and not row["delivered_at"] and not row["rejected_at"]][:10])
        if name in ("pii_ack", "pii_reject"):
            message = self.messages[params["p_id"]]
            if message["recipient"] != user_id:
                raise AssertionError("Only the recipient acknowledges")
            if user_id in self.fail_ack_before_commit:
                self.fail_ack_before_commit.remove(user_id)
                raise TransportError("A confirmação não chegou ao servidor.")
            field = "delivered_at" if name == "pii_ack" else "rejected_at"
            message[field] = NOW
            if user_id in self.fail_ack_after_commit:
                self.fail_ack_after_commit.remove(user_id)
                raise TransportError("A resposta da confirmação se perdeu.")
            return None
        if name == "pii_statuses":
            return [{"id": row["id"], "delivered_at": row["delivered_at"],
                     "rejected_at": row["rejected_at"]} for row in self.messages.values()
                    if row["sender"] == user_id and row["id"] in params["p_ids"]]
        raise AssertionError("Unexpected RPC: " + name)


class FakeTransport:
    def __init__(self, mailbox, config):
        self.mailbox = mailbox
        self.config = config
        self.auth = {}

    def set_auth(self, auth):
        self.auth = deepcopy(auth)

    def sign_up(self):
        user_id = str(UUID(int=self.mailbox.next_identity))
        self.mailbox.next_identity += 1
        self.mailbox.signups += 1
        self.auth = self.mailbox.auth(user_id)
        return deepcopy(self.auth)

    def refresh(self, refresh_token):
        user_id = refresh_token.removeprefix("refresh-")
        if user_id in self.mailbox.offline:
            raise TransportError("Sem conexão de teste.")
        self.auth = self.mailbox.auth(user_id)
        return deepcopy(self.auth)

    def rpc(self, name, params=None):
        return self.mailbox.rpc(self.auth["user"]["id"], name, params or {})


class PhoneServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.mailbox = FakeMailbox()
        self.alice = self.new_client("alice")
        self.bob = self.new_client("bob")
        self.alice_id = self.alice.snapshot()["user_id"]
        self.bob_id = self.bob.snapshot()["user_id"]

    def tearDown(self):
        self.directory.cleanup()

    def new_client(self, name):
        service = PhoneService(self.root / name, transport_factory=self.mailbox.factory)
        service.configure(DEFAULT_URL, PUBLIC_KEY)
        self.assertTrue(service.unlock(PASSWORD)["connected"])
        return service

    def reopen(self, name):
        service = PhoneService(self.root / name, transport_factory=self.mailbox.factory)
        service.unlock(PASSWORD)
        return service

    def accept_contacts(self):
        self.alice.request_contact(self.bob.snapshot()["number"])
        self.bob.sync()
        self.bob.accept_contact(self.alice_id)
        self.alice.sync()

    def alice_messages(self):
        return self.alice.snapshot()["messages"]

    def bob_messages(self):
        return self.bob.snapshot()["messages"]

    def test_request_and_acceptance_are_required_before_chat(self):
        self.alice.request_contact(self.bob.snapshot()["number"])
        self.assertFalse(self.alice.snapshot()["contacts"][0]["incoming"])
        with self.assertRaises(PhoneError):
            self.alice.send_text(self.bob_id, "Antes de aceitar")
        self.bob.sync()
        received = self.bob.snapshot()["contacts"][0]
        self.assertEqual(received["state"], "pending")
        self.assertTrue(received["incoming"])
        self.assertTrue(received["fingerprint"])
        self.bob.accept_contact(self.alice_id)
        self.alice.sync()
        self.assertEqual(self.alice.snapshot()["contacts"][0]["state"], "accepted")
        self.alice.send_text(self.bob_id, "Agora podemos conversar")
        self.bob.sync()
        self.assertEqual(self.bob_messages()[0]["text"], "Agora podemos conversar")

    def test_declined_contact_cannot_send(self):
        self.alice.request_contact(self.bob.snapshot()["number"])
        self.bob.sync()
        self.bob.decline_contact(self.alice_id)
        self.alice.sync()
        self.assertEqual(self.alice.snapshot()["contacts"][0]["state"], "declined")
        with self.assertRaises(PhoneError):
            self.alice.send_text(self.bob_id, "Não enviar")

    def test_offline_outbox_survives_restart_and_delivers_once(self):
        self.accept_contacts()
        self.mailbox.offline.add(self.alice_id)
        text = "Mensagem privada que aguarda o retorno da conexão"
        queued = self.alice.send_text(self.bob_id, text)
        self.assertFalse(queued["connected"])
        self.assertEqual(queued["messages"][0]["status"], "queued")
        self.assertEqual(len(self.mailbox.messages), 0)
        before_private = self.alice._vault.identity.private_key_b64
        self.alice = self.reopen("alice")
        self.assertEqual(self.alice._vault.identity.private_key_b64, before_private)
        self.assertEqual(self.alice_messages()[0]["status"], "queued")
        for path in (self.root / "alice").iterdir():
            self.assertNotIn(text.encode(), path.read_bytes())
        self.mailbox.offline.remove(self.alice_id)
        self.alice.sync()
        self.assertEqual(self.alice_messages()[0]["status"], "sent")
        self.assertEqual(len(self.mailbox.messages), 1)
        wire = next(iter(self.mailbox.messages.values()))
        self.assertNotIn(text, wire["payload"])
        self.bob.sync()
        self.bob.sync()
        self.alice.sync()
        self.assertEqual([m["text"] for m in self.bob_messages()], [text])
        self.assertEqual(self.alice_messages()[0]["status"], "delivered")
        self.assertEqual(self.mailbox.signups, 2)

    def test_retry_after_lost_send_response_reuses_uuid_and_ciphertext(self):
        self.accept_contacts()
        self.mailbox.fail_send_after_commit.add(self.alice_id)
        self.alice.send_text(self.bob_id, "Resposta perdida, mensagem preservada")
        self.assertEqual(self.alice_messages()[0]["status"], "queued")
        original = deepcopy(next(iter(self.mailbox.messages.values())))
        self.alice.sync()
        self.assertEqual(len(self.mailbox.messages), 1)
        self.assertEqual(next(iter(self.mailbox.messages.values()))["payload"], original["payload"])
        self.bob.sync()
        self.alice.sync()
        self.assertEqual(len(self.bob_messages()), 1)
        self.assertEqual(self.alice_messages()[0]["status"], "delivered")

    def test_retry_after_lost_ack_response_preserves_received_history(self):
        self.accept_contacts()
        self.alice.send_text(self.bob_id, "Persistir antes de confirmar")
        self.mailbox.fail_ack_after_commit.add(self.bob_id)
        self.assertFalse(self.bob.sync()["connected"])
        self.assertEqual(len(self.bob_messages()), 1)
        self.assertEqual(self.bob_messages()[0]["status"], "received")
        self.bob = self.reopen("bob")
        self.assertEqual(len(self.bob_messages()), 1)
        self.assertEqual(self.bob_messages()[0]["status"], "delivered")
        self.alice.sync()
        self.assertEqual(self.alice_messages()[0]["status"], "delivered")

    def test_retry_after_ack_never_reached_server_does_not_duplicate(self):
        self.accept_contacts()
        self.alice.send_text(self.bob_id, "Confirmar novamente")
        self.mailbox.fail_ack_before_commit.add(self.bob_id)
        self.bob.sync()
        self.assertEqual(len(self.bob_messages()), 1)
        self.bob.sync()
        self.assertEqual(len(self.bob_messages()), 1)
        self.assertEqual(self.bob_messages()[0]["status"], "delivered")

    def test_150_unicode_characters_allowed_but_151_and_blank_refused(self):
        self.accept_contacts()
        self.alice.send_text(self.bob_id, "🎨" * 150)
        self.bob.sync()
        self.assertEqual(self.bob_messages()[0]["text"], "🎨" * 150)
        for text in ("🎨" * 151, "a" * 151, "", " \n\t"):
            with self.subTest(text=text[:10]), self.assertRaises(PhoneError):
                self.alice.send_text(self.bob_id, text)
        self.assertEqual(len(self.alice_messages()), 1)

    def test_valid_pii_attachment_roundtrip_and_gui_snapshot_contains_no_bytes(self):
        self.accept_contacts()
        design = PixelDesign(10, 10, name="Pequeno planeta")
        design.set_pixel(3, 4, "#ED5598")
        data = encode_design(design)
        path = self.root / "meu planeta.pii"
        path.write_bytes(data)
        self.alice.send_file(self.bob_id, str(path))
        wire = next(iter(self.mailbox.messages.values()))
        self.assertNotIn(path.name, wire["payload"])
        self.assertNotIn(base64.b64encode(data).decode(), wire["payload"])
        self.bob.sync()
        message = self.bob_messages()[0]
        self.assertEqual(message["type"], "file")
        self.assertEqual(message["filename"], path.name)
        self.assertNotIn("data", message)
        self.assertNotIn("payload", message)
        self.assertEqual(self.bob.attachment(message["id"]), (path.name, data))
        self.bob = self.reopen("bob")
        self.assertEqual(self.bob.attachment(message["id"]), (path.name, data))

    def test_attachment_requires_valid_pii_format_and_safe_filename(self):
        self.accept_contacts()
        for name, data in (("nota.txt", b"not .pii"), ("falso.pii", b"not a valid design"),
                           ("invalido:arquivo.pii", encode_design(PixelDesign(10, 10)))):
            path = self.root / name
            path.write_bytes(data)
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.alice.send_file(self.bob_id, str(path))
        self.assertEqual(self.alice_messages(), [])

    def test_tampered_ciphertext_is_rejected_without_history_or_delivery(self):
        self.accept_contacts()
        self.alice.send_text(self.bob_id, "Não exibir se adulterada")
        row = next(iter(self.mailbox.messages.values()))
        damaged = bytearray(base64.b64decode(row["payload"]))
        damaged[-1] ^= 1
        row["payload"] = base64.b64encode(damaged).decode()
        self.bob.sync()
        self.assertEqual(self.bob_messages(), [])
        self.assertIsNone(row["delivered_at"])
        self.assertIsNotNone(row["rejected_at"])
        self.alice.sync()
        self.assertEqual(self.alice_messages()[0]["status"], "rejected")

    def test_authenticated_envelope_with_wrong_context_is_rejected(self):
        self.accept_contacts()
        self.alice.send_text(self.bob_id, "Contexto também é autenticado")
        row = next(iter(self.mailbox.messages.values()))
        payload = unseal(self.bob._vault.identity, self.alice._vault.identity.public_key_b64, row["payload"])
        payload["to"] = str(uuid4())
        row["payload"] = seal(self.alice._vault.identity, self.bob._vault.identity.public_key_b64, payload)
        self.bob.sync()
        self.assertEqual(self.bob_messages(), [])
        self.assertIsNotNone(row["rejected_at"])

    def test_authenticated_oversize_text_is_refused_by_recipient_too(self):
        self.accept_contacts()
        self.alice.send_text(self.bob_id, "Original válido")
        row = next(iter(self.mailbox.messages.values()))
        payload = unseal(self.bob._vault.identity, self.alice._vault.identity.public_key_b64, row["payload"])
        payload["text"] = "x" * 151
        row["payload"] = seal(self.alice._vault.identity, self.bob._vault.identity.public_key_b64, payload)
        self.bob.sync()
        self.assertEqual(self.bob_messages(), [])
        self.assertIsNotNone(row["rejected_at"])

    def test_regeneration_retires_alias_but_preserves_identity_history_and_contacts(self):
        self.accept_contacts()
        self.alice.send_text(self.bob_id, "Antes da troca")
        self.bob.sync()
        self.alice.sync()
        old_number = self.alice.snapshot()["number"]
        old_key = self.alice._vault.identity.private_key_b64
        result = self.alice.regenerate_number()
        self.assertNotEqual(result["number"], old_number)
        self.assertEqual(result["user_id"], self.alice_id)
        self.assertEqual(self.alice._vault.identity.private_key_b64, old_key)
        self.assertEqual(len(result["messages"]), 1)
        self.assertEqual(result["contacts"][0]["state"], "accepted")
        self.assertIn(old_number.replace(" ", ""), self.mailbox.reserved_numbers)
        self.bob.sync()
        self.assertEqual(self.bob.snapshot()["contacts"][0]["number"], result["number"].replace(" ", ""))
        with self.assertRaises(PhoneError):
            self.bob.request_contact(old_number)
        self.bob.send_text(self.alice_id, "Depois da troca")
        self.alice.sync()
        self.assertEqual(len(self.alice_messages()), 2)
        self.alice = self.reopen("alice")
        self.assertEqual(self.alice.snapshot()["number"], result["number"])

    def test_changed_pinned_key_blocks_send_and_never_replaces_pin(self):
        self.accept_contacts()
        original = self.alice._store.contact(self.bob_id)["public_key"]
        self.mailbox.profiles[self.bob_id]["public_key"] = Identity.generate().public_key_b64
        result = self.alice.sync()
        self.assertFalse(result["connected"])
        self.assertIn("chave", result["status"].lower())
        self.assertEqual(self.alice._store.contact(self.bob_id)["public_key"], original)
        self.assertEqual(self.alice.snapshot()["contacts"][0]["state"], "blocked")
        with self.assertRaises(PhoneError):
            self.alice.send_text(self.bob_id, "Não transmitir")
        self.assertEqual(self.mailbox.messages, {})

    def test_changing_project_cannot_reuse_existing_identity(self):
        original = self.alice._vault.identity.private_key_b64
        with self.assertRaises(PhoneError):
            self.alice.configure("https://other-project.supabase.co", PUBLIC_KEY)
        self.assertEqual(self.alice.config.url, DEFAULT_URL)
        self.alice = self.reopen("alice")
        self.assertEqual(self.alice._vault.identity.private_key_b64, original)
        self.assertEqual(self.mailbox.signups, 2)

    def test_invalid_contact_numbers_and_own_number_do_not_create_contacts(self):
        for number in ("123", "abcdef", "000000", "１２３４５６", self.alice.snapshot()["number"]):
            with self.subTest(number=number), self.assertRaises(PhoneError):
                self.alice.request_contact(number)
        self.assertEqual(self.alice.snapshot()["contacts"], [])

    def test_recipient_offline_keeps_server_queue_until_reopening(self):
        self.accept_contacts()
        self.mailbox.offline.add(self.bob_id)
        self.alice.send_text(self.bob_id, "Entregar quando você voltar")
        self.assertEqual(self.alice_messages()[0]["status"], "sent")
        self.assertEqual(self.bob_messages(), [])
        self.assertFalse(self.bob.sync()["connected"])
        self.alice.sync()
        row = next(iter(self.mailbox.messages.values()))
        self.assertIsNone(row["delivered_at"])
        self.mailbox.offline.remove(self.bob_id)
        self.bob = self.reopen("bob")
        self.assertEqual(self.bob_messages()[0]["text"], "Entregar quando você voltar")
        self.alice.sync()
        self.assertEqual(self.alice_messages()[0]["status"], "delivered")

    def test_largest_supported_pii_fits_envelope_and_encrypted_history_limits(self):
        self.accept_contacts()
        colors = [TRANSPARENT] + [f"#{index:06X}" for index in range(128 * 128 - 1)]
        design = PixelDesign(128, 128, colors, "x" * 4096)
        data = encode_design(design)
        self.assertEqual(len(data), MAX_FILE_SIZE)
        path = self.root / "maximo.pii"
        path.write_bytes(data)
        self.alice.send_file(self.bob_id, str(path))
        row = next(iter(self.mailbox.messages.values()))
        self.assertLessEqual(len(row["payload"]), 190000)
        self.bob.sync()
        self.assertEqual(self.bob.attachment(row["id"]), (path.name, data))
        self.alice = self.reopen("alice")
        self.assertEqual(self.alice.attachment(row["id"]), (path.name, data))

    def test_expired_auth_refresh_retains_user_id_and_encryption_key(self):
        key = self.alice._vault.identity.private_key_b64
        auth = dict(self.alice._vault.auth, expires_at=0)
        self.alice._vault.save_auth(auth)
        self.alice.sync()
        self.assertEqual(self.alice.snapshot()["user_id"], self.alice_id)
        self.assertEqual(self.alice._vault.identity.private_key_b64, key)
        self.assertGreater(self.alice._vault.auth["expires_at"], time.time())
        self.assertEqual(self.mailbox.signups, 2)

    def test_failed_refresh_never_creates_replacement_anonymous_identity(self):
        self.alice._vault.save_auth(dict(self.alice._vault.auth, expires_at=0))
        self.mailbox.offline.add(self.alice_id)
        result = self.alice.sync()
        self.assertFalse(result["connected"])
        self.assertEqual(result["user_id"], self.alice_id)
        self.assertEqual(self.mailbox.signups, 2)

    def test_missing_vault_with_existing_history_requires_restore_without_new_identity(self):
        self.accept_contacts()
        self.alice.send_text(self.bob_id, "Histórico precisa da identidade original")
        vault_path = self.root / "alice" / "identity.vault"
        vault_path.unlink()
        reopened = PhoneService(self.root / "alice", transport_factory=self.mailbox.factory)
        with self.assertRaises(PhoneError) as raised:
            reopened.unlock(PASSWORD)
        self.assertIn("cofre", str(raised.exception).lower())
        self.assertFalse(vault_path.exists())
        self.assertEqual(self.mailbox.signups, 2)


if __name__ == "__main__":
    unittest.main()
