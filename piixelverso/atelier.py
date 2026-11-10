"""Coordinate the Ateliê view, document session, and user workflows."""
from __future__ import annotations

from html import escape
from pathlib import Path

from PySide6.QtCore import QRect, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMenu, QMessageBox, QVBoxLayout

from .brand import app_icon, ensure_fonts
from .colors import CustomColorDialog
from .editor.actions import EditorActions
from .editor.history import (
    PixelCommand as _PixelCommand,
    RenameCommand as _RenameCommand,
    ResizeCanvasCommand as _ResizeCanvasCommand,
)
from .editor.new_design_dialog import NewDesignDialog
from .editor.palette import COLOR_NAMES, PALETTE
from .editor.session import EditorSession
from .editor.view import AtelierView, VIEW_ATTRIBUTES
from .export_dialog import ExportPngDialog
from .format import DesignFormatError, load_design, save_design
from .materials import TRANSPARENT_OUTLINE, display_color, material_reference
from .model import PixelDesign, is_transparent, normalize_color, validate_name
from .module_api import ModuleHomeState, ModulePage
from .operations import replace_color_changes
from .png_export import save_png
from .preferences import PreferencesError, PreferencesStore
from .replace import ReplaceColorDialog
from .resize import count_cropped_pixels, resized_design
from .resize_dialog import ResizeCanvasDialog
from .selection import (
    SelectionPayload, capture_selection, cut_selection_changes, paste_selection_changes,
)
from .theme import APP_STYLE, BORDER, INK, PINK, apply_palette
from .ui.icons import icon
from .ui.widgets import button, label


STYLE = APP_STYLE


class PixelCommand(_PixelCommand):
    """Preserve the previous constructor for callers importing from this module."""

    def __init__(self, window, before, after, text="Pintar pixels"):
        super().__init__(window.session, before, after, text)
        self.window = window


class RenameCommand(_RenameCommand):
    def __init__(self, window, name):
        super().__init__(window.session, name)
        self.window = window


class ResizeCanvasCommand(_ResizeCanvasCommand):
    def __init__(self, window, before, after):
        super().__init__(window.session, before, after)
        self.window = window


class AtelierModule(ModulePage):
    def __init__(self, parent=None, preferences: PreferencesStore | None = None):
        super().__init__(parent)
        self.setObjectName("atelierModule")
        self._active = True
        self.preferences = preferences if preferences is not None else PreferencesStore()
        self.color_names = dict(COLOR_NAMES)
        self._custom_color_names: dict[str, str] = {}
        self._saved_colors = {}
        ensure_fonts()
        apply_palette(QApplication.instance())
        self.session = EditorSession(self)
        self.history = self.session.history
        self.setWindowIcon(app_icon())
        self.setMinimumSize(1120, 750)
        self.resize(1380, 900)
        self._swatches = {}
        self._custom_colors: list[str] = []
        self._recent_colors: list[str] = []
        self._selection_clipboard: SelectionPayload | None = None
        self._counts_timer = QTimer(self)
        self._counts_timer.setSingleShot(True)
        self._counts_timer.timeout.connect(self.refresh_counts)
        self._create_actions()
        self._build()
        self.session.changed.connect(self.refresh_design)
        self.session.geometry_changed.connect(self._sync_canvas_document)
        self._load_saved_colors()
        self._connect_command_bar()
        self.history.indexChanged.connect(self._history_changed)
        self.refresh_design()
        self.select_color("#E7794B")
        self._history_changed()
        QTimer.singleShot(0, self.fit_canvas)

    @property
    def design(self) -> PixelDesign:
        return self.session.design

    @design.setter
    def design(self, value: PixelDesign) -> None:
        self.session.design = value

    @property
    def file_path(self) -> Path | None:
        return self.session.file_path

    @file_path.setter
    def file_path(self, value: Path | None) -> None:
        self.session.file_path = value

    def _build(self):
        self.view = AtelierView(self.design, self.color_names, self.command_actions, parent=self)
        host = QVBoxLayout(self)
        host.setContentsMargins(0, 0, 0, 0)
        host.setSpacing(0)
        host.addWidget(self.view)
        for name in VIEW_ATTRIBUTES:
            setattr(self, name, getattr(self.view, name))
        self._swatches = self.view.swatches
        self.view.home_requested.connect(self.home_requested.emit)
        self.view.rename_requested.connect(self.rename_design)
        self.view.color_selected.connect(self.select_color)
        self.view.color_picked.connect(self.pick_color)
        self.view.color_context_requested.connect(self._show_color_menu)
        self.view.recent_color_selected.connect(self.select_recent_color)
        self.canvas.changed.connect(self._canvas_changed)
        self.canvas.stroke_finished.connect(self._commit_stroke)
        self.canvas.color_picked.connect(self.pick_color)
        self.canvas.selection_changed.connect(self._sync_selection_actions)
        for key in ("cut", "copy", "paste"):
            self.canvas.addAction(self.command_actions[key])

    def _create_actions(self):
        self._actions = EditorActions(
            self,
            handlers={
                "new": self.new_design,
                "open": self.open_design,
                "save": self.save,
                "save_as": self.save_as,
                "export_png": self.export_png,
                "resize_canvas": self.show_resize_canvas_dialog,
                "undo": self.undo,
                "redo": self.redo,
                "cut": self.cut_selection,
                "copy": self.copy_selection,
                "paste": self.paste_selection,
                "replace_color": self.show_replace_color_dialog,
                "custom_color": self.custom_color,
                "fit": self.fit_canvas,
            },
            select_tool=self.select_tool,
            set_shape_fill=self.set_shape_fill,
            icon_factory=icon,
            select_recent_color=self.select_recent_color,
        )
        self.command_actions = self._actions.commands
        self.tool_action_group = self._actions.tool_group
        self.recent_color_actions = self._actions.recent_color_actions

    def _add_swatch(self, color, name, index):
        self.view.add_swatch(color, name, index)

    def _sync_canvas_document(self):
        self.canvas.set_design(self.design)

    def focus_default(self):
        self.canvas.setFocus()

    def home_state(self) -> ModuleHomeState:
        return ModuleHomeState(self.design.name, not self.history.isClean())

    def confirm_close(self) -> bool:
        return self.confirm_discard()

    def attach_navigation(self, home_action, settings_action):
        super().attach_navigation(home_action, settings_action)
        file_menu = self.command_bar.menus["file"]
        file_menu.addSeparator()
        file_menu.addAction(home_action)
        file_menu.addAction(settings_action)


    def _connect_command_bar(self):
        self.display_mode_combo.currentIndexChanged.connect(self.change_display_mode)
        self.command_bar.grid_checkbox.toggled.connect(self.toggle_grid)
        self.zoom.valueChanged.connect(self.set_zoom)

    def select_tool(self, tool):
        self.canvas.finish_stroke()
        self.canvas.tool = tool
        self.command_actions[tool].setChecked(True)
        self._sync_shape_actions()

    def set_shape_fill(self, filled: bool):
        self.canvas.finish_stroke()
        self.canvas.shape_filled = bool(filled)
        self.command_actions["shape_fill"].setChecked(self.canvas.shape_filled)

    def _sync_shape_actions(self):
        self.command_actions["shape_fill"].setEnabled(
            self._active and self.canvas.tool in ("rectangle", "ellipse")
        )

    def _sync_selection_actions(self, *_args):
        selected = self.canvas.has_selection
        self.command_actions["copy"].setEnabled(self._active and selected)
        self.command_actions["cut"].setEnabled(self._active and selected)
        self.command_actions["paste"].setEnabled(
            self._active and self._selection_clipboard is not None
        )

    def copy_selection(self) -> bool:
        self.canvas.finish_stroke()
        rect = self.canvas.selection_tuple()
        if not self._active or rect is None:
            return False
        self._selection_clipboard = capture_selection(self.design, rect)
        self._sync_selection_actions()
        return True

    def cut_selection(self) -> bool:
        self.canvas.finish_stroke()
        rect = self.canvas.selection_tuple()
        if not self._active or rect is None:
            return False
        self._selection_clipboard = capture_selection(self.design, rect)
        after = cut_selection_changes(self.design, rect)
        if after:
            before = {index: self.design.pixels[index] for index in after}
            self.session.commit_pixels(before, after, "Recortar seleção")
        self._sync_selection_actions()
        return True

    def paste_selection(self) -> bool:
        self.canvas.finish_stroke()
        payload = self._selection_clipboard
        if not self._active or payload is None:
            return False
        current = self.canvas.selection
        preferred_left = current.x() + 1 if current is not None else 0
        preferred_top = current.y() + 1 if current is not None else 0
        left = max(0, min(max(0, self.design.width - payload.width), preferred_left))
        top = max(0, min(max(0, self.design.height - payload.height), preferred_top))
        after = paste_selection_changes(self.design, payload, left, top)
        if after:
            before = {index: self.design.pixels[index] for index in after}
            self.session.commit_pixels(before, after, "Colar seleção")
        visible_width = min(payload.width, self.design.width - left)
        visible_height = min(payload.height, self.design.height - top)
        self.canvas.set_selection(QRect(left, top, visible_width, visible_height))
        return True

    @property
    def recent_colors(self) -> tuple[str, ...]:
        """Session colors; selecting a recent slot keeps its number stable."""
        return tuple(self._recent_colors)

    def select_recent_color(self, index: int):
        if not self._active or not 0 <= index < len(self._recent_colors):
            return
        # A keyboard change during a gesture starts the next gesture in the new
        # color instead of changing the color of an unfinished geometric preview.
        self.canvas.finish_stroke()
        self.select_color(self._recent_colors[index], remember=False)

    def _sync_recent_color_actions(self):
        for index, action in enumerate(self.recent_color_actions):
            action.setEnabled(self._active and index < len(self._recent_colors))

    def select_color(self, color, *, remember=True):
        color = normalize_color(color)
        if color is None:
            raise ValueError("Uma célula vazia não pode ser selecionada como material.")
        if remember:
            self._recent_colors = [color] + [value for value in self._recent_colors if value != color][:8]
        self.canvas.color = color
        self.active_hex.setText(material_reference(color))
        name = "Bead transparente" if is_transparent(color) else self._custom_color_names.get(color, "")
        self.active_color_name.setText(name)
        self.active_color_name.setToolTip(f"<p>{escape(name)}</p>" if name else "")
        self.active_color_name.setVisible(bool(name))
        active_border = TRANSPARENT_OUTLINE if is_transparent(color) else BORDER
        self.active_swatch.setStyleSheet(
            f"background: {display_color(color)}; border: 2px solid {active_border}; border-radius: 5px;"
        )
        for value, swatch in self._swatches.items():
            base_border = TRANSPARENT_OUTLINE if is_transparent(value) else BORDER
            border = f"2px solid {INK}" if value == color else f"1px solid {base_border}"
            swatch.setStyleSheet(
                f"QPushButton {{ background: {display_color(value)}; border: {border}; "
                f"border-radius: 5px; }} QPushButton:hover {{ border: 2px solid {PINK}; }}"
            )
        self.recent_colors_widget.set_colors(self._recent_colors, self.canvas.color)
        self._sync_recent_color_actions()

    def pick_color(self, color):
        self.select_color(color)
        self.select_tool("pencil")

    def custom_color(self):
        self._edit_custom_color("#E7794B" if is_transparent(self.canvas.color) else self.canvas.color)

    def show_replace_color_dialog(self):
        self.canvas.finish_stroke()
        if not self.design.counts():
            return
        target_colors = dict(COLOR_NAMES)
        for item in self.preferences.saved_colors():
            target_colors[item.color] = item.name or COLOR_NAMES.get(item.color, "Personalizada")
        dialog = ReplaceColorDialog(
            self.design, self.color_names, self.canvas.color, self.window(),
            target_colors=target_colors,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.replace_color(dialog.source_color(), dialog.target_color())

    def replace_color(self, source: str, target: str) -> int:
        """Replace every occurrence with one undo step; keep new colors in this session."""
        self.canvas.finish_stroke()
        after = replace_color_changes(self.design, source, target)
        if not after:
            return 0
        before = {index: self.design.pixels[index] for index in after}
        self.session.commit_pixels(before, after, "Substituir cor")
        self.add_custom_color(next(iter(after.values())))
        return len(after)

    def _edit_custom_color(self, color, *, save_for_future=False):
        dialog = CustomColorDialog(
            color, self.window(), name=self._custom_color_names.get(color, ""),
            save_for_future=save_for_future,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.add_custom_color(dialog.color_value(), dialog.color_name(), dialog.save_for_future())

    def _load_saved_colors(self):
        for item in self.preferences.saved_colors():
            self._saved_colors[item.color] = item
            self._remember_custom_color(item.color, item.name)

    def _remember_custom_color(self, color, name="", *, replace_name=False):
        if name:
            self._custom_color_names[color] = name
            self.color_names[color] = name
        elif replace_name:
            self._custom_color_names.pop(color, None)
            self.color_names[color] = COLOR_NAMES.get(color, "Personalizada")
        else:
            self.color_names.setdefault(color, "Personalizada")
        if color not in self._swatches:
            self._add_swatch(color, self.color_names[color], len(PALETTE) + len(self._custom_colors))
            self._custom_colors.append(color)
        self._refresh_color_tooltip(color)

    def _refresh_color_tooltip(self, color):
        name = self.color_names.get(color, "Personalizada")
        if color in self._saved_colors:
            note = "Salva para próximas sessões"
        else:
            note = "Cor da paleta inicial" if color in COLOR_NAMES else "Disponível nesta sessão"
        self._swatches[color].setToolTip(
            f"<p>{escape(name)} · {material_reference(color)}<br>{note}</p>"
        )

    def add_custom_color(self, color: str, name: str = "", persist: bool = False) -> None:
        value = normalize_color(color)
        if value is None:
            raise ValueError("A cor precisa ter um valor RGB.")
        if (not isinstance(name, str) or len(name.strip()) > 80
                or any(ord(char) < 32 for char in name)):
            raise ValueError("O nome da cor deve ter até 80 caracteres, em uma linha.")
        name = name.strip()
        self._remember_custom_color(value, name, replace_name=bool(persist))
        error = None
        if persist:
            try:
                self.preferences.save_color(value, name)
            except (PreferencesError, OSError, ValueError) as exc:
                error = exc
            else:
                self._saved_colors = {item.color: item for item in self.preferences.saved_colors()}
        self._refresh_color_tooltip(value)
        self.select_color(value)
        self.refresh_counts()
        QTimer.singleShot(0, self, lambda: self._reveal_color(value))
        if error is not None:
            QMessageBox.warning(
                self.window(), "Cor adicionada nesta sessão",
                "A cor foi adicionada à sessão, mas não foi possível salvá-la para próximas sessões."
                f"\n\n{error}",
            )

    def _reveal_color(self, color):
        body = self.palette_scroll.widget()
        body.layout().activate()
        body.adjustSize()
        self.palette_scroll.ensureWidgetVisible(self._swatches[color], 0, 8)

    def forget_saved_color(self, color: str) -> None:
        value = normalize_color(color)
        if value is None or value not in self._saved_colors:
            return
        try:
            self.preferences.remove_color(value)
        except (PreferencesError, OSError, ValueError) as error:
            QMessageBox.warning(self.window(), "Não foi possível remover a cor salva", str(error))
            return
        self._saved_colors.pop(value, None)
        self._refresh_color_tooltip(value)

    def _show_color_menu(self, color, position):
        if is_transparent(color):
            return
        menu = QMenu(self)
        save = menu.addAction("Editar cor salva…" if color in self._saved_colors else "Salvar cor…")
        save.triggered.connect(lambda _checked=False: self._edit_custom_color(color, save_for_future=True))
        if color in self._saved_colors:
            forget = menu.addAction("Remover das cores salvas")
            forget.triggered.connect(lambda _checked=False: self.forget_saved_color(color))
        menu.exec(self._swatches[color].mapToGlobal(position))
        menu.deleteLater()

    def toggle_grid(self, checked):
        self.canvas.show_grid = checked
        self.canvas.update()

    def change_display_mode(self, index):
        self.canvas.finish_stroke()
        self.canvas.set_display_mode(self.display_mode_combo.itemData(index))
        self._update_view_status()

    def set_zoom(self, percent):
        self.canvas.set_zoom(percent)
        self.zoom_label.setText(f"{round(self.canvas.cell_size / 16 * 100)}%")
        self._update_view_status()

    def _update_view_status(self):
        self.canvas_view_label.setText(f"{self.display_mode_combo.currentText()} · {self.zoom_label.text()}")

    def fit_canvas(self):
        available = self.viewport.viewport().size()
        cell = min((available.width() - 2 * self.canvas.MARGIN - 18) // self.design.width,
                   (available.height() - 2 * self.canvas.MARGIN - 18) // self.design.height)
        self.zoom.setValue(max(25, min(250, int(cell / 16 * 100))))

    def _canvas_changed(self):
        self._counts_timer.start(0)
        self._update_title()

    def _commit_stroke(self, before, after):
        shapes = {"line": "Desenhar linha reta", "rectangle": "Desenhar retângulo", "ellipse": "Desenhar elipse"}
        text = "Apagar pixels" if self.canvas.is_erasing else (
            shapes.get(self.canvas.tool, "Mover seleção" if self.canvas.tool == "selection" else (
                "Preencher área" if self.canvas.tool == "bucket" else "Pintar pixels")))
        self.session.commit_pixels(before, after, text)

    def prepare_navigation(self):
        """Commit the current gesture and name before leaving this module."""
        self.rename_design()
        self.canvas.finish_stroke()

    def set_active(self, active: bool):
        """Keep editor commands scoped to the visible module."""
        self._active = bool(active)
        for action in self.command_actions.values():
            action.setEnabled(self._active)
        self._sync_recent_color_actions()
        self._history_changed()

    def _history_changed(self, *args):
        self.command_actions["undo"].setEnabled(self._active and self.history.canUndo())
        self.command_actions["redo"].setEnabled(self._active and self.history.canRedo())
        self.command_actions["replace_color"].setEnabled(self._active and self.design.filled_count > 0)
        self._sync_shape_actions()
        self._sync_selection_actions()
        self._update_title()

    def undo(self):
        self.canvas.finish_stroke()
        self.history.undo()

    def redo(self):
        self.canvas.finish_stroke()
        self.history.redo()

    def _update_title(self):
        dirty = not self.history.isClean() or self.canvas.has_pending_changes
        self.setWindowTitle(f"{self.design.name}{' *' if dirty else ''} — Ateliê · Piixel")
        self.status_text.setText("●  Alterações não salvas" if dirty else (
            f"Salvo em {self.file_path.name}" if self.file_path else "Tudo pronto para criar. Seu design fica no seu computador."))

    def refresh_design(self):
        self.canvas.update()
        self.name_edit.setText(self.design.name)
        self.dimensions.setText(f"{self.design.width} × {self.design.height}")
        self.refresh_counts()
        self._update_title()

    def refresh_counts(self):
        counts = self.design.counts()
        self.command_actions["replace_color"].setEnabled(self._active and bool(counts))
        total = sum(counts.values())
        number = lambda value: f"{value:,}".replace(",", ".")
        self.total_label.setText(number(total))
        self.color_total.setText(f"{len(counts)} {'cor usada' if len(counts) == 1 else 'cores usadas'}")
        self.empty_total.setText(f"{number(self.design.width * self.design.height - total)} vazios")
        self.count_view.set_counts(counts)

    def rename_design(self):
        if self.name_edit.text() == self.design.name:
            return
        name = self.name_edit.text().strip() or "Sem título"
        try:
            validate_name(name)
        except ValueError as error:
            self.name_edit.setText(self.design.name)
            QMessageBox.warning(self.window(), "Nome muito longo", str(error))
            return
        if name != self.design.name:
            self.canvas.finish_stroke()
            self.session.rename(name)
        else:
            self.name_edit.setText(name)

    def confirm_discard(self):
        self.rename_design()
        self.canvas.finish_stroke()
        if self.history.isClean():
            return True
        dialog = QMessageBox(self.window())
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle("Salvar seu design?")
        dialog.setText("Seu design tem alterações não salvas.")
        dialog.setInformativeText("Salve para continuar criando de onde parou.")
        save_button = dialog.addButton("Salvar", QMessageBox.ButtonRole.AcceptRole)
        discard_button = dialog.addButton("Descartar alterações", QMessageBox.ButtonRole.DestructiveRole)
        dialog.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(save_button)
        dialog.exec()
        if dialog.clickedButton() == save_button:
            return self.save()
        return dialog.clickedButton() == discard_button

    def _replace_design(self, design, path=None):
        self.canvas.finish_stroke()
        self.session.replace(design, path)
        QTimer.singleShot(0, self.fit_canvas)

    def new_design(self):
        dialog = NewDesignDialog(self.window())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not self.confirm_discard():
            return
        self._replace_design(PixelDesign(dialog.width_input.value(), dialog.height_input.value(),
                                        name=dialog.name.text().strip() or "Sem título"))

    def show_resize_canvas_dialog(self):
        self.rename_design()
        self.canvas.finish_stroke()
        dialog = ResizeCanvasDialog(self.design, parent=self.window())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        width, height, anchor = dialog.target_width(), dialog.target_height(), dialog.anchor()
        cropped = count_cropped_pixels(self.design, width, height, anchor)
        if cropped:
            message = (
                "A redução removerá 1 peça que ficará fora da prancheta."
                if cropped == 1 else f"A redução removerá {cropped} peças que ficarão fora da prancheta."
            )
            answer = QMessageBox.question(
                self.window(), "Reduzir a prancheta?",
                message + "\n\nDeseja continuar? Você poderá desfazer essa alteração.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        return self.resize_canvas(width, height, anchor)

    def resize_canvas(self, width: int, height: int, anchor: str = "center") -> bool:
        after = resized_design(self.design, width, height, anchor)
        if (width, height) == (self.design.width, self.design.height):
            return False
        self.rename_design()
        self.canvas.finish_stroke()
        self.session.resize(after)
        return True

    def open_design(self):
        path, _ = QFileDialog.getOpenFileName(self.window(), "Abrir design", "", "Design Piixelverso (*.pii)")
        if path:
            self.load_path(path)

    def load_path(self, path):
        try:
            design = load_design(path)
        except FileNotFoundError:
            QMessageBox.warning(
                self.window(), "Arquivo não encontrado",
                "Arquivo não encontrado. Verifique se o arquivo foi movido ou apagado.",
            )
            return False
        except (OSError, DesignFormatError, ValueError) as error:
            QMessageBox.warning(self.window(), "Não foi possível abrir", f"O arquivo não pôde ser aberto.\n\n{error}")
            return False
        if not self.confirm_discard():
            return False
        self._replace_design(design, path)
        self.document_accessed.emit(str(self.file_path), self.design.clone())
        return True

    def save(self):
        self.rename_design()
        self.canvas.finish_stroke()
        return self._save_path(self.file_path) if self.file_path else self.save_as()

    def save_as(self):
        self.rename_design()
        self.canvas.finish_stroke()
        name = self.file_path.name if self.file_path else "meu-design.pii"
        path, _ = QFileDialog.getSaveFileName(self.window(), "Salvar design", str(self.file_path or name), "Design Piixelverso (*.pii)")
        if not path:
            return False
        target = Path(path)
        if target.suffix.lower() != ".pii":
            target = Path(str(target) + ".pii")
            if target.exists():
                reply = QMessageBox.question(self.window(), "Substituir arquivo?", f"{target.name} já existe. Deseja substituí-lo?",
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                             QMessageBox.StandardButton.No)
                if reply != QMessageBox.StandardButton.Yes:
                    return False
        return self._save_path(target)

    def export_png(self):
        self.rename_design()
        self.canvas.finish_stroke()
        try:
            dialog = ExportPngDialog(
                self.design, piece_size_mm=self.preferences.piece_size_mm(),
                display_mode=self.canvas.display_mode, show_grid=self.canvas.show_grid,
                parent=self.window(),
            )
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self.window(), "Não foi possível exportar o PNG", str(error))
            return False
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        initial_path = self.file_path.with_suffix(".png") if self.file_path else Path("meu-design.png")
        chosen, _ = QFileDialog.getSaveFileName(
            self.window(), "Exportar como PNG", str(initial_path), "Imagem PNG (*.png)"
        )
        if not chosen:
            return False
        target = Path(chosen)
        if target.suffix.lower() != ".png":
            target = Path(str(target) + ".png")
            if target.exists():
                answer = QMessageBox.question(
                    self.window(), "Substituir imagem?",
                    f"{target.name} já existe. Deseja substituir a imagem?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return False
        return self.export_png_path(
            target, display_mode=dialog.display_mode(), show_grid=dialog.show_grid(),
            piece_size_mm=dialog.piece_size_mm(),
        )

    def export_png_path(self, path, *, display_mode=None, show_grid=None, piece_size_mm=None) -> bool:
        """Write an image while keeping the open document and its save state."""
        self.rename_design()
        self.canvas.finish_stroke()
        target = Path(path)
        try:
            save_png(
                self.design, target,
                display_mode=self.canvas.display_mode if display_mode is None else display_mode,
                show_grid=self.canvas.show_grid if show_grid is None else show_grid,
                piece_size_mm=self.preferences.piece_size_mm() if piece_size_mm is None else piece_size_mm,
            )
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.warning(
                self.window(), "Não foi possível exportar o PNG",
                f"A imagem não pôde ser salva.\n\n{error}",
            )
            return False
        self.status_text.setText(f"Imagem PNG exportada para {target.name}.")
        return True

    def _save_path(self, path):
        try:
            self.session.save(path, writer=save_design)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self.window(), "Não foi possível salvar", f"Seu design continua aberto. Tente salvar em outra pasta.\n\n{error}")
            return False
        self._update_title()
        self.document_accessed.emit(str(self.file_path), self.design.clone())
        return True

    def closeEvent(self, event):
        if self.confirm_discard():
            event.accept()
        else:
            event.ignore()
