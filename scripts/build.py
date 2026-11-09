"""Gera um aplicativo desktop para o sistema em que este script for executado."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    entry_point = root / "run_piixelverso.py"
    if not entry_point.is_file():
        print(f"Arquivo de entrada não encontrado: {entry_point}", file=sys.stderr)
        return 1
    if importlib.util.find_spec("PyInstaller") is None:
        print(
            "Instale as ferramentas de build antes de continuar:\n"
            "  python -m pip install -r requirements-dev.txt",
            file=sys.stderr,
        )
        return 1

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--noupx",
        "--name",
        "Piixel",
        "--onedir",
        "--contents-directory",
        "_internal",
        "--distpath",
        str(root / "dist"),
        "--workpath",
        str(root / "build"),
        "--specpath",
        str(root / "build"),
        "--add-data",
        f"{root / 'piixelverso' / 'assets'}{os.pathsep}piixelverso/assets",
    ]
    if sys.platform == "win32":
        # The script can run both as a module in checks and directly from a ZIP.
        if __package__:
            from .windows_assets import create_windows_assets
        else:
            from windows_assets import create_windows_assets
        assets = create_windows_assets(root)
        command.extend(["--icon", str(assets["icon"]), "--version-file", str(assets["version_file"])])
    command.append(str(entry_point))
    try:
        subprocess.run(command, cwd=root, check=True)
    except subprocess.CalledProcessError as exc:
        print("O empacotamento falhou. Confira as mensagens acima.", file=sys.stderr)
        return exc.returncode or 1
    print(f"Aplicativo gerado em: {root / 'dist'}")
    print("Distribua a pasta inteira do aplicativo para manter suas dependências.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
