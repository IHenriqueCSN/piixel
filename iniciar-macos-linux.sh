#!/usr/bin/env sh
set -eu

PIIXELVERSO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PIIXELVERSO_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Instale Python 3.11 ou superior para iniciar o Piixelverso." >&2
    exit 1
fi

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "O Piixelverso precisa de Python 3.11 ou superior." >&2
    exit 1
fi

if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi

if ! .venv/bin/python -c 'import PySide6.QtWidgets' >/dev/null 2>&1; then
    echo "Instalando os componentes do Piixelverso. A primeira execução precisa de internet."
    .venv/bin/python -m pip install -r requirements.txt
fi

exec .venv/bin/python -m piixelverso
