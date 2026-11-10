from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from piixelverso.format import (
    DesignFormatError, HEADER, MAX_FILE_SIZE, decode_design, encode_design,
    load_design, save_design,
)
from piixelverso.model import TRANSPARENT, PixelDesign


def with_crc(data):
    return bytes(data[:-4]) + struct.pack("<I", zlib.crc32(data[:-4]) & 0xFFFFFFFF)


class FormatTests(unittest.TestCase):
    def test_roundtrip_unicode_and_empty_cells(self):
        design = PixelDesign(3, 2, [None, "#ffffff", "#aabbcc", "#aabbcc", None, "#000000"], "Coração do Piixelverso ♥ 🎨")
        binary = encode_design(design)
        self.assertEqual(binary[:5], b"PII\x00\x01")
        self.assertEqual(decode_design(binary), design)
        self.assertEqual(encode_design(decode_design(binary)), binary)

    def test_empty_roundtrip(self):
        design = PixelDesign(1, 1, name="")
        self.assertEqual(decode_design(encode_design(design)), design)

    def test_transparent_piece_uses_v2_and_remains_distinct_from_empty_and_white(self):
        design = PixelDesign(3, 1, [None, TRANSPARENT, "#FFFFFF"], "Base transparente")
        binary = encode_design(design)
        self.assertEqual(binary[:5], b"PII\x00\x02")
        self.assertEqual(decode_design(binary), design)
        self.assertEqual(decode_design(binary).counts(), {TRANSPARENT: 1, "#FFFFFF": 1})

        legacy = encode_design(PixelDesign(2, 1, [None, "#FFFFFF"]))
        self.assertEqual(legacy[:5], b"PII\x00\x01")
        self.assertEqual(decode_design(legacy), PixelDesign(2, 1, [None, "#FFFFFF"]))

    def test_v2_rejects_unknown_partial_alpha(self):
        data = bytearray(encode_design(PixelDesign(1, 1, [TRANSPARENT], "")))
        data[HEADER.size] = 0x80
        with self.assertRaisesRegex(DesignFormatError, "transparência"):
            decode_design(with_crc(data))

    def test_maximum_unique_palette(self):
        design = PixelDesign(128, 128, [f"#{index:06X}" for index in range(128 * 128)])
        binary = encode_design(design)
        self.assertLessEqual(len(binary), MAX_FILE_SIZE)
        self.assertEqual(decode_design(binary), design)

    def test_truncation_and_trailing_data(self):
        data = encode_design(PixelDesign(2, 2))
        for length in range(len(data)):
            with self.subTest(length=length), self.assertRaises(DesignFormatError):
                decode_design(data[:length])
        with self.assertRaises(DesignFormatError):
            decode_design(data + b"extra")

    def test_bad_checksum(self):
        data = bytearray(encode_design(PixelDesign(1, 1)))
        data[-1] ^= 1
        with self.assertRaisesRegex(DesignFormatError, "integridade"):
            decode_design(data)

    def test_bad_magic_version_dimensions(self):
        original = encode_design(PixelDesign(1, 1))
        for offset, replacement in ((0, b"NOPE"), (4, b"\x03"), (5, b"\x00\x00")):
            data = bytearray(original)
            data[offset:offset + len(replacement)] = replacement
            with self.subTest(offset=offset), self.assertRaises(DesignFormatError):
                decode_design(with_crc(data))

    def test_invalid_palette_index(self):
        data = bytearray(encode_design(PixelDesign(1, 1, ["#FF0000"], "")))
        struct.pack_into("<H", data, HEADER.size + 3, 2)
        with self.assertRaisesRegex(DesignFormatError, "inexistente"):
            decode_design(with_crc(data))

    def test_duplicate_palette(self):
        data = bytearray(encode_design(PixelDesign(2, 1, ["#FF0000", "#00FF00"], "")))
        data[HEADER.size + 3:HEADER.size + 6] = data[HEADER.size:HEADER.size + 3]
        with self.assertRaisesRegex(DesignFormatError, "duplicadas"):
            decode_design(with_crc(data))

    def test_invalid_utf8(self):
        data = bytearray(encode_design(PixelDesign(1, 1, name="a")))
        data[HEADER.size] = 0xFF
        with self.assertRaisesRegex(DesignFormatError, "UTF-8"):
            decode_design(with_crc(data))

    def test_oversize_file(self):
        with self.assertRaises(DesignFormatError):
            decode_design(b"\x00" * (MAX_FILE_SIZE + 1))

    def test_invalid_in_memory_design(self):
        design = PixelDesign(1, 1)
        design.pixels[0] = "bad"
        with self.assertRaises(DesignFormatError):
            encode_design(design)

    def test_save_and_load(self):
        design = PixelDesign(2, 1, [None, "#123456"], "Teste")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "design.pii"
            save_design(design, target)
            self.assertEqual(load_design(target), design)
            design.set_pixel(0, 0, "#FFFFFF")
            save_design(design, target)
            self.assertEqual(load_design(target), design)
            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_atomic_failure_keeps_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "design.pii"
            original = PixelDesign(1, 1)
            save_design(original, target)
            replacement = PixelDesign(1, 1, ["#FFFFFF"])
            with patch("piixelverso.format.os.replace", side_effect=OSError("Teste de falha")):
                with self.assertRaises(OSError):
                    save_design(replacement, target)
            self.assertEqual(load_design(target), original)
            self.assertEqual(list(Path(directory).iterdir()), [target])


if __name__ == "__main__":
    unittest.main()
