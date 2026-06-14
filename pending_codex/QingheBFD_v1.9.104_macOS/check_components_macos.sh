#!/bin/bash
# Qinghe BFD v2.0.1-beta.14 - macOS component checker.

set -e

SCRIPT_BASE="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts"
MODULE_DIR="$SCRIPT_BASE/Modules/black_frame_detector"
MAIN_SCRIPT="$SCRIPT_BASE/Edit/清何黑帧夹帧检测.lua"

echo "Qinghe BFD v2.0.1-beta.14 macOS component check"
echo "DaVinci Resolve script base:"
echo "  $SCRIPT_BASE"
echo ""

[ -d "$SCRIPT_BASE" ] && echo "OK: DaVinci Resolve Fusion/Scripts exists" || echo "MISS: DaVinci Resolve Fusion/Scripts"
[ -f "$MAIN_SCRIPT" ] && echo "OK: main Lua script" || echo "MISS: main Lua script"
[ -d "$MODULE_DIR" ] && echo "OK: module directory" || echo "MISS: module directory"

for file in config.lua version_compat.lua ffmpeg_runner.lua black_frame_analyzer.lua marker_manager.lua ui_bridge.lua report_generator.lua duplicate_detector.lua py_params_bridge.lua progress_bridge.lua; do
    [ -f "$MODULE_DIR/$file" ] && echo "OK: $file" || echo "MISS: $file"
done

if [ -f "$MODULE_DIR/ffmpeg/macos/ffmpeg" ]; then
    echo "OK: bundled ffmpeg/macos/ffmpeg"
    DYLD_LIBRARY_PATH="$MODULE_DIR/ffmpeg/macos/lib" "$MODULE_DIR/ffmpeg/macos/ffmpeg" -version | head -n 1 || true
else
    echo "MISS: bundled ffmpeg/macos/ffmpeg"
fi

if command -v python3 >/dev/null 2>&1; then
    echo "OK: python3 $(python3 --version 2>&1)"
    python3 -c "import PySide6; print('OK: PySide6')" 2>/dev/null || echo "MISS: PySide6"
else
    echo "MISS: python3"
fi

if [ -f "$MODULE_DIR/ui_launcher_path.txt" ]; then
    echo "OK: ui_launcher_path.txt"
    cat "$MODULE_DIR/ui_launcher_path.txt"
else
    echo "MISS: ui_launcher_path.txt"
fi
