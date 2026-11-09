"""Recent color shortcuts through real Qt focus, navigation and drawing events."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QSpinBox, QVBoxLayout

from piixelverso.app import MainWindow, STYLE
from piixelverso.atelier import AtelierModule
from piixelverso.editor.palette import PALETTE
from piixelverso.format import encode_design, save_design
from piixelverso.model import PixelDesign
from piixelverso.preferences import PreferencesStore


class RecentColorShortcutTests(unittest.TestCase):
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
        self.atelier._replace_design(PixelDesign(8, 8, name="Cores recentes"))
        self.extra_modules = []
        self.app.processEvents()
        self.atelier.zoom.setValue(100)
        self.app.processEvents()

    def tearDown(self):
        popup = QApplication.activePopupWidget()
        while popup is not None:
            popup.close()
            self.app.processEvents()
            popup = QApplication.activePopupWidget()
        for module in [self.atelier, *self.extra_modules]:
            module.canvas.cancel_stroke()
            module.canvas.finish_stroke()
            module.name_edit.setText(module.design.name)
            module.history.setClean()
        for module in self.extra_modules:
            module.close()
            module.deleteLater()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def key(self, digit, *, target=None, modifiers=Qt.KeyboardModifier.NoModifier):
        target = target or self.atelier.canvas
        self.window.activateWindow()
        target.setFocus()
        self.app.processEvents()
        QTest.keyClick(target, Qt.Key(int(Qt.Key.Key_0) + digit), modifiers)
        self.app.processEvents()

    def seed(self, count=9):
        colors = [color for _name, color in PALETTE[:count]]
        for color in colors:
            self.atelier.select_color(color)
        return tuple(dict.fromkeys(reversed(["#E7794B", *colors])))[:9]

    def test_recent_list_deduplicates_normalizes_and_keeps_nine_latest_choices(self):
        self.assertEqual(self.atelier.recent_colors, ("#E7794B",))
        colors = [f"#{0x123A00 + index:06X}" for index in range(12)]
        for color in colors:
            self.atelier.select_color(color.lower())
        self.assertEqual(self.atelier.recent_colors, tuple(reversed(colors[-9:])))
        self.atelier.select_color(colors[-4].lower())
        self.assertEqual(self.atelier.recent_colors[0], colors[-4])
        self.assertEqual(len(self.atelier.recent_colors), 9)
        self.assertEqual(len(set(self.atelier.recent_colors)), 9)
        self.assertFalse(self.preferences.path.exists())
        self.assertEqual(self.preferences.saved_colors(), [])

    def test_all_nine_digits_select_the_visible_slot_without_editing_the_design(self):
        expected = self.seed()
        self.atelier.select_tool("rectangle")
        before = encode_design(self.atelier.design)
        for digit, color in enumerate(expected, 1):
            with self.subTest(digit=digit):
                button = self.atelier.view.recent_colors_widget.buttons[digit - 1]
                self.assertEqual(button.text(), str(digit))
                self.assertEqual(button.property("color"), color)
                self.key(digit)
                self.assertEqual(self.atelier.canvas.color, color)
                self.assertEqual(self.atelier.recent_colors, expected)
                self.assertEqual(self.atelier.canvas.tool, "rectangle")
        self.assertEqual(encode_design(self.atelier.design), before)
        self.assertEqual(self.atelier.history.count(), 0)
        self.assertTrue(self.atelier.history.isClean())

    def test_shortcuts_work_after_palette_click_and_from_the_numeric_keypad(self):
        self.seed(4)
        color = PALETTE[7][1]
        swatch = self.atelier._swatches[color]
        QTest.mouseClick(swatch, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        expected = self.atelier.recent_colors
        self.key(2, target=swatch)
        self.assertEqual(self.atelier.canvas.color, expected[1])
        self.key(3, modifiers=Qt.KeyboardModifier.KeypadModifier)
        self.assertEqual(self.atelier.canvas.color, expected[2])
        self.assertEqual(self.atelier.recent_colors, expected)

    def test_alternating_numbers_and_clicking_recent_colors_keep_the_slots_stable(self):
        expected = self.seed(3)
        for digit in (1, 2, 1, 2, 1, 2):
            self.key(digit)
            self.assertEqual(self.atelier.canvas.color, expected[digit - 1])
            self.assertEqual(self.atelier.recent_colors, expected)
        widget = self.atelier.view.recent_colors_widget
        for index in (0, 2, 1):
            QTest.mouseClick(widget.buttons[index], Qt.MouseButton.LeftButton)
            self.app.processEvents()
            self.assertEqual(self.atelier.canvas.color, expected[index])
            self.assertEqual(self.atelier.recent_colors, expected)

    def test_empty_slots_and_out_of_range_selections_are_harmless(self):
        original = self.atelier.canvas.color
        self.assertTrue(self.atelier.recent_color_actions[0].isEnabled())
        for action, button in zip(self.atelier.recent_color_actions[1:],
                                  self.atelier.view.recent_colors_widget.buttons[1:]):
            self.assertFalse(action.isEnabled())
            self.assertFalse(button.isEnabled())
        self.key(9)
        for index in (-1, 9, 99):
            self.atelier.select_recent_color(index)
        self.assertEqual(self.atelier.canvas.color, original)
        self.assertEqual(self.atelier.recent_colors, (original,))

    def test_typing_numbers_in_the_design_name_does_not_select_colors(self):
        self.seed(9)
        original = self.atelier.canvas.color
        name = self.atelier.name_edit
        name.setFocus()
        name.selectAll()
        self.app.processEvents()
        QTest.keyClicks(name, "123456789")
        self.app.processEvents()
        self.assertEqual(name.text(), "123456789")
        self.assertEqual(self.atelier.canvas.color, original)

    def test_modal_text_and_dimension_fields_keep_their_numeric_input(self):
        self.seed(9)
        original = self.atelier.canvas.color
        dialog = QDialog(self.window)
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        line = QLineEdit()
        size = QSpinBox()
        size.setRange(10, 128)
        layout.addWidget(line)
        layout.addWidget(size)
        dialog.show()
        dialog.activateWindow()
        self.app.processEvents()
        try:
            line.setFocus()
            QTest.keyClicks(line, "123456789")
            self.app.processEvents()
            self.assertEqual(line.text(), "123456789")
            size.setFocus()
            size.selectAll()
            QTest.keyClicks(size, "128")
            self.app.processEvents()
            self.assertEqual(size.value(), 128)
            self.assertEqual(self.atelier.canvas.color, original)
        finally:
            dialog.close()
            dialog.deleteLater()
            self.app.processEvents()

    def test_shortcuts_are_inactive_on_home_settings_and_piixelfone(self):
        self.seed(4)
        original = self.atelier.canvas.color
        self.window.show_home()
        self.app.processEvents()
        self.key(2, target=self.window.home_page.module_buttons["atelier"])
        self.assertTrue(all(not action.isEnabled() for action in self.atelier.recent_color_actions))
        self.assertEqual(self.atelier.canvas.color, original)
        settings = self.window.open_module("settings")
        self.app.processEvents()
        self.key(3, target=settings.home_button)
        self.assertEqual(self.atelier.canvas.color, original)
        phone = self.window.open_module("piixelfone")
        self.app.processEvents()
        self.key(4, target=phone.home_button)
        self.assertEqual(self.atelier.canvas.color, original)
        self.window.open_module("atelier")
        self.app.processEvents()
        self.key(2)
        self.assertEqual(self.atelier.canvas.color, self.atelier.recent_colors[1])

    def test_session_colors_survive_navigation_new_and_open_but_reset_on_restart(self):
        expected = self.seed(4)
        self.window.show_home()
        self.window.open_module("atelier")
        self.atelier._replace_design(PixelDesign(10, 10, name="Novo design"))
        self.assertEqual(self.atelier.recent_colors, expected)
        path = self.root / "outro.pii"
        save_design(PixelDesign(12, 10, name="Design aberto"), path)
        self.assertTrue(self.atelier.load_path(path))
        self.assertEqual(self.atelier.recent_colors, expected)
        fresh = AtelierModule(preferences=PreferencesStore(self.preferences.path))
        self.extra_modules.append(fresh)
        self.assertEqual(fresh.recent_colors, ("#E7794B",))
        self.assertEqual(self.preferences.saved_colors(), [])

    def test_custom_picker_and_material_colors_enter_the_recent_slots(self):
        custom, saved = "#12AB34", "#BA43D8"
        self.atelier.add_custom_color(custom, name="Cor da sessão")
        self.atelier.add_custom_color(saved, name="Minha cor salva", persist=True)
        self.assertEqual(self.atelier.recent_colors[:2], (saved, custom))
        self.assertIn("Minha cor salva", self.atelier.view.recent_colors_widget.buttons[0].toolTip())
        self.atelier.pick_color("#AABBCC")
        self.assertEqual(self.atelier.recent_colors[0], "#AABBCC")
        self.assertEqual(self.atelier.canvas.tool, "pencil")
        design = PixelDesign(8, 8)
        design.set_pixel(2, 2, custom)
        self.atelier._replace_design(design)
        self.app.processEvents()
        counts = self.atelier.count_view
        QTest.mouseClick(counts.viewport(), Qt.MouseButton.LeftButton,
                         pos=counts.visualRect(counts.model().index(0, 0)).center())
        self.app.processEvents()
        self.assertEqual(self.atelier.canvas.color, custom)
        self.assertEqual(self.atelier.recent_colors[0], custom)

    def test_switching_color_during_a_shape_finishes_it_with_the_original_color(self):
        first, second = "#245448", "#ED5598"
        self.atelier.select_color(first)
        self.atelier.select_color(second)
        self.atelier.select_tool("line")
        canvas = self.atelier.canvas
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=canvas.cell_center(1, 2))
        QTest.mouseMove(canvas, canvas.cell_center(4, 2))
        self.app.processEvents()
        self.assertTrue(self.atelier.design.is_empty)
        self.key(2)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=canvas.cell_center(4, 2))
        self.app.processEvents()
        self.assertEqual(self.atelier.canvas.color, first)
        self.assertEqual(self.atelier.canvas.tool, "line")
        self.assertEqual(self.atelier.design.counts(), {second: 4})
        self.assertEqual(self.atelier.history.count(), 1)
        self.atelier.undo()
        self.assertTrue(self.atelier.design.is_empty)

    def test_recent_buttons_remain_clickable_when_the_custom_palette_scrolls(self):
        self.window.resize(1120, 750)
        for index in range(30):
            self.atelier.add_custom_color(f"#{0xA11000 + index:06X}")
        self.app.processEvents()
        recent = self.atelier.view.recent_colors_widget
        before = recent.mapTo(self.atelier, recent.rect().topLeft())
        scroll = self.atelier.palette_scroll
        scrollbar = scroll.verticalScrollBar()
        self.assertGreater(scrollbar.maximum(), 0)
        scrollbar.setValue(scrollbar.maximum())
        self.app.processEvents()
        self.assertEqual(recent.mapTo(self.atelier, recent.rect().topLeft()), before)
        self.assertFalse(scroll.isAncestorOf(recent))
        self.assertLessEqual(recent.width(), scroll.viewport().width())
        expected = self.atelier.recent_colors[2]
        QTest.mouseClick(recent.buttons[2], Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(self.atelier.canvas.color, expected)


if __name__ == "__main__":
    unittest.main()
