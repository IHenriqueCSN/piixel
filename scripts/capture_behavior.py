"""Capture UI and data artifacts for before/after refactoring comparisons."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Captura telas, arquivos e atalhos do Piixel para comparação.")
    parser.add_argument("output", type=Path, help="Pasta de saída das capturas")
    parser.add_argument("--compare", type=Path, help="Pasta de uma captura anterior, no mesmo ambiente")
    args = parser.parse_args(argv)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))

    from PySide6.QtWidgets import QApplication
    from piixelverso.app import MainWindow, STYLE
    from piixelverso.export_dialog import ExportPngDialog
    from piixelverso.format import encode_design, load_design
    from piixelverso.png_export import render_png
    from piixelverso.preferences import PreferencesStore
    from piixelverso.replace import ReplaceColorDialog
    from piixelverso.resize_dialog import ResizeCanvasDialog

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)

    def grab(widget, filename):
        app.processEvents()
        if not widget.grab().save(str(output / filename)):
            raise OSError(f"Não foi possível gravar a captura {filename}.")

    with TemporaryDirectory(prefix="piixel-behavior-") as temporary:
        settings_path = Path(temporary) / "preferences.json"
        preferences = PreferencesStore(settings_path)
        preferences.save_color("#ED5598", "Rosa Piixel")
        preferences.set_piece_size_mm(5.0)
        window = MainWindow(preferences=preferences)
        window.show()
        grab(window, "home.png")
        window.resize(1120, 750)
        grab(window, "home-minimum.png")
        window.resize(1380, 900)
        atelier = window.open_module("atelier")
        example = root / "examples/cogumelo-do-bosque.pii"
        atelier._replace_design(load_design(example), example)
        atelier.add_custom_color("#8154CE")
        atelier.select_color("#ED5598")
        app.processEvents()
        atelier.fit_canvas()
        grab(window, "atelier.png")
        atelier.display_mode_combo.setCurrentIndex(1)
        grab(window, "atelier-beads.png")
        atelier.select_tool("rectangle")
        atelier.set_shape_fill(True)
        grab(window, "shape-toolbar.png")
        for filename, dialog in (
            ("replace.png", ReplaceColorDialog(atelier.design, atelier.color_names, "#ED5598", window)),
            ("resize.png", ResizeCanvasDialog(atelier.design, window)),
            ("export.png", ExportPngDialog(atelier.design, display_mode="beads", show_grid=False, parent=window)),
        ):
            dialog.show()
            grab(dialog, filename)
            dialog.reject()
        window.open_module("settings")
        grab(window, "settings.png")
        window.open_module("atelier")
        window.resize(1120, 750)
        grab(window, "atelier-minimum.png")
        for mode in ("squares", "beads"):
            for grid in (False, True):
                if not render_png(atelier.design, display_mode=mode, show_grid=grid).save(
                    str(output / f"export-{mode}-{grid}.png")
                ):
                    raise OSError("Não foi possível gravar uma exportação de referência.")
        (output / "design.pii").write_bytes(encode_design(atelier.design))
        (output / "preferences.json").write_bytes(settings_path.read_bytes())
        bindings = {
            key: {"text": action.text(), "shortcuts": [seq.toString() for seq in action.shortcuts()],
                  "checkable": action.isCheckable()}
            for key, action in atelier.command_actions.items()
        }
        (output / "commands.json").write_text(json.dumps(bindings, sort_keys=True, ensure_ascii=False))
        atelier.history.setClean()
        window.close()

    artifacts = {path.name: path.read_bytes() for path in output.iterdir() if path.is_file()}
    if args.compare:
        previous = {path.name: path.read_bytes() for path in args.compare.iterdir() if path.is_file()}
        differences = sorted(name for name in artifacts.keys() | previous.keys()
                             if artifacts.get(name) != previous.get(name))
        if differences:
            print("Artefatos diferentes: " + ", ".join(differences), file=sys.stderr)
            return 1
        print(f"{len(artifacts)} artefatos idênticos byte a byte.")
    else:
        print(json.dumps({name: hashlib.sha256(data).hexdigest() for name, data in sorted(artifacts.items())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
