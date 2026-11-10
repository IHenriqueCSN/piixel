"""Exercise session colors, explicit persistence and the custom-color dialog."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from piixelverso.atelier import AtelierModule, STYLE
from piixelverso.colors import CustomColorDialog
from piixelverso.format import load_design
from piixelverso.model import TRANSPARENT, PixelDesign
from piixelverso.preferences import PreferencesError, PreferencesStore


class CustomColorsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.settings_path = self.root / "preferences.json"
        self.modules = []
        self.module = self.make_module()

    def make_module(self, settings_path=None):
        module = AtelierModule(preferences=PreferencesStore(settings_path or self.settings_path))
        self.modules.append(module)
        module.show()
        self.app.processEvents()
        return module

    def close_module(self, module):
        module.canvas.finish_stroke()
        module.name_edit.setText(module.design.name)
        module.history.setClean()
        module.close()
        module.deleteLater()
        self.modules.remove(module)
        self.app.processEvents()

    def tearDown(self):
        for module in list(reversed(self.modules)):
            self.close_module(module)
        self.directory.cleanup()

    def paint_cell(self, x=1, y=1):
        self.module._replace_design(PixelDesign(4, 4, name="Cores da sessão"))
        self.app.processEvents()
        QTest.mouseClick(self.module.canvas, Qt.MouseButton.LeftButton,
                         pos=self.module.canvas.cell_center(x, y))
        self.app.processEvents()

    def test_more_than_eight_session_colors_appear_and_do_not_survive_restart(self):
        colors = [f"#{0x101000 + index:06X}" for index in range(12)]
        for color in colors:
            self.module.add_custom_color(color)
        self.app.processEvents()
        for color in colors:
            self.assertIn(color, self.module._swatches)
            swatch = self.module._swatches[color]
            self.assertFalse(swatch.grab().isNull())
            image = swatch.grab().toImage()
            self.assertEqual(image.pixelColor(image.width() // 2, image.height() // 2), QColor(color))
        self.assertEqual(self.module.canvas.color, colors[-1])
        self.assertEqual(self.module.preferences.saved_colors(), [])
        self.assertFalse(self.settings_path.exists())
        self.close_module(self.module)
        self.module = self.make_module()
        for color in colors:
            self.assertNotIn(color, self.module._swatches)

    def test_color_dialog_defaults_to_session_and_requires_valid_rgb(self):
        dialog = CustomColorDialog("#123ABC", parent=self.module)
        dialog.show()
        self.app.processEvents()
        self.assertFalse(dialog.save_checkbox.isChecked())
        self.assertFalse(dialog.name_edit.isEnabled())
        dialog.hex_edit.setText("não é uma cor")
        self.app.processEvents()
        self.assertFalse(dialog.add_button.isEnabled())
        dialog.hex_edit.setText("#58aae1")
        self.app.processEvents()
        self.assertTrue(dialog.add_button.isEnabled())
        self.assertEqual(dialog.color_value(), "#58AAE1")
        with patch("piixelverso.atelier.CustomColorDialog", return_value=dialog):
            with patch.object(dialog, "exec", return_value=QDialog.DialogCode.Accepted):
                self.module.custom_color()
        self.assertIn("#58AAE1", self.module._swatches)
        self.assertEqual(self.module.preferences.saved_colors(), [])

        dialog.save_checkbox.setChecked(True)
        self.app.processEvents()
        self.assertTrue(dialog.name_edit.isEnabled())
        dialog.name_edit.setText("Azul de verão")
        with patch("piixelverso.atelier.CustomColorDialog", return_value=dialog):
            with patch.object(dialog, "exec", return_value=QDialog.DialogCode.Accepted):
                self.module.custom_color()
        saved = self.module.preferences.saved_colors()
        self.assertEqual([(entry.color, entry.name) for entry in saved], [("#58AAE1", "Azul de verão")])
        dialog.close()
        dialog.deleteLater()
        self.app.processEvents()

    def test_transparent_material_is_standard_and_cannot_be_saved_as_custom(self):
        self.assertIn(TRANSPARENT, self.module._swatches)
        dialog = CustomColorDialog(TRANSPARENT, parent=self.module)
        dialog.show()
        self.app.processEvents()
        self.assertFalse(dialog.add_button.isEnabled())
        with self.assertRaises(PreferencesError):
            self.module.preferences.save_color(TRANSPARENT, "Duplicada")
        self.assertFalse(self.settings_path.exists())
        dialog.close()
        dialog.deleteLater()

    def test_saved_color_name_reloads_in_the_palette_and_material_count(self):
        color, name = "#A104E6", "Lilás do estoque"
        self.module.add_custom_color(color.lower(), name=name, persist=True)
        self.app.processEvents()
        self.assertEqual(self.module.canvas.color, color)
        self.assertEqual(self.module.active_color_name.text(), name)
        self.assertTrue(self.module.active_color_name.isVisible())
        self.assertIn(name, self.module._swatches[color].toolTip())
        self.paint_cell()
        first = self.module.count_view.model().index(0, 0)
        self.assertEqual(first.data(Qt.ItemDataRole.DisplayRole), name)
        self.assertEqual(self.module.design.counts(), {color: 1})

        self.close_module(self.module)
        self.module = self.make_module()
        self.assertIn(color, self.module._swatches)
        self.module.select_color(color)
        self.assertEqual(self.module.active_color_name.text(), name)
        self.assertEqual(self.module.color_names[color], name)
        # A saved user name belongs to the settings file, not the module globals.
        unrelated = self.make_module(self.root / "another-user.json")
        self.assertNotIn(color, unrelated._swatches)
        self.assertNotEqual(unrelated.color_names.get(color), name)

    def test_saving_a_design_preserves_rgb_without_saving_the_palette_color(self):
        color = "#1122EE"
        self.module.add_custom_color(color)
        self.paint_cell()
        path = self.root / "cor-temporaria.pii"
        self.assertTrue(self.module._save_path(path))
        self.assertEqual(load_design(path).get_pixel(1, 1), color)
        self.assertEqual(self.module.preferences.saved_colors(), [])
        self.close_module(self.module)
        self.module = self.make_module()
        self.assertNotIn(color, self.module._swatches)
        self.assertTrue(self.module.load_path(path))
        self.assertEqual(self.module.design.get_pixel(1, 1), color)
        self.assertEqual(self.module.preferences.saved_colors(), [])

    def test_long_saved_name_keeps_the_palette_columns_inside_the_viewport(self):
        color, name = "#A31BA4", "R" * 80
        self.module.resize(1120, 750)
        self.module.add_custom_color(color, name=name, persist=True)
        self.app.processEvents()
        scroll = self.module.palette_scroll
        self.assertLessEqual(scroll.widget().minimumWidth(), scroll.viewport().width())
        self.assertEqual(self.module.active_color_name.text(), name)
        self.close_module(self.module)
        self.module = self.make_module()
        self.module.resize(1120, 750)
        self.module.select_color(color)
        self.app.processEvents()
        self.assertEqual(self.module.active_color_name.text(), name)
        self.assertLessEqual(self.module.palette_scroll.widget().minimumWidth(),
                             self.module.palette_scroll.viewport().width())

    def test_forgetting_a_saved_color_keeps_it_for_this_session(self):
        color, name = "#531A92", "Roxo personalizado"
        self.module.add_custom_color(color, name=name, persist=True)
        self.module.forget_saved_color(color)
        self.app.processEvents()
        self.assertIn(color, self.module._swatches)
        self.assertEqual(self.module.canvas.color, color)
        self.assertEqual(self.module.color_names[color], name)
        self.assertEqual(self.module.preferences.saved_colors(), [])
        self.close_module(self.module)
        self.module = self.make_module()
        self.assertNotIn(color, self.module._swatches)

    def test_failed_persistence_keeps_the_color_available_in_the_session(self):
        color = "#BA20F1"
        with patch.object(self.module.preferences, "save_color", side_effect=PreferencesError("Disco indisponível")):
            with patch("piixelverso.atelier.QMessageBox.warning") as warning:
                self.module.add_custom_color(color, name="Minha cor", persist=True)
                warning.assert_called_once()
        self.app.processEvents()
        self.assertIn(color, self.module._swatches)
        self.assertEqual(self.module.canvas.color, color)
        self.assertEqual(self.module.preferences.saved_colors(), [])
        self.assertFalse(self.settings_path.exists())


if __name__ == "__main__":
    unittest.main()
