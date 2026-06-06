#!/bin/bash
# ============================================================
# black_frame_detector 卸载脚本 (macOS / Linux / Windows Git Bash)
# 用法:
#   chmod +x uninstall.sh
#   ./uninstall.sh
# ============================================================

set -e

PLUGIN_NAME="black_frame_detector"

# 检测操作系统
case "$(uname -s)" in
    Darwin)
        OS="macos"
        INSTALL_DIR="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/$PLUGIN_NAME"
        ;;
    Linux)
        OS="linux"
        INSTALL_DIR="$HOME/.local/share/DaVinciResolve/Fusion/Scripts/Edit/$PLUGIN_NAME"
        ;;
    MINGW*|MSYS*|CYGWIN*)
        OS="windows"
        INSTALL_DIR="$APPDATA/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Edit/$PLUGIN_NAME"
        # 转换路径格式
        INSTALL_DIR=$(echo "$INSTALL_DIR" | sed 's/\\/\//g')
        ;;
    *)
        echo "❌ 不支持的操作系统: $(uname -s)"
        exit 1
        ;;
esac

echo "============================================"
echo "  黑帧夹帧检测插件 卸载程序"
echo "============================================"
echo ""
echo "  操作系统: $OS"
echo "  安装路径: $INSTALL_DIR"
echo ""

if [ ! -d "$INSTALL_DIR" ]; then
    echo "⚠️  未找到已安装的插件目录，无需卸载。"
    exit 0
fi

echo "以下文件将被删除:"
find "$INSTALL_DIR" -type f | while read f; do
    echo "  - $f"
done

echo ""
read -p "确认卸载? (y/N): " confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "已取消卸载。"
    exit 0
fi

rm -rf "$INSTALL_DIR"
echo ""
echo "✅ 插件已成功卸载。"
echo ""
echo "如需重新安装，运行:"
echo "  项目目录/install/install.sh"
