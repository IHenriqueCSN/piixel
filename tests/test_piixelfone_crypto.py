import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nacl.public import Box, PublicKey
from nacl.secret import SecretBox

from piixelverso.piixelfone.crypto import (
    CryptoError, Identity, MAX_JSON_BYTES, MAX_VAULT_BYTES, Vault, fingerprint,
    seal, seal_local, unseal, unseal_local,
)


class CryptoTests(unittest.TestCase):
    def setUp(self):
        self.alice = Identity.generate()
        self.bob = Identity.generate()

    def test_authenticated_unicode_roundtrip(self):
        payload = {"text": "Olá, Pii! 🐱", "version": 1}
        encrypted = seal(self.alice, self.bob.public_key_b64, payload)
        self.assertEqual(unseal(self.bob, self.alice.public_key_b64, encrypted), payload)
        self.assertNotEqual(encrypted, seal(self.alice, self.bob.public_key_b64, payload))
        self.assertNotIn("Olá", encrypted)

    def test_wrong_recipient_or_sender_and_tampering_are_rejected(self):
        encrypted = seal(self.alice, self.bob.public_key_b64, {"text": "sigilo"})
        eve = Identity.generate()
        with self.assertRaises(CryptoError):
            unseal(eve, self.alice.public_key_b64, encrypted)
        with self.assertRaises(CryptoError):
            unseal(self.bob, eve.public_key_b64, encrypted)
        altered = bytearray(base64.b64decode(encrypted))
        altered[-1] ^= 1
        with self.assertRaises(CryptoError):
            unseal(self.bob, self.alice.public_key_b64, base64.b64encode(altered).decode())

    def test_identity_restoration_and_full_fingerprint(self):
        restored = Identity.from_private(self.alice.private_key_b64)
        self.assertEqual(restored.public_key_b64, self.alice.public_key_b64)
        self.assertEqual(len(fingerprint(restored.public_key_b64).replace(" ", "")), 64)
        self.assertNotEqual(fingerprint(self.alice.public_key_b64), fingerprint(self.bob.public_key_b64))

    def test_malformed_keys_and_ciphertexts(self):
        for key in ("not a key", "", base64.b64encode(b"short").decode(), None):
            with self.subTest(key=key):
                with self.assertRaises(CryptoError):
                    Identity.from_private(key)
                with self.assertRaises(CryptoError):
                    fingerprint(key)
                with self.assertRaises(CryptoError):
                    seal(self.alice, key, {})
        for ciphertext in ("", "!", "YQ==", "YQ==\n", "A" * (MAX_JSON_BYTES * 2), None):
            with self.subTest(ciphertext=str(ciphertext)[:20]), self.assertRaises(CryptoError):
                unseal(self.bob, self.alice.public_key_b64, ciphertext)

    def test_low_order_public_key_is_rejected(self):
        with self.assertRaises(CryptoError):
            seal(self.alice, base64.b64encode(bytes(32)).decode(), {})

    def test_message_payload_limits_and_structure(self):
        for payload in ([], "text", {"x": float("nan")}, {"text": "x" * MAX_JSON_BYTES}):
            with self.subTest(payload_type=type(payload)), self.assertRaises(CryptoError):
                seal(self.alice, self.bob.public_key_b64, payload)
        box = Box(self.alice._private, PublicKey(base64.b64decode(self.bob.public_key_b64)))
        for data in (b"[]", b'{"a":1,"a":2}', b'{"a":NaN}', b"\xff"):
            encrypted = base64.b64encode(box.encrypt(data)).decode()
            with self.subTest(data=data), self.assertRaises(CryptoError):
                unseal(self.bob, self.alice.public_key_b64, encrypted)

    def test_local_encryption_and_tampering(self):
        key = os.urandom(32)
        sealed = seal_local(key, {"body": "mensagem local"})
        self.assertEqual(unseal_local(key, sealed), {"body": "mensagem local"})
        with self.assertRaises(CryptoError):
            unseal_local(os.urandom(32), sealed)
        with self.assertRaises(CryptoError):
            seal_local(b"bad", {})
        with self.assertRaises(CryptoError):
            unseal_local(key, "YQ==")

    def test_local_records_can_hold_attachment_and_sealed_envelope(self):
        key = os.urandom(32)
        # Local history keeps the attachment and transport envelope together.
        # Its bound deliberately exceeds that of a network message envelope.
        payload = {"attachment": "a" * (270 * 1024)}
        self.assertEqual(unseal_local(key, seal_local(key, payload)), payload)


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "phone" / "vault.json"
        self.vault = Vault.create(self.path, "senha local segura")

    def test_identity_and_tokens_are_encrypted_and_survive_unlock(self):
        tokens = {"access_token": "ACCESS-PRIVATE-123", "refresh_token": "REFRESH-PRIVATE-456"}
        self.vault.save_auth(tokens)
        stored = self.path.read_text()
        for secret in ("senha local segura", self.vault.identity.private_key_b64,
                       base64.b64encode(self.vault.storage_key).decode(), *tokens.values()):
            self.assertNotIn(secret, stored)
        reopened = Vault.unlock(self.path, "senha local segura")
        self.assertEqual(reopened.identity.public_key_b64, self.vault.identity.public_key_b64)
        self.assertEqual(reopened.storage_key, self.vault.storage_key)
        self.assertEqual(reopened.auth, tokens)
        self.assertEqual(set(json.loads(stored)), {"version", "salt", "ciphertext"})
        if os.name == "posix":
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_wrong_password_and_tampered_vault_are_rejected(self):
        with self.assertRaisesRegex(CryptoError, "incorreta"):
            Vault.unlock(self.path, "senha completamente diferente")
        outer = json.loads(self.path.read_text())
        raw = bytearray(base64.b64decode(outer["ciphertext"]))
        raw[-1] ^= 2
        outer["ciphertext"] = base64.b64encode(raw).decode()
        self.path.write_text(json.dumps(outer))
        with self.assertRaises(CryptoError):
            Vault.unlock(self.path, "senha local segura")

    def test_creation_never_overwrites_existing_identity(self):
        existing = self.path.read_bytes()
        with self.assertRaises(CryptoError):
            Vault.create(self.path, "outra senha local")
        self.assertEqual(self.path.read_bytes(), existing)

    def test_short_password_is_rejected(self):
        target = self.path.parent / "new.json"
        with self.assertRaises(CryptoError):
            Vault.create(target, "curta")
        self.assertFalse(target.exists())

    def test_auth_copy_does_not_mutate_saved_state(self):
        self.vault.save_auth({"nested": {"token": "one"}})
        exposed = self.vault.auth
        exposed["nested"]["token"] = "two"
        self.assertEqual(self.vault.auth["nested"]["token"], "one")

    def test_failed_atomic_save_preserves_old_vault_and_auth(self):
        self.vault.save_auth({"token": "old"})
        old_bytes = self.path.read_bytes()
        with patch("piixelverso.piixelfone.crypto.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.vault.save_auth({"token": "new"})
        self.assertEqual(self.path.read_bytes(), old_bytes)
        self.assertEqual(self.vault.auth, {"token": "old"})
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_vault_rejects_extra_kdf_parameters_and_oversize_before_hashing(self):
        outer = json.loads(self.path.read_text())
        outer["memlimit"] = 2**50
        self.path.write_text(json.dumps(outer))
        with patch("piixelverso.piixelfone.crypto.pwhash.argon2id.kdf") as kdf:
            with self.assertRaises(CryptoError):
                Vault.unlock(self.path, "senha local segura")
            kdf.assert_not_called()
        self.path.write_bytes(b" " * (MAX_VAULT_BYTES + 1))
        with patch("piixelverso.piixelfone.crypto.pwhash.argon2id.kdf") as kdf:
            with self.assertRaises(CryptoError):
                Vault.unlock(self.path, "senha local segura")
            kdf.assert_not_called()


if __name__ == "__main__":
    unittest.main()
