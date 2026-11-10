"""Exercise bucket filling and global color replacement through the native UI."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from piixelverso.app import MainWindow
from piixelverso.atelier import AtelierModule, PALETTE, STYLE
from piixelverso.format import encode_design, load_design
from piixelverso.materials import material_reference
from piixelverso.model import TRANSPARENT, PixelDesign
from piixelverso.preferences import PreferencesStore


SOURCE = "#E7794B"
TARGET = "#245448"
WHITE = "#FFFFFF"


class PaintToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.settings_path = self.root / "preferences.json"
        self.preferences = PreferencesStore(self.settings_path)
        self.window = AtelierModule(preferences=self.preferences)
        self.window.show()
        self.window.activateWindow()
        self.set_design(["....", "....", "....", "...."])

    def tearDown(self):
        popup = QApplication.activePopupWidget()
        while popup is not None:
            popup.close()
            self.app.processEvents()
            popup = QApplication.activePopupWidget()
        self.window.canvas.finish_stroke()
        self.window.name_edit.setText(self.window.design.name)
        self.window.history.setClean()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def set_design(self, rows, colors=None):
        palette = {".": None, "S": SOURCE, "T": TARGET, "W": WHITE}
        palette.update(colors or {})
        design = PixelDesign(
            len(rows[0]), len(rows),
            [palette[cell] for row in rows for cell in row],
            name="Ferramentas do Ateliê",
        )
        self.window._replace_design(design)
        self.app.processEvents()
        self.window.zoom.setValue(100)
        self.app.processEvents()
        return design.clone()

    def click_cell(self, x, y, button=Qt.MouseButton.LeftButton):
        QTest.mouseClick(self.window.canvas, button,
                         pos=self.window.canvas.cell_center(x, y))
        self.app.processEvents()

    def key(self, key, modifiers=Qt.KeyboardModifier.NoModifier):
        self.window.activateWindow()
        self.window.canvas.setFocus()
        self.app.processEvents()
        QTest.keyClick(self.window.canvas, key, modifiers)
        self.app.processEvents()

    def activate_custom_target(self, dialog):
        index = dialog.target_combo.findText("Escolher cor personalizada…")
        self.assertGreaterEqual(index, 0)
        self.assertEqual(index, dialog.target_combo.count() - 1)
        dialog.target_combo.setCurrentIndex(index)
        dialog.target_combo.activated.emit(index)
        self.app.processEvents()

    def assert_counts(self, expected):
        self.assertEqual(self.window.design.counts(), expected)
        self.assertEqual(self.window.total_label.text(), str(sum(expected.values())))
        number = len(expected)
        self.assertEqual(self.window.color_total.text(),
                         f"{number} {'cor usada' if number == 1 else 'cores usadas'}")
        model = self.window.count_view.model()
        displayed = {}
        for row in range(model.rowCount()):
            color, count, _name = model.index(row, 0).data(Qt.ItemDataRole.UserRole)
            displayed[color] = count
        self.assertEqual(displayed, expected)

    def test_bucket_fills_only_connected_empty_cells_with_one_saved_history_step(self):
        original = self.set_design(["..WWW", "..WWW", "WW.WW", "..W..", "..W.."])
        path = self.root / "balde.pii"
        self.assertTrue(self.window._save_path(path))
        self.window.select_color(TARGET)
        self.window.select_tool("bucket")
        self.click_cell(0, 0)

        self.assertEqual(self.window.design.get_pixel(1, 1), TARGET)
        self.assertIsNone(self.window.design.get_pixel(2, 2), "A diagonal não une regiões")
        self.assertIsNone(self.window.design.get_pixel(0, 3))
        self.assertEqual(self.window.design.get_pixel(2, 0), WHITE)
        self.assert_counts({WHITE: 12, TARGET: 4})
        self.assertEqual(self.window.empty_total.text(), "9 vazios")
        self.assertEqual(self.window.history.count(), 1)
        self.assertFalse(self.window.history.isClean())
        self.assertIn(" *", self.window.windowTitle())
        filled = self.window.design.clone()

        self.window.undo()
        self.assertEqual(self.window.design, original)
        self.assert_counts({WHITE: 12})
        self.assertTrue(self.window.history.isClean())
        self.window.redo()
        self.assertEqual(self.window.design, filled)
        self.assert_counts({WHITE: 12, TARGET: 4})
        self.assertFalse(self.window.history.isClean())
        self.assertTrue(self.window._save_path(path))
        self.assertEqual(load_design(path), filled)
        self.window.undo()
        self.assertFalse(self.window.history.isClean())
        self.window.redo()
        self.assertTrue(self.window.history.isClean())

    def test_bucket_same_color_does_not_dirty_or_create_an_undo_step(self):
        self.set_design(["SSS", "SSS"])
        self.window.select_color(SOURCE)
        self.window.select_tool("bucket")
        before = encode_design(self.window.design)
        self.click_cell(1, 1)
        self.assertEqual(encode_design(self.window.design), before)
        self.assertEqual(self.window.history.count(), 0)
        self.assertTrue(self.window.history.isClean())
        self.assertFalse(self.window.command_actions["undo"].isEnabled())
        self.assertNotIn(" *", self.window.windowTitle())

    def test_bucket_drag_does_not_fill_another_region_and_right_click_erases_one_piece(self):
        original = self.set_design(["..W..", "..W.."])
        self.window.select_color(TARGET)
        self.window.select_tool("bucket")
        canvas = self.window.canvas
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=canvas.cell_center(0, 0))
        QTest.mouseMove(canvas, canvas.cell_center(4, 1))
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=canvas.cell_center(4, 1))
        self.app.processEvents()
        self.assert_counts({TARGET: 4, WHITE: 2})
        self.assertIsNone(self.window.design.get_pixel(4, 1))
        self.assertEqual(self.window.history.count(), 1)
        filled = self.window.design.clone()

        self.click_cell(0, 0, Qt.MouseButton.RightButton)
        self.assertIsNone(self.window.design.get_pixel(0, 0))
        self.assertEqual(self.window.design.get_pixel(1, 0), TARGET)
        self.assert_counts({TARGET: 3, WHITE: 2})
        self.assertEqual(self.window.history.count(), 2)
        self.window.undo()
        self.assertEqual(self.window.design, filled)
        self.window.undo()
        self.assertEqual(self.window.design, original)
        self.assertTrue(self.window.history.isClean())

    def test_bucket_uses_the_same_logical_cells_in_squares_and_beads_including_the_hole(self):
        for mode in ("squares", "beads"):
            with self.subTest(mode=mode):
                original = self.set_design(["SS", "S."])
                combo = self.window.display_mode_combo
                combo.setCurrentIndex(combo.findData(mode))
                self.window.select_color(TARGET)
                self.window.select_tool("bucket")
                self.app.processEvents()
                self.assertTrue(self.window.history.isClean())
                # cell_center is inside the visible hole when a bead is drawn.
                self.click_cell(0, 0)
                self.assert_counts({TARGET: 3})
                self.assertIsNone(self.window.design.get_pixel(1, 1))
                self.assertEqual(self.window.history.count(), 1)
                self.window.undo()
                self.assertEqual(self.window.design, original)
                self.assertTrue(self.window.history.isClean())

    def test_replace_merges_disconnected_islands_and_preserves_saved_color_names(self):
        source, target = "#A104E6", "#58AAE1"
        self.window.add_custom_color(source, name="Lilás do estoque", persist=True)
        self.window.add_custom_color(target, name="Azul de verão", persist=True)
        saved = self.settings_path.read_bytes()
        original = self.set_design(["S..S", ".T..", ".SW."], {"S": source, "T": target})

        self.assertEqual(self.window.replace_color(source.lower(), target.lower()), 3)
        self.assert_counts({target: 4, WHITE: 1})
        self.assertEqual(self.window.history.count(), 1)
        self.assertFalse(self.window.history.isClean())
        self.assertEqual(self.window.canvas.color, target)
        self.assertEqual(self.window.active_color_name.text(), "Azul de verão")
        first = self.window.count_view.model().index(0, 0)
        self.assertEqual(first.data(Qt.ItemDataRole.DisplayRole), "Azul de verão")
        self.assertEqual(self.window.color_names[source], "Lilás do estoque")
        self.assertEqual(self.settings_path.read_bytes(), saved)
        replaced = self.window.design.clone()

        self.window.undo()
        self.assertEqual(self.window.design, original)
        self.assert_counts({source: 3, target: 1, WHITE: 1})
        self.assertTrue(self.window.history.isClean())
        self.window.redo()
        self.assertEqual(self.window.design, replaced)
        self.assert_counts({target: 4, WHITE: 1})
        self.assertEqual(self.settings_path.read_bytes(), saved)

    def test_replace_adds_a_new_target_to_the_session_palette_without_saving_it(self):
        self.window.add_custom_color("#A104E6", name="Minha favorita", persist=True)
        saved = self.settings_path.read_bytes()
        self.set_design(["S.S", ".S."])
        target = "#123ABC"
        self.assertNotIn(target, self.window._swatches)

        self.assertEqual(self.window.replace_color(SOURCE, target.lower()), 3)
        self.app.processEvents()
        self.assertIn(target, self.window._swatches)
        self.assertEqual(self.window.canvas.color, target)
        self.assertEqual(self.window.active_hex.text(), target)
        self.assert_counts({target: 3})
        self.assertEqual(self.settings_path.read_bytes(), saved)
        reloaded = PreferencesStore(self.settings_path)
        self.assertEqual([(entry.color, entry.name) for entry in reloaded.saved_colors()],
                         [("#A104E6", "Minha favorita")])

    def test_replace_noops_preserve_the_clean_design_selection_and_history(self):
        self.set_design(["SS", ".."])
        self.window.select_color(TARGET)
        before = encode_design(self.window.design)
        for source, target in ((SOURCE, SOURCE.lower()), ("#123ABC", "#456DEF")):
            with self.subTest(source=source, target=target):
                self.assertEqual(self.window.replace_color(source, target), 0)
                self.assertEqual(encode_design(self.window.design), before)
                self.assertEqual(self.window.canvas.color, TARGET)
                self.assertEqual(self.window.history.count(), 0)
                self.assertTrue(self.window.history.isClean())
                self.assertEqual(self.preferences.saved_colors(), [])
                self.assertFalse(self.settings_path.exists())

    def test_ctrl_h_opens_the_real_dialog_and_applies_its_validated_choice(self):
        self.set_design(["SS.T", "S..."])
        self.window.select_color(TARGET)
        dialogs = []

        def accept_dialog(dialog):
            dialogs.append(dialog)
            dialog.show()
            self.app.processEvents()
            source_index = dialog.source_combo.findData(SOURCE)
            self.assertGreaterEqual(source_index, 0)
            dialog.source_combo.setCurrentIndex(source_index)
            self.assertIn("3", dialog.preview_label.text())
            self.assertFalse(dialog.target_combo.isEditable())
            dialog.target_combo.setCurrentIndex(-1)
            self.assertFalse(dialog.replace_button.isEnabled())
            dialog.target_combo.setCurrentIndex(dialog.target_combo.findData(SOURCE))
            self.assertFalse(dialog.replace_button.isEnabled())
            dialog.target_combo.setCurrentIndex(dialog.target_combo.findData(TARGET))
            self.app.processEvents()
            self.assertTrue(dialog.replace_button.isEnabled())
            self.assertEqual(dialog.source_color(), SOURCE)
            self.assertEqual(dialog.target_color(), TARGET)
            QTest.mouseClick(dialog.replace_button, Qt.MouseButton.LeftButton)
            self.app.processEvents()
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
            return dialog.result()

        with patch("piixelverso.atelier.ReplaceColorDialog.exec", new=accept_dialog):
            self.key(Qt.Key.Key_H, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(len(dialogs), 1)
        self.assert_counts({TARGET: 4})
        self.assertEqual(self.window.history.count(), 1)

    def test_canceling_the_replacement_dialog_leaves_pixels_and_palette_untouched(self):
        self.set_design(["S.S", ".T."])
        before = encode_design(self.window.design)
        palette = set(self.window._swatches)
        dialogs = []
        chosen = []

        def cancel_dialog(dialog):
            dialogs.append(dialog)
            dialog.show()
            with patch("piixelverso.replace.QColorDialog.getColor",
                       return_value=QColor("#123ABC")) as picker:
                self.activate_custom_target(dialog)
                picker.assert_called_once()
            self.assertEqual(dialog.target_color(), "#123ABC")
            chosen.append(dialog.target_color())
            self.app.processEvents()
            QTest.keyClick(dialog, Qt.Key.Key_Escape)
            self.app.processEvents()
            self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)
            return dialog.result()

        with patch("piixelverso.atelier.ReplaceColorDialog.exec", new=cancel_dialog):
            QTest.mouseClick(self.window.command_bar.buttons["replace_color"],
                             Qt.MouseButton.LeftButton)
            self.app.processEvents()
        self.assertEqual(len(dialogs), 1)
        self.assertEqual(chosen, ["#123ABC"])
        self.assertEqual(encode_design(self.window.design), before)
        self.assertEqual(set(self.window._swatches), palette)
        self.assertEqual(self.window.history.count(), 0)
        self.assertTrue(self.window.history.isClean())
        self.assertFalse(self.settings_path.exists())

    def test_target_dropdown_includes_the_palette_and_saved_custom_colors_unused_in_the_design(self):
        named, unnamed = "#08AA22", "#5B51CC"
        name = "<b>Verde & folhas</b> " + "muito longo " * 5
        name = name[:80]
        self.window.add_custom_color(named, name=name, persist=True)
        self.window.add_custom_color(unnamed, persist=True)
        self.window.add_custom_color("#112233")
        saved = self.settings_path.read_bytes()
        original = self.set_design(["SS.U", "S..."], {"U": "#334455"})
        self.window.select_color(TARGET)
        dialogs = []

        def accept_saved_target(dialog):
            dialogs.append(dialog)
            dialog.show()
            self.app.processEvents()
            self.assertFalse(dialog.target_combo.isEditable())
            self.assertEqual(dialog.target_color(), TARGET)
            sources = {dialog.source_combo.itemData(i) for i in range(dialog.source_combo.count())}
            self.assertEqual(sources, {SOURCE, "#334455"})
            self.assertEqual(dialog.source_color(), SOURCE)
            self.assertIn("3 peças", dialog.source_combo.currentText())
            for label, color in PALETTE:
                with self.subTest(color=color):
                    index = dialog.target_combo.findData(color)
                    self.assertGreaterEqual(index, 0)
                    self.assertIn(label, dialog.target_combo.itemText(index))
                    self.assertIn(material_reference(color), dialog.target_combo.itemText(index))
                    self.assertFalse(dialog.target_combo.itemIcon(index).isNull())
            named_index = dialog.target_combo.findData(named)
            self.assertGreaterEqual(named_index, 0)
            self.assertIn(named, dialog.target_combo.itemText(named_index))
            tooltip = dialog.target_combo.itemData(named_index, Qt.ItemDataRole.ToolTipRole)
            self.assertIn("&lt;b&gt;Verde &amp; folhas&lt;/b&gt;", tooltip)
            self.assertLessEqual(dialog.width(), 600)
            unnamed_index = dialog.target_combo.findData(unnamed)
            self.assertGreaterEqual(unnamed_index, 0)
            self.assertIn(unnamed, dialog.target_combo.itemText(unnamed_index))
            self.assertEqual(dialog.target_combo.findData("#112233"), -1)
            self.assertEqual(dialog.target_combo.findData("#334455"), -1)
            dialog.target_combo.setCurrentIndex(named_index)
            self.assertTrue(dialog.replace_button.isEnabled())
            QTest.mouseClick(dialog.replace_button, Qt.MouseButton.LeftButton)
            self.app.processEvents()
            return dialog.result()

        with patch("piixelverso.atelier.ReplaceColorDialog.exec", new=accept_saved_target):
            self.key(Qt.Key.Key_H, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(len(dialogs), 1)
        self.assert_counts({named: 3, "#334455": 1})
        self.assertEqual(self.window.history.count(), 1)
        self.assertEqual(self.settings_path.read_bytes(), saved)
        self.window.undo()
        self.assertEqual(self.window.design, original)
        self.assertTrue(self.window.history.isClean())

    def test_replacement_dropdown_uses_transparent_as_source_and_target(self):
        self.set_design(["X.S"], {"X": TRANSPARENT})
        dialogs = []

        def reject_dialog(dialog):
            dialogs.append(dialog)
            return QDialog.DialogCode.Rejected

        with patch("piixelverso.atelier.ReplaceColorDialog.exec", new=reject_dialog):
            self.window.show_replace_color_dialog()
        instance = dialogs[0]
        self.assertGreaterEqual(instance.source_combo.findData(TRANSPARENT), 0)
        target_index = instance.target_combo.findData(TRANSPARENT)
        self.assertGreaterEqual(target_index, 0)
        self.assertIn("Transparente", instance.target_combo.itemText(target_index))
        self.assertEqual(self.window.replace_color(SOURCE, TRANSPARENT), 1)
        self.assertEqual(self.window.design.counts(), {TRANSPARENT: 2})

    def test_canceling_the_custom_target_picker_restores_the_previous_dropdown_choice(self):
        self.set_design(["SS.T", "S..."])
        self.window.select_color(TARGET)
        before = encode_design(self.window.design)
        palette = set(self.window._swatches)
        dialogs = []
        restored = []

        def cancel_picker_then_dialog(dialog):
            dialogs.append(dialog)
            dialog.show()
            self.app.processEvents()
            original_source = dialog.source_color()
            original_target = dialog.target_color()
            with patch("piixelverso.replace.QColorDialog.getColor",
                       return_value=QColor()) as picker:
                self.activate_custom_target(dialog)
                picker.assert_called_once()
            self.assertEqual(dialog.source_color(), original_source)
            self.assertEqual(dialog.target_color(), original_target)
            self.assertEqual(dialog.target_combo.currentData(), TARGET)
            self.assertTrue(dialog.replace_button.isEnabled())
            restored.append(dialog.target_color())
            dialog.reject()
            return dialog.result()

        with patch("piixelverso.atelier.ReplaceColorDialog.exec", new=cancel_picker_then_dialog):
            self.key(Qt.Key.Key_H, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(len(dialogs), 1)
        self.assertEqual(restored, [TARGET])
        self.assertEqual(encode_design(self.window.design), before)
        self.assertEqual(set(self.window._swatches), palette)
        self.assertEqual(self.window.history.count(), 0)
        self.assertFalse(self.settings_path.exists())

    def test_custom_target_can_choose_an_existing_color_without_duplicate_entries(self):
        self.set_design(["SS.T", "S..."])
        self.window.select_color(SOURCE)
        dialogs = []

        def choose_existing_target(dialog):
            dialogs.append(dialog)
            dialog.show()
            self.app.processEvents()
            self.assertFalse(dialog.replace_button.isEnabled())
            original_count = dialog.target_combo.count()
            with patch("piixelverso.replace.QColorDialog.getColor",
                       return_value=QColor(TARGET.lower())) as picker:
                self.activate_custom_target(dialog)
                picker.assert_called_once()
            self.assertEqual(dialog.target_combo.count(), original_count)
            self.assertEqual(sum(dialog.target_combo.itemData(i) == TARGET
                                 for i in range(dialog.target_combo.count())), 1)
            self.assertEqual(dialog.source_color(), SOURCE)
            self.assertEqual(dialog.target_color(), TARGET)
            self.assertTrue(dialog.replace_button.isEnabled())
            QTest.mouseClick(dialog.replace_button, Qt.MouseButton.LeftButton)
            self.app.processEvents()
            return dialog.result()

        with patch("piixelverso.atelier.ReplaceColorDialog.exec", new=choose_existing_target):
            self.key(Qt.Key.Key_H, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(len(dialogs), 1)
        self.assert_counts({TARGET: 4})
        self.assertEqual(self.window.history.count(), 1)
        self.assertFalse(self.settings_path.exists())

    def test_g_selects_the_bucket_exclusively_without_stealing_the_design_name(self):
        for key, tool in ((Qt.Key.Key_G, "bucket"), (Qt.Key.Key_B, "pencil"),
                          (Qt.Key.Key_E, "eraser"), (Qt.Key.Key_I, "picker")):
            with self.subTest(tool=tool):
                self.key(key)
                self.assertEqual(self.window.canvas.tool, tool)
                self.assertTrue(self.window.tool_buttons[tool].isChecked())
                checked = [name for name in ("pencil", "eraser", "picker", "bucket")
                           if self.window.command_actions[name].isChecked()]
                self.assertEqual(checked, [tool])
        self.window.select_tool("eraser")
        self.window.name_edit.setFocus()
        self.window.name_edit.selectAll()
        self.app.processEvents()
        QTest.keyClicks(self.window.name_edit, "G")
        self.app.processEvents()
        self.assertEqual(self.window.name_edit.text(), "G")
        self.assertEqual(self.window.canvas.tool, "eraser")

    def test_new_actions_are_inactive_on_home_and_restore_with_the_module(self):
        shell = MainWindow(preferences=self.preferences)
        try:
            shell.show()
            shell.activateWindow()
            module = shell.open_module("atelier")
            self.assertTrue(module.command_actions["bucket"].isEnabled())
            self.assertFalse(module.command_actions["replace_color"].isEnabled())
            module._replace_design(PixelDesign(2, 2, [SOURCE, None, None, None], name="Cor no Ateliê"))
            self.app.processEvents()
            module.select_tool("eraser")
            shell.show_home()
            self.app.processEvents()
            self.assertIsNone(shell.current_module)
            for key in ("bucket", "replace_color"):
                self.assertFalse(module.command_actions[key].isEnabled())
                self.assertFalse(module.command_bar.buttons[key].isEnabled())
            target = shell.home_page.module_buttons["atelier"]
            target.setFocus()
            with patch("piixelverso.atelier.ReplaceColorDialog.exec",
                       side_effect=AssertionError("O diálogo não deve abrir na página inicial")):
                QTest.keyClick(target, Qt.Key.Key_G)
                QTest.keyClick(target, Qt.Key.Key_H, Qt.KeyboardModifier.ControlModifier)
                self.app.processEvents()
            self.assertEqual(module.canvas.tool, "eraser")
            self.assertTrue(module.history.isClean())
            self.assertIs(shell.open_module("atelier"), module)
            self.app.processEvents()
            for key in ("bucket", "replace_color"):
                self.assertTrue(module.command_actions[key].isEnabled())
            module.set_active(False)
            self.assertFalse(module.command_actions["bucket"].isEnabled())
            self.assertFalse(module.command_actions["replace_color"].isEnabled())
        finally:
            for module in shell.module_pages.values():
                module.canvas.finish_stroke()
                module.name_edit.setText(module.design.name)
                module.history.setClean()
            shell.close()
            shell.deleteLater()
            self.app.processEvents()

    def test_added_commands_fit_the_compact_bar_at_the_minimum_window_width(self):
        self.window.resize(1120, 750)
        self.app.processEvents()
        bar = self.window.command_bar
        self.assertLessEqual(bar.height(), 44)
        self.assertIn("bucket", bar.buttons)
        self.assertIn("replace_color", bar.buttons)
        controls = list(bar.buttons.values()) + [
            bar.display_mode_combo, bar.grid_checkbox, bar.zoom_slider, bar.zoom_label,
        ]
        for control in controls:
            with self.subTest(control=control.accessibleName() or control.objectName()):
                self.assertTrue(control.isVisible())
                bounds = QRect(control.mapTo(bar, QPoint(0, 0)), control.size())
                self.assertTrue(bar.rect().contains(bounds), f"Controle fora da barra: {bounds}")


if __name__ == "__main__":
    unittest.main()
