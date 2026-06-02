#!/bin/bash
# Qinghe BFD v1.9.104 - macOS uninstaller.

PLUGIN_NAME="black_frame_detector"
SCRIPT_BASE="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts"
EDIT_DIR="$SCRIPT_BASE/Edit"
MODULE_DIR="$SCRIPT_BASE/Modules/$PLUGIN_NAME"
MAIN_SCRIPT="清何黑帧夹帧检测.lua"

echo "============================================"
echo "  清何黑帧夹帧检测 v1.9.104 macOS 卸载"
echo "============================================"
echo "将删除："
echo "  $EDIT_DIR/$MAIN_SCRIPT"
echo "  $SCRIPT_BASE/$MAIN_SCRIPT"
echo "  $MODULE_DIR"
echo ""

read -r -p "确认卸载? (y/N): " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "已取消。"
    read -r -p "按回车退出..."
    exit 0
fi

rm -f "$EDIT_DIR/$MAIN_SCRIPT" 2>/dev/null
rm -f "$SCRIPT_BASE/$MAIN_SCRIPT" 2>/dev/null
rm -rf "$MODULE_DIR" 2>/dev/null
rm -f "$HOME/.bfd_io_cache.lua" 2>/dev/null

echo "卸载完成。"
read -r -p "按回车退出..."
