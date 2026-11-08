"""Exercise local opt-in colors and recent-file persistence without a GUI."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from piixelverso.preferences import (
    MAX_PREFERENCES_BYTES, MAX_RECENT_FILES, MAX_THUMBNAIL_BYTES,
    PreferencesError, PreferencesStore, SavedColor,
)


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.path = self.root / "settings" / "preferences.json"
        self.store = PreferencesStore(self.path)

    def tearDown(self):
        self.directory.cleanup()

    def file(self, name, modified):
        path = self.root / name
        path.write_bytes(b"design")
        os.utime(path, ns=(modified, modified))
        return path

    def test_first_start_does_not_create_preferences_or_colors(self):
        self.assertIsNone(self.store.load_error)
        self.assertEqual(self.store.recent_files(), [])
        self.assertEqual(self.store.saved_colors(), [])
        self.assertFalse(self.path.exists())
        design = self.file("design.pii", time.time_ns())
        self.store.record_file(design, b"cached preview")
        reopened = PreferencesStore(self.path)
        self.assertEqual(reopened.saved_colors(), [])

    def test_explicitly_saved_named_colors_persist_normalize_and_remove(self):
        self.store.save_color("#ed5598", "  Rosa da marca ♥  ")
        self.store.save_color("#292343")
        reopened = PreferencesStore(self.path)
        self.assertEqual(reopened.saved_colors(), [
            SavedColor("#ED5598", "Rosa da marca ♥"), SavedColor("#292343", "")])
        reopened.save_color("#ED5598", "Rosa Hama")
        self.assertEqual(len(reopened.saved_colors()), 2)
        self.assertEqual(reopened.saved_colors()[0].name, "Rosa Hama")
        reopened.remove_color("#ed5598")
        self.assertEqual(PreferencesStore(self.path).saved_colors(), [SavedColor("#292343")])

    def test_recent_files_sort_by_real_modification_time_and_deduplicate(self):
        now = time.time_ns()
        old = self.file("antigo.pii", now - 20_000)
        new = self.file("novo.pii", now)
        self.store.record_file(new, b"new image")
        self.store.record_file(old, b"old image")
        self.assertEqual([entry.name for entry in self.store.recent_files()], ["novo.pii", "antigo.pii"])
        self.store.record_file(self.root / "other" / ".." / "antigo.pii", b"updated image")
        self.assertEqual(len(self.store.recent_files()), 2)
        self.assertEqual(self.store.recent_files()[1].thumbnail, b"updated image")
        os.utime(old, ns=(now + 20_000, now + 20_000))
        self.store.record_file(old, b"modified image")
        reopened = PreferencesStore(self.path)
        self.assertEqual(reopened.recent_files()[0].path, str(old))
        self.assertEqual(reopened.recent_files()[0].thumbnail, b"modified image")

    def test_moved_file_keeps_old_path_and_cached_thumbnail(self):
        path = self.file("meu desenho.pii", time.time_ns())
        self.store.record_file(path, b"cached thumbnail")
        before = self.store.recent_files()[0]
        path.rename(path.with_name("movido.pii"))
        reopened = PreferencesStore(self.path)
        self.assertEqual(reopened.recent_files(), [before])
        self.assertFalse(Path(reopened.recent_files()[0].path).exists())
        reopened.record_file(path, b"last thumbnail")
        self.assertEqual(reopened.recent_files()[0].modified_ns, before.modified_ns)

    def test_recent_limit_and_stable_ties_keep_last_updated_entry_first(self):
        now = time.time_ns()
        for index in range(MAX_RECENT_FILES + 3):
            path = self.file(f"design-{index:02d}.pii", now + index)
            self.store.record_file(path, str(index).encode())
        entries = self.store.recent_files()
        self.assertEqual(len(entries), MAX_RECENT_FILES)
        self.assertEqual(entries[0].name, "design-22.pii")
        self.assertEqual(entries[-1].name, "design-03.pii")
        a = self.file("empate-a.pii", now + 100)
        b = self.file("empate-b.pii", now + 100)
        self.store.record_file(a, b"a")
        self.store.record_file(b, b"b")
        self.assertEqual([e.name for e in PreferencesStore(self.path).recent_files()[:2]],
                         ["empate-b.pii", "empate-a.pii"])

    def test_user_selected_symlink_path_is_not_replaced_with_target(self):
        target = self.file("original.pii", time.time_ns())
        link = self.root / "atalho.pii"
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest("Symlinks indisponíveis para este usuário/plataforma")
        self.store.record_file(link, b"image")
        self.assertEqual(self.store.recent_files()[0].path, str(link))

    def test_atomic_failure_keeps_disk_and_memory_and_cleans_temporary(self):
        self.store.save_color("#ED5598", "Rosa")
        old_bytes = self.path.read_bytes()
        old_colors = self.store.saved_colors()
        with patch("piixelverso.preferences.os.replace", side_effect=OSError("Disco indisponível")):
            with self.assertRaises(PreferencesError):
                self.store.save_color("#292343", "Tinta")
        self.assertEqual(self.path.read_bytes(), old_bytes)
        self.assertEqual(self.store.saved_colors(), old_colors)
        self.assertEqual(list(self.path.parent.glob(".*.tmp")), [])
        path = self.file("salvo.pii", time.time_ns())
        with patch("piixelverso.preferences.os.replace", side_effect=OSError("Falha")):
            with self.assertRaises(PreferencesError):
                self.store.record_file(path, b"image")
        self.assertEqual(self.store.recent_files(), [])
        self.assertEqual(self.path.read_bytes(), old_bytes)

    def test_invalid_colors_names_and_large_thumbnail_never_change_state(self):
        for color, name in [(None, ""), ("red", ""), ("#FFF", ""), ("#FFFFFF", "a" * 81),
                            ("#FFFFFF", "nome\ninválido"), ("#FFFFFF", "\ud800")]:
            with self.subTest(color=color, name=repr(name)):
                with self.assertRaises(PreferencesError):
                    self.store.save_color(color, name)
        with self.assertRaises(PreferencesError):
            self.store.record_file(self.root / "missing.pii", b"x" * (MAX_THUMBNAIL_BYTES + 1))
        for invalid_path in ("invalid\x00path", None):
            with self.assertRaises(PreferencesError):
                self.store.record_file(invalid_path, b"")
        self.assertEqual(self.store.saved_colors(), [])
        self.assertEqual(self.store.recent_files(), [])
        self.assertFalse(self.path.exists())

    def test_corrupt_preferences_are_not_rewritten_during_load(self):
        self.path.parent.mkdir()
        self.path.write_bytes(b"{broken data")
        original = self.path.read_bytes()
        loaded = PreferencesStore(self.path)
        self.assertTrue(loaded.load_error)
        self.assertEqual(loaded.saved_colors(), [])
        self.assertEqual(loaded.recent_files(), [])
        self.assertEqual(self.path.read_bytes(), original)

    def test_invalid_version_schema_and_base64_are_reported_without_a_gui(self):
        self.path.parent.mkdir()
        payloads = [
            {"version": 2, "recent_files": [], "saved_colors": []},
            {"version": True, "recent_files": [], "saved_colors": []},
            {"version": 1, "recent_files": {}, "saved_colors": []},
            {"version": 1, "recent_files": [], "saved_colors": [{"color": "not RGB"}]},
            {"version": 1, "recent_files": [{"path": str(self.root / "a.pii"),
              "modified_ns": 1, "thumbnail": "%%INVALID%%"}], "saved_colors": []},
        ]
        for payload in payloads:
            self.path.write_text(json.dumps(payload))
            loaded = PreferencesStore(self.path)
            self.assertTrue(loaded.load_error)
            self.assertEqual(loaded.recent_files(), [])
            self.assertEqual(loaded.saved_colors(), [])

    def test_oversized_preferences_are_bounded(self):
        self.path.parent.mkdir()
        self.path.write_bytes(b" " * (MAX_PREFERENCES_BYTES + 1))
        loaded = PreferencesStore(self.path)
        self.assertTrue(loaded.load_error)
        self.assertEqual(loaded.recent_files(), [])

    def test_environment_override_uses_application_directory(self):
        directory = self.root / "portable-data"
        with patch.dict(os.environ, {"PIIXEL_DATA_DIR": str(directory)}):
            loaded = PreferencesStore()
            self.assertEqual(loaded.path, directory / "preferences.json")
            loaded.save_color("#FFFFFF", "Branco")
        self.assertTrue((directory / "preferences.json").is_file())


if __name__ == "__main__":
    unittest.main()
