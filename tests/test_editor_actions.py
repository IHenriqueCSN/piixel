"""Command bindings can be used without constructing an Ateliê view."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QToolButton, QWidget

from piixelverso.editor.actions import COMMANDS, TOOL_KEYS, EditorActions


class EditorActionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.parent = QWidget()
        self.calls = []
        self.tools = []
        self.fills = []
        handlers = {
            definition.key: lambda key=definition.key: self.calls.append(key)
            for definition in COMMANDS
            if definition.key not in TOOL_KEYS and definition.key != "shape_fill"
        }
        self.actions = EditorActions(
            self.parent, handlers=handlers, select_tool=self.tools.append,
            set_shape_fill=self.fills.append, icon_factory=lambda _kind: QIcon(),
        )

    def tearDown(self):
        self.parent.close()
        self.parent.deleteLater()
        self.app.processEvents()

    def test_two_controls_share_one_command_and_callback(self):
        action = self.actions.commands["save"]
        first, second = QToolButton(self.parent), QToolButton(self.parent)
        first.setDefaultAction(action)
        second.setDefaultAction(action)
        first.click()
        second.click()
        self.assertEqual(self.calls, ["save", "save"])
        self.assertIs(first.defaultAction(), second.defaultAction())
        self.assertIn(action, self.parent.actions())
        self.assertIs(action.parent(), self.parent)

    def test_tools_are_exclusive_and_fill_is_an_independent_option(self):
        self.assertTrue(self.actions.commands["pencil"].isChecked())
        for tool in ("rectangle", "ellipse", "pencil"):
            self.actions.commands[tool].trigger()
            selected = [key for key in TOOL_KEYS if self.actions.commands[key].isChecked()]
            self.assertEqual(selected, [tool])
        self.assertEqual(self.tools, ["rectangle", "ellipse", "pencil"])
        self.assertEqual(self.calls, [])

        fill = self.actions.commands["shape_fill"]
        self.assertFalse(fill.isEnabled())
        self.assertFalse(fill.isChecked())
        fill.setChecked(True)
        fill.setEnabled(True)
        fill.trigger()
        self.assertEqual(self.fills, [True, False])
        self.assertTrue(self.actions.commands["pencil"].isChecked())


if __name__ == "__main__":
    unittest.main()
