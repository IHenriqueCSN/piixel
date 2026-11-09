"""Validate Windows packaging data without requiring a Windows desktop here."""
from __future__ import annotations

import ast
from contextlib import contextmanager, redirect_stdout
import ctypes
import io
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import shutil
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication


PROJECT = Path(__file__).resolve().parents[1]


class WindowsAssetsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name) / "Piixel com espaços"
        self.root.mkdir()
        self.metadata("2.3.4")
        target = self.root / "piixelverso" / "assets" / "brand"
        target.mkdir(parents=True)
        shutil.copyfile(PROJECT / "piixelverso/assets/brand/symbol.svg", target / "symbol.svg")

    def tearDown(self):
        self.directory.cleanup()

    def metadata(self, version):
        if isinstance(version, str):
            encoded = repr(version)
        else:
            encoded = str(version).lower()
        (self.root / "pyproject.toml").write_text(
            "[project]\nname = 'piixelverso'\nversion = " + encoded + "\n", encoding="utf-8"
        )

    def test_version_comes_from_project_metadata_and_fits_windows_words(self):
        from scripts.windows_assets import read_version
        self.assertEqual(read_version(self.root), "2.3.4")
        self.metadata("65535.0.65535")
        self.assertEqual(read_version(self.root), "65535.0.65535")
        for version in ("", "1.2", "1.2.3.4", "1.2.3rc1", "1.2.3+local", "-1.2.3",
                        "1.2.65536", "1.2.x", "１.2.3", 123, True):
            with self.subTest(version=version):
                self.metadata(version)
                with self.assertRaises(ValueError):
                    read_version(self.root)

    def test_icon_contains_seven_real_transparent_png_resolutions(self):
        from scripts.windows_assets import create_windows_assets
        result = create_windows_assets(self.root)
        self.assertEqual(result["version"], "2.3.4")
        icon = Path(result["icon"])
        self.assertEqual(icon, self.root / "build/windows/piixel.ico")
        raw = icon.read_bytes()
        self.assertEqual(struct.unpack_from("<HHH", raw), (0, 1, 7))
        previous_end = 6 + 7 * 16
        for index, expected in enumerate((16, 24, 32, 48, 64, 128, 256)):
            with self.subTest(size=expected):
                width, height, colors, reserved, planes, bits, length, offset = struct.unpack_from(
                    "<BBBBHHII", raw, 6 + index * 16
                )
                self.assertEqual((width or 256, height or 256), (expected, expected))
                self.assertEqual((colors, reserved, planes, bits), (0, 0, 1, 32))
                self.assertGreaterEqual(offset, previous_end)
                self.assertLessEqual(offset + length, len(raw))
                payload = raw[offset:offset + length]
                self.assertTrue(payload.startswith(b"\x89PNG\r\n\x1a\n"))
                image = QImage.fromData(payload, "PNG")
                self.assertFalse(image.isNull())
                self.assertEqual((image.width(), image.height()), (expected, expected))
                self.assertTrue(image.hasAlphaChannel())
                self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
                self.assertTrue(any(image.pixelColor(x, y).alpha()
                                    for x in range(expected) for y in range(expected)))
                previous_end = offset + length
        self.assertEqual(previous_end, len(raw))

    def test_version_resource_has_matching_numeric_and_display_versions(self):
        from scripts.windows_assets import create_windows_assets
        result = create_windows_assets(self.root)
        resource = Path(result["version_file"])
        self.assertEqual(resource, self.root / "build/windows/version_info.txt")
        document = ast.parse(resource.read_text(encoding="utf-8-sig"), mode="eval")
        calls = [node for node in ast.walk(document) if isinstance(node, ast.Call)]
        fixed = next(node for node in calls if isinstance(node.func, ast.Name)
                     and node.func.id == "FixedFileInfo")
        fields = {item.arg: ast.literal_eval(item.value) for item in fixed.keywords}
        self.assertEqual(fields["filevers"], (2, 3, 4, 0))
        self.assertEqual(fields["prodvers"], (2, 3, 4, 0))
        strings = {ast.literal_eval(node.args[0]): ast.literal_eval(node.args[1])
                   for node in calls if isinstance(node.func, ast.Name)
                   and node.func.id == "StringStruct"}
        self.assertEqual(strings["FileVersion"], "2.3.4")
        self.assertEqual(strings["ProductVersion"], "2.3.4")
        self.assertEqual(strings["OriginalFilename"], "Piixel.exe")
        self.assertEqual(strings["ProductName"], "Piixel")

    @unittest.skipUnless(sys.platform == "win32", "Parser de recursos PE exige as dependências Windows")
    def test_windows_pyinstaller_loads_the_generated_version_resource(self):
        from scripts.windows_assets import create_windows_assets
        try:
            from PyInstaller.utils.win32.versioninfo import load_version_info_from_text_file
        except ImportError:
            self.skipTest("PyInstaller para Windows não está instalado")
        resource = create_windows_assets(self.root)["version_file"]
        info = load_version_info_from_text_file(str(resource))
        self.assertEqual(info.ffi.fileVersionMS, (2 << 16) | 3)
        self.assertEqual(info.ffi.fileVersionLS, 4 << 16)
        self.assertTrue(info.toRaw())


class InstallerMutexTests(unittest.TestCase):
    @staticmethod
    def kernel(handle=123):
        return SimpleNamespace(CreateMutexW=Mock(return_value=handle), CloseHandle=Mock(return_value=True))

    def test_normal_windows_session_holds_the_mutex_until_the_app_finishes(self):
        from piixelverso import startup
        kernel = self.kernel()
        with patch.object(startup.sys, "platform", "win32"), patch.object(
            ctypes, "WinDLL", return_value=kernel, create=True
        ):
            with startup._installer_mutex():
                kernel.CreateMutexW.assert_called_once_with(None, False, "Piixel.Piixelverso.Desktop")
                kernel.CloseHandle.assert_not_called()
            kernel.CloseHandle.assert_called_once_with(123)

    def test_failed_application_also_releases_the_mutex(self):
        from piixelverso import startup
        kernel = self.kernel()
        with patch.object(startup.sys, "platform", "win32"), patch.object(
            ctypes, "WinDLL", return_value=kernel, create=True
        ):
            with self.assertRaisesRegex(RuntimeError, "falha simulada"):
                with startup._installer_mutex():
                    raise RuntimeError("falha simulada")
        kernel.CloseHandle.assert_called_once_with(123)

    def test_non_windows_launch_does_not_load_windows_libraries(self):
        from piixelverso import startup
        with patch.object(startup.sys, "platform", "linux"), patch.object(
            ctypes, "WinDLL", create=True
        ) as loader:
            with startup._installer_mutex():
                pass
        loader.assert_not_called()

    def test_feedback_helpers_and_help_do_not_acquire_the_application_mutex(self):
        from piixelverso import startup
        with patch.object(startup, "_installer_mutex", side_effect=AssertionError("mutex indevido")), patch(
            "piixelverso.splash.run_splash", return_value=19
        ) as splash:
            self.assertEqual(startup.main([startup._SPLASH_ARGUMENT]), 19)
            self.assertEqual(startup.main([startup._PAGE_LOADING_ARGUMENT, '{"message":"Carregando…"}']), 19)
            with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as stopped:
                startup.main(["--help"])
            self.assertEqual(stopped.exception.code, 0)
        self.assertEqual(splash.call_count, 2)

    def test_mutex_outlives_startup_feedback_and_is_released_after_failure(self):
        from piixelverso import startup
        events = []

        @contextmanager
        def mutex():
            events.append("acquired")
            try:
                yield
            finally:
                events.append("released")

        handle = SimpleNamespace(close=lambda: events.append("feedback closed"))

        def run_app(argv, *, startup):
            self.assertEqual(events, ["acquired"])
            raise RuntimeError("aplicativo indisponível")

        with patch.object(startup, "_installer_mutex", mutex), patch.object(
            startup._SplashProcess, "launch", return_value=handle
        ), patch.dict(sys.modules, {"piixelverso.app": SimpleNamespace(main=run_app)}):
            with self.assertRaisesRegex(RuntimeError, "indisponível"):
                startup.main([])
        self.assertEqual(events, ["acquired", "feedback closed", "released"])


class BuildCommandTests(unittest.TestCase):
    def test_windows_build_bundles_the_icon_and_version_resource(self):
        from scripts import build
        assets = {"icon": Path("pasta com espaços/piixel.ico"),
                  "version_file": Path("pasta com espaços/version_info.txt")}
        with patch.object(build.sys, "platform", "win32"), patch.object(
            build.importlib.util, "find_spec", return_value=object()
        ), patch("scripts.windows_assets.create_windows_assets", return_value=assets) as prepare, patch.object(
            build.subprocess, "run"
        ) as execute, redirect_stdout(io.StringIO()):
            self.assertEqual(build.main(), 0)
        prepare.assert_called_once_with(PROJECT)
        command = execute.call_args.args[0]
        self.assertEqual(command[command.index("--icon") + 1], str(assets["icon"]))
        self.assertEqual(command[command.index("--version-file") + 1], str(assets["version_file"]))
        self.assertEqual(command[command.index("--contents-directory") + 1], "_internal")
        self.assertEqual(command[-1], str(PROJECT / "run_piixelverso.py"))

    def test_other_platforms_do_not_load_windows_packaging_assets(self):
        from scripts import build
        with patch.object(build.sys, "platform", "linux"), patch.object(
            build.importlib.util, "find_spec", return_value=object()
        ), patch("scripts.windows_assets.create_windows_assets") as prepare, patch.object(
            build.subprocess, "run"
        ) as execute, redirect_stdout(io.StringIO()):
            self.assertEqual(build.main(), 0)
        prepare.assert_not_called()
        self.assertNotIn("--icon", execute.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
