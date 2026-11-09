"""Dialog for choosing a new drawing's name and canvas dimensions."""
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QSpinBox

from ..ui.widgets import label


class NewDesignDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Novo design")
        self.setMinimumWidth(360)
        form = QFormLayout(self)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(14)
        self.name = QLineEdit("Meu novo design")
        self.name.setMaxLength(120)
        self.width_input, self.height_input = QSpinBox(), QSpinBox()
        for field in (self.width_input, self.height_input):
            field.setRange(1, 128)
            field.setValue(32)
        form.addRow("Nome", self.name)
        form.addRow("Colunas", self.width_input)
        form.addRow("Linhas", self.height_input)
        note = label("Cada célula da grade corresponde a uma peça.", "muted")
        note.setWordWrap(True)
        form.addRow(note)
        buttons = QDialogButtonBox()
        buttons.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.addButton("Criar design", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

