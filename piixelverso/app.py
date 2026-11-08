"""Piixel application shell and navigation between its desktop modules."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QStackedWidget

from .atelier import AtelierModule, icon
from .brand import app_icon, ensure_fonts
from .home import HomePage
from .modules import MODULES
from .format import DesignFormatError, load_design
from .model import PixelDesign
from .preferences import PreferencesError, PreferencesStore
from .theme import APP_STYLE, apply_palette
from .thumbnails import thumbnail_png

STYLE = APP_STYLE


class MainWindow(QMainWindow):
    """Keep module widgets alive so navigating home never discards their work."""

    def __init__(self, preferences: PreferencesStore | None = None):
        super().__init__()
        ensure_fonts()
        apply_palette(QApplication.instance())
        self.setObjectName("piixelWindow")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(1120, 750)
        self.resize(1380, 900)
        self.preferences = preferences if preferences is not None else PreferencesStore()
        self._refreshing_recent_files = False
        self._recent_error_reported = False
        self.current_module: str | None = None
        self.module_pages: dict[str, AtelierModule] = {}
        self._opened_modules: set[str] = set()
        self._definitions = {module.id: module for module in MODULES}
        self._factories = {"atelier": AtelierModule}

        self.pages = QStackedWidget()
        self.pages.setObjectName("applicationPages")
        self.setCentralWidget(self.pages)
        self.home_page = HomePage(
            MODULES,
            module_icons={module.id: icon(module.icon_name) for module in MODULES},
        )
        self.pages.addWidget(self.home_page)
        self.home_page.module_requested.connect(self.open_module)
        self.home_page.recent_file_requested.connect(self.open_design_path)

        self.home_action = QAction("Tela inicial", self)
        self.home_action.setShortcut(QKeySequence("Alt+Home"))
        self.home_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.home_action.setToolTip("Voltar à tela inicial (Alt+Home)")
        self.home_action.triggered.connect(self.show_home)
        self.addAction(self.home_action)
        self.show_home()
        if self.preferences.load_error:
            QTimer.singleShot(0, self._show_preferences_load_error)

    def _get_module(self, module_id: str) -> AtelierModule:
        if module_id not in self._definitions or module_id not in self._factories:
            raise ValueError(f"Módulo desconhecido: {module_id}")
        if module_id not in self.module_pages:
            module = self._factories[module_id](parent=self.pages, preferences=self.preferences)
            module.set_active(False)
            self.pages.addWidget(module)
            self.module_pages[module_id] = module
            module.home_requested.connect(self.show_home)
            module.document_accessed.connect(self._record_recent_file)
            module.windowTitleChanged.connect(
                lambda _title, key=module_id: self._sync_module_state(key)
            )
            module.home_button.setToolTip("Voltar à tela inicial (Alt+Home)")
            file_menu = module.command_bar.menus["file"]
            file_menu.addSeparator()
            file_menu.addAction(self.home_action)
        return self.module_pages[module_id]

    def _sync_module_state(self, module_id: str):
        if module_id not in self._opened_modules:
            return
        module = self.module_pages[module_id]
        self.home_page.set_module_state(
            module_id, module.design.name, not module.history.isClean()
        )
        if self.current_module == module_id:
            self.setWindowTitle(module.windowTitle())

    def open_module(self, module_id: str) -> AtelierModule:
        module = self._get_module(module_id)
        if self.current_module and self.current_module != module_id:
            previous = self.module_pages[self.current_module]
            previous.prepare_navigation()
            previous.set_active(False)
        self.current_module = module_id
        self._opened_modules.add(module_id)
        self.pages.setCurrentWidget(module)
        module.set_active(True)
        self.home_action.setEnabled(True)
        self._sync_module_state(module_id)
        QTimer.singleShot(0, lambda: self._focus_module_if_current(module_id))
        return module

    def _focus_module_if_current(self, module_id: str):
        if self.current_module == module_id:
            self.module_pages[module_id].canvas.setFocus()

    def show_home(self):
        if self.current_module:
            module_id = self.current_module
            module = self.module_pages[module_id]
            module.prepare_navigation()
            module.set_active(False)
            self._sync_module_state(module_id)
        self.current_module = None
        self.pages.setCurrentWidget(self.home_page)
        self.home_action.setEnabled(False)
        self.setWindowTitle("Piixel — Início")
        self.refresh_recent_files()
        QTimer.singleShot(0, self._focus_home_if_current)

    def _focus_home_if_current(self):
        if self.current_module is None:
            self.home_page.focus_default_module()

    def open_design_path(self, path: str | Path) -> bool:
        module = self._get_module("atelier")
        if not module.load_path(path):
            return False
        self.open_module("atelier")
        return True

    def _record_recent_file(self, path: str, design: PixelDesign):
        try:
            self.preferences.record_file(path, thumbnail_png(design))
            self._recent_error_reported = False
        except (PreferencesError, OSError, ValueError, RuntimeError) as error:
            self._warn_recent_error(error)
        self.home_page.set_recent_files(self.preferences.recent_files())

    def refresh_recent_files(self):
        """Refresh known files on returning home; keep moved files identifiable."""
        if self._refreshing_recent_files:
            return
        self._refreshing_recent_files = True
        try:
            for entry in self.preferences.recent_files():
                path = Path(entry.path)
                try:
                    if not path.is_file() or path.stat().st_mtime_ns == entry.modified_ns:
                        continue
                    design = load_design(path)
                except (OSError, DesignFormatError, ValueError):
                    continue
                try:
                    self.preferences.record_file(path, thumbnail_png(design))
                except (PreferencesError, OSError, ValueError, RuntimeError) as error:
                    self._warn_recent_error(error)
                    break
            self.home_page.set_recent_files(self.preferences.recent_files())
        finally:
            self._refreshing_recent_files = False

    def _warn_recent_error(self, error: Exception):
        if not self._recent_error_reported:
            self._recent_error_reported = True
            message = f"Não foi possível guardar a lista de arquivos recentes.\n\n{error}"
            QTimer.singleShot(0, lambda: QMessageBox.warning(self, "Arquivos recentes", message))

    def _show_preferences_load_error(self):
        if self.preferences.load_error:
            QMessageBox.warning(self, "Preferências", self.preferences.load_error)

    def closeEvent(self, event):
        # An editor may be hidden on the home screen and still contain a design.
        atelier = self.module_pages.get("atelier")
        if atelier is not None and not atelier.confirm_discard():
            event.ignore()
            return
        event.accept()


def main(argv=None, *, startup=None):
    parser = argparse.ArgumentParser(description="Piixel — ferramentas do Piixelverso")
    parser.add_argument("design", nargs="?", help="Arquivo .pii para abrir diretamente no Ateliê")
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Piixel")
    app.setOrganizationName("Piixelverso")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setFont(QFont("DejaVu Sans", 10))
    window = MainWindow()
    if startup is not None:
        startup.finish(window)
    window.show()
    if args.design:
        QTimer.singleShot(0, lambda: window.open_design_path(args.design))
    return app.exec()
