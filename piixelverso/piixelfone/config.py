"""Public Piixelfone connection settings; no administrative credentials belong here."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit


DEFAULT_URL = "https://ukxwkgzwokzllprivknn.supabase.co"
MAX_CONFIG_BYTES = 16_384


class ConfigError(ValueError):
    """A missing or invalid public connection setting."""


@dataclass(frozen=True)
class Config:
    url: str = DEFAULT_URL
    public_key: str = ""

    def __post_init__(self):
        if isinstance(self.url, str):
            object.__setattr__(self, "url", self.url.strip().rstrip("/"))
        if isinstance(self.public_key, str):
            object.__setattr__(self, "public_key", self.public_key.strip())

    def validate(self) -> Config:
        if not isinstance(self.url, str) or len(self.url) > 2048:
            raise ConfigError("Informe uma URL HTTPS válida para o servidor.")
        if any(ord(character) <= 32 for character in self.url):
            raise ConfigError("Informe uma URL HTTPS válida para o servidor.")
        try:
            parsed = urlsplit(self.url)
            valid = (
                parsed.scheme == "https" and parsed.hostname
                and parsed.username is None and parsed.password is None
                and not parsed.path and not parsed.query and not parsed.fragment
                and parsed.port in (None, 443)
                and re.fullmatch(r"[A-Za-z0-9.-]+", parsed.hostname)
                and not parsed.hostname.startswith((".", "-"))
                and not parsed.hostname.endswith((".", "-"))
                and ".." not in parsed.hostname
            )
        except ValueError:
            valid = False
        if not valid:
            raise ConfigError("Informe apenas a URL HTTPS do projeto, sem caminhos ou credenciais.")
        if not isinstance(self.public_key, str) or not self.public_key:
            raise ConfigError(
                "Para usar o Piixelfone, informe a chave pública de conexão. "
                "Se não souber qual usar, entre em contato com o administrador do sistema."
            )
        key = self.public_key
        if len(key) > 8192 or any(character.isspace() for character in key):
            raise ConfigError("A chave pública de conexão é inválida.")
        if key.startswith("sb_secret_") or "service_role" in key.lower():
            raise ConfigError("Use somente a chave pública. Chaves administrativas não são permitidas.")
        if re.fullmatch(r"sb_publishable_[A-Za-z0-9_-]{10,}", key):
            return self
        # Reading the legacy JWT role classifies the supplied key. The server
        # still verifies its signature; this client never treats it as proof.
        try:
            parts = key.split(".")
            if len(parts) != 3 or any(not re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in parts):
                raise ValueError
            decoded = base64.b64decode(
                parts[1] + "=" * (-len(parts[1]) % 4), altchars=b"-_", validate=True
            )
            payload = json.loads(decoded)
            if not isinstance(payload, dict) or payload.get("role") != "anon":
                raise ValueError
        except (ValueError, UnicodeError, TypeError, RecursionError):
            raise ConfigError(
                "Use uma chave Publishable (sb_publishable_…) ou a chave legada anon public. "
                "Chaves administrativas não são permitidas."
            ) from None
        return self


def load_config(path: str | Path) -> Config:
    path = Path(path)
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_CONFIG_BYTES + 1)
    except FileNotFoundError:
        return Config()
    except OSError:
        raise ConfigError("Não foi possível ler a configuração do Piixelfone.") from None
    try:
        if len(raw) > MAX_CONFIG_BYTES:
            raise ValueError
        document = json.loads(raw)
        if not isinstance(document, dict) or document.get("version") != 1:
            raise ValueError
        config = Config(document["url"], document["public_key"])
        return config.validate()
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise ConfigError(
            "A configuração do Piixelfone é inválida. Informe novamente os dados de conexão."
        ) from None


def save_config(path: str | Path, config: Config) -> None:
    config.validate()
    path = Path(path)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps({
            "version": 1, "url": config.url, "public_key": config.public_key,
        }, ensure_ascii=False).encode("utf-8")
        descriptor, temporary = tempfile.mkstemp(prefix=".connection-", suffix=".tmp", dir=path.parent)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError:
        raise ConfigError("Não foi possível salvar a configuração do Piixelfone.") from None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass
