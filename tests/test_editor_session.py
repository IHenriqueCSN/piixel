"""The document session can be exercised without constructing editor widgets."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest

from PySide6.QtWidgets import QApplication

from piixelverso.editor.history import PixelCommand, RenameCommand, ResizeCanvasCommand
from piixelverso.editor.session import EditorSession
from piixelverso.format import load_design, save_design
from piixelverso.model import PixelDesign
from piixelverso.resize import resized_design


class EditorSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.session = EditorSession(design=PixelDesign(10, 10, name="Desenho original"))

    def test_default_session_has_the_existing_initial_document_and_history_limit(self):
        session = EditorSession()
        self.assertEqual(session.design, PixelDesign(name="Meu primeiro design"))
        self.assertIsNone(session.file_path)
        self.assertEqual(session.history.undoLimit(), 300)
        self.assertTrue(session.history.isClean())

    def test_paint_rename_resize_undo_and_redo_keep_the_document_identity(self):
        document = self.session.design
        original = document.clone()
        self.session.commit_pixels({0: None, 99: None}, {0: "#ED5598", 99: "#FFFFFF"}, "Desenhar linha reta")
        painted = document.clone()
        self.session.rename("Nome novo")
        renamed = document.clone()
        self.session.resize(resized_design(document, 12, 14, "center"))
        resized = document.clone()
        self.assertIs(self.session.design, document)
        self.assertEqual(self.session.history.count(), 3)
        self.assertEqual(self.session.history.undoText(), "Redimensionar prancheta")
        self.assertIsInstance(self.session.history.command(0), PixelCommand)
        self.assertIsInstance(self.session.history.command(1), RenameCommand)
        self.assertIsInstance(self.session.history.command(2), ResizeCanvasCommand)

        for expected in (renamed, painted, original):
            self.session.history.undo()
            self.assertEqual(document, expected)
            self.assertIs(self.session.design, document)
        self.assertTrue(self.session.history.isClean())
        for expected in (painted, renamed, resized):
            self.session.history.redo()
            self.assertEqual(document, expected)
            self.assertIs(self.session.design, document)
        self.assertFalse(self.session.history.isClean())

    def test_resize_emits_geometry_before_content_and_preserves_the_current_name(self):
        self.session.design.set_pixel(9, 9, "#FFFFFF")
        after = resized_design(self.session.design, 12, 12)
        after.name = "Nome que não pertence ao redimensionamento"
        events = []
        self.session.geometry_changed.connect(lambda: events.append(("geometry", self.session.design.width)))
        self.session.changed.connect(lambda: events.append(("content", self.session.design.width)))
        self.session.resize(after)
        self.assertEqual(events, [("geometry", 12), ("content", 12)])
        self.assertEqual(self.session.design.name, "Desenho original")
        events.clear()
        self.session.history.undo()
        self.assertEqual(events, [("geometry", 10), ("content", 10)])
        self.assertEqual(self.session.design.get_pixel(9, 9), "#FFFFFF")

    def test_resize_snapshots_do_not_change_when_the_resized_document_is_painted(self):
        self.session.design.set_pixel(9, 9, "#FFFFFF")
        self.session.resize(resized_design(self.session.design, 12, 12))
        resized = self.session.design.clone()
        self.session.commit_pixels({0: None}, {0: "#ED5598"})
        self.session.history.undo()
        self.assertEqual(self.session.design, resized)
        self.session.history.undo()
        self.session.history.redo()
        self.assertEqual(self.session.design, resized)

    def test_save_marks_only_the_successful_document_state_clean(self):
        self.session.commit_pixels({0: None}, {0: "#ED5598"})
        events = []
        self.session.changed.connect(lambda: events.append("content"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "desenho.pii"
            self.session.save(path, writer=save_design)
            self.assertEqual(load_design(path), self.session.design)
            self.assertEqual(self.session.file_path, path)
            self.assertTrue(self.session.history.isClean())
            self.assertEqual(events, [], "Salvar não deve reconstruir campos da interface")
            self.session.history.undo()
            self.assertFalse(self.session.history.isClean())
            self.session.history.redo()
            self.assertTrue(self.session.history.isClean())

    def test_failed_save_keeps_the_old_path_dirty_state_and_history(self):
        self.session.file_path = Path("anterior.pii")
        self.session.commit_pixels({0: None}, {0: "#ED5598"})
        before = self.session.design.clone()
        history = (self.session.history.count(), self.session.history.index())

        def fail(design, path):
            self.assertIs(design, self.session.design)
            raise OSError("Falha de gravação simulada")

        with self.assertRaisesRegex(OSError, "simulada"):
            self.session.save("novo.pii", writer=fail)
        self.assertEqual(self.session.file_path, Path("anterior.pii"))
        self.assertFalse(self.session.history.isClean())
        self.assertEqual((self.session.history.count(), self.session.history.index()), history)
        self.assertEqual(self.session.design, before)

    def test_replacing_a_document_syncs_geometry_before_clearing_history(self):
        self.session.commit_pixels({0: None}, {0: "#ED5598"})
        replacement = PixelDesign(14, 12, name="Outro design")
        events = []
        self.session.geometry_changed.connect(
            lambda: events.append(("geometry", self.session.design, self.session.history.count())))
        self.session.changed.connect(
            lambda: events.append(("content", self.session.design, self.session.history.count())))
        self.session.replace(replacement, "outro.pii")
        self.assertEqual(events, [("geometry", replacement, 1), ("content", replacement, 0)])
        self.assertIs(self.session.design, replacement)
        self.assertEqual(self.session.file_path, Path("outro.pii"))
        self.assertFalse(self.session.history.canUndo())
        self.assertTrue(self.session.history.isClean())

    def test_new_document_replacement_resets_the_previous_file_path(self):
        self.session.file_path = Path("anterior.pii")
        replacement = PixelDesign(16, 16, name="Novo design")
        self.session.replace(replacement)
        self.assertIs(self.session.design, replacement)
        self.assertIsNone(self.session.file_path)
        self.assertTrue(self.session.history.isClean())


if __name__ == "__main__":
    unittest.main()
