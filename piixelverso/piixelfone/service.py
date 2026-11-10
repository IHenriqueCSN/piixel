"""Application use cases for the encrypted mailbox (no GUI or network threads)."""
from __future__ import annotations

import base64
import binascii
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import time
from uuid import UUID, uuid4

from ..format import MAX_FILE_SIZE, decode_design
from .config import Config, ConfigError, load_config, save_config
from .crypto import CryptoError, Vault, fingerprint, seal, unseal
from .store import Store
from .transport import Transport, TransportError

MAX_ENVELOPE_BYTES = 190000


class PhoneError(ValueError):
    """An actionable message that may be presented directly to the user."""


def _uuid(value) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as error:
        raise PhoneError("O servidor retornou uma identificação inválida.") from error


def _number(value) -> str:
    number = str(value).replace(" ", "")
    if len(number) != 6 or not number.isascii() or not number.isdecimal() or number[0] == "0":
        raise PhoneError("Informe um Piixelfone com seis dígitos, como 584 093.")
    return number


def _filename(value) -> str:
    if (not isinstance(value, str) or not value or len(value) > 180
            or any(ord(char) < 32 for char in value)
            or any(char in value for char in '/\\:*?"<>|')
            or value in (".", "..") or value.endswith((" ", "."))
            or not value.lower().endswith(".pii")):
        raise PhoneError("O nome do anexo .pii é inválido.")
    return value


class PhoneService:
    """Single-worker service. Persist before send/ACK; UUIDs make retries safe."""

    def __init__(self, data_dir: Path, *, transport_factory=Transport):
        self.data_dir = Path(data_dir)
        try:
            self.config = load_config(self.data_dir / "connection.json")
        except ConfigError:
            # A damaged public settings file must remain repairable in the UI.
            self.config = Config()
        self._transport_factory = transport_factory
        self._transport = None
        self._vault = None
        self._store = None
        self._profile = {}
        self._registered = False
        self._connected = False
        self._status = "Configure a conexão para começar."
        self._blocked_peers = set()

    @property
    def configured(self) -> bool:
        try:
            self.config.validate()
            return True
        except ValueError:
            return False

    @property
    def has_vault(self) -> bool:
        return (self.data_dir / "identity.vault").is_file()

    def configure(self, url: str, key: str) -> None:
        config = Config(url.strip(), key.strip()).validate()
        if self._vault and self._vault.auth.get("project_url", config.url) != config.url:
            raise PhoneError("Esta identidade pertence a outro servidor. Mantenha a URL original.")
        save_config(self.data_dir / "connection.json", config)
        self.config = config
        self._transport = None
        self._registered = False

    def unlock(self, password: str) -> dict:
        if not self.configured:
            raise PhoneError("Informe a chave pública de conexão antes de continuar.")
        path = self.data_dir / "identity.vault"
        if not self.has_vault and (self.data_dir / "history.sqlite3").exists():
            raise PhoneError(
                "O cofre da sua identidade não foi encontrado, mas há um histórico neste computador. "
                "Restaure o arquivo identity.vault original a partir de um backup para recuperar as conversas."
            )
        vault = Vault.unlock(path, password) if self.has_vault else Vault.create(path, password)
        if vault.auth.get("project_url", self.config.url) != self.config.url:
            raise PhoneError("Esta identidade pertence a outro servidor. Confira a URL da conexão.")
        self._vault = vault
        self._store = Store(self.data_dir / "history.sqlite3", vault.storage_key)
        self._profile = dict(vault.auth.get("profile") or {})
        self._transport = self._transport_factory(self.config)
        self._transport.set_auth(vault.auth)
        self._registered = False
        return self.sync()

    def _require_unlocked(self):
        if self._vault is None or self._store is None:
            raise PhoneError("Desbloqueie o Piixelfone com sua senha local.")

    def _save_auth(self, auth):
        user = auth.get("user") or {}
        user_id = _uuid(user.get("id"))
        previous = self._vault.auth.get("user") or {}
        if previous.get("id") and _uuid(previous["id"]) != user_id:
            raise PhoneError("A identidade do servidor mudou. A conexão foi interrompida.")
        saved = dict(auth)
        saved["project_url"] = self.config.url
        saved["profile"] = self._profile
        self._vault.save_auth(saved)
        self._transport.set_auth(saved)

    def _authenticate(self):
        auth = self._vault.auth
        if not auth.get("refresh_token"):
            self._save_auth(self._transport.sign_up())
        elif not auth.get("access_token") or float(auth.get("expires_at", 0)) < time.time() + 30:
            self._save_auth(self._transport.refresh(auth["refresh_token"]))

    def _rpc(self, name, params=None):
        try:
            return self._transport.rpc(name, params or {})
        except TransportError as error:
            if error.status != 401 or not self._vault.auth.get("refresh_token"):
                raise
            self._save_auth(self._transport.refresh(self._vault.auth["refresh_token"]))
            return self._transport.rpc(name, params or {})

    def _profile_data(self, row):
        if not isinstance(row, dict):
            raise PhoneError("O servidor retornou um contato inválido.")
        user_id = _uuid(row.get("user_id"))
        number = _number(row.get("number"))
        public_key = row.get("public_key")
        fingerprint(public_key)  # validates key encoding and length
        return {"user_id": user_id, "number": number, "public_key": public_key}

    def _connect(self):
        self._require_unlocked()
        if self._transport is None:
            self._transport = self._transport_factory(self.config)
            self._transport.set_auth(self._vault.auth)
        self._authenticate()
        if not self._registered:
            profile = self._profile_data(self._rpc("pii_register", {
                "p_public_key": self._vault.identity.public_key_b64,
            }))
            if (profile["user_id"] != _uuid(self._vault.auth["user"]["id"])
                    or profile["public_key"] != self._vault.identity.public_key_b64):
                raise PhoneError("A chave de identidade no servidor não confere. A conexão foi interrompida.")
            self._profile = profile
            self._save_auth(self._vault.auth)
            self._registered = True

    def _sync_contacts(self):
        rows = self._rpc("pii_contacts")
        if not isinstance(rows, list) or len(rows) > 1000:
            raise PhoneError("A lista de contatos retornada pelo servidor é inválida.")
        for row in rows:
            contact = self._profile_data(row)
            state = row.get("state")
            if state not in ("pending", "accepted", "declined") or type(row.get("incoming")) is not bool:
                raise PhoneError("O servidor retornou uma solicitação de contato inválida.")
            contact.update(state=state, incoming=row["incoming"])
            previous = self._store.contact(contact["user_id"])
            if previous and previous["public_key"] != contact["public_key"]:
                self._blocked_peers.add(contact["user_id"])
                raise PhoneError("A chave de um contato mudou. O envio foi bloqueado; verifique a identidade com essa pessoa.")
            self._store.put_contact(contact)

    def _peer(self, peer_id, *, accepted=True):
        peer_id = _uuid(peer_id)
        contact = self._store.contact(peer_id)
        if contact is None:
            raise PhoneError("Este contato não está na sua lista.")
        if peer_id in self._blocked_peers:
            raise PhoneError("A chave deste contato mudou. Verifique a identidade antes de continuar.")
        if accepted and contact["state"] != "accepted":
            raise PhoneError("O contato precisa aceitar a solicitação antes de receber mensagens.")
        return contact

    def sync(self) -> dict:
        self._require_unlocked()
        try:
            self._connect()
            self._sync_contacts()
            self._send_outbox()
            self._receive()
            self._acknowledge()
            self._statuses()
        except TransportError as error:
            self._connected = False
            self._status = f"{error} Mensagens na fila serão enviadas ao reconectar."
        except (PhoneError, CryptoError) as error:
            self._connected = False
            self._status = str(error)
        else:
            self._connected = True
            self._status = "Conectado · mensagens protegidas por criptografia de ponta a ponta."
        return self.snapshot()

    def _send_outbox(self):
        for message in self._store.outbox()[:30]:
            contact = self._store.contact(message["peer_id"])
            if not contact or contact["state"] != "accepted" or message["peer_id"] in self._blocked_peers:
                continue
            self._rpc("pii_send", {"p_id": message["id"], "p_recipient": message["peer_id"],
                                   "p_payload": message["payload"]})
            self._store.set_status(message["id"], "sent")

    def _receive(self):
        rows = self._rpc("pii_inbox")
        if not isinstance(rows, list) or len(rows) > 100:
            raise PhoneError("A fila recebida do servidor é inválida.")
        for row in rows:
            message_id = _uuid(row.get("id"))
            if self._store.message(message_id):
                continue  # local persistence happened before a previous lost ACK
            sender = _uuid(row.get("sender"))
            recipient = _uuid(row.get("recipient"))
            if recipient != self._profile["user_id"]:
                raise PhoneError("Foi recebida uma mensagem destinada a outra identidade.")
            peer = self._peer(sender)
            try:
                content = unseal(self._vault.identity, peer["public_key"], row.get("payload"))
                self._validate_content(content, message_id, sender, recipient)
            except (CryptoError, PhoneError, ValueError, TypeError, binascii.Error):
                # Never display unauthenticated content or call it delivered.
                self._rpc("pii_reject", {"p_id": message_id})
                continue
            record = dict(content)
            record.update(peer_id=sender, direction="incoming", status="received",
                          created_at=str(row.get("created_at") or ""))
            self._store.put_message(record)

    def _validate_content(self, content, message_id, sender, recipient):
        if (content.get("v") != 1 or content.get("id") != message_id
                or content.get("from") != sender or content.get("to") != recipient):
            raise PhoneError("A identificação da mensagem cifrada não confere.")
        kind = content.get("type")
        if kind == "text":
            text = content.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 150:
                raise PhoneError("As mensagens devem ter entre 1 e 150 caracteres.")
            if set(content) != {"v", "id", "from", "to", "type", "text"}:
                raise PhoneError("A mensagem contém campos inesperados.")
        elif kind == "file":
            _filename(content.get("filename"))
            encoded = content.get("data")
            if not isinstance(encoded, str) or len(encoded) > ((MAX_FILE_SIZE + 2) // 3) * 4:
                raise PhoneError("O anexo excede o tamanho permitido.")
            data = base64.b64decode(encoded, validate=True)
            if (len(data) > MAX_FILE_SIZE or len(data) != content.get("size")
                    or hashlib.sha256(data).hexdigest() != content.get("sha256")):
                raise PhoneError("O anexo recebido está corrompido.")
            decode_design(data)
            if set(content) != {"v", "id", "from", "to", "type", "filename", "data", "size", "sha256"}:
                raise PhoneError("O anexo contém campos inesperados.")
        else:
            raise PhoneError("Este tipo de mensagem não é compatível com o Piixelfone.")

    def _acknowledge(self):
        for message in self._store.pending_ack()[:100]:
            self._rpc("pii_ack", {"p_id": message["id"]})
            self._store.set_status(message["id"], "delivered")

    def _statuses(self):
        pending = [m for c in self._store.contacts() for m in self._store.messages(c["user_id"])
                   if m["direction"] == "outgoing" and m["status"] == "sent"]
        for start in range(0, len(pending), 100):
            rows = self._rpc("pii_statuses", {"p_ids": [m["id"] for m in pending[start:start + 100]]})
            if not isinstance(rows, list):
                raise PhoneError("O servidor retornou estados de entrega inválidos.")
            allowed = {m["id"] for m in pending[start:start + 100]}
            for row in rows:
                if row.get("id") not in allowed:
                    continue
                if row.get("rejected_at"):
                    self._store.set_status(row["id"], "rejected")
                elif row.get("delivered_at"):
                    self._store.set_status(row["id"], "delivered")

    def request_contact(self, number: str) -> dict:
        self._connect()
        peer = self._rpc("pii_lookup", {"p_number": _number(number)})
        if not peer:
            raise PhoneError("Piixelfone não encontrado. Confira o número com seu contato.")
        peer = self._profile_data(peer)
        if peer["user_id"] == self._profile["user_id"]:
            raise PhoneError("Este é o seu próprio Piixelfone.")
        previous = self._store.contact(peer["user_id"])
        if previous and previous["public_key"] != peer["public_key"]:
            raise PhoneError("A chave deste contato mudou. Verifique a identidade com essa pessoa.")
        self._rpc("pii_request", {"p_peer": peer["user_id"]})
        if not previous:
            self._store.put_contact(dict(peer, state="pending", incoming=False))
        return self.sync()

    def accept_contact(self, peer_id) -> dict:
        self._connect()
        peer = self._peer(peer_id, accepted=False)
        if peer["state"] != "pending" or not peer["incoming"]:
            raise PhoneError("Não há uma solicitação recebida para este contato.")
        self._rpc("pii_accept", {"p_peer": peer["user_id"]})
        return self.sync()

    def decline_contact(self, peer_id) -> dict:
        self._connect()
        peer = self._peer(peer_id, accepted=False)
        self._rpc("pii_decline", {"p_peer": peer["user_id"]})
        return self.sync()

    def _queue(self, peer_id, body):
        self._require_unlocked()
        peer = self._peer(peer_id)
        sender = _uuid((self._vault.auth.get("user") or {}).get("id"))
        content = dict(body, v=1, id=str(uuid4()), **{"from": sender, "to": peer["user_id"]})
        self._validate_content(content, content["id"], sender, peer["user_id"])
        payload = seal(self._vault.identity, peer["public_key"], content)
        if len(payload) > MAX_ENVELOPE_BYTES:
            raise PhoneError("O anexo excede o tamanho permitido para envio.")
        record = dict(content, peer_id=peer["user_id"], direction="outgoing", status="queued",
                      created_at=datetime.now(timezone.utc).isoformat(), payload=payload)
        self._store.put_message(record)
        return self.sync()

    def send_text(self, peer_id: str, text: str) -> dict:
        return self._queue(peer_id, {"type": "text", "text": text})

    def send_file(self, peer_id: str, path: str) -> dict:
        source = Path(path)
        filename = _filename(source.name)
        with source.open("rb") as stream:
            data = stream.read(MAX_FILE_SIZE + 1)
        if len(data) > MAX_FILE_SIZE:
            raise PhoneError("O arquivo .pii excede o tamanho máximo permitido.")
        decode_design(data)
        return self._queue(peer_id, {"type": "file", "filename": filename, "size": len(data),
                                   "sha256": hashlib.sha256(data).hexdigest(),
                                   "data": base64.b64encode(data).decode("ascii")})

    def regenerate_number(self) -> dict:
        self._connect()
        profile = self._profile_data(self._rpc("pii_regenerate"))
        if profile["user_id"] != self._profile["user_id"] or profile["public_key"] != self._profile["public_key"]:
            raise PhoneError("A identidade mudou durante a troca de número. A conexão foi interrompida.")
        self._profile = profile
        self._save_auth(self._vault.auth)
        return self.sync()

    def attachment(self, message_id: str) -> tuple[str, bytes]:
        self._require_unlocked()
        message = self._store.message(_uuid(message_id))
        if not message or message.get("type") != "file":
            raise PhoneError("Este anexo não está disponível no histórico local.")
        return _filename(message["filename"]), base64.b64decode(message["data"], validate=True)

    def snapshot(self) -> dict:
        contacts = []
        messages = []
        if self._store:
            for contact in self._store.contacts():
                visible = dict(contact)
                visible["fingerprint"] = fingerprint(contact["public_key"])
                if contact["user_id"] in self._blocked_peers:
                    visible["state"] = "blocked"
                contacts.append(visible)
                for message in self._store.messages(contact["user_id"]):
                    # Keep attachment bytes/ciphertext out of GUI snapshots.
                    messages.append({key: value for key, value in message.items()
                                     if key not in ("data", "payload")})
        number = self._profile.get("number", "")
        return {"number": f"{number[:3]} {number[3:]}" if number else "",
                "user_id": self._profile.get("user_id", ""), "contacts": contacts,
                "messages": messages, "connected": self._connected, "status": self._status,
                "fingerprint": fingerprint(self._vault.identity.public_key_b64) if self._vault else ""}
