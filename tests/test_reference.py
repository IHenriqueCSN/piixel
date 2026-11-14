"""Reference images stay convenient, transient, and separate from .pii files."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication

from piixelverso.atelier import AtelierModule
from piixelverso.format import encode_design
from piixelverso.model import PixelDesign
from piixelverso.preferences import PreferencesStore
from piixelverso.reference import load_reference_image, validate_reference_image


class ReferenceImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.preferences = PreferencesStore(self.root / "preferences.json")
        self.window = AtelierModule(preferences=self.preferences)
        self.window.show()
        self.window._replace_design(PixelDesign(8, 8, name="Constelação"))
        self.window.history.setClean()
        self.image_path = self.root / "referência colorida.png"
        image = QImage(80, 50, QImage.Format.Format_ARGB32)
        image.fill(QColor("#E7794B"))
        self.assertTrue(image.save(str(self.image_path)))
        self.app.processEvents()

    def tearDown(self):
        QApplication.clipboard().clear()
        self.window.history.setClean()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def test_loader_accepts_images_and_rejects_invalid_files(self):
        image = load_reference_image(self.image_path)
        self.assertEqual((image.width(), image.height()), (80, 50))
        invalid = self.root / "não é imagem.txt"
        invalid.write_text("olá", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "formato"):
            load_reference_image(invalid)
        with self.assertRaisesRegex(ValueError, "vazia"):
            validate_reference_image(QImage())

    def test_opening_reference_does_not_change_document_or_history(self):
        before = encode_design(self.window.design)
        history = (
            self.window.history.count(), self.window.history.index(),
            self.window.history.isClean(),
        )

        self.assertTrue(self.window.load_reference_path(self.image_path))

        self.assertTrue(self.window.reference_panel.has_image)
        self.assertEqual(self.window.reference_path, self.image_path.absolute())
        self.assertEqual(self.window.reference_panel.source_label.text(), self.image_path.name)
        self.assertIs(
            self.window.side_stack.currentWidget(), self.window.reference_panel
        )
        self.assertEqual(encode_design(self.window.design), before)
        self.assertEqual(
            (self.window.history.count(), self.window.history.index(),
             self.window.history.isClean()), history,
        )

        saved = self.root / "arte.pii"
        self.assertTrue(self.window._save_path(saved))
        self.assertEqual(saved.read_bytes(), before)

    def test_panel_can_return_to_counts_without_discarding_reference(self):
        self.window.load_reference_path(self.image_path)
        self.window.view.show_reference_panel(False)
        self.assertIs(self.window.side_stack.currentWidget(), self.window.side_stack.widget(0))
        self.assertTrue(self.window.reference_panel.has_image)
        self.window.command_actions["reference_panel"].trigger()
        self.assertIs(self.window.side_stack.currentWidget(), self.window.reference_panel)
        self.assertEqual(
            self.window.command_actions["reference_panel"].shortcut().toString(),
            "Ctrl+Shift+R",
        )

    def test_clipboard_image_is_loaded_without_a_file_path(self):
        image = QImage(24, 16, QImage.Format.Format_RGB32)
        image.fill(QColor("#245448"))
        QApplication.clipboard().setImage(image)

        self.assertTrue(self.window.paste_reference_image())

        self.assertTrue(self.window.reference_panel.has_image)
        self.assertIsNone(self.window.reference_path)
        self.assertEqual(self.window.reference_panel.source_label.text(), "Imagem colada")

    def test_file_picker_remove_and_invalid_file_are_safe(self):
        with patch(
            "piixelverso.atelier.QFileDialog.getOpenFileName",
            return_value=(str(self.image_path), "Imagens (*.png)"),
        ):
            self.assertTrue(self.window.open_reference_image())
        before_source = self.window.reference_panel.source_label.text()
        invalid = self.root / "quebrada.png"
        invalid.write_bytes(b"not an image")
        with patch("piixelverso.atelier.QMessageBox.warning") as warning:
            self.assertFalse(self.window.load_reference_path(invalid))
            warning.assert_called_once()
        self.assertTrue(self.window.reference_panel.has_image)
        self.assertEqual(self.window.reference_panel.source_label.text(), before_source)

        self.window.remove_reference_image()
        self.assertFalse(self.window.reference_panel.has_image)
        self.assertIsNone(self.window.reference_path)
        self.assertEqual(
            self.window.reference_panel.source_label.text(),
            "Nenhuma imagem carregada",
        )

    def test_local_file_drop_is_recognized(self):
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(self.image_path))])
        dropped = self.window.reference_panel._local_image_path(mime)
        self.assertIsNotNone(dropped)
        self.assertEqual(Path(dropped), self.image_path)


if __name__ == "__main__":
    unittest.main()
