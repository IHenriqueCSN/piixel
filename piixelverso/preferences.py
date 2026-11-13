"""Local recent-file metadata and colors explicitly saved by the user."""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import tempfile
import time

from .model import is_transparent, normalize_color


MAX_RECENT_FILES = 20
MAX_THUMBNAIL_BYTES = 64 * 1024
MAX_PREFERENCES_BYTES = 4 * 1024 * 1024
MAX_COLOR_NAME = 80
DEFAULT_PIECE_SIZE_MM = 5.0
DEFAULT_APPEARANCE_MODE = "system"
MIN_PIECE_SIZE_MM = 0.1
MAX_PIECE_SIZE_MM = 100.0


def validate_piece_size_mm(value) -> float:
    """Validate the physical side of a grid cell, independently of the GUI."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("O tamanho de cada peça deve ser um número em milímetros.")
    try:
        normalized = float(value)
    except OverflowError as error:
        raise ValueError("O tamanho de cada peça deve estar entre 0,1 e 100 mm.") from error
    if not math.isfinite(normalized) or not MIN_PIECE_SIZE_MM <= normalized <= MAX_PIECE_SIZE_MM:
        raise ValueError("O tamanho de cada peça deve estar entre 0,1 e 100 mm.")
    return normalized


class PreferencesError(OSError):
    """Local preferences could not be validated or written."""


@dataclass(frozen=True)
class RecentFile:
    path: str
    modified_ns: int
    thumbnail: bytes

    @property
    def name(self) -> str:
        return Path(self.path).name


@dataclass(frozen=True)
class SavedColor:
    color: str
    name: str = ""


def _absolute_path(path: str | os.PathLike[str]) -> str:
    try:
        raw = os.fspath(path)
    except TypeError as error:
        raise PreferencesError("O caminho do arquivo é inválido.") from error
    if not isinstance(raw, str) or not raw or "\x00" in raw or len(raw) > 32768:
        raise PreferencesError("O caminho do arquivo é inválido.")
    # Keep a user-selected symlink as that path; do not replace it with its target.
    return os.path.abspath(os.path.expanduser(raw))


def _path_key(path: str) -> str:
    return os.path.normcase(path)


def _saved_color(color: str, name: str = "") -> SavedColor:
    try:
        normalized = normalize_color(color)
    except (ValueError, TypeError) as error:
        raise PreferencesError("A cor deve estar no formato #RRGGBB.") from error
    if normalized is None:
        raise PreferencesError("Uma célula vazia não é uma cor para salvar.")
    if is_transparent(normalized):
        raise PreferencesError("A bead transparente já faz parte da paleta padrão.")
    if not isinstance(name, str):
        raise PreferencesError("O nome da cor deve ser um texto.")
    name = name.strip()
    if len(name) > MAX_COLOR_NAME or any(ord(char) < 32 for char in name):
        raise PreferencesError(f"O nome da cor deve ter até {MAX_COLOR_NAME} caracteres, em uma linha.")
    try:
        name.encode("utf-8")
    except UnicodeEncodeError as error:
        raise PreferencesError("O nome da cor contém um caractere inválido.") from error
    return SavedColor(normalized, name)


def _thumbnail(data: bytes) -> bytes:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise PreferencesError("A miniatura deve conter bytes de imagem.")
    if len(data) > MAX_THUMBNAIL_BYTES:
        raise PreferencesError("A miniatura excede o tamanho permitido.")
    return bytes(data)


def _default_preferences_path() -> Path:
    override = os.environ.get("PIIXEL_DATA_DIR")
    if override:
        return Path(override).expanduser().absolute() / "preferences.json"
    from PySide6.QtCore import QStandardPaths

    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
    if not location:
        raise PreferencesError("Não foi possível localizar a pasta de dados do Piixel.")
    return Path(location) / "Piixelverso" / "Piixel" / "preferences.json"


class PreferencesStore:
    """A bounded JSON store whose successful writes replace state atomically."""

    def __init__(self, path: Path | None = None):
        self.path = Path(_absolute_path(path)) if path is not None else _default_preferences_path()
        self.load_error: str | None = None
        self._recents: list[RecentFile] = []
        self._colors: list[SavedColor] = []
        self._piece_size_mm = DEFAULT_PIECE_SIZE_MM
        self._appearance_mode = DEFAULT_APPEARANCE_MODE
        self._load()

    def recent_files(self) -> list[RecentFile]:
        """Return cached entries; missing files remain available for an explicit open."""
        return list(self._recents)

    def saved_colors(self) -> list[SavedColor]:
        return list(self._colors)

    def piece_size_mm(self) -> float:
        return self._piece_size_mm

    def appearance_mode(self) -> str:
        return self._appearance_mode

    def set_piece_size_mm(self, value) -> None:
        try:
            size = validate_piece_size_mm(value)
        except ValueError as error:
            raise PreferencesError(str(error)) from error
        self._commit(self._recents, self._colors, piece_size_mm=size)

    def set_appearance_mode(self, mode: str) -> None:
        from .theme import validate_appearance_mode
        try:
            appearance = validate_appearance_mode(mode)
        except ValueError as error:
            raise PreferencesError(str(error)) from error
        self._commit(self._recents, self._colors, appearance_mode=appearance)

    def set_settings(self, piece_size_mm, appearance_mode: str) -> None:
        """Persist the settings screen atomically."""
        from .theme import validate_appearance_mode
        try:
            size = validate_piece_size_mm(piece_size_mm)
            appearance = validate_appearance_mode(appearance_mode)
        except ValueError as error:
            raise PreferencesError(str(error)) from error
        self._commit(
            self._recents, self._colors,
            piece_size_mm=size, appearance_mode=appearance,
        )

    def record_file(self, path: str | Path, thumbnail: bytes) -> None:
        normalized = _absolute_path(path)
        preview = _thumbnail(thumbnail)
        key = _path_key(normalized)
        previous = next((entry for entry in self._recents if _path_key(entry.path) == key), None)
        try:
            modified_ns = Path(normalized).stat().st_mtime_ns
        except OSError:
            # A just-opened file can be moved before its recent entry is written.
            modified_ns = previous.modified_ns if previous is not None else time.time_ns()
        entries = [RecentFile(normalized, modified_ns, preview)]
        entries.extend(entry for entry in self._recents if _path_key(entry.path) != key)
        entries.sort(key=lambda entry: entry.modified_ns, reverse=True)
        self._commit(entries[:MAX_RECENT_FILES], self._colors)

    def save_color(self, color: str, name: str = "") -> None:
        saved = _saved_color(color, name)
        colors = list(self._colors)
        for index, entry in enumerate(colors):
            if entry.color == saved.color:
                colors[index] = saved
                break
        else:
            colors.append(saved)
        self._commit(self._recents, colors)

    def remove_color(self, color: str) -> None:
        saved = _saved_color(color)
        colors = [entry for entry in self._colors if entry.color != saved.color]
        if len(colors) != len(self._colors):
            self._commit(self._recents, colors)

    def _load(self) -> None:
        try:
            with self.path.open("rb") as stream:
                raw = stream.read(MAX_PREFERENCES_BYTES + 1)
            if len(raw) > MAX_PREFERENCES_BYTES:
                raise PreferencesError("O arquivo de preferências excede o tamanho permitido.")
            data = json.loads(raw.decode("utf-8"))
            recents, colors, piece_size_mm, appearance_mode = self._decode(data)
        except FileNotFoundError:
            return
        except (OSError, ValueError, TypeError, UnicodeError, binascii.Error) as error:
            self.load_error = f"Não foi possível carregar as preferências locais: {error}"
            return
        self._recents, self._colors = recents, colors
        self._piece_size_mm, self._appearance_mode = piece_size_mm, appearance_mode

    @staticmethod
    def _decode(data) -> tuple[list[RecentFile], list[SavedColor], float, str]:
        if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
            raise PreferencesError("A versão das preferências não é suportada.")
        records, color_records = data.get("recent_files"), data.get("saved_colors")
        if not isinstance(records, list) or not isinstance(color_records, list):
            raise PreferencesError("As listas de preferências são inválidas.")
        if len(records) > MAX_RECENT_FILES:
            raise PreferencesError("A lista de arquivos recentes excede o limite permitido.")
        recent_by_path: dict[str, RecentFile] = {}
        for record in records:
            if not isinstance(record, dict):
                raise PreferencesError("Uma entrada de arquivo recente é inválida.")
            path = _absolute_path(record.get("path", ""))
            modified = record.get("modified_ns")
            if type(modified) is not int or not -(2**63) <= modified < 2**63:
                raise PreferencesError("A data de modificação do arquivo é inválida.")
            encoded = record.get("thumbnail")
            if not isinstance(encoded, str) or len(encoded) > ((MAX_THUMBNAIL_BYTES + 2) // 3) * 4:
                raise PreferencesError("A miniatura armazenada é inválida.")
            preview = _thumbnail(base64.b64decode(encoded, validate=True))
            item = RecentFile(path, modified, preview)
            key = _path_key(path)
            if key not in recent_by_path or modified > recent_by_path[key].modified_ns:
                recent_by_path[key] = item
        recent = sorted(recent_by_path.values(), key=lambda entry: entry.modified_ns, reverse=True)
        colors: dict[str, SavedColor] = {}
        for record in color_records:
            if not isinstance(record, dict):
                raise PreferencesError("Uma entrada de cor salva é inválida.")
            item = _saved_color(record.get("color"), record.get("name", ""))
            colors[item.color] = item
        piece_size_mm = validate_piece_size_mm(data.get("piece_size_mm", DEFAULT_PIECE_SIZE_MM))
        from .theme import validate_appearance_mode
        appearance_mode = validate_appearance_mode(
            data.get("appearance_mode", DEFAULT_APPEARANCE_MODE)
        )
        return recent, list(colors.values()), piece_size_mm, appearance_mode

    def _commit(self, recent: list[RecentFile], colors: list[SavedColor], *,
                piece_size_mm: float | None = None,
                appearance_mode: str | None = None) -> None:
        size = self._piece_size_mm if piece_size_mm is None else validate_piece_size_mm(piece_size_mm)
        from .theme import validate_appearance_mode
        appearance = self._appearance_mode if appearance_mode is None else validate_appearance_mode(
            appearance_mode
        )
        data = {
            "version": 1,
            "piece_size_mm": size,
            "appearance_mode": appearance,
            "recent_files": [
                {"path": entry.path, "modified_ns": entry.modified_ns,
                 "thumbnail": base64.b64encode(entry.thumbnail).decode("ascii")}
                for entry in recent
            ],
            "saved_colors": [{"color": entry.color, "name": entry.name} for entry in colors],
        }
        try:
            content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            if len(content) > MAX_PREFERENCES_BYTES:
                raise PreferencesError("As preferências excedem o tamanho permitido.")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(prefix=f".{self.path.name}.", suffix=".tmp",
                                                 dir=self.path.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
                temporary = None
            finally:
                if temporary is not None:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass
        except (OSError, UnicodeError, ValueError) as error:
            if isinstance(error, PreferencesError):
                raise
            raise PreferencesError(f"Não foi possível salvar as preferências locais: {error}") from error
        self._recents, self._colors = list(recent), list(colors)
        self._piece_size_mm = size
        self._appearance_mode = appearance
        self.load_error = None
