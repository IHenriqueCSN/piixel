"""Authenticated Piixelfone encryption and a password-protected local vault.

Messages use libsodium's Curve25519/XSalsa20-Poly1305 ``Box``. Identity keys
are static: this provides authenticated encryption, but no forward secrecy.
The service must pin and verify the peer's public key before calling these
functions; this module cannot authenticate a server-provided directory entry.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from nacl import exceptions, pwhash, utils
from nacl.bindings import crypto_box_BOXZEROBYTES
from nacl.public import Box, PrivateKey, PublicKey
from nacl.secret import SecretBox


MAX_JSON_BYTES = 256 * 1024
MAX_LOCAL_JSON_BYTES = 1024 * 1024
MAX_VAULT_BYTES = 64 * 1024
_BOX_OVERHEAD = Box.NONCE_SIZE + crypto_box_BOXZEROBYTES
_LOCAL_OVERHEAD = SecretBox.NONCE_SIZE + SecretBox.MACBYTES
_VAULT_VERSION = 1
# These are deliberately not loaded from the vault file. An untrusted file
# must not select arbitrarily expensive password hashing parameters.
_KDF_OPSLIMIT = pwhash.argon2id.OPSLIMIT_INTERACTIVE
_KDF_MEMLIMIT = pwhash.argon2id.MEMLIMIT_INTERACTIVE


class CryptoError(ValueError):
    """Invalid keys, ciphertext, password, or vault contents."""


def _encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _decode(value: str, *, size: int | None = None, maximum: int = MAX_JSON_BYTES + 64) -> bytes:
    if not isinstance(value, str) or len(value) > ((maximum + 2) // 3) * 4:
        raise CryptoError("Dados criptográficos inválidos.")
    try:
        result = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error, UnicodeEncodeError) as error:
        raise CryptoError("Dados criptográficos inválidos.") from error
    if len(result) > maximum or (size is not None and len(result) != size):
        raise CryptoError("Tamanho de chave ou mensagem inválido.")
    if _encode(result) != value:
        raise CryptoError("Codificação criptográfica inválida.")
    return result


def _json_bytes(payload: dict[str, Any], *, maximum: int = MAX_JSON_BYTES) -> bytes:
    if not isinstance(payload, dict):
        raise CryptoError("A mensagem deve ser um objeto.")
    try:
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                             sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise CryptoError("Conteúdo de mensagem inválido.") from error
    if len(encoded) > maximum:
        raise CryptoError("A mensagem excede o tamanho permitido.")
    return encoded


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CryptoError("A mensagem contém campos duplicados.")
        result[key] = value
    return result


def _reject_constant(_value):
    raise CryptoError("A mensagem contém um número inválido.")


def _json_object(data: bytes, *, maximum: int = MAX_JSON_BYTES) -> dict:
    if len(data) > maximum:
        raise CryptoError("A mensagem excede o tamanho permitido.")
    try:
        result = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object,
                            parse_constant=_reject_constant)
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise CryptoError("Conteúdo de mensagem inválido.") from error
    if not isinstance(result, dict):
        raise CryptoError("A mensagem deve ser um objeto.")
    return result


class Identity:
    """A Curve25519 identity whose private key stays on this device."""

    __slots__ = ("_private",)

    def __init__(self, private: PrivateKey):
        self._private = private

    @classmethod
    def generate(cls) -> Identity:
        return cls(PrivateKey.generate())

    @classmethod
    def from_private(cls, private_b64: str) -> Identity:
        return cls(PrivateKey(_decode(private_b64, size=PrivateKey.SIZE, maximum=PrivateKey.SIZE)))

    @property
    def private_key_b64(self) -> str:
        return _encode(bytes(self._private))

    @property
    def public_key_b64(self) -> str:
        return _encode(bytes(self._private.public_key))


def fingerprint(public_b64: str) -> str:
    """Full SHA-256 fingerprint for comparison using a trusted channel."""
    raw = _decode(public_b64, size=PublicKey.SIZE, maximum=PublicKey.SIZE)
    digest = hashlib.sha256(raw).hexdigest().upper()
    return " ".join(digest[index:index + 4] for index in range(0, len(digest), 4))


def _box(identity: Identity, peer_public_b64: str) -> Box:
    raw = _decode(peer_public_b64, size=PublicKey.SIZE, maximum=PublicKey.SIZE)
    try:
        return Box(identity._private, PublicKey(raw))
    except (exceptions.CryptoError, ValueError, TypeError) as error:
        raise CryptoError("Chave pública inválida.") from error


def seal(identity: Identity, peer_public_b64: str, payload: dict) -> str:
    """Encrypt an object for the peer with a fresh random nonce."""
    cleartext = _json_bytes(payload)
    try:
        return _encode(bytes(_box(identity, peer_public_b64).encrypt(cleartext)))
    except exceptions.CryptoError as error:
        raise CryptoError("Não foi possível criptografar a mensagem.") from error


def unseal(identity: Identity, peer_public_b64: str, sealed_b64: str) -> dict:
    ciphertext = _decode(sealed_b64, maximum=MAX_JSON_BYTES + _BOX_OVERHEAD)
    if len(ciphertext) < _BOX_OVERHEAD:
        raise CryptoError("Mensagem criptografada incompleta.")
    try:
        cleartext = _box(identity, peer_public_b64).decrypt(ciphertext)
    except exceptions.CryptoError as error:
        raise CryptoError("A autenticidade da mensagem não pôde ser verificada.") from error
    return _json_object(cleartext)


def _local_box(key: bytes) -> SecretBox:
    if not isinstance(key, bytes) or len(key) != SecretBox.KEY_SIZE:
        raise CryptoError("Chave local inválida.")
    return SecretBox(key)


def seal_local(key: bytes, payload: dict) -> str:
    return _encode(bytes(_local_box(key).encrypt(_json_bytes(payload, maximum=MAX_LOCAL_JSON_BYTES))))


def unseal_local(key: bytes, sealed_b64: str) -> dict:
    ciphertext = _decode(sealed_b64, maximum=MAX_LOCAL_JSON_BYTES + _LOCAL_OVERHEAD)
    if len(ciphertext) < _LOCAL_OVERHEAD:
        raise CryptoError("Dados locais incompletos.")
    try:
        return _json_object(_local_box(key).decrypt(ciphertext), maximum=MAX_LOCAL_JSON_BYTES)
    except exceptions.CryptoError as error:
        raise CryptoError("Não foi possível verificar os dados locais.") from error


def _password_key(password: str, salt: bytes, *, creating: bool = False) -> bytes:
    if not isinstance(password, str) or (creating and len(password) < 8):
        raise CryptoError("Use uma senha local com pelo menos 8 caracteres.")
    if len(password) > 1024:
        raise CryptoError("A senha local é muito longa.")
    try:
        return pwhash.argon2id.kdf(SecretBox.KEY_SIZE, password.encode("utf-8"), salt,
                                  opslimit=_KDF_OPSLIMIT, memlimit=_KDF_MEMLIMIT)
    except (ValueError, UnicodeError, exceptions.CryptoError) as error:
        raise CryptoError("Não foi possível proteger o cofre local.") from error


def _atomic_write(path: Path, data: bytes, *, exclusive: bool = False) -> None:
    """Replace fully written bytes, or atomically create without overwriting."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        # mkstemp already creates mode 0600; explicit fchmod keeps that invariant
        # visible on POSIX without relying on the user's umask.
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            # A link is atomic and cannot replace an existing identity. Both
            # paths are on the same filesystem (also supported on Windows NTFS).
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
    finally:
        if descriptor != -1:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


class Vault:
    """An unlocked in-memory session of a password-encrypted local vault.

    Only salt and ciphertext are stored on disk. The password is discarded
    after Argon2id derivation; the derived key remains in memory while unlocked.
    Losing the file or its password loses access to this cryptographic identity.
    """

    def __init__(self, path: Path, salt: bytes, key: bytes, identity: Identity,
                 storage_key: bytes, auth: dict):
        self._path = path
        self._salt = salt
        self._key = key
        self._identity = identity
        self._storage_key = storage_key
        self._auth = _json_object(_json_bytes(auth))

    @property
    def identity(self) -> Identity:
        return self._identity

    @property
    def storage_key(self) -> bytes:
        return self._storage_key

    @property
    def auth(self) -> dict:
        # Do not let an unsaved in-place mutation silently change session state.
        return _json_object(_json_bytes(self._auth))

    @classmethod
    def create(cls, path: Path, password: str) -> Vault:
        path = Path(path)
        if path.exists():
            raise CryptoError("Já existe um cofre Piixelfone neste local.")
        salt = utils.random(pwhash.argon2id.SALTBYTES)
        key = _password_key(password, salt, creating=True)
        vault = cls(path, salt, key, Identity.generate(), utils.random(SecretBox.KEY_SIZE), {})
        try:
            _atomic_write(path, vault._serialized(), exclusive=True)
        except FileExistsError as error:
            raise CryptoError("Já existe um cofre Piixelfone neste local.") from error
        return vault

    @classmethod
    def unlock(cls, path: Path, password: str) -> Vault:
        path = Path(path)
        with path.open("rb") as stream:
            data = stream.read(MAX_VAULT_BYTES + 1)
        outer = _json_object(data, maximum=MAX_VAULT_BYTES)
        if set(outer) != {"version", "salt", "ciphertext"} or type(outer["version"]) is not int or outer["version"] != _VAULT_VERSION:
            raise CryptoError("Formato de cofre Piixelfone inválido ou incompatível.")
        salt = _decode(outer["salt"], size=pwhash.argon2id.SALTBYTES,
                       maximum=pwhash.argon2id.SALTBYTES)
        key = _password_key(password, salt)
        try:
            inner = unseal_local(key, outer["ciphertext"])
        except CryptoError as error:
            raise CryptoError("Senha local incorreta ou cofre danificado.") from error
        if set(inner) != {"identity_private_key", "storage_key", "auth"} or not isinstance(inner["auth"], dict):
            raise CryptoError("Conteúdo de cofre Piixelfone inválido.")
        return cls(path, salt, key, Identity.from_private(inner["identity_private_key"]),
                   _decode(inner["storage_key"], size=SecretBox.KEY_SIZE,
                           maximum=SecretBox.KEY_SIZE), inner["auth"])

    def _serialized(self, *, auth: dict | None = None) -> bytes:
        payload = {
            "identity_private_key": self.identity.private_key_b64,
            "storage_key": _encode(self.storage_key),
            "auth": self._auth if auth is None else auth,
        }
        result = _json_bytes({"version": _VAULT_VERSION, "salt": _encode(self._salt),
                              "ciphertext": seal_local(self._key, payload)}, maximum=MAX_VAULT_BYTES)
        return result

    def save_auth(self, auth: dict) -> None:
        replacement = _json_object(_json_bytes(auth))
        _atomic_write(self._path, self._serialized(auth=replacement))
        self._auth = replacement

    def save(self) -> None:
        _atomic_write(self._path, self._serialized())
