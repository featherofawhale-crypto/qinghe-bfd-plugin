#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

LOG_DIR="${HOME:-.}/.qinghe_bfd"
mkdir -p "$LOG_DIR" >/dev/null 2>&1 || true
printf '%s run_ui.sh start pid=%s cwd=%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$$" "$PWD" >> "$LOG_DIR/launch.log" 2>/dev/null || true

export QINGHE_USE_EXTERNAL_BRIDGE="${QINGHE_USE_EXTERNAL_BRIDGE:-1}"

PYINSTALLER_GUI="./QingheBFDControl/QingheBFDControl"
APP_BUNDLE="./QingheBFDControl.app/Contents/MacOS/QingheBFDControl"
APP_BUNDLE_NUITKA="./QingheBFDControl.app/Contents/MacOS/app"
if [ -x "$PYINSTALLER_GUI" ]; then
  printf '%s exec pyinstaller gui\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_DIR/launch.log" 2>/dev/null || true
  exec "$PYINSTALLER_GUI" "$@"
fi
if [ -x "$APP_BUNDLE" ]; then
  printf '%s exec app bundle\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_DIR/launch.log" 2>/dev/null || true
  exec "$APP_BUNDLE" "$@"
fi
if [ -x "$APP_BUNDLE_NUITKA" ]; then
  printf '%s exec nuitka app\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_DIR/launch.log" 2>/dev/null || true
  exec "$APP_BUNDLE_NUITKA" "$@"
fi

PYTHON="${PYTHON:-python3}"
if [ "${QINGHE_ALLOW_PIP_INSTALL:-0}" != "1" ]; then
  if "$PYTHON" -c "import PySide6" >/dev/null 2>&1; then
    exec "$PYTHON" app.py "$@"
  fi
  echo "未找到内置 QingheBFDControl，且当前系统没有 PySide6。"
  echo "请重新安装完整 macOS DMG。正式安装包不默认联网下载依赖。"
  echo "开发调试如需自动安装依赖，可设置 QINGHE_ALLOW_PIP_INSTALL=1。"
  exit 1
fi

if ! "$PYTHON" -c "import PySide6" >/dev/null 2>&1; then
  "$PYTHON" -m pip install -r requirements.txt
fi

exec "$PYTHON" app.py "$@"
