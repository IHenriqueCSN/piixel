"""Gera um aplicativo desktop para o sistema em que este script for executado."""

from __future__ import annotations

import importlib.util
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
        "--name",
        "Piixelverso",
        "--onedir",
        "--distpath",
        str(root / "dist"),
        "--workpath",
        str(root / "build"),
        "--specpath",
        str(root / "build"),
        str(entry_point),
    ]
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
