"""Keep earlier Ateliê imports and command constructors working after extraction."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PySide6.QtWidgets import QApplication

from piixelverso.atelier import AtelierModule, PixelCommand, RenameCommand, ResizeCanvasCommand
from piixelverso.model import PixelDesign
from piixelverso.preferences import PreferencesStore
from piixelverso.resize import resized_design


class EditorCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_original_command_constructors_still_update_document_and_view(self):
        with TemporaryDirectory() as directory:
            editor = AtelierModule(preferences=PreferencesStore(Path(directory) / "preferences.json"))
            try:
                editor._replace_design(PixelDesign(10, 10, name="Original"))
                design = editor.design
                pixel = PixelCommand(editor, {0: None}, {0: "#ED5598"})
                editor.history.push(pixel)
                self.assertIs(pixel.window, editor)
                self.assertEqual(editor.design.get_pixel(0, 0), "#ED5598")
                self.assertEqual(editor.total_label.text(), "1")
                editor.undo()
                self.assertEqual(editor.total_label.text(), "0")
                editor.redo()

                rename = RenameCommand(editor, "Nome atualizado")
                editor.history.push(rename)
                self.assertIs(rename.window, editor)
                self.assertEqual(editor.name_edit.text(), "Nome atualizado")
                editor.undo()
                self.assertEqual(editor.name_edit.text(), "Original")

                resize = ResizeCanvasCommand(editor, design.clone(), resized_design(design, 12, 14))
                editor.history.push(resize)
                self.assertIs(resize.window, editor)
                self.assertIs(editor.design, design)
                self.assertEqual(editor.dimensions.text(), "12 × 14")
                editor.undo()
                self.assertEqual(editor.dimensions.text(), "10 × 10")
                self.assertEqual(editor.design.get_pixel(0, 0), "#ED5598")
            finally:
                editor.history.setClean()
                editor.close()
                editor.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
