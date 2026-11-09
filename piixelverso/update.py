"""Secure discovery and download of Piixel releases from GitHub."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Callable
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


REPOSITORY = "IHenriqueCSN/piixel"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MAX_RELEASE_BYTES = 1024 * 1024
MAX_CHECKSUM_BYTES = 4096
MAX_INSTALLER_BYTES = 512 * 1024 * 1024
_VERSION = re.compile(r"(?:0|[1-9][0-9]{0,4})(?:\.(?:0|[1-9][0-9]{0,4})){2}")
_SHA256 = re.compile(r"[0-9a-fA-F]{64}")


class UpdateError(RuntimeError):
    """A release could not be trusted, downloaded or interpreted."""


@dataclass(frozen=True)
class Release:
    version: str
    title: str
    notes: str
    installer_name: str
    installer_url: str
    checksum_url: str
    page_url: str


def parse_version(value: str, *, allow_v: bool = False) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise UpdateError("A versão publicada é inválida.")
    candidate = value[1:] if allow_v and value.startswith("v") else value
    if not _VERSION.fullmatch(candidate):
        raise UpdateError("A versão publicada deve usar o formato 1.2.3.")
    return tuple(map(int, candidate.split(".")))


def _https_url(value, label: str) -> str:
    if not isinstance(value, str) or len(value) > 4096:
        raise UpdateError(f"O endereço de {label} é inválido.")
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.netloc or parts.username or parts.password:
        raise UpdateError(f"O endereço de {label} não é HTTPS.")
    return value


def _read_response(response, limit: int) -> bytes:
    raw_length = response.headers.get("Content-Length")
    if raw_length:
        try:
            if int(raw_length) > limit:
                raise UpdateError("A resposta do servidor excede o tamanho permitido.")
        except ValueError as error:
            raise UpdateError("O servidor informou um tamanho inválido.") from error
    data = response.read(limit + 1)
    if len(data) > limit:
        raise UpdateError("A resposta do servidor excede o tamanho permitido.")
    final_url = getattr(response, "geturl", lambda: "https://github.com")()
    _https_url(final_url, "resposta")
    return data


class UpdateClient:
    def __init__(self, *, opener=None, timeout: float = 12.0):
        self._open = opener or urlopen
        self.timeout = timeout

    @staticmethod
    def _request(url: str, *, accept: str = "application/octet-stream") -> Request:
        return Request(
            _https_url(url, "atualização"),
            headers={
                "Accept": accept,
                "User-Agent": "Piixel-Updater",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    def _small_download(self, url: str, limit: int, *, accept: str) -> bytes:
        try:
            with self._open(self._request(url, accept=accept), timeout=self.timeout) as response:
                return _read_response(response, limit)
        except UpdateError:
            raise
        except (OSError, TimeoutError, ValueError) as error:
            raise UpdateError("Não foi possível acessar o servidor de atualizações.") from error

    def latest(self, current_version: str) -> Release | None:
        current = parse_version(current_version)
        raw = self._small_download(
            LATEST_RELEASE_URL, MAX_RELEASE_BYTES,
            accept="application/vnd.github+json",
        )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError) as error:
            raise UpdateError("O servidor retornou dados de atualização inválidos.") from error
        if not isinstance(payload, dict) or payload.get("draft") is not False:
            raise UpdateError("A publicação mais recente é inválida.")
        if payload.get("prerelease") is not False:
            return None
        tag = payload.get("tag_name")
        remote = parse_version(tag, allow_v=True)
        version = ".".join(map(str, remote))
        if remote <= current:
            return None
        installer_name = f"Piixel-Setup-{version}-x64.exe"
        checksum_name = f"{installer_name}.sha256"
        assets = payload.get("assets")
        if not isinstance(assets, list):
            raise UpdateError("A publicação não contém os arquivos de atualização.")
        urls: dict[str, str] = {}
        for asset in assets:
            if isinstance(asset, dict) and asset.get("name") in (installer_name, checksum_name):
                urls[asset["name"]] = _https_url(asset.get("browser_download_url"), "arquivo")
        if set(urls) != {installer_name, checksum_name}:
            raise UpdateError("A publicação não contém o instalador e o checksum esperados.")
        title = payload.get("name") if isinstance(payload.get("name"), str) else ""
        notes = payload.get("body") if isinstance(payload.get("body"), str) else ""
        page_url = _https_url(payload.get("html_url"), "publicação")
        return Release(
            version, title.strip()[:160], notes.strip()[:4000], installer_name,
            urls[installer_name], urls[checksum_name], page_url,
        )

    def download(self, release: Release, directory: Path, *,
                 progress: Callable[[int, int | None], None] | None = None,
                 cancelled: Callable[[], bool] | None = None) -> Path:
        checksum_data = self._small_download(
            release.checksum_url, MAX_CHECKSUM_BYTES, accept="text/plain",
        )
        expected = self._checksum(checksum_data, release.installer_name)
        destination = Path(directory) / release.installer_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_file() and self._file_hash(destination) == expected:
            if progress:
                progress(destination.stat().st_size, destination.stat().st_size)
            return destination

        temporary: Path | None = None
        try:
            request = self._request(release.installer_url)
            with self._open(request, timeout=self.timeout) as response:
                final_url = getattr(response, "geturl", lambda: release.installer_url)()
                _https_url(final_url, "download")
                raw_length = response.headers.get("Content-Length")
                total = None
                if raw_length:
                    try:
                        total = int(raw_length)
                    except ValueError as error:
                        raise UpdateError("O servidor informou um tamanho inválido.") from error
                    if total < 1 or total > MAX_INSTALLER_BYTES:
                        raise UpdateError("O instalador excede o tamanho permitido.")
                digest = hashlib.sha256()
                received = 0
                with tempfile.NamedTemporaryFile(
                    prefix=f".{release.installer_name}.", suffix=".part",
                    dir=destination.parent, delete=False,
                ) as stream:
                    temporary = Path(stream.name)
                    while True:
                        if cancelled and cancelled():
                            raise UpdateError("Download cancelado.")
                        chunk = response.read(128 * 1024)
                        if not chunk:
                            break
                        received += len(chunk)
                        if received > MAX_INSTALLER_BYTES:
                            raise UpdateError("O instalador excede o tamanho permitido.")
                        stream.write(chunk)
                        digest.update(chunk)
                        if progress:
                            progress(received, total)
                    stream.flush()
                    os.fsync(stream.fileno())
            if received == 0 or (total is not None and received != total):
                raise UpdateError("O download do instalador ficou incompleto.")
            if digest.hexdigest() != expected:
                raise UpdateError("A verificação SHA-256 do instalador falhou.")
            os.replace(temporary, destination)
            temporary = None
            return destination
        except UpdateError:
            raise
        except (OSError, TimeoutError, ValueError) as error:
            raise UpdateError("Não foi possível baixar a atualização.") from error
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def _checksum(data: bytes, filename: str) -> str:
        try:
            lines = data.decode("ascii").splitlines()
        except UnicodeError as error:
            raise UpdateError("O checksum publicado é inválido.") from error
        matches = []
        for line in lines:
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2 and _SHA256.fullmatch(parts[0]) and parts[1].lstrip("*") == filename:
                matches.append(parts[0].lower())
        if len(matches) != 1:
            raise UpdateError("O checksum publicado não corresponde ao instalador.")
        return matches[0]

    @staticmethod
    def _file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(128 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
