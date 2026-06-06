#!/bin/bash
# Qinghe BFD v2.0.0-内测版 - macOS one-click installer.
# Target: ~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit
# Target: ~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Modules/black_frame_detector

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR/QingheBFD_Plugin_macOS"
if [ ! -d "$SOURCE_DIR" ]; then
    SOURCE_DIR="$SCRIPT_DIR"
fi

PLUGIN_NAME="black_frame_detector"
SCRIPT_BASE="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts"
EDIT_DIR="$SCRIPT_BASE/Edit"
MODULE_DIR="$SCRIPT_BASE/Modules/$PLUGIN_NAME"
BACKUP_DIR="$MODULE_DIR/backup_$(date +%Y%m%d_%H%M%S)"
MAIN_SCRIPT="清何黑帧夹帧检测.lua"

echo "============================================"
echo "  清何黑帧夹帧检测 v2.0.0-内测版 macOS 一键安装"
echo "============================================"
echo "主脚本: $EDIT_DIR/$MAIN_SCRIPT"
echo "模块:   $MODULE_DIR"
echo ""

if [ ! -f "$SOURCE_DIR/$MAIN_SCRIPT" ]; then
    echo "未找到主脚本: $SOURCE_DIR/$MAIN_SCRIPT"
    read -r -p "按回车退出..."
    exit 1
fi

mkdir -p "$EDIT_DIR" "$MODULE_DIR"

if [ -f "$EDIT_DIR/$MAIN_SCRIPT" ] || [ -d "$MODULE_DIR" ]; then
    mkdir -p "$BACKUP_DIR"
    [ -f "$EDIT_DIR/$MAIN_SCRIPT" ] && cp "$EDIT_DIR/$MAIN_SCRIPT" "$BACKUP_DIR/Edit_$MAIN_SCRIPT"
    [ -f "$SCRIPT_BASE/$MAIN_SCRIPT" ] && cp "$SCRIPT_BASE/$MAIN_SCRIPT" "$BACKUP_DIR/Root_$MAIN_SCRIPT"
    find "$MODULE_DIR" -maxdepth 1 -type f -name "*.lua" -exec cp {} "$BACKUP_DIR/" \; 2>/dev/null || true
fi

rm -f "$EDIT_DIR/$MAIN_SCRIPT" "$SCRIPT_BASE/$MAIN_SCRIPT" 2>/dev/null || true
find "$MODULE_DIR" -maxdepth 1 -type f -name "*.lua" -delete 2>/dev/null || true

cp "$SOURCE_DIR/$MAIN_SCRIPT" "$EDIT_DIR/"
cp "$SOURCE_DIR/$MAIN_SCRIPT" "$SCRIPT_BASE/"

if [ -d "$SOURCE_DIR/modules" ]; then
    cp "$SOURCE_DIR/modules/"*.lua "$MODULE_DIR/"
else
    echo "未找到 modules 目录"
    read -r -p "按回车退出..."
    exit 1
fi

if [ -d "$SOURCE_DIR/ffmpeg" ]; then
    rm -rf "$MODULE_DIR/ffmpeg"
    cp -a "$SOURCE_DIR/ffmpeg" "$MODULE_DIR/"
    chmod +x "$MODULE_DIR/ffmpeg/macos/ffmpeg" 2>/dev/null || true
fi

if [ -d "$SOURCE_DIR/pyside_ui" ]; then
    rm -rf "$MODULE_DIR/pyside_ui"
    cp -a "$SOURCE_DIR/pyside_ui" "$MODULE_DIR/"
    chmod +x "$MODULE_DIR/pyside_ui/run_ui.sh" 2>/dev/null || true
    printf "%s\n" "$MODULE_DIR/pyside_ui/run_ui.sh" > "$MODULE_DIR/ui_launcher_path.txt"
fi

rm -f "$HOME/.bfd_io_cache.lua" 2>/dev/null || true

FAIL=0
for file in "$EDIT_DIR/$MAIN_SCRIPT" "$MODULE_DIR/config.lua" "$MODULE_DIR/ffmpeg_runner.lua" "$MODULE_DIR/black_frame_analyzer.lua" "$MODULE_DIR/duplicate_detector.lua"; do
    if [ -f "$file" ]; then
        echo "OK: $file"
    else
        echo "缺失: $file"
        FAIL=1
    fi
done

if [ -f "$MODULE_DIR/ffmpeg/macos/ffmpeg" ]; then
    echo "OK: bundled ffmpeg/macos/ffmpeg"
else
    echo "提示: 未安装捆绑 ffmpeg，插件会尝试系统 PATH 中的 ffmpeg"
fi

if [ -f "$MODULE_DIR/ui_launcher_path.txt" ]; then
    echo "OK: ui_launcher_path.txt"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
    echo "安装完成。重启 DaVinci Resolve 后打开：工作区 -> 脚本 -> Edit -> 清何黑帧夹帧检测"
else
    echo "安装不完整，请查看上面的缺失项。"
fi

read -r -p "按回车退出..."
