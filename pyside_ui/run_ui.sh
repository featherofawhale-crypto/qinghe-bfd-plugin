#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
if ! "$PYTHON" -c "import PySide6" >/dev/null 2>&1; then
  "$PYTHON" -m pip install -r requirements.txt
fi

"$PYTHON" app.py
