"""Exercise recent-file persistence, thumbnails and opening from the home page."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from piixelverso.app import MainWindow, STYLE
from piixelverso.format import encode_design, save_design
from piixelverso.model import PixelDesign
from piixelverso.preferences import PreferencesStore


MISSING_MESSAGE = "Arquivo não encontrado. Verifique se o arquivo foi movido ou apagado."


class RecentFilesUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.settings_path = self.root / "preferences.json"
        self.windows = []
        self.window = self.make_window()

    def make_window(self):
        window = MainWindow(preferences=PreferencesStore(self.settings_path))
        self.windows.append(window)
        window.show()
        window.activateWindow()
        self.app.processEvents()
        return window

    def close_window(self, window):
        for module in window.module_pages.values():
            module.canvas.finish_stroke()
            module.name_edit.setText(module.design.name)
            module.history.setClean()
        window.close()
        window.deleteLater()
        self.windows.remove(window)
        self.app.processEvents()

    def tearDown(self):
        for window in list(reversed(self.windows)):
            self.close_window(window)
        self.directory.cleanup()

    def make_design_file(self, filename, *, color="#ED5598", name="Título do desenho"):
        path = self.root / filename
        design = PixelDesign(8, 8, name=name)
        for y in range(2, 6):
            for x in range(2, 6):
                design.set_pixel(x, y, color)
        save_design(design, path)
        return path, design

    def paint_cell(self, module, x=0, y=0):
        self.app.processEvents()
        QTest.mouseClick(module.canvas, Qt.MouseButton.LeftButton,
                         pos=module.canvas.cell_center(x, y))
        self.app.processEvents()

    def recent_index(self, path):
        view = self.window.home_page.recent_panel.view
        model = view.model()
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            entry = index.data(Qt.ItemDataRole.UserRole)
            if entry is not None and Path(entry.path) == path:
                return index
        self.fail(f"Arquivo não aparece na lista: {path}")

    def click_recent(self, path):
        view = self.window.home_page.recent_panel.view
        index = self.recent_index(path)
        view.scrollTo(index)
        self.app.processEvents()
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                         pos=view.visualRect(index).center())
        self.app.processEvents()

    def test_opened_and_saved_files_keep_named_thumbnails_across_restart(self):
        original, design = self.make_design_file(
            "nome-do-arquivo.pii", name="O título interno é diferente"
        )
        self.assertTrue(self.window.open_design_path(original))
        self.app.processEvents()
        module = self.window.module_pages["atelier"]
        self.paint_cell(module)
        duplicate = self.root / "outro-arquivo.pii"
        self.assertTrue(module._save_path(duplicate))
        self.window.show_home()
        self.app.processEvents()

        entries = self.window.preferences.recent_files()
        self.assertEqual({Path(entry.path) for entry in entries}, {original, duplicate})
        before = {entry.path: entry.thumbnail for entry in entries}
        for entry in entries:
            self.assertTrue(Path(entry.path).is_absolute())
            self.assertEqual(entry.name, Path(entry.path).name)
            self.assertFalse(QImage.fromData(entry.thumbnail).isNull())
        index = self.recent_index(original)
        self.assertEqual(index.data(Qt.ItemDataRole.DisplayRole), original.name)
        self.assertIn(str(original), index.data(Qt.ItemDataRole.ToolTipRole))
        self.assertNotEqual(index.data(Qt.ItemDataRole.DisplayRole), design.name)

        self.close_window(self.window)
        self.window = self.make_window()
        reloaded = self.window.preferences.recent_files()
        self.assertEqual({entry.path: entry.thumbnail for entry in reloaded}, before)
        self.assertEqual(self.window.module_pages, {})
        self.assertIsNone(self.window.current_module)
        self.assertEqual(self.window.home_page.recent_panel.view.model().rowCount(), 2)

    def test_click_and_enter_load_the_file_in_atelier(self):
        path, original = self.make_design_file("clicavel.pii")
        self.assertTrue(self.window.open_design_path(path))
        self.window.show_home()
        changed = original.clone()
        changed.name = "Atualizado no disco"
        changed.set_pixel(0, 0, "#BDE7EE")
        save_design(changed, path)
        self.window.refresh_recent_files()
        self.app.processEvents()

        self.click_recent(path)
        module = self.window.module_pages["atelier"]
        self.assertEqual(self.window.current_module, "atelier")
        self.assertEqual(module.design, changed)
        self.assertEqual(module.file_path, path)
        self.assertTrue(module.history.isClean())

        self.window.show_home()
        self.app.processEvents()
        view = self.window.home_page.recent_panel.view
        index = self.recent_index(path)
        view.setCurrentIndex(index)
        view.setFocus()
        QTest.keyClick(view, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.window.current_module, "atelier")
        self.assertIs(self.window.module_pages["atelier"], module)
        self.assertEqual(module.design, changed)

    def test_moved_or_deleted_recent_warns_without_discarding_the_open_design(self):
        path, _design = self.make_design_file("mover-ou-apagar.pii")
        self.assertTrue(self.window.open_design_path(path))
        module = self.window.module_pages["atelier"]
        module.select_color("#BDE7EE")
        self.paint_cell(module)
        self.window.show_home()
        self.app.processEvents()
        before = encode_design(module.design)
        history = (module.history.count(), module.history.index(), module.history.isClean())
        cached = self.window.preferences.recent_files()[0].thumbnail
        moved = self.root / "movido.pii"

        for operation in ("move", "delete"):
            with self.subTest(operation=operation):
                if operation == "move":
                    path.rename(moved)
                else:
                    path.unlink()
                self.window.refresh_recent_files()
                self.app.processEvents()
                self.assertEqual(self.window.preferences.recent_files()[0].thumbnail, cached)
                with patch("piixelverso.atelier.QMessageBox.warning") as warning:
                    with patch.object(module, "confirm_discard", side_effect=AssertionError(
                        "Um arquivo ausente não deve perguntar se o desenho aberto será descartado"
                    )):
                        self.click_recent(path)
                    warning.assert_called_once()
                    self.assertIs(warning.call_args.args[0], self.window)
                    self.assertEqual(warning.call_args.args[2], MISSING_MESSAGE)
                self.assertIsNone(self.window.current_module)
                self.assertIs(self.window.pages.currentWidget(), self.window.home_page)
                self.assertEqual(encode_design(module.design), before)
                self.assertEqual((module.history.count(), module.history.index(),
                                  module.history.isClean()), history)
                if operation == "move":
                    moved.rename(path)

    def test_latest_modified_sort_and_external_preview_refresh_are_not_open_order(self):
        newer, _newer_design = self.make_design_file("mais-novo.pii", color="#BDE7EE")
        older, _older_design = self.make_design_file("mais-antigo.pii", color="#ED5598")
        stamp = time.time_ns()
        os.utime(newer, ns=(stamp, stamp))
        os.utime(older, ns=(stamp - 2_000_000_000, stamp - 2_000_000_000))
        self.assertTrue(self.window.open_design_path(newer))
        self.assertTrue(self.window.open_design_path(older))
        self.window.show_home()
        self.app.processEvents()
        entries = self.window.preferences.recent_files()
        self.assertEqual([Path(entry.path) for entry in entries], [newer, older])
        previous_thumbnail = next(entry.thumbnail for entry in entries if Path(entry.path) == older)
        editor = self.window.module_pages["atelier"]
        previous_editor = encode_design(editor.design)

        changed = PixelDesign(8, 8, ["#292343"] * 64, name="Alteração externa")
        save_design(changed, older)
        os.utime(older, ns=(stamp + 2_000_000_000, stamp + 2_000_000_000))
        self.window.refresh_recent_files()
        self.app.processEvents()
        entries = self.window.preferences.recent_files()
        self.assertEqual([Path(entry.path) for entry in entries], [older, newer])
        self.assertNotEqual(entries[0].thumbnail, previous_thumbnail)
        self.assertFalse(QImage.fromData(entries[0].thumbnail).isNull())
        self.assertEqual(encode_design(editor.design), previous_editor)


if __name__ == "__main__":
    unittest.main()
