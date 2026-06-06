#!/bin/bash
# ============================================================
# black_frame_detector 安装脚本 (macOS / Linux)
# 版本: v1.0.0
# 用法:
#   chmod +x install.sh
#   ./install.sh          # 安装
#   ./install.sh --force  # 强制覆盖安装
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLUGIN_NAME="black_frame_detector"
FORCE=false

[[ "$1" == "--force" || "$1" == "-f" ]] && FORCE=true

# ============================================================
# 检测操作系统
# ============================================================
detect_os() {
    case "$(uname -s)" in
        Darwin)  OS="macos" ;;
        Linux)   OS="linux" ;;
        MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
        *) echo "❌ 不支持的操作系统: $(uname -s)"; exit 1 ;;
    esac
}

# ============================================================
# 检测Resolve安装状态
# ============================================================
detect_resolve() {
    if [[ "$OS" == "macos" ]]; then
        INSTALL_BASE="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit"
    elif [[ "$OS" == "linux" ]]; then
        INSTALL_BASE="$HOME/.local/share/DaVinciResolve/Fusion/Scripts/Edit"
    else
        INSTALL_BASE="$APPDATA/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Edit"
    fi

    INSTALL_DIR="$INSTALL_BASE/$PLUGIN_NAME"

    if [ ! -d "$INSTALL_BASE" ]; then
        echo "⚠️  未找到 DaVinci Resolve 脚本目录:"
        echo "   $INSTALL_BASE"
        echo ""
        echo "   请确保已安装 DaVinci Resolve 并至少运行过一次。"
        echo "   如果已安装，请手动指定路径。"
        echo ""
        read -p "   是否手动输入安装路径? (y/N): " manual
        if [[ "$manual" =~ ^[Yy]$ ]]; then
            read -p "   请输入安装路径: " INSTALL_BASE
            INSTALL_DIR="$INSTALL_BASE/$PLUGIN_NAME"
        else
            exit 1
        fi
    fi
}

# ============================================================
# 检测FFmpeg
# ============================================================
check_ffmpeg() {
    echo ""
    echo "🔍 检查 FFmpeg..."
    if command -v ffmpeg &>/dev/null; then
        local ver=$(ffmpeg -version 2>&1 | head -1)
        echo "   ✅ FFmpeg 已安装: $ver"

        # 检查 blackdetect 滤镜
        if ffmpeg -filters 2>&1 | grep -q blackdetect; then
            echo "   ✅ blackdetect 滤镜可用"
        else
            echo "   ⚠️  blackdetect 滤镜不可用，请升级 FFmpeg"
        fi
    else
        echo "   ❌ FFmpeg 未安装"
        echo ""
        echo "   请先安装 FFmpeg:"
        if [[ "$OS" == "macos" ]]; then
            echo "     brew install ffmpeg"
        elif [[ "$OS" == "linux" ]]; then
            echo "     Ubuntu/Debian: sudo apt install ffmpeg"
            echo "     CentOS/RHEL:   sudo yum install ffmpeg"
            echo "     Arch:          sudo pacman -S ffmpeg"
        fi
    fi
    echo ""
}

# ============================================================
# 安装文件
# ============================================================
install_files() {
    echo "📦 安装文件到: $INSTALL_DIR"

    if [ -d "$INSTALL_DIR" ]; then
        if $FORCE; then
            echo "   🔄 强制覆盖已存在的安装..."
            rm -rf "$INSTALL_DIR"
        else
            echo "   ⚠️  目录已存在，使用 --force 强制覆盖安装"
            exit 1
        fi
    fi

    # 创建目标目录
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR/modules"

    # 复制所有必需的Lua文件
    cp "$PROJECT_DIR/black_frame_detector.lua" "$INSTALL_DIR/"

    # 复制模块目录
    cp "$PROJECT_DIR/modules/config.lua" "$INSTALL_DIR/modules/"
    cp "$PROJECT_DIR/modules/version_compat.lua" "$INSTALL_DIR/modules/"
    cp "$PROJECT_DIR/modules/ffmpeg_runner.lua" "$INSTALL_DIR/modules/"
    cp "$PROJECT_DIR/modules/black_frame_analyzer.lua" "$INSTALL_DIR/modules/"
    cp "$PROJECT_DIR/modules/marker_manager.lua" "$INSTALL_DIR/modules/"
    cp "$PROJECT_DIR/modules/ui_bridge.lua" "$INSTALL_DIR/modules/"
    cp "$PROJECT_DIR/modules/report_generator.lua" "$INSTALL_DIR/modules/"

    # 复制README（可选）
    if [ -f "$PROJECT_DIR/README.md" ]; then
        cp "$PROJECT_DIR/README.md" "$INSTALL_DIR/"
    fi

    echo "   ✅ 文件复制完成"
}

# ============================================================
# 验证安装
# ============================================================
verify_install() {
    echo ""
    echo "🔍 验证安装..."

    local files=(
        "black_frame_detector.lua"
        "modules/config.lua"
        "modules/version_compat.lua"
        "modules/ffmpeg_runner.lua"
        "modules/black_frame_analyzer.lua"
        "modules/marker_manager.lua"
        "modules/ui_bridge.lua"
        "modules/report_generator.lua"
    )

    local all_ok=true
    for f in "${files[@]}"; do
        if [ -f "$INSTALL_DIR/$f" ]; then
            echo "   ✅ $f"
        else
            echo "   ❌ $f - 缺失"
            all_ok=false
        fi
    done

    if $all_ok; then
        echo ""
        echo "============================================"
        echo "  ✅ 安装成功!"
        echo "============================================"
        echo ""
        echo "  安装路径: $INSTALL_DIR"
        echo ""
        echo "  使用方法:"
        echo "    1. 启动 DaVinci Resolve"
        echo "    2. 打开一个项目和时间线"
        echo "    3. 菜单栏 → 工作区 → 脚本 → $PLUGIN_NAME"
        echo "    (或在 Edit/Fusion 页面的 工作区 → 脚本 菜单)"
        echo ""
        echo "  卸载方法:"
        echo "    cd $(dirname "$SCRIPT_DIR") && ./install/uninstall.sh"
        echo ""
    else
        echo ""
        echo "❌ 安装验证失败，部分文件缺失"
        exit 1
    fi
}

# ============================================================
# 主流程
# ============================================================
echo "============================================"
echo "  黑帧夹帧检测插件 安装程序 v1.0.0"
echo "  兼容 DaVinci Resolve 17/18/19/20"
echo "============================================"

detect_os
echo "  操作系统: $OS"
detect_resolve
check_ffmpeg
install_files
verify_install
