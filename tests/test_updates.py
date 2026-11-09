"""Release discovery, verified downloads and updater integration."""
from __future__ import annotations

import hashlib
import base64
import io
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import time
import tomllib
import unittest
from unittest.mock import patch
import subprocess
import sys

from PySide6.QtWidgets import QApplication, QWidget

from piixelverso.preferences import PreferencesStore
from piixelverso.update import LATEST_RELEASE_URL, Release, UpdateClient, UpdateError, parse_version
from piixelverso.update_ui import UpdateController


class Response(io.BytesIO):
    def __init__(self, data: bytes, url: str, *, length: bool = True):
        super().__init__(data)
        self._url = url
        self.headers = {"Content-Length": str(len(data))} if length else {}

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def release_payload(version="0.3.0", *, prerelease=False, assets=True):
    installer = f"Piixel-Setup-{version}-x64.exe"
    files = []
    if assets:
        files = [
            {"name": installer, "browser_download_url": f"https://github.com/files/{installer}"},
            {"name": installer + ".sha256",
             "browser_download_url": f"https://github.com/files/{installer}.sha256"},
        ]
    return {
        "draft": False, "prerelease": prerelease, "tag_name": f"v{version}",
        "name": f"Piixel {version}", "body": "Novidades da versão.",
        "html_url": f"https://github.com/IHenriqueCSN/piixel/releases/tag/v{version}",
        "assets": files,
    }


class UpdateClientTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def client(self, responses):
        def open_url(request, timeout):
            data = responses[request.full_url]
            if isinstance(data, tuple):
                data, final_url = data
            else:
                final_url = request.full_url
            return Response(data, final_url)
        return UpdateClient(opener=open_url)

    def test_runtime_and_installer_versions_have_one_release_number(self):
        from piixelverso import __version__

        project = tomllib.loads(
            (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(__version__, project["project"]["version"])

    def test_version_order_is_numeric_and_strict(self):
        self.assertEqual(parse_version("1.10.2"), (1, 10, 2))
        self.assertEqual(parse_version("v2.0.0", allow_v=True), (2, 0, 0))
        for invalid in ("1.2", "01.2.3", "1.2.3.4", "1.2.3-beta", "V1.2.3", 123):
            with self.subTest(invalid=invalid), self.assertRaises(UpdateError):
                parse_version(invalid, allow_v=True)

    def test_latest_requires_the_exact_installer_and_checksum(self):
        payload = release_payload()
        client = self.client({LATEST_RELEASE_URL: json.dumps(payload).encode()})
        release = client.latest("0.2.0")
        self.assertEqual(release.version, "0.3.0")
        self.assertEqual(release.installer_name, "Piixel-Setup-0.3.0-x64.exe")
        self.assertIn("Novidades", release.notes)
        self.assertIsNone(client.latest("0.3.0"))
        self.assertIsNone(client.latest("1.0.0"))

        broken = self.client({LATEST_RELEASE_URL: json.dumps(release_payload(assets=False)).encode()})
        with self.assertRaisesRegex(UpdateError, "instalador e o checksum"):
            broken.latest("0.2.0")

    def test_prerelease_is_not_offered(self):
        client = self.client({
            LATEST_RELEASE_URL: json.dumps(release_payload(prerelease=True)).encode(),
        })
        self.assertIsNone(client.latest("0.2.0"))

    def test_download_verifies_sha256_and_reports_progress(self):
        installer = b"MZ" + os.urandom(10000)
        digest = hashlib.sha256(installer).hexdigest()
        payload = release_payload()
        name = "Piixel-Setup-0.3.0-x64.exe"
        urls = {
            LATEST_RELEASE_URL: json.dumps(payload).encode(),
            f"https://github.com/files/{name}": (installer, "https://objects.githubusercontent.com/file"),
            f"https://github.com/files/{name}.sha256": f"{digest}  {name}\n".encode(),
        }
        client = self.client(urls)
        found = client.latest("0.2.0")
        progress = []
        path = client.download(found, self.root / "updates", progress=lambda *value: progress.append(value))
        self.assertEqual(path.read_bytes(), installer)
        self.assertEqual(progress[-1], (len(installer), len(installer)))
        self.assertEqual(list(path.parent.glob("*.part")), [])

        # A verified existing installer is reused without downloading the executable again.
        reuse = self.client({
            found.checksum_url: f"{digest}  {name}\n".encode(),
        })
        self.assertEqual(reuse.download(found, path.parent), path)

    def test_bad_checksum_and_cancellation_never_publish_a_partial_installer(self):
        data = b"MZunsafe"
        name = "Piixel-Setup-0.3.0-x64.exe"
        release = Release(
            "0.3.0", "", "", name, "https://github.com/installer",
            "https://github.com/checksum", "https://github.com/release",
        )
        wrong = "0" * 64
        client = self.client({
            release.checksum_url: f"{wrong}  {name}\n".encode(),
            release.installer_url: data,
        })
        with self.assertRaisesRegex(UpdateError, "SHA-256"):
            client.download(release, self.root)
        self.assertFalse((self.root / name).exists())
        self.assertEqual(list(self.root.glob("*.part")), [])

        digest = hashlib.sha256(data).hexdigest()
        cancelled = self.client({
            release.checksum_url: f"{digest}  {name}\n".encode(),
            release.installer_url: data,
        })
        with self.assertRaisesRegex(UpdateError, "cancelado"):
            cancelled.download(release, self.root, cancelled=lambda: True)
        self.assertFalse((self.root / name).exists())
        self.assertEqual(list(self.root.glob("*.part")), [])


class FakeWindow(QWidget):
    def __init__(self, path: Path):
        super().__init__()
        self.preferences = PreferencesStore(path)
        self.close_allowed = True
        self.close_checks = 0

    def confirm_close_for_update(self):
        self.close_checks += 1
        return self.close_allowed

    def cancel_update_close(self):
        pass


class UpdateControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.window = FakeWindow(Path(self.directory.name) / "preferences.json")

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def wait_until(self, predicate, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(0.01)
        self.fail("A operação em segundo plano não terminou.")

    def test_automatic_check_runs_off_the_gui_and_reports_no_update_silently(self):
        class Client:
            def latest(self, version):
                self.version = version
                return None

        client = Client()
        controller = UpdateController(self.window, client=client, supported=True)
        statuses = []
        controller.status_changed.connect(statuses.append)
        self.assertTrue(controller.check_automatically())
        self.assertTrue(controller.busy)
        self.wait_until(lambda: not controller.busy)
        self.assertEqual(client.version, "0.2.0")
        self.assertIn("versão mais recente", statuses[-1])
        controller.shutdown()

    def test_source_build_does_not_contact_the_update_server(self):
        class Client:
            def latest(self, _version):
                raise AssertionError("Não deve consultar a rede")

        controller = UpdateController(self.window, client=Client(), supported=False)
        self.assertFalse(controller.check_automatically())
        self.assertFalse(controller.check(manual=True))
        self.assertIn("instalado no Windows", controller.status_text)

    def test_install_respects_unsaved_work_before_starting_helper(self):
        controller = UpdateController(self.window, supported=True)
        installer = Path(self.directory.name) / "Piixel-Setup-0.3.0-x64.exe"
        installer.write_bytes(b"MZ")
        self.window.close_allowed = False
        with patch("piixelverso.startup.launch_update_after_exit") as launch:
            self.assertFalse(controller._install(installer))
            launch.assert_not_called()
        self.assertEqual(self.window.close_checks, 1)


class WindowsUpdateLaunchTests(unittest.TestCase):
    def test_external_powershell_waits_for_the_app_then_runs_and_restarts(self):
        from piixelverso import startup

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installer = root / "Piixel-Setup-0.3.0-x64.exe"
            installer.write_bytes(b"MZ")
            powershell = root / "Windows" / "System32/WindowsPowerShell/v1.0/powershell.exe"
            powershell.parent.mkdir(parents=True)
            powershell.write_bytes(b"MZ")
            with patch.object(startup.sys, "platform", "win32"), \
                 patch.object(startup.sys, "frozen", True, create=True), \
                 patch.dict(startup.os.environ, {"SystemRoot": str(root / "Windows")}), \
                 patch.object(startup.subprocess, "CREATE_NO_WINDOW", 1, create=True), \
                 patch.object(startup.subprocess, "DETACHED_PROCESS", 2, create=True), \
                 patch.object(startup.subprocess, "CREATE_NEW_PROCESS_GROUP", 4, create=True), \
                 patch.object(startup.subprocess, "Popen") as popen:
                self.assertTrue(startup.launch_update_after_exit(installer))
            command = popen.call_args.args[0]
            self.assertEqual(Path(command[0]), powershell)
            encoded = command[command.index("-EncodedCommand") + 1]
            script = base64.b64decode(encoded).decode("utf-16le")
            self.assertIn(f"Wait-Process -Id {os.getpid()}", script)
            self.assertIn(str(installer.resolve()), script)
            self.assertIn("/SILENT", script)
            self.assertIn("Start-Process -FilePath $restart", script)
            self.assertEqual(popen.call_args.kwargs["creationflags"], 7)

    def test_launcher_rejects_source_builds_and_unexpected_files(self):
        from piixelverso import startup

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "arquivo.exe"
            path.write_bytes(b"MZ")
            with patch.object(startup.sys, "platform", "linux"):
                self.assertFalse(startup.launch_update_after_exit(path))
            with patch.object(startup.sys, "platform", "win32"), \
                 patch.object(startup.sys, "frozen", True, create=True):
                self.assertFalse(startup.launch_update_after_exit(path))


if __name__ == "__main__":
    unittest.main()
