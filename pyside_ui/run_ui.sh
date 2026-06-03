#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

RESOLVE_SCRIPT_API="${RESOLVE_SCRIPT_API:-/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting}"
RESOLVE_SCRIPT_LIB="${RESOLVE_SCRIPT_LIB:-/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so}"
export RESOLVE_SCRIPT_API
export RESOLVE_SCRIPT_LIB

PYTHON="${PYTHON:-python3}"
if ! "$PYTHON" -c "import PySide6" >/dev/null 2>&1; then
  "$PYTHON" -m pip install -r requirements.txt
fi

"$PYTHON" app.py
