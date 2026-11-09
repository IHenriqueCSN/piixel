"""Bounded HTTPS transport for Supabase Auth and encrypted mailbox RPCs.

Only public API keys and the signed user's access token leave this layer.
Application passwords, private encryption keys and cleartext messages never do.
"""
from __future__ import annotations

import json
import math
import re
import socket
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from .config import Config


TIMEOUT_SECONDS = 8
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REQUEST_BYTES = 256 * 1024
_RPC_NAME = re.compile(r"pii_[a-z_]+\Z")


class TransportError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, code: str = "connection"):
        super().__init__(message)
        self.status = status
        self.code = code
        self.user_message = message


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # urllib otherwise copies API/auth headers into redirected requests.
        return None


def _error(status: int, body: bytes = b"") -> TransportError:
    code = ""
    try:
        document = json.loads(body)
        if isinstance(document, dict):
            candidate = document.get("error_code", document.get("code", ""))
            if isinstance(candidate, str) and len(candidate) < 100:
                code = candidate
    except (ValueError, UnicodeError, RecursionError):
        pass
    # Never display server message/details/hint: they can echo tokens or the
    # encrypted envelope. Match a small set of machine-readable error codes.
    if code == "anonymous_provider_disabled":
        return TransportError(
            "O acesso anônimo está desativado no servidor. Contate o administrador do sistema.",
            status=status, code="anonymous_disabled",
        )
    if code in ("captcha_failed", "captcha_verification_failed"):
        return TransportError(
            "O servidor exige uma verificação CAPTCHA que esta versão não oferece. "
            "Contate o administrador do sistema.", status=status, code="captcha_required",
        )
    if status == 401:
        return TransportError(
            "A conexão não foi autorizada. Verifique a chave pública e a sessão do Piixelfone.",
            status=status, code="unauthorized",
        )
    if status == 429 or code in ("over_request_rate_limit", "over_email_send_rate_limit", "P0429"):
        return TransportError(
            "Muitas tentativas em pouco tempo. Aguarde um momento antes de tentar novamente.",
            status=status, code="rate_limit",
        )
    if status in (404, 503) or code in ("PGRST202", "PGRST205", "42P01", "42883"):
        return TransportError(
            "O serviço Piixelfone está indisponível ou ainda não foi configurado. "
            "Contate o administrador do sistema; o projeto também pode estar pausado.",
            status=status, code="service_unavailable",
        )
    if status == 403:
        return TransportError(
            "O servidor não permitiu esta operação. Verifique a aceitação do contato "
            "ou contate o administrador do sistema.", status=status, code="forbidden",
        )
    if 300 <= status < 400:
        return TransportError(
            "O servidor tentou redirecionar a conexão. Verifique a URL do projeto.",
            status=status, code="redirect",
        )
    if status == 409:
        return TransportError(
            "A operação está em conflito com os dados do servidor. Atualize a conversa e tente novamente.",
            status=status, code="conflict",
        )
    if status >= 500:
        return TransportError(
            "O servidor está temporariamente indisponível. Tentaremos novamente ao reconectar.",
            status=status, code="server_error",
        )
    return TransportError(
        "O servidor recusou a operação. Verifique os dados e a configuração do Piixelfone.",
        status=status, code="request_rejected",
    )


class Transport:
    """Synchronous transport; callers run this on the module's network worker.

    ``requester`` follows ``urlopen(request, timeout=...)`` for isolated tests.
    The production opener refuses every redirect and uses inherited TLS trust.
    """

    def __init__(self, config: Config, *, requester: Callable | None = None):
        self.config = config.validate()
        self.auth: dict = {}
        self._requester = requester or build_opener(_NoRedirects()).open

    def set_auth(self, auth: dict) -> None:
        if not auth:
            self.auth = {}
            return
        self.auth = self._normalize_auth(auth)

    @staticmethod
    def _normalize_auth(document: object) -> dict:
        try:
            if not isinstance(document, dict):
                raise ValueError
            access = document["access_token"]
            refresh = document["refresh_token"]
            if any(not isinstance(token, str) or not token or not token.isascii() or len(token) > 16_384
                   or any(character.isspace() for character in token) for token in (access, refresh)):
                raise ValueError
            user_id = str(UUID(document["user"]["id"]))
            expires = document.get("expires_at")
            if expires is None:
                expires_in = document.get("expires_in", 3600)
                if isinstance(expires_in, bool) or not isinstance(expires_in, (int, float)):
                    raise ValueError
                expires = time.time() + expires_in
            if isinstance(expires, bool) or not isinstance(expires, (int, float)) or not math.isfinite(expires):
                raise ValueError
            if expires < 0 or expires > 253402300799:
                raise ValueError
            return {"access_token": access, "refresh_token": refresh,
                    "user": {"id": user_id}, "expires_at": int(expires)}
        except (ValueError, KeyError, TypeError, AttributeError):
            raise TransportError("O servidor retornou uma sessão inválida.", code="invalid_response") from None

    def sign_up(self) -> dict:
        """Create one anonymous Auth identity; only used when no vault auth exists.

        Official auth-js signInAnonymously sends {data:{}} to POST /signup:
        https://github.com/supabase/supabase-js/blob/master/packages/core/auth-js/src/GoTrueClient.ts
        """
        auth = self._normalize_auth(self._post("/auth/v1/signup", {"data": {}}, authenticated=False))
        self.auth = auth
        return dict(auth)

    def refresh(self, refresh_token: str) -> dict:
        if (not isinstance(refresh_token, str) or not refresh_token
                or len(refresh_token) > 16_384 or any(character.isspace() for character in refresh_token)):
            raise TransportError("Não foi possível recuperar a sessão local.", code="invalid_session")
        auth = self._normalize_auth(self._post(
            "/auth/v1/token?grant_type=refresh_token", {"refresh_token": refresh_token}, authenticated=False
        ))
        self.auth = auth
        return dict(auth)

    def rpc(self, name: str, params: dict | None = None):
        if not isinstance(name, str) or not _RPC_NAME.fullmatch(name):
            raise TransportError("Operação de conexão inválida.", code="invalid_request")
        if params is not None and not isinstance(params, dict):
            raise TransportError("Parâmetros de conexão inválidos.", code="invalid_request")
        return self._post("/rest/v1/rpc/" + name, params or {}, authenticated=True)

    def _post(self, path: str, document: dict, *, authenticated: bool):
        try:
            body = json.dumps(document, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise TransportError("Dados de conexão inválidos.", code="invalid_request") from None
        if len(body) > MAX_REQUEST_BYTES:
            raise TransportError("O conteúdo excede o limite permitido pelo Piixelfone.", code="request_too_large")
        headers = {"apikey": self.config.public_key, "Content-Type": "application/json",
                   "Accept": "application/json", "User-Agent": "Piixel-Piixelfone/1"}
        if authenticated:
            access_token = self.auth.get("access_token")
            if not access_token:
                raise TransportError("Conecte o Piixelfone antes de continuar.", code="missing_session")
            headers["Authorization"] = "Bearer " + access_token
        request = Request(self.config.url + path, data=body, headers=headers, method="POST")
        try:
            with self._requester(request, timeout=TIMEOUT_SECONDS) as response:
                status = getattr(response, "status", 200)
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise TransportError("A resposta do servidor excede o limite permitido.", code="response_too_large")
                if status < 200 or status >= 300:
                    raise _error(status, raw)
        except HTTPError as error:
            try:
                error_body = error.read(32_769)
            except (OSError, ValueError):
                error_body = b""
            finally:
                error.close()
            raise _error(error.code, error_body[:32_768]) from None
        except (socket.timeout, TimeoutError):
            raise TransportError(
                "A conexão demorou para responder. Verifique a internet e tente novamente.", code="timeout"
            ) from None
        except (URLError, OSError):
            raise TransportError(
                "Não foi possível conectar ao Piixelfone. Verifique sua conexão com a internet.", code="connection"
            ) from None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError, RecursionError):
            raise TransportError("O servidor retornou uma resposta inválida.", code="invalid_response") from None
