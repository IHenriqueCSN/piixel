"""Qt controller for non-blocking checks and user-approved Windows updates."""
from __future__ import annotations

import sys
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from . import __version__
from .update import Release, UpdateClient, UpdateError


class UpdateController(QObject):
    status_changed = Signal(str)
    busy_changed = Signal(bool)
    _check_finished = Signal(object, object, bool)
    _download_progress = Signal(int, int)
    _download_finished = Signal(object, object)

    def __init__(self, window, *, client: UpdateClient | None = None,
                 supported: bool | None = None):
        super().__init__(window)
        self.window = window
        self.client = client or UpdateClient()
        self.supported = (
            sys.platform == "win32" and bool(getattr(sys, "frozen", False))
            if supported is None else bool(supported)
        )
        self._busy = False
        self._closed = False
        self._cancel = threading.Event()
        self._progress_dialog: QProgressDialog | None = None
        self._check_finished.connect(self._on_check_finished)
        self._download_progress.connect(self._on_download_progress)
        self._download_finished.connect(self._on_download_finished)

    @property
    def status_text(self) -> str:
        if self.supported:
            return f"Versão instalada: {__version__}"
        return (
            f"Versão atual: {__version__}. As atualizações automáticas ficam disponíveis "
            "no Piixel instalado no Windows."
        )

    @property
    def busy(self) -> bool:
        return self._busy

    def check_automatically(self) -> bool:
        return self.check(manual=False)

    def check(self, *, manual: bool = True) -> bool:
        if not self.supported:
            if manual:
                self.status_changed.emit(self.status_text)
            return False
        if self._closed or self._busy:
            return False
        self._set_busy(True)
        self.status_changed.emit("Verificando atualizações…")

        def work():
            release = error = None
            try:
                release = self.client.latest(__version__)
            except Exception as caught:
                error = caught
            self._check_finished.emit(release, error, manual)

        threading.Thread(target=work, name="PiixelUpdateCheck", daemon=True).start()
        return True

    def _on_check_finished(self, release, error, manual: bool):
        if self._closed:
            return
        self._set_busy(False)
        if error is not None:
            self.status_changed.emit("Não foi possível verificar atualizações.")
            if manual:
                QMessageBox.warning(
                    self.window, "Não foi possível verificar atualizações",
                    str(error) if isinstance(error, UpdateError) else
                    "Ocorreu uma falha inesperada durante a verificação.",
                )
            return
        if release is None:
            message = f"O Piixel {__version__} já é a versão mais recente."
            self.status_changed.emit(message)
            if manual:
                QMessageBox.information(self.window, "Piixel está atualizado", message)
            return
        self.status_changed.emit(f"Piixel {release.version} disponível.")
        self._offer_release(release)

    def _offer_release(self, release: Release):
        dialog = QMessageBox(self.window)
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setWindowTitle("Atualização disponível")
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(
            f"O Piixel {release.version} está disponível.\n"
            f"Você está usando a versão {__version__}."
        )
        details = release.notes.strip()
        if details:
            dialog.setInformativeText(details[:1200])
        update_button = dialog.addButton("Baixar e instalar", QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton("Mais tarde", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton() is update_button:
            self._download(release)

    def _download(self, release: Release):
        if self._closed or self._busy:
            return
        self._cancel.clear()
        self._set_busy(True)
        self.status_changed.emit(f"Baixando o Piixel {release.version}…")
        progress = QProgressDialog(
            "Baixando e verificando a atualização…", "Cancelar", 0, 0, self.window,
        )
        progress.setWindowTitle("Atualizando o Piixel")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.canceled.connect(self._cancel.set)
        self._progress_dialog = progress
        progress.show()

        def report(received: int, total: int | None):
            self._download_progress.emit(received, total or 0)

        def work():
            path = error = None
            try:
                directory = self.window.preferences.path.parent / "updates"
                path = self.client.download(
                    release, directory, progress=report,
                    cancelled=self._cancel.is_set,
                )
            except Exception as caught:
                error = caught
            self._download_finished.emit(path, error)

        threading.Thread(target=work, name="PiixelUpdateDownload", daemon=True).start()

    def _on_download_progress(self, received: int, total: int):
        dialog = self._progress_dialog
        if dialog is None:
            return
        if total > 0:
            dialog.setRange(0, total)
            dialog.setValue(min(received, total))
        else:
            dialog.setRange(0, 0)

    def _on_download_finished(self, path, error):
        dialog = self._progress_dialog
        self._progress_dialog = None
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()
        if self._closed:
            return
        self._set_busy(False)
        if error is not None:
            cancelled = self._cancel.is_set()
            self.status_changed.emit("Download cancelado." if cancelled else
                                     "Não foi possível baixar a atualização.")
            if not cancelled:
                QMessageBox.warning(
                    self.window, "Não foi possível baixar a atualização",
                    str(error) if isinstance(error, UpdateError) else
                    "Ocorreu uma falha inesperada durante o download.",
                )
            return
        self.status_changed.emit("Atualização pronta para instalar.")
        self._install(path)

    def _install(self, installer) -> bool:
        if not self.window.confirm_close_for_update():
            self.status_changed.emit(
                "Atualização baixada. Feche o trabalho pendente e verifique novamente."
            )
            return False
        from .startup import launch_update_after_exit
        if not launch_update_after_exit(installer):
            self.window.cancel_update_close()
            QMessageBox.warning(
                self.window, "Não foi possível iniciar a atualização",
                "O instalador foi verificado, mas o processo de atualização não pôde ser iniciado.",
            )
            return False
        self.window.close()
        QApplication.quit()
        return True

    def _set_busy(self, value: bool):
        self._busy = bool(value)
        self.busy_changed.emit(self._busy)

    def shutdown(self):
        self._closed = True
        self._cancel.set()
        if self._progress_dialog is not None:
            self._progress_dialog.close()
            self._progress_dialog = None

