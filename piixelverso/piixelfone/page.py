"""Native Piixelfone page; all cryptographic and network work stays off the GUI."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import queue
import tempfile
import threading

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QStackedWidget,
    QVBoxLayout, QWidget,
)

from ..brand import svg_pixmap
from ..module_api import ModulePage
from ..preferences import PreferencesStore
from ..theme import (
    BORDER, CREAM, INK, LIGHT_PINK, MUTED, PALE_BLUE, WHITE,
    apply_themed_stylesheet, theme_color,
)
from ..ui.loading import LoadingOverlay


SETUP_MESSAGE = (
    "Para usar o Piixelfone, informe a chave pública de conexão. "
    "Se não souber qual usar, entre em contato com o administrador do sistema."
)

STYLE = f"""
QWidget#piixelfoneModule, QWidget#phoneBody {{ background: {CREAM}; }}
QFrame#phoneHeader {{ background: {CREAM}; border-bottom: 1px solid {BORDER}; }}
QFrame#phoneCard {{ background: {WHITE}; border: 1px solid {BORDER}; border-radius: 12px; }}
QLabel#phoneTitle {{ color: {INK}; font-size: 28px; font-weight: 700; }}
QLabel#phoneNumber {{ color: {INK}; font-size: 23px; font-weight: 700; letter-spacing: 2px; }}
QLabel#phoneSection {{ font-size: 15px; font-weight: 700; }}
QLabel#phoneMuted, QLabel#phoneStatus {{ color: {MUTED}; font-size: 11px; }}
QLabel#phoneNotice {{ background: {PALE_BLUE}; border-radius: 8px; padding: 10px; }}
QPlainTextEdit, QListWidget {{ background: {WHITE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 7px; }}
QListWidget::item {{ padding: 12px; border-bottom: 1px solid {BORDER}; }}
QListWidget::item:selected {{ background: {LIGHT_PINK}; color: {INK}; }}
QPushButton#phoneCompact {{ padding: 4px 10px; font-size: 11px; }}
"""


def _label(text: str = "", name: str = "phoneMuted") -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


def _number(value: str) -> str:
    digits = str(value).replace(" ", "")
    return f"{digits[:3]} {digits[3:]}" if len(digits) == 6 else str(value)


class _WorkerSignals(QObject):
    completed = Signal(str, object, object)


@dataclass(frozen=True)
class _Job:
    name: str
    args: tuple


class _Worker:
    """One serial worker, independent of Qt thread destruction at application exit."""

    def __init__(self, service, signals: _WorkerSignals):
        self.service = service
        self.signals = signals
        self.jobs: queue.Queue[_Job | None] = queue.Queue()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, name="Piixelfone", daemon=True)
        self.thread.start()

    def submit(self, name: str, *args) -> None:
        if not self.stopped.is_set():
            self.jobs.put(_Job(name, args))

    def stop(self) -> None:
        self.stopped.set()
        self.jobs.put(None)

    def _run(self) -> None:
        while not self.stopped.is_set():
            job = self.jobs.get()
            if job is None or self.stopped.is_set():
                return
            result = error = None
            try:
                if job.name == "save_attachment":
                    message_id, destination = job.args
                    _filename, data = self.service.attachment(message_id)
                    _save_attachment(Path(destination), data)
                    result = destination
                else:
                    result = getattr(self.service, job.name)(*job.args)
            except Exception as caught:
                # Only user-facing errors cross into the GUI; never expose a traceback.
                if hasattr(caught, "user_message"):
                    error = str(caught.user_message)
                elif isinstance(caught, (ValueError, OSError)):
                    error = str(caught)
                else:
                    error = "Não foi possível concluir a operação. Tente novamente."
            if not self.stopped.is_set():
                try:
                    self.signals.completed.emit(job.name, result, error)
                except RuntimeError:
                    # The application may have destroyed the page while a request ended.
                    return
            # Release password arguments before waiting for the next operation.
            del job


def _save_attachment(destination: Path, data: bytes) -> None:
    """Atomically save only at the location explicitly selected by the user."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{destination.name}.", suffix=".tmp",
                                         dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class PiixelfoneModule(ModulePage):
    """Connection setup, local identity unlock, contacts, and encrypted conversations."""

    def __init__(self, parent=None, preferences: PreferencesStore | None = None, *, service=None):
        super().__init__(parent)
        self.preferences = preferences if preferences is not None else PreferencesStore()
        if service is None:
            from .service import PhoneService
            service = PhoneService(self.preferences.path.parent / "piixelfone")
        self.service = service
        self._active = True
        self._unlocked = False
        self._busy = False
        self._closed = False
        self._selected_peer: str | None = None
        self._snapshot: dict = {"contacts": [], "messages": [], "number": ""}
        self._rendered_messages = None
        self._sending_text = ""
        self._loading_page: QWidget | None = None
        self._loading_focus: QWidget | None = None
        self.setObjectName("piixelfoneModule")
        self.setWindowTitle("Piixel — Piixelfone")
        apply_themed_stylesheet(self, STYLE)
        self._build()
        self._signals = _WorkerSignals(self)
        self._signals.completed.connect(self._completed)
        self._worker = _Worker(service, self._signals)
        # stop() never touches Qt and can also run during QObject destruction.
        self.destroyed.connect(lambda _object=None, worker=self._worker: worker.stop())
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(5000)
        self.poll_timer.timeout.connect(self._poll)
        self._show_unlock() if self.service.configured else self._show_config()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QFrame(objectName="phoneHeader")
        header.setFixedHeight(44)
        top = QHBoxLayout(header)
        top.setContentsMargins(28, 0, 28, 0)
        mascot = QLabel()
        mascot.setPixmap(svg_pixmap("symbol.svg", 44, 38))
        mascot.setAccessibleName("Pii, o mascote do Piixelverso")
        top.addWidget(mascot)
        wordmark = QLabel()
        wordmark.setPixmap(svg_pixmap("wordmark.svg", 142, 25))
        wordmark.setAccessibleName("Piixelverso")
        top.addWidget(wordmark)
        top.addSpacing(16)
        edition = _label("PIIXEL / PIIXELFONE", "edition")
        edition.setWordWrap(False)
        top.addWidget(edition)
        top.addStretch()
        self.connection_button = QPushButton("Conexão", objectName="phoneCompact")
        self.connection_button.clicked.connect(self._show_config)
        top.addWidget(self.connection_button)
        self.home_button = QPushButton("← Início", objectName="phoneCompact")
        self.home_button.setToolTip("Voltar à tela inicial (Alt+Home)")
        self.home_button.setAccessibleName("Voltar à tela inicial")
        self.home_button.clicked.connect(self.home_requested.emit)
        top.addWidget(self.home_button)
        root.addWidget(header)

        self.stage = QStackedWidget()
        self.stage.addWidget(self._build_config())
        self.stage.addWidget(self._build_unlock())
        self.stage.addWidget(self._build_chat())
        root.addWidget(self.stage, 1)
        self.loading_overlay = LoadingOverlay(self.stage)
        self.status_label = _label("", "phoneStatus")
        self.status_label.setContentsMargins(28, 7, 28, 8)
        self.status_label.setMinimumHeight(32)
        root.addWidget(self.status_label)

    @staticmethod
    def _centered_panel() -> tuple[QWidget, QVBoxLayout]:
        page = QWidget(objectName="phoneBody")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.addStretch()
        row = QHBoxLayout()
        row.addStretch()
        card = QFrame(objectName="phoneCard")
        card.setMaximumWidth(650)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        contents = QVBoxLayout(card)
        contents.setContentsMargins(30, 26, 30, 28)
        contents.setSpacing(15)
        row.addWidget(card, 1)
        row.addStretch()
        outer.addLayout(row)
        outer.addStretch()
        # A scroll container keeps setup usable with large system fonts.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll, contents

    def _build_config(self) -> QWidget:
        page, layout = self._centered_panel()
        layout.addWidget(_label("Conecte o Piixelfone", "phoneTitle"))
        layout.addWidget(_label(SETUP_MESSAGE))
        form = QFormLayout()
        form.setSpacing(12)
        self.url_input = QLineEdit(str(self.service.config.url))
        self.url_input.setObjectName("phoneProjectUrl")
        self.url_input.setMaxLength(2048)
        self.url_input.setAccessibleName("URL do projeto Supabase")
        form.addRow("URL do projeto", self.url_input)
        self.key_input = QLineEdit(str(self.service.config.public_key))
        self.key_input.setObjectName("phonePublicKey")
        self.key_input.setMaxLength(4096)
        self.key_input.setPlaceholderText("sb_publishable_… ou chave anon pública")
        self.key_input.setAccessibleName("Chave pública de conexão")
        form.addRow("Chave pública", self.key_input)
        layout.addLayout(form)
        layout.addWidget(_label(
            "Use apenas a chave pública do projeto. Chaves administrativas, como "
            "service_role ou sb_secret, não devem ser usadas no aplicativo.", "phoneNotice"
        ))
        layout.addWidget(_label(
            "O administrador também precisa preparar o servidor e habilitar o acesso "
            "anônimo no Supabase. As instruções estão em docs/PIIXELFONE_SERVIDOR.md."
        ))
        self.configure_button = QPushButton("Salvar conexão", objectName="primary")
        self.configure_button.clicked.connect(self._configure)
        layout.addWidget(self.configure_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.config_back_button = QPushButton("Voltar", objectName="phoneCompact")
        self.config_back_button.clicked.connect(self._show_unlock)
        layout.addWidget(self.config_back_button, 0, Qt.AlignmentFlag.AlignLeft)
        return page

    def _build_unlock(self) -> QWidget:
        page, layout = self._centered_panel()
        self.unlock_title = _label("Seu Piixelfone", "phoneTitle")
        layout.addWidget(self.unlock_title)
        self.unlock_note = _label()
        layout.addWidget(self.unlock_note)
        self.password_input = QLineEdit()
        self.password_input.setObjectName("phonePassword")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMaxLength(256)
        self.password_input.setPlaceholderText("Senha local do Piixelfone")
        self.password_input.setAccessibleName("Senha local do Piixelfone")
        layout.addWidget(self.password_input)
        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setObjectName("phonePasswordConfirmation")
        self.confirm_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password_input.setMaxLength(256)
        self.confirm_password_input.setPlaceholderText("Repita a senha local")
        self.confirm_password_input.setAccessibleName("Confirmação da senha local")
        layout.addWidget(self.confirm_password_input)
        self.unlock_button = QPushButton("Desbloquear", objectName="primary")
        self.unlock_button.clicked.connect(self._unlock)
        self.password_input.returnPressed.connect(self._unlock)
        self.confirm_password_input.returnPressed.connect(self._unlock)
        layout.addWidget(self.unlock_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.vault_note = _label(
            "Esta senha protege suas chaves e o histórico neste computador. "
            "Ela não é enviada ao servidor. Guarde-a: sem ela, não será possível "
            "recuperar a identidade e as mensagens locais.", "phoneNotice"
        )
        layout.addWidget(self.vault_note)
        return page

    def _build_chat(self) -> QWidget:
        page = QWidget(objectName="phoneBody")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 20, 28, 12)
        layout.setSpacing(14)
        identity_row = QHBoxLayout()
        identity_column = QVBoxLayout()
        identity_column.setSpacing(2)
        identity_column.addWidget(_label("Seu Piixelfone"))
        self.number_label = _label("—", "phoneNumber")
        self.number_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        identity_column.addWidget(self.number_label)
        identity_row.addLayout(identity_column)
        self.copy_button = QPushButton("Copiar número", objectName="phoneCompact")
        self.copy_button.clicked.connect(self._copy_number)
        identity_row.addWidget(self.copy_button)
        identity_row.addStretch()
        self.regenerate_button = QPushButton("Regenerar número", objectName="phoneCompact")
        self.regenerate_button.clicked.connect(self._regenerate)
        identity_row.addWidget(self.regenerate_button)
        layout.addLayout(identity_row)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        contacts_panel = QWidget()
        contacts_layout = QVBoxLayout(contacts_panel)
        contacts_layout.setContentsMargins(0, 0, 10, 0)
        contacts_layout.setSpacing(10)
        contacts_layout.addWidget(_label("Conversas", "phoneSection"))
        add_row = QHBoxLayout()
        self.number_input = QLineEdit()
        self.number_input.setObjectName("phoneContactNumber")
        self.number_input.setMaxLength(12)
        self.number_input.setPlaceholderText("Número: 584 093")
        self.number_input.setAccessibleName("Número do contato")
        self.number_input.returnPressed.connect(self._request_contact)
        add_row.addWidget(self.number_input, 1)
        self.add_contact_button = QPushButton("Adicionar", objectName="phoneCompact")
        self.add_contact_button.clicked.connect(self._request_contact)
        add_row.addWidget(self.add_contact_button)
        contacts_layout.addLayout(add_row)
        self.contacts_list = QListWidget()
        self.contacts_list.setObjectName("phoneContacts")
        self.contacts_list.setAccessibleName("Conversas e convites")
        self.contacts_list.currentItemChanged.connect(self._select_contact)
        contacts_layout.addWidget(self.contacts_list, 1)
        contacts_layout.addWidget(_label(
            "Adicione um número e aguarde a aceitação do convite para conversar."
        ))
        splitter.addWidget(contacts_panel)
        conversation = QWidget()
        chat_layout = QVBoxLayout(conversation)
        chat_layout.setContentsMargins(10, 0, 0, 0)
        chat_layout.setSpacing(10)
        selected_row = QHBoxLayout()
        self.contact_title = _label("Selecione uma conversa", "phoneSection")
        selected_row.addWidget(self.contact_title, 1)
        self.verify_button = QPushButton("Verificar contato", objectName="phoneCompact")
        self.verify_button.clicked.connect(self._verify_contact)
        selected_row.addWidget(self.verify_button)
        chat_layout.addLayout(selected_row)
        self.contact_note = _label("", "phoneNotice")
        chat_layout.addWidget(self.contact_note)
        invitation_row = QHBoxLayout()
        self.accept_button = QPushButton("Aceitar convite", objectName="primary")
        self.accept_button.clicked.connect(self._accept_contact)
        invitation_row.addWidget(self.accept_button)
        self.decline_button = QPushButton("Recusar", objectName="phoneCompact")
        self.decline_button.clicked.connect(self._decline_contact)
        invitation_row.addWidget(self.decline_button)
        invitation_row.addStretch()
        chat_layout.addLayout(invitation_row)
        self.messages_list = QListWidget()
        self.messages_list.setObjectName("phoneMessages")
        self.messages_list.setWordWrap(True)
        self.messages_list.setAccessibleName("Histórico de mensagens")
        self.messages_list.currentItemChanged.connect(self._update_attachment_button)
        self.messages_list.itemDoubleClicked.connect(lambda _item: self._save_selected_attachment())
        chat_layout.addWidget(self.messages_list, 1)
        self.save_attachment_button = QPushButton("Salvar arquivo .pii", objectName="phoneCompact")
        self.save_attachment_button.clicked.connect(self._save_selected_attachment)
        chat_layout.addWidget(self.save_attachment_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.message_input = QPlainTextEdit()
        self.message_input.setObjectName("phoneMessageInput")
        self.message_input.setPlaceholderText("Escreva uma mensagem de até 150 caracteres…")
        self.message_input.setAccessibleName("Mensagem de até 150 caracteres")
        self.message_input.setMaximumHeight(100)
        self.message_input.textChanged.connect(self._text_changed)
        chat_layout.addWidget(self.message_input)
        self.send_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self.message_input)
        self.send_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.send_shortcut.activated.connect(self._send_text)
        controls = QHBoxLayout()
        self.attachment_button = QPushButton("Anexar .pii", objectName="phoneCompact")
        self.attachment_button.clicked.connect(self._send_file)
        controls.addWidget(self.attachment_button)
        self.counter_label = _label("0 / 150")
        controls.addWidget(self.counter_label)
        controls.addStretch()
        self.send_button = QPushButton("Enviar", objectName="primary")
        self.send_button.setToolTip("Enviar mensagem (Ctrl+Enter)")
        self.send_button.clicked.connect(self._send_text)
        controls.addWidget(self.send_button)
        chat_layout.addLayout(controls)
        chat_layout.addWidget(_label(
            "Criptografia de ponta a ponta · As mensagens pendentes serão entregues "
            "quando vocês se conectarem novamente."
        ))
        splitter.addWidget(conversation)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([290, 800])
        layout.addWidget(splitter, 1)
        self._update_controls()
        return page

    def _show_config(self) -> None:
        if self._busy or self._unlocked:
            return
        self.url_input.setText(str(self.service.config.url))
        self.key_input.setText(str(self.service.config.public_key))
        self.config_back_button.setVisible(bool(self.service.configured))
        self.stage.setCurrentIndex(0)
        self.status_label.clear()
        self.key_input.setFocus()

    def _show_unlock(self) -> None:
        if self._busy:
            return
        existing = bool(self.service.has_vault)
        self.unlock_title.setText("Bem-vindo de volta" if existing else "Crie seu Piixelfone")
        self.unlock_note.setText(
            "Informe a senha local para abrir suas conversas."
            if existing else
            "Escolha uma senha local com pelo menos 8 caracteres. "
            "Seu número será criado ao conectar ao serviço."
        )
        self.confirm_password_input.setVisible(not existing)
        self.unlock_button.setText("Desbloquear" if existing else "Criar Piixelfone")
        self.stage.setCurrentIndex(1)
        self.status_label.clear()
        self.password_input.setFocus()

    def _configure(self) -> None:
        self._submit("configure", self.url_input.text().strip(), self.key_input.text().strip())

    def _unlock(self) -> None:
        password = self.password_input.text()
        if not self.service.has_vault:
            if len(password) < 8:
                self.status_label.setText("Escolha uma senha local com pelo menos 8 caracteres.")
                return
            if password != self.confirm_password_input.text():
                self.status_label.setText("As senhas não coincidem. Digite-as novamente.")
                return
        if not password:
            self.status_label.setText("Informe a senha local do Piixelfone.")
            return
        if self._submit("unlock", password):
            # Do not keep the password in visible widget storage during network work.
            self.password_input.clear()
            self.confirm_password_input.clear()

    def _submit(self, name: str, *args) -> bool:
        if self._busy or self._closed:
            return False
        self._busy = True
        message = {
            "configure": "Salvando conexão…", "unlock": "Abrindo suas conversas…",
            "sync": "Sincronizando…", "save_attachment": "Salvando arquivo…",
            "regenerate_number": "Gerando um novo número…",
            "request_contact": "Enviando convite…", "accept_contact": "Aceitando convite…",
            "decline_contact": "Recusando convite…", "send_text": "Enviando mensagem…",
            "send_file": "Enviando arquivo…",
        }.get(name, "Carregando…")
        self.status_label.setText(message)
        if name != "sync":
            # Polling is deliberately quiet. Explicit actions cover only this
            # module's body, leaving navigation back to the other modules free.
            self._loading_page = self.stage.currentWidget()
            self._loading_focus = QApplication.focusWidget()
            self._loading_page.setEnabled(False)
            self.loading_overlay.show_loading(message)
        self._update_controls()
        self._worker.submit(name, *args)
        return True

    def _finish_loading(self) -> QWidget | None:
        self.loading_overlay.hide_loading()
        page, focus = self._loading_page, self._loading_focus
        self._loading_page = self._loading_focus = None
        if page is not None:
            page.setEnabled(True)
        if (page is self.stage.currentWidget() and focus is not None
                and page is not None and page.isAncestorOf(focus)):
            return focus
        return None

    def _completed(self, name: str, result, error) -> None:
        if self._closed:
            return
        self._busy = False
        restore_focus = self._finish_loading()
        if error:
            self.status_label.setText(str(error))
            self._update_controls()
            if (restore_focus is not None and restore_focus.isVisible()
                    and self._active and self.isVisible()):
                restore_focus.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if name == "configure":
            self._show_unlock()
            self.status_label.setText("Conexão salva. Suas mensagens continuarão protegidas pelas chaves locais.")
        elif name == "save_attachment":
            self.status_label.setText(f"Arquivo salvo em {result}")
        else:
            if name == "unlock":
                self._unlocked = True
                self.connection_button.hide()
                self.stage.setCurrentIndex(2)
                self.poll_timer.start()
            if isinstance(result, dict):
                self._apply_snapshot(result)
            if name == "send_text" and self.message_input.toPlainText() == self._sending_text:
                self.message_input.clear()
            if name == "request_contact":
                self.number_input.clear()
        self._update_controls()
        if (restore_focus is not None and restore_focus.isVisible()
                and self._active and self.isVisible()):
            restore_focus.setFocus(Qt.FocusReason.OtherFocusReason)

    def _apply_snapshot(self, snapshot: dict) -> None:
        self._snapshot = snapshot
        self.number_label.setText(_number(snapshot.get("number", "")) or "Aguardando conexão")
        self.status_label.setText(str(snapshot.get("status", "")))
        self.copy_button.setEnabled(bool(snapshot.get("number")))
        self.contacts_list.blockSignals(True)
        self.contacts_list.clear()
        selected_item = None
        for contact in snapshot.get("contacts", []):
            state = contact.get("state", "pending")
            caption = {
                "accepted": "Conversa aceita", "declined": "Convite recusado",
                "blocked": "Chave de segurança alterada",
            }.get(state, "Convite recebido" if contact.get("incoming") else "Aguardando aceitação")
            item = QListWidgetItem(f"{_number(contact.get('number', ''))}\n{caption}")
            item.setData(Qt.ItemDataRole.UserRole, contact["user_id"])
            self.contacts_list.addItem(item)
            if contact["user_id"] == self._selected_peer:
                selected_item = item
        if selected_item is not None:
            self.contacts_list.setCurrentItem(selected_item)
        elif self._selected_peer and not self._contact():
            self._selected_peer = None
        self.contacts_list.blockSignals(False)
        self._render_conversation()
        self._update_controls()

    def _contact(self) -> dict | None:
        return next((contact for contact in self._snapshot.get("contacts", [])
                     if contact.get("user_id") == self._selected_peer), None)

    def _select_contact(self, current, _previous=None) -> None:
        self._selected_peer = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        self._rendered_messages = None
        self._render_conversation()
        self._update_controls()

    def _render_conversation(self) -> None:
        contact = self._contact()
        self.contact_title.setText(_number(contact.get("number", "")) if contact else "Selecione uma conversa")
        state = contact.get("state") if contact else None
        incoming = bool(contact and contact.get("incoming") and state == "pending")
        self.accept_button.setVisible(incoming)
        self.decline_button.setVisible(incoming)
        self.contact_note.setText(
            "Este contato quer conversar com você. Aceite o convite para começar."
            if incoming else
            "Aguardando o contato aceitar seu convite."
            if state == "pending" else
            "Convite recusado."
            if state == "declined" else
            "A chave deste contato mudou. O envio foi bloqueado; confirme a identidade por outro canal."
            if state == "blocked" else
            "Compare o código de segurança com o contato por outro meio antes de compartilhar arquivos."
            if state == "accepted" else
            "Escolha uma conversa ou adicione o número de um contato."
        )
        records = [record for record in self._snapshot.get("messages", [])
                   if record.get("peer_id") == self._selected_peer]
        rendered = repr(records)
        if rendered != self._rendered_messages:
            old = self.messages_list.currentItem()
            selected = old.data(Qt.ItemDataRole.UserRole) if old is not None else None
            scrollbar = self.messages_list.verticalScrollBar()
            at_bottom = scrollbar.value() >= scrollbar.maximum() - 4
            old_position = scrollbar.value()
            self.messages_list.clear()
            for record in records:
                outgoing = record.get("direction") == "outgoing"
                who = "Você" if outgoing else "Contato"
                status = {
                    "queued": "Na fila", "sent": "Enviada", "delivered": "Entregue",
                    "received": "Recebida", "rejected": "Não recebida",
                }.get(record.get("status"), "")
                if not outgoing and record.get("status") == "delivered":
                    status = "Recebida"
                date = str(record.get("created_at", "")).replace("T", " ")[:16]
                content = str(record.get("text", ""))
                if record.get("type") == "file" or "filename" in record:
                    content = f"Arquivo .pii: {record.get('filename', 'design.pii')}\nSelecione para salvar uma cópia."
                item = QListWidgetItem(f"{who} · {date} · {status}\n{content}")
                item.setData(Qt.ItemDataRole.UserRole, record["id"])
                item.setBackground(QColor(theme_color("cream" if outgoing else "pale_blue")))
                self.messages_list.addItem(item)
                if record["id"] == selected:
                    self.messages_list.setCurrentItem(item)
            if at_bottom:
                self.messages_list.scrollToBottom()
            else:
                scrollbar.setValue(old_position)
            self._rendered_messages = rendered
        self._update_attachment_button()

    def refresh_theme(self) -> None:
        self._rendered_messages = None
        self._render_conversation()

    def _update_controls(self) -> None:
        if not hasattr(self, "send_button"):
            return
        accepted = bool(self._contact() and self._contact().get("state") == "accepted")
        ready = self._unlocked and accepted
        self.configure_button.setEnabled(not self._busy)
        self.unlock_button.setEnabled(not self._busy)
        self.connection_button.setEnabled(not self._busy)
        self.regenerate_button.setEnabled(self._unlocked and not self._busy)
        self.add_contact_button.setEnabled(self._unlocked and not self._busy)
        self.accept_button.setEnabled(not self._busy)
        self.decline_button.setEnabled(not self._busy)
        self.verify_button.setEnabled(self._contact() is not None and not self._busy)
        self.message_input.setEnabled(ready)
        self.attachment_button.setEnabled(ready and not self._busy)
        text = self.message_input.toPlainText()
        self.send_button.setEnabled(ready and not self._busy and bool(text.strip()) and len(text) <= 150)
        self.send_shortcut.setEnabled(ready and not self._busy)
        self._update_attachment_button()

    def _text_changed(self) -> None:
        text = self.message_input.toPlainText()
        if len(text) > 150:
            self.message_input.blockSignals(True)
            self.message_input.setPlainText(text[:150])
            self.message_input.moveCursor(QTextCursor.MoveOperation.End)
            self.message_input.blockSignals(False)
            text = text[:150]
        self.counter_label.setText(f"{len(text)} / 150")
        self._update_controls()

    def _poll(self) -> None:
        if self._unlocked and not self._busy and not self._closed:
            self._submit("sync")

    def _request_contact(self) -> None:
        number = self.number_input.text().replace(" ", "")
        if len(number) != 6 or not number.isascii() or not number.isdecimal():
            self.status_label.setText("Informe o número de 6 dígitos do contato, como 584 093.")
            return
        self._submit("request_contact", number)

    def _accept_contact(self) -> None:
        if self._selected_peer:
            self._submit("accept_contact", self._selected_peer)

    def _decline_contact(self) -> None:
        if self._selected_peer:
            self._submit("decline_contact", self._selected_peer)

    def _send_text(self) -> None:
        if self.send_button.isEnabled() and self._selected_peer:
            self._sending_text = self.message_input.toPlainText()
            self._submit("send_text", self._selected_peer, self._sending_text)

    def _send_file(self) -> None:
        if not self.attachment_button.isEnabled() or not self._selected_peer:
            return
        path, _selected = QFileDialog.getOpenFileName(
            self.window(), "Enviar design pelo Piixelfone", "", "Design Piixelverso (*.pii)"
        )
        if path:
            self._submit("send_file", self._selected_peer, path)

    def _selected_attachment(self) -> dict | None:
        item = self.messages_list.currentItem()
        if item is None:
            return None
        identifier = item.data(Qt.ItemDataRole.UserRole)
        return next((record for record in self._snapshot.get("messages", [])
                     if record.get("id") == identifier and
                     (record.get("type") == "file" or "filename" in record)), None)

    def _update_attachment_button(self, *_args) -> None:
        self.save_attachment_button.setEnabled(not self._busy and self._selected_attachment() is not None)

    def _save_selected_attachment(self) -> None:
        record = self._selected_attachment()
        if record is None or self._busy:
            return
        name = str(record.get("filename", "design.pii")).replace("\\", "/").rsplit("/", 1)[-1]
        destination, _selected = QFileDialog.getSaveFileName(
            self.window(), "Salvar design recebido", name, "Design Piixelverso (*.pii)"
        )
        if destination:
            if not destination.lower().endswith(".pii"):
                destination += ".pii"
            self._submit("save_attachment", record["id"], destination)

    def _copy_number(self) -> None:
        number = self._snapshot.get("number", "")
        if number:
            QApplication.clipboard().setText(_number(number))
            self.status_label.setText("Número copiado.")

    def _regenerate(self) -> None:
        if self._busy or not self._unlocked:
            return
        dialog = QMessageBox(self.window())
        dialog.setWindowTitle("Regenerar número do Piixelfone")
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText("Deseja gerar um novo número para seu Piixelfone?")
        dialog.setInformativeText(
            "O número antigo deixará de receber novos convites. "
            "Seus contatos, suas conversas e suas chaves de segurança serão mantidos."
        )
        confirm = dialog.addButton("Regenerar número", QMessageBox.ButtonRole.AcceptRole)
        cancel = dialog.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(cancel)
        dialog.exec()
        if dialog.clickedButton() is confirm:
            self._submit("regenerate_number")

    def _verify_contact(self) -> None:
        contact = self._contact()
        if contact is None:
            return
        dialog = QMessageBox(self.window())
        dialog.setWindowTitle("Verificar contato")
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(f"Código de segurança de {_number(contact.get('number', ''))}")
        dialog.setInformativeText(
            f"{contact.get('fingerprint', '')}\n\n"
            "Compare este código com o código da chave pública que seu contato vê no "
            "próprio Piixelfone, por ligação ou pessoalmente. Essa conferência confirma "
            "a identidade antes da primeira conversa. Uma mudança de chave será bloqueada."
        )
        # Show both codes so either user can check the other's public identity.
        own_fingerprint = self._snapshot.get("fingerprint", "")
        if own_fingerprint:
            dialog.setDetailedText(f"Código da sua chave pública:\n{own_fingerprint}")
        dialog.exec()

    def focus_default(self) -> None:
        target = self.key_input if self.stage.currentIndex() == 0 else (
            self.password_input if self.stage.currentIndex() == 1 else self.number_input
        )
        target.setFocus(Qt.FocusReason.OtherFocusReason)

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        # Keep mailbox synchronization running while another module is visible.

    def shutdown(self) -> None:
        if not self._closed:
            self._closed = True
            self.poll_timer.stop()
            self._finish_loading()
            self._worker.stop()
