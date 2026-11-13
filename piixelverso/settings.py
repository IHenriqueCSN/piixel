"""Application preferences, independent of the Ateliê document."""
from __future__ import annotations

from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from .brand import svg_pixmap
from .module_api import ModulePage
from .preferences import (
    MAX_PIECE_SIZE_MM, MIN_PIECE_SIZE_MM, PreferencesStore,
)
from .theme import (
    BORDER, CREAM, INK, MUTED, WHITE, apply_themed_stylesheet, theme_controller,
)


SETTINGS_STYLE = f"""
QWidget#settingsModule, QWidget#settingsBody {{ background: {CREAM}; }}
QFrame#settingsHeader {{ background: {CREAM}; border-bottom: 1px solid {BORDER}; }}
QLabel#settingsTitle {{ color: {INK}; font-size: 30px; font-weight: 700; }}
QLabel#settingsSubtitle, QLabel#settingsNote, QLabel#settingsStatus {{ color: {MUTED}; font-size: 12px; }}
QLabel#settingsCardTitle {{ color: {INK}; font-size: 16px; font-weight: 700; }}
QFrame#settingsCard {{ background: {WHITE}; border: 1px solid {BORDER}; border-radius: 12px; }}
QPushButton#settingsHomeButton {{ padding: 3px 12px; font-size: 11px; }}
QDoubleSpinBox {{ border: 1px solid {BORDER}; border-radius: 6px; padding: 8px; background: {WHITE}; }}
"""


class SettingsModule(ModulePage):
    def __init__(self, parent=None, preferences: PreferencesStore | None = None):
        super().__init__(parent)
        self.preferences = preferences if preferences is not None else PreferencesStore()
        self.updater = None
        self.theme = theme_controller()
        self._active = True
        self.setObjectName("settingsModule")
        apply_themed_stylesheet(self, SETTINGS_STYLE)
        self.setWindowTitle("Piixel — Configurações")
        self._build()
        self.piece_size_input.valueChanged.connect(self._update_status)
        self.appearance_input.currentIndexChanged.connect(self._appearance_changed)

    @staticmethod
    def _label(text: str, name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(name)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        return label

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame(objectName="settingsHeader")
        header.setFixedHeight(44)
        top = QHBoxLayout(header)
        top.setContentsMargins(28, 0, 28, 0)
        symbol = QLabel()
        symbol.setPixmap(svg_pixmap("symbol.svg", 44, 38))
        symbol.setAccessibleName("Pii, o mascote do Piixelverso")
        top.addWidget(symbol)
        wordmark = QLabel()
        wordmark.setPixmap(svg_pixmap("wordmark.svg", 142, 25))
        wordmark.setAccessibleName("Piixelverso")
        top.addWidget(wordmark)
        top.addSpacing(16)
        edition = self._label("PIIXEL / CONFIGURAÇÕES", "edition")
        edition.setWordWrap(False)
        top.addWidget(edition)
        top.addStretch()
        self.home_button = QPushButton("← Início")
        self.home_button.setObjectName("settingsHomeButton")
        self.home_button.setAccessibleName("Voltar à tela inicial")
        self.home_button.setToolTip("Voltar à tela inicial (Alt+Home)")
        self.home_button.setFixedHeight(28)
        self.home_button.clicked.connect(self.home_requested.emit)
        top.addWidget(self.home_button)
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget(objectName="settingsBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(40, 36, 40, 36)
        body_layout.setSpacing(0)
        row = QHBoxLayout()
        row.addStretch()
        panel = QWidget()
        panel.setMaximumWidth(760)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        contents = QVBoxLayout(panel)
        contents.setContentsMargins(0, 0, 0, 0)
        contents.setSpacing(16)
        contents.addWidget(self._label("Configurações", "settingsTitle"))
        contents.addWidget(self._label(
            "Ajuste as preferências usadas pelos módulos do Piixel.", "settingsSubtitle"
        ))

        appearance_card = QFrame(objectName="settingsCard")
        appearance_layout = QVBoxLayout(appearance_card)
        appearance_layout.setContentsMargins(28, 26, 28, 26)
        appearance_layout.setSpacing(16)
        appearance_layout.addWidget(self._label("Aparência", "settingsCardTitle"))
        appearance_layout.addWidget(self._label(
            "Escolha o tema do Piixel. A opção Sistema acompanha a preferência de aparência "
            "do Windows ou Linux.", "settingsNote"
        ))
        appearance_form = QFormLayout()
        appearance_form.setSpacing(12)
        self.appearance_input = QComboBox()
        self.appearance_input.setObjectName("appearanceMode")
        self.appearance_input.setAccessibleName("Aparência do Piixel")
        self.appearance_input.addItem("Sistema", "system")
        self.appearance_input.addItem("Claro", "light")
        self.appearance_input.addItem("Escuro", "dark")
        selected = self.appearance_input.findData(self.preferences.appearance_mode())
        self.appearance_input.setCurrentIndex(max(0, selected))
        self.appearance_input.setFixedWidth(180)
        appearance_form.addRow("Tema", self.appearance_input)
        appearance_layout.addLayout(appearance_form)
        appearance_layout.addWidget(self._label(
            "A prancheta mantém sempre as mesmas cores para que o desenho continue fiel. "
            "A escolha é visualizada imediatamente e será guardada ao salvar.", "settingsNote"
        ))
        contents.addWidget(appearance_card)

        card = QFrame(objectName="settingsCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 26)
        card_layout.setSpacing(16)
        card_layout.addWidget(self._label("Tamanho de cada peça", "settingsCardTitle"))
        card_layout.addWidget(self._label(
            "Define o tamanho físico de cada célula da grade nas medidas das imagens PNG. "
            "O padrão é 5 mm por peça, como uma peça hama beads.", "settingsNote"
        ))
        form = QFormLayout()
        form.setSpacing(12)
        self.piece_size_input = QDoubleSpinBox()
        self.piece_size_input.setObjectName("pieceSizeMm")
        self.piece_size_input.setAccessibleName("Tamanho de cada peça em milímetros")
        self.piece_size_input.setLocale(QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil))
        self.piece_size_input.setRange(MIN_PIECE_SIZE_MM, MAX_PIECE_SIZE_MM)
        self.piece_size_input.setDecimals(2)
        self.piece_size_input.setSingleStep(0.1)
        self.piece_size_input.setSuffix(" mm")
        self.piece_size_input.setKeyboardTracking(False)
        self.piece_size_input.setValue(self.preferences.piece_size_mm())
        self.piece_size_input.setFixedWidth(180)
        form.addRow("Lado da peça", self.piece_size_input)
        card_layout.addLayout(form)
        card_layout.addWidget(self._label(
            "A largura vai da peça mais à esquerda à mais à direita; a altura, da peça mais alta "
            "à mais baixa. As margens vazias ficam fora da medida.", "settingsNote"
        ))
        card_layout.addWidget(self._label(
            "Clique em Salvar configurações para aplicar o valor às próximas exportações. "
            "Ele continuará disponível ao reabrir o Piixel.", "settingsNote"
        ))
        self.save_button = QPushButton("Salvar configurações")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save_settings)
        card_layout.addWidget(self.save_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.status_label = self._label("", "settingsStatus")
        self.status_label.setMinimumHeight(20)
        card_layout.addWidget(self.status_label)
        contents.addWidget(card)

        update_card = QFrame(objectName="settingsCard")
        update_layout = QVBoxLayout(update_card)
        update_layout.setContentsMargins(28, 26, 28, 26)
        update_layout.setSpacing(12)
        update_layout.addWidget(self._label("Atualizações do Piixel", "settingsCardTitle"))
        update_layout.addWidget(self._label(
            "Procura novas versões publicadas pelo Piixelverso. Antes de instalar, o programa "
            "confere o SHA-256 do arquivo baixado.", "settingsNote"
        ))
        self.update_button = QPushButton("Verificar atualizações")
        self.update_button.setObjectName("checkUpdatesButton")
        self.update_button.setEnabled(False)
        self.update_button.clicked.connect(self.check_updates)
        update_layout.addWidget(self.update_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.update_status_label = self._label(
            "As informações de atualização ainda não estão disponíveis.", "settingsStatus"
        )
        self.update_status_label.setMinimumHeight(20)
        update_layout.addWidget(self.update_status_label)
        contents.addWidget(update_card)
        contents.addStretch(1)
        row.addWidget(panel, 1)
        row.addStretch()
        body_layout.addLayout(row, 1)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

    def _update_status(self):
        changed = (
            self.piece_size_input.value() != self.preferences.piece_size_mm()
            or self.appearance_input.currentData() != self.preferences.appearance_mode()
        )
        self.status_label.setText("Alteração ainda não salva." if changed else "")

    def _appearance_changed(self):
        if self.theme is not None:
            self.theme.set_mode(self.appearance_input.currentData())
        self._update_status()

    def save_settings(self):
        self.piece_size_input.interpretText()
        try:
            self.preferences.set_settings(
                self.piece_size_input.value(), self.appearance_input.currentData()
            )
        except (OSError, ValueError) as error:
            self.status_label.setText("Não foi possível salvar as configurações.")
            QMessageBox.warning(self.window(), "Não foi possível salvar as configurações", str(error))
            return False
        self.status_label.setText("Configurações salvas.")
        return True

    def prepare_navigation(self):
        """Keep the pending input in this session; only Save writes preferences."""
        self.piece_size_input.interpretText()

    def set_active(self, active: bool):
        self._active = bool(active)
        self.piece_size_input.setEnabled(self._active)
        self.appearance_input.setEnabled(self._active)
        self.save_button.setEnabled(self._active)
        self._sync_update_button()

    def attach_updater(self, updater) -> None:
        self.updater = updater
        self.update_status_label.setText(updater.status_text)
        updater.status_changed.connect(self.update_status_label.setText)
        updater.busy_changed.connect(lambda _busy: self._sync_update_button())
        self._sync_update_button()

    def _sync_update_button(self):
        enabled = bool(
            self._active and self.updater is not None and self.updater.supported
            and not self.updater.busy
        )
        self.update_button.setEnabled(enabled)

    def check_updates(self):
        if self.updater is not None:
            return self.updater.check(manual=True)
        return False

    def focus_default(self):
        self.appearance_input.setFocus(Qt.FocusReason.OtherFocusReason)
