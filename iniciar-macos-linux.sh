#!/usr/bin/env sh
set -eu

PIIXELVERSO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PIIXELVERSO_DIR"

if [ ! -x .venv/bin/python ]; then
    if ! command -v python3 >/dev/null 2>&1; then
        echo "Instale Python 3.11 ou superior para iniciar o Piixelverso." >&2
        exit 1
    fi
    if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
        echo "O Piixelverso precisa de Python 3.11 ou superior." >&2
        exit 1
    fi
    python3 -m venv .venv
fi

if ! .venv/bin/python -c 'from importlib.util import find_spec; raise SystemExit(0 if find_spec("PySide6") and find_spec("nacl") else 1)' >/dev/null 2>&1; then
    echo "Instalando os componentes do Piixelverso. A primeira execução precisa de internet."
    .venv/bin/python -m pip install -r requirements.txt
fi

exec .venv/bin/python -m piixelverso "$@"
