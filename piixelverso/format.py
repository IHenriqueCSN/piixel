"""Leitura e gravação do formato binário versionado .pii."""

from __future__ import annotations

import os
from pathlib import Path
import struct
import tempfile
import zlib

from .model import MAX_DIMENSION, MAX_NAME_BYTES, PixelDesign, normalize_color

MAGIC = b"PII\x00"
VERSION = 1
HEADER = struct.Struct("<4sBHHHH")
CHECKSUM = struct.Struct("<I")
MAX_PIXELS = MAX_DIMENSION * MAX_DIMENSION
MAX_FILE_SIZE = HEADER.size + MAX_NAME_BYTES + MAX_PIXELS * 5 + CHECKSUM.size


class DesignFormatError(ValueError):
    """Um arquivo não representa um design .pii válido e suportado."""


def encode_design(design: PixelDesign) -> bytes:
    try:
        design.validate()
    except (ValueError, TypeError, AttributeError) as exc:
        raise DesignFormatError(f"Não foi possível salvar o design: {exc}") from exc
    name = design.name.encode("utf-8")
    normalized = [normalize_color(color) for color in design.pixels]
    palette = sorted({color for color in normalized if color is not None})
    indices = {color: index + 1 for index, color in enumerate(palette)}
    payload = bytearray(HEADER.pack(MAGIC, VERSION, design.width, design.height, len(palette), len(name)))
    payload.extend(name)
    for color in palette:
        payload.extend(bytes.fromhex(color[1:]))
    for color in normalized:
        payload.extend(struct.pack("<H", 0 if color is None else indices[color]))
    payload.extend(CHECKSUM.pack(zlib.crc32(payload) & 0xFFFFFFFF))
    return bytes(payload)


def decode_design(data: bytes) -> PixelDesign:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise DesignFormatError("O conteúdo do arquivo deve ser binário.")
    if not HEADER.size + CHECKSUM.size <= len(data) <= MAX_FILE_SIZE:
        raise DesignFormatError("O arquivo está incompleto ou excede o tamanho permitido.")
    magic, version, width, height, palette_count, name_size = HEADER.unpack_from(data)
    if magic != MAGIC:
        raise DesignFormatError("Este arquivo não é um design .pii.")
    if version != VERSION:
        raise DesignFormatError(f"A versão {version} do formato .pii não é suportada.")
    if not (1 <= width <= MAX_DIMENSION and 1 <= height <= MAX_DIMENSION):
        raise DesignFormatError("As dimensões da grade são inválidas.")
    count = width * height
    if palette_count > count:
        raise DesignFormatError("A paleta contém mais cores que a grade comporta.")
    if name_size > MAX_NAME_BYTES:
        raise DesignFormatError("O nome do design excede o tamanho permitido.")
    expected_size = HEADER.size + name_size + palette_count * 3 + count * 2 + CHECKSUM.size
    if len(data) != expected_size:
        raise DesignFormatError("O tamanho do arquivo não corresponde ao conteúdo declarado.")
    checksum = CHECKSUM.unpack_from(data, len(data) - CHECKSUM.size)[0]
    if zlib.crc32(data[:-CHECKSUM.size]) & 0xFFFFFFFF != checksum:
        raise DesignFormatError("O arquivo está corrompido: a verificação de integridade falhou.")
    offset = HEADER.size
    try:
        name = bytes(data[offset:offset + name_size]).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise DesignFormatError("O nome do design contém texto UTF-8 inválido.") from exc
    offset += name_size
    palette = [None]
    for _ in range(palette_count):
        palette.append("#" + bytes(data[offset:offset + 3]).hex().upper())
        offset += 3
    if len(set(palette[1:])) != palette_count:
        raise DesignFormatError("A paleta contém cores duplicadas.")
    pixels = []
    for index in range(count):
        color_index = struct.unpack_from("<H", data, offset + index * 2)[0]
        if color_index > palette_count:
            raise DesignFormatError("Uma célula aponta para uma cor inexistente na paleta.")
        pixels.append(palette[color_index])
    return PixelDesign(width, height, pixels, name)


def save_design(design: PixelDesign, path: str | os.PathLike[str]) -> None:
    """Substitua o destino somente após gravar o arquivo completo no mesmo diretório."""
    data = encode_design(design)
    target = Path(path)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_design(path: str | os.PathLike[str]) -> PixelDesign:
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_FILE_SIZE + 1)
    return decode_design(data)
