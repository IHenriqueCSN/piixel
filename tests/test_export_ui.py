"""Exercise PNG export choices, file handling and shared measurement settings."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from piixelverso.app import MainWindow, STYLE
from piixelverso.format import encode_design
from piixelverso.model import PixelDesign
from piixelverso.preferences import PreferencesStore


CORAL = "#E7794B"
FOREST = "#245448"


class ExportPngUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.preferences = PreferencesStore(self.root / "preferences.json")
        self.window = MainWindow(preferences=self.preferences)
        self.window.show()
        self.window.activateWindow()
        self.atelier = self.window.open_module("atelier")
        self.atelier._replace_design(PixelDesign(
            4, 3,
            [CORAL, FOREST, None, None,
             CORAL, None, FOREST, None,
             None, None, CORAL, "#FFFFFF"],
            name="Exportação do João",
        ))
        self.source_path = self.root / "design do João.pii"
        self.assertTrue(self.atelier._save_path(self.source_path))
        self.app.processEvents()

    def tearDown(self):
        popup = QApplication.activePopupWidget()
        while popup is not None:
            popup.close()
            self.app.processEvents()
            popup = QApplication.activePopupWidget()
        for module in self.window.module_pages.values():
            if hasattr(module, "history"):
                module.canvas.finish_stroke()
                module.name_edit.setText(module.design.name)
                module.history.setClean()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def editor_state(self):
        return (
            encode_design(self.atelier.design),
            self.atelier.file_path,
            self.atelier.history.count(), self.atelier.history.index(),
            self.atelier.history.isClean(),
            self.source_path.read_bytes(),
            self.preferences.path.read_bytes(),
            self.preferences.recent_files(),
            self.atelier.canvas.display_mode, self.atelier.canvas.show_grid,
        )

    def key_export(self):
        self.window.activateWindow()
        self.atelier.canvas.setFocus()
        self.app.processEvents()
        QTest.keyClick(self.atelier.canvas, Qt.Key.Key_E,
                       Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        self.app.processEvents()

    def click_export_menu(self):
        bar = self.atelier.command_bar.menubar
        menu = self.atelier.command_bar.menus["file"]
        QTest.mouseClick(bar, Qt.MouseButton.LeftButton,
                         pos=bar.actionGeometry(menu.menuAction()).center())
        self.app.processEvents()
        self.assertTrue(menu.isVisible())
        action = self.atelier.command_actions["export_png"]
        self.assertIn(action, menu.actions())
        QTest.mouseClick(menu, Qt.MouseButton.LeftButton,
                         pos=menu.actionGeometry(action).center())
        self.app.processEvents()

    def accept_options(self, mode, grid):
        def accept(dialog):
            dialog.show()
            self.app.processEvents()
            self.assertEqual(dialog.display_mode(), self.atelier.canvas.display_mode)
            self.assertEqual(dialog.show_grid(), self.atelier.canvas.show_grid)
            self.assertEqual(dialog.piece_size_mm(), self.preferences.piece_size_mm())
            self.assertFalse(dialog.preview_label.pixmap().isNull())
            dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData(mode))
            dialog.grid_checkbox.setChecked(grid)
            self.app.processEvents()
            self.assertEqual(dialog.display_mode(), mode)
            self.assertEqual(dialog.show_grid(), grid)
            self.assertTrue(dialog.export_button.isEnabled())
            QTest.mouseClick(dialog.export_button, Qt.MouseButton.LeftButton)
            self.app.processEvents()
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
            return dialog.result()
        return accept

    def read_png(self, path):
        self.assertTrue(path.is_file(), str(path))
        self.assertTrue(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        image = QImage(str(path))
        self.assertFalse(image.isNull())
        return image

    def test_file_menu_and_shortcut_export_all_display_options_to_the_chosen_folder(self):
        from piixelverso.png_export import export_layout

        destination = self.root / "imagens exportadas"
        destination.mkdir()
        self.atelier.display_mode_combo.setCurrentIndex(1)
        self.atelier.command_bar.grid_checkbox.setChecked(False)
        self.app.processEvents()
        before = self.editor_state()
        images = {}
        for mode, grid in (("squares", False), ("squares", True),
                           ("beads", False), ("beads", True)):
            with self.subTest(mode=mode, grid=grid):
                path = destination / f"{mode}-{grid}.png"
                with patch("piixelverso.atelier.ExportPngDialog.exec",
                           new=self.accept_options(mode, grid)), patch(
                    "piixelverso.atelier.QFileDialog.getSaveFileName",
                    return_value=(str(path), "PNG (*.png)"),
                ) as picker:
                    if not images:
                        self.click_export_menu()
                    else:
                        self.key_export()
                    picker.assert_called_once()
                    args = picker.call_args.args
                    self.assertIs(args[0], self.window)
                    self.assertEqual(Path(args[2]).name, self.source_path.with_suffix(".png").name)
                    self.assertIn("*.png", args[3])
                image = self.read_png(path)
                self.assertEqual(image.dotsPerMeterX(), 6400)
                self.assertEqual(image.dotsPerMeterY(), 6400)
                images[mode, grid] = image
                self.assertEqual(self.editor_state(), before)

        layout = export_layout(self.atelier.design, 5.0)
        cx, cy = layout.grid_left + layout.cell_size // 2, layout.grid_top + layout.cell_size // 2
        self.assertEqual(images["squares", False].pixelColor(cx, cy).name().upper(), CORAL)
        self.assertEqual(images["beads", False].pixelColor(cx, cy).name().upper(), "#FFFFFF")
        border_x = layout.grid_left + layout.cell_size
        for mode in ("squares", "beads"):
            self.assertNotEqual(images[mode, False].pixelColor(border_x, cy),
                                images[mode, True].pixelColor(border_x, cy))
        self.assertEqual(layout.width_label, "20 mm")
        self.assertEqual(layout.height_label, "15 mm")
        self.assertEqual(images["squares", False].pixelColor(
            layout.grid_left + layout.grid_width // 2, layout.horizontal_arrow_y).name(), "#000000")
        self.assertEqual(images["squares", False].pixelColor(
            layout.vertical_arrow_x, layout.grid_top + layout.grid_height // 2).name(), "#000000")

    def test_canceling_export_options_preserves_the_document_and_skips_the_file_chooser(self):
        before = self.editor_state()
        with patch("piixelverso.atelier.ExportPngDialog.exec",
                   return_value=QDialog.DialogCode.Rejected) as options, patch(
            "piixelverso.atelier.QFileDialog.getSaveFileName",
            side_effect=AssertionError("Cancelar as opções não deve abrir o seletor de arquivos"),
        ):
            self.key_export()
            options.assert_called_once()
        self.assertEqual(self.editor_state(), before)
        self.assertEqual(list(self.root.rglob("*.png")), [])

    def test_preview_and_png_measure_only_the_painted_design_inside_an_empty_border(self):
        from piixelverso.png_export import export_layout

        design = PixelDesign(10, 9, name="Peças dentro da grade")
        design.set_pixel(2, 1, CORAL)
        design.set_pixel(6, 5, FOREST)
        design.set_pixel(7, 6, "#FFFFFF")
        self.atelier._replace_design(design)
        self.assertTrue(self.atelier._save_path(self.source_path))
        self.app.processEvents()
        for mm, width_label, height_label in ((5.0, "30 mm", "30 mm"),
                                             (2.6, "15,6 mm", "15,6 mm")):
            self.preferences.set_piece_size_mm(mm)
            for mode in ("squares", "beads"):
                with self.subTest(piece_size_mm=mm, mode=mode):
                    before = self.editor_state()
                    path = self.root / f"arte-{mode}-{mm}.png"
                    accept = self.accept_options(mode, False)

                    def accept_measured_design(dialog):
                        self.assertIn(f"Largura: {width_label}", dialog.dimensions_label.text())
                        self.assertIn(f"Altura: {height_label}", dialog.dimensions_label.text())
                        return accept(dialog)

                    with patch("piixelverso.atelier.ExportPngDialog.exec",
                               new=accept_measured_design), patch(
                        "piixelverso.atelier.QFileDialog.getSaveFileName",
                        return_value=(str(path), "PNG (*.png)"),
                    ):
                        self.key_export()
                    image = self.read_png(path)
                    layout = export_layout(design, mm)
                    self.assertEqual((layout.width_label, layout.height_label),
                                     (width_label, height_label))
                    self.assertEqual(layout.design_left, layout.grid_left + 2 * layout.cell_size)
                    self.assertEqual(layout.design_top, layout.grid_top + layout.cell_size)
                    self.assertEqual((layout.design_width, layout.design_height),
                                     (6 * layout.cell_size, 6 * layout.cell_size))
                    self.assertEqual(image.pixelColor(
                        layout.design_left + layout.design_width // 2,
                        layout.horizontal_arrow_y).name(), "#000000")
                    self.assertEqual(image.pixelColor(
                        layout.vertical_arrow_x,
                        layout.design_top + layout.design_height // 2).name(), "#000000")
                    self.assertEqual(image.pixelColor(
                        layout.grid_left + layout.grid_width,
                        layout.horizontal_arrow_y).name(), "#ffffff")
                    self.assertEqual(image.dotsPerMeterX(), round(32000 / mm))
                    self.assertEqual(self.editor_state(), before)

    def test_canceling_the_save_location_does_not_write_or_change_the_document(self):
        before = self.editor_state()
        with patch("piixelverso.atelier.ExportPngDialog.exec",
                   new=self.accept_options("beads", True)), patch(
            "piixelverso.atelier.QFileDialog.getSaveFileName", return_value=("", "PNG (*.png)"),
        ) as picker:
            self.key_export()
            picker.assert_called_once()
        self.assertEqual(self.editor_state(), before)
        self.assertEqual(list(self.root.rglob("*.png")), [])

    def test_png_extension_is_added_without_overwriting_a_pii_file(self):
        before = self.editor_state()
        with patch("piixelverso.atelier.ExportPngDialog.exec",
                   new=self.accept_options("squares", False)), patch(
            "piixelverso.atelier.QFileDialog.getSaveFileName",
            return_value=(str(self.source_path), "PNG (*.png)"),
        ):
            self.key_export()
        self.read_png(Path(str(self.source_path) + ".png"))
        self.assertEqual(self.editor_state(), before)

    def test_an_existing_implicit_png_requires_overwrite_confirmation(self):
        path = self.root / "imagem.png"
        path.write_bytes(b"Imagem anterior preservada")
        before = self.editor_state()
        with patch("piixelverso.atelier.ExportPngDialog.exec",
                   new=self.accept_options("squares", False)), patch(
            "piixelverso.atelier.QFileDialog.getSaveFileName",
            return_value=(str(path.with_suffix("")), "PNG (*.png)"),
        ), patch("piixelverso.atelier.QMessageBox.question",
                 return_value=QMessageBox.StandardButton.No) as confirmation:
            self.key_export()
            confirmation.assert_called_once()
        self.assertEqual(path.read_bytes(), b"Imagem anterior preservada")
        self.assertEqual(self.editor_state(), before)

    def test_export_failure_reports_the_error_and_preserves_document_and_existing_image(self):
        path = self.root / "anterior.png"
        path.write_bytes(b"Imagem anterior preservada")
        before = self.editor_state()
        with patch("piixelverso.atelier.save_png", side_effect=OSError("Disco indisponível")), patch(
            "piixelverso.atelier.QMessageBox.warning",
        ) as warning:
            self.assertFalse(self.atelier.export_png_path(path, display_mode="beads", show_grid=False))
            warning.assert_called_once()
            self.assertIs(warning.call_args.args[0], self.window)
        self.assertEqual(path.read_bytes(), b"Imagem anterior preservada")
        self.assertEqual(self.editor_state(), before)

    def test_settings_change_the_next_png_measurements_without_discarding_the_atelier_session(self):
        from piixelverso.png_export import export_layout

        self.atelier.zoom.setValue(100)
        self.atelier.select_color("#ED5598")
        self.app.processEvents()
        QTest.mouseClick(self.atelier.canvas, Qt.MouseButton.LeftButton,
                         pos=self.atelier.canvas.cell_center(1, 2))
        self.app.processEvents()
        design = encode_design(self.atelier.design)
        history = (self.atelier.history.count(), self.atelier.history.index(), self.atelier.history.isClean())
        recents = self.preferences.recent_files()
        self.window.show_home()
        self.app.processEvents()
        QTest.mouseClick(self.window.home_page.module_buttons["settings"], Qt.MouseButton.LeftButton)
        self.app.processEvents()
        settings = self.window.module_pages["settings"]
        self.assertEqual(self.window.current_module, "settings")
        self.assertIn("Configurações", self.window.windowTitle())
        self.assertIs(settings.preferences, self.preferences)
        self.assertEqual(settings.piece_size_input.value(), 5.0)
        self.assertFalse(self.atelier.command_actions["export_png"].isEnabled())
        with patch("piixelverso.atelier.ExportPngDialog.exec",
                   side_effect=AssertionError("O atalho do Ateliê não deve abrir em Configurações")):
            QTest.keyClick(settings.save_button, Qt.Key.Key_E,
                           Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            self.app.processEvents()
        settings.piece_size_input.setValue(2.6)
        QTest.mouseClick(settings.save_button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(self.preferences.piece_size_mm(), 2.6)
        self.assertEqual(PreferencesStore(self.preferences.path).piece_size_mm(), 2.6)

        QTest.keyClick(settings.save_button, Qt.Key.Key_Home, Qt.KeyboardModifier.AltModifier)
        self.app.processEvents()
        self.assertIsNone(self.window.current_module)
        QTest.mouseClick(self.window.home_page.module_buttons["atelier"], Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertIs(self.window.module_pages["atelier"], self.atelier)
        self.assertEqual(encode_design(self.atelier.design), design)
        self.assertEqual((self.atelier.history.count(), self.atelier.history.index(), self.atelier.history.isClean()), history)
        self.assertTrue(self.atelier.command_actions["export_png"].isEnabled())
        path = self.root / "medidas-personalizadas.png"
        self.assertTrue(self.atelier.export_png_path(path, display_mode="squares", show_grid=False))
        image = self.read_png(path)
        self.assertEqual(image.dotsPerMeterX(), round(32000 / 2.6))
        self.assertEqual(image.dotsPerMeterY(), round(32000 / 2.6))
        layout = export_layout(self.atelier.design, 2.6)
        self.assertEqual((layout.width_label, layout.height_label), ("10,4 mm", "7,8 mm"))
        self.assertEqual(self.preferences.recent_files(), recents)
        self.assertEqual((self.atelier.history.count(), self.atelier.history.index(), self.atelier.history.isClean()), history)
        self.window.open_module("settings")
        self.app.processEvents()
        self.assertIs(self.window.module_pages["settings"], settings)

    def test_export_commits_pending_paint_and_name_before_rendering_the_png(self):
        from piixelverso.png_export import export_layout

        self.atelier.zoom.setValue(100)
        self.atelier.select_color("#ED5598")
        self.atelier.name_edit.setText("Nome antes de exportar")
        self.app.processEvents()
        QTest.mousePress(self.atelier.canvas, Qt.MouseButton.LeftButton,
                         pos=self.atelier.canvas.cell_center(3, 0))
        path = self.root / "ultimo-pixel.png"
        exported = self.atelier.export_png_path(path, display_mode="squares", show_grid=False)
        QTest.mouseRelease(self.atelier.canvas, Qt.MouseButton.LeftButton,
                           pos=self.atelier.canvas.cell_center(3, 0))
        self.assertTrue(exported)
        self.app.processEvents()
        image = self.read_png(path)
        layout = export_layout(self.atelier.design, 5.0)
        x = layout.grid_left + 3 * layout.cell_size + layout.cell_size // 2
        y = layout.grid_top + layout.cell_size // 2
        self.assertEqual(image.pixelColor(x, y).name().upper(), "#ED5598")
        self.assertEqual(self.atelier.design.name, "Nome antes de exportar")
        self.assertEqual(self.atelier.design.get_pixel(3, 0), "#ED5598")
        self.assertFalse(self.atelier.history.isClean())
        self.assertEqual(self.atelier.file_path, self.source_path)


if __name__ == "__main__":
    unittest.main()
