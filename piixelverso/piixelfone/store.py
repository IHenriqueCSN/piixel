"""Local Piixelfone history, encrypted with a key kept in the password vault.

Connections belong to individual operations so the GUI and the network worker
never share SQLite connection objects.  Only routing IDs and delivery state are
indexed in clear text; contacts and complete message records are authenticated
with SecretBox before being written to disk.
"""
from __future__ import annotations

import base64
import binascii
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterator

from .crypto import CryptoError, seal_local, unseal_local


MAX_RECORD_BYTES = 512 * 1024
MAX_CIPHERTEXT_BYTES = 768 * 1024
MAX_CONTACT_BYTES = 8192
_DIRECTIONS = {"incoming", "outgoing"}
_STATUSES = {"queued", "sent", "delivered", "received", "rejected"}
_CONTACT_STATES = {"pending", "accepted", "declined"}
_STATUS_RANK = {"queued": 0, "sent": 1, "received": 1, "delivered": 2, "rejected": 2}


class StoreError(ValueError):
    """The local history cannot be read or safely updated."""


def _identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128 or "\x00" in value:
        raise StoreError(f"Identificador de {name} inválido.")
    return value


def _json_copy(record: object, maximum: int) -> dict:
    if not isinstance(record, dict):
        raise StoreError("Registro local inválido.")
    try:
        encoded = json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > maximum:
            raise StoreError("O registro excede o limite do histórico local.")
        return json.loads(encoded)
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, StoreError):
            raise
        raise StoreError("Registro local inválido.") from error


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise StoreError("Data da mensagem inválida.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as error:
        raise StoreError("Data da mensagem inválida.") from error


def _contact(record: object) -> dict:
    result = _json_copy(record, MAX_CONTACT_BYTES)
    _identifier(result.get("user_id"), "contato")
    number = result.get("number")
    if not isinstance(number, str) or len(number) > 16 or not number.replace(" ", "").isdigit():
        raise StoreError("Número do contato inválido.")
    digits = number.replace(" ", "")
    if len(digits) != 6 or digits[0] == "0" or not digits.isascii():
        raise StoreError("Número do contato inválido.")
    result["number"] = digits
    key = result.get("public_key")
    try:
        if not isinstance(key, str) or len(key) != 44 or len(base64.b64decode(key, validate=True)) != 32:
            raise StoreError("Chave pública do contato inválida.")
    except (binascii.Error, ValueError) as error:
        if isinstance(error, StoreError):
            raise
        raise StoreError("Chave pública do contato inválida.") from error
    if (not isinstance(result.get("state"), str) or result["state"] not in _CONTACT_STATES
            or type(result.get("incoming")) is not bool):
        raise StoreError("Estado do contato inválido.")
    return result


def _message(record: object) -> dict:
    result = _json_copy(record, MAX_RECORD_BYTES)
    _identifier(result.get("id"), "mensagem")
    _identifier(result.get("peer_id"), "contato")
    if (not isinstance(result.get("direction"), str) or result["direction"] not in _DIRECTIONS
            or not isinstance(result.get("status"), str) or result["status"] not in _STATUSES):
        raise StoreError("Estado da mensagem inválido.")
    if result["direction"] == "incoming" and result["status"] not in {"received", "delivered", "rejected"}:
        raise StoreError("Estado da mensagem recebida inválido.")
    if result["direction"] == "outgoing" and result["status"] == "received":
        raise StoreError("Estado da mensagem enviada inválido.")
    _timestamp(result.get("created_at"))
    if "text" in result and (not isinstance(result["text"], str) or len(result["text"]) > 150):
        raise StoreError("A mensagem deve ter no máximo 150 caracteres.")
    for field in ("filename", "data", "payload", "sender", "recipient"):
        if field in result and not isinstance(result[field], str):
            raise StoreError("Conteúdo da mensagem inválido.")
    return result


class Store:
    def __init__(self, path: Path, storage_key: bytes):
        if not isinstance(storage_key, bytes) or len(storage_key) != 32:
            raise StoreError("Chave do histórico local inválida.")
        self.path = Path(path)
        self._key = storage_key
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._restrict_permissions(self.path.parent, 0o700)
            with self._connection(write=True) as connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1):
                    raise StoreError("Esta versão do histórico exige uma versão mais recente do Piixel.")
                connection.execute("CREATE TABLE IF NOT EXISTS metadata (name TEXT PRIMARY KEY, sealed TEXT NOT NULL)")
                connection.execute("CREATE TABLE IF NOT EXISTS contacts (user_id TEXT PRIMARY KEY, sealed TEXT NOT NULL)")
                connection.execute("""CREATE TABLE IF NOT EXISTS messages (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    peer_id TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    status TEXT NOT NULL,
                    sealed TEXT NOT NULL
                )""")
                connection.execute("CREATE INDEX IF NOT EXISTS messages_peer ON messages(peer_id, sequence)")
                connection.execute("CREATE INDEX IF NOT EXISTS messages_delivery ON messages(direction, status, sequence)")
                check = connection.execute("SELECT sealed FROM metadata WHERE name = 'key_check'").fetchone()
                if check is None:
                    connection.execute("INSERT INTO metadata(name, sealed) VALUES('key_check', ?)",
                                       (self._seal({"piixelfone_store": 1}),))
                elif self._unseal(check[0]) != {"piixelfone_store": 1}:
                    raise StoreError("Não foi possível verificar o histórico local.")
                connection.execute("PRAGMA user_version = 1")
                if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise StoreError("O histórico local está danificado.")
            self._restrict_permissions(self.path, 0o600)
        except OSError as error:
            raise StoreError("Não foi possível preparar o histórico local.") from error

    @staticmethod
    def _restrict_permissions(path: Path, mode: int) -> None:
        # Windows ACLs remain controlled by the user's profile directory.
        if os.name != "nt":
            path.chmod(mode)

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            connection = sqlite3.connect(self.path, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA secure_delete = ON")
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if write:
                connection.commit()
        except (sqlite3.Error, OSError) as error:
            if connection is not None:
                connection.rollback()
            raise StoreError("Não foi possível acessar o histórico local.") from error
        except BaseException:
            if connection is not None:
                connection.rollback()
            raise
        finally:
            if connection is not None:
                connection.close()

    def _seal(self, value: dict) -> str:
        try:
            return seal_local(self._key, value)
        except CryptoError as error:
            raise StoreError("Não foi possível proteger o histórico local.") from error

    def _unseal(self, sealed: object) -> dict:
        if not isinstance(sealed, str) or len(sealed) > MAX_CIPHERTEXT_BYTES:
            raise StoreError("O histórico local está danificado.")
        try:
            return unseal_local(self._key, sealed)
        except CryptoError as error:
            raise StoreError("Não foi possível desbloquear o histórico local; a chave é diferente ou os dados estão danificados.") from error

    def _read_contact(self, row: sqlite3.Row) -> dict:
        contact = _contact(self._unseal(row["sealed"]))
        if contact["user_id"] != row["user_id"]:
            raise StoreError("O histórico de contatos está danificado.")
        return contact

    def _read_message(self, row: sqlite3.Row) -> dict:
        record = _message(self._unseal(row["sealed"]))
        if any(record[field] != row[field] for field in ("id", "peer_id", "direction", "status")):
            raise StoreError("O histórico de mensagens está danificado.")
        return record

    def contacts(self) -> list[dict]:
        with self._connection() as connection:
            result = [self._read_contact(row) for row in connection.execute("SELECT * FROM contacts ORDER BY user_id")]
        return sorted(result, key=lambda item: (item["number"], item["user_id"]))

    def contact(self, user_id: str) -> dict | None:
        _identifier(user_id, "contato")
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM contacts WHERE user_id = ?", (user_id,)).fetchone()
            return None if row is None else self._read_contact(row)

    def put_contact(self, contact: dict) -> None:
        record = _contact(contact)
        with self._connection(write=True) as connection:
            row = connection.execute("SELECT * FROM contacts WHERE user_id = ?", (record["user_id"],)).fetchone()
            if row is not None and self._read_contact(row)["public_key"] != record["public_key"]:
                raise StoreError("A chave de segurança deste contato mudou. O envio foi bloqueado; confirme a identidade do contato.")
            connection.execute("""INSERT INTO contacts(user_id, sealed) VALUES(?, ?)
                ON CONFLICT(user_id) DO UPDATE SET sealed = excluded.sealed""",
                               (record["user_id"], self._seal(record)))

    def _messages(self, clause: str = "", parameters: tuple = ()) -> list[dict]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM messages " + clause + " ORDER BY sequence", parameters)
            result = [self._read_message(row) for row in rows]
        # The stable sort preserves insertion order when server timestamps tie.
        return sorted(result, key=lambda item: _timestamp(item["created_at"]))

    def messages(self, peer_id: str) -> list[dict]:
        _identifier(peer_id, "contato")
        return self._messages("WHERE peer_id = ?", (peer_id,))

    def all_messages(self) -> list[dict]:
        return self._messages()

    def message(self, message_id: str) -> dict | None:
        _identifier(message_id, "mensagem")
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
            return None if row is None else self._read_message(row)

    def put_message(self, record: dict) -> None:
        value = _message(record)
        with self._connection(write=True) as connection:
            row = connection.execute("SELECT * FROM messages WHERE id = ?", (value["id"],)).fetchone()
            if row is None:
                connection.execute("""INSERT INTO messages(id, peer_id, direction, status, sealed)
                    VALUES(?, ?, ?, ?, ?)""", (value["id"], value["peer_id"], value["direction"],
                                               value["status"], self._seal(value)))
                return
            previous = self._read_message(row)
            if {key: item for key, item in previous.items() if key != "status"} != {
                key: item for key, item in value.items() if key != "status"
            }:
                raise StoreError("Já existe uma mensagem diferente com este identificador.")
            self._update_status(connection, row, value["status"])

    def _update_status(self, connection: sqlite3.Connection, row: sqlite3.Row, status: str) -> None:
        previous = self._read_message(row)
        if not isinstance(status, str) or status not in _STATUSES:
            raise StoreError("Estado da mensagem inválido.")
        if previous["status"] == status:
            return
        if _STATUS_RANK[status] < _STATUS_RANK[previous["status"]]:
            return
        if previous["status"] in {"delivered", "rejected"}:
            return
        previous["status"] = status
        _message(previous)
        connection.execute("UPDATE messages SET status = ?, sealed = ? WHERE id = ?",
                           (status, self._seal(previous), previous["id"]))

    def set_status(self, message_id: str, status: str) -> None:
        _identifier(message_id, "mensagem")
        with self._connection(write=True) as connection:
            row = connection.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
            if row is None:
                raise StoreError("Mensagem não encontrada no histórico local.")
            self._update_status(connection, row, status)

    def outbox(self) -> list[dict]:
        return self._messages("WHERE direction = 'outgoing' AND status = 'queued'")

    def pending_ack(self) -> list[dict]:
        return self._messages("WHERE direction = 'incoming' AND status = 'received'")
