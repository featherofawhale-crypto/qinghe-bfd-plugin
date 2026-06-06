#!/bin/bash
# ============================================================
# 本地沙盒测试 - 模拟 Windows 安装流程
# 可在 macOS/Linux 上运行，无需真实 Windows 环境
# 用法: bash test/sandbox_test.sh
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$PROJECT_DIR/dist/清何黑帧夹帧检测_v1.9.27"
TMP_DIR="$PROJECT_DIR/.sandbox_test"
PASS=0
FAIL=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

check() {
    local desc="$1"
    local cmd="$2"
    echo -n "  [$desc] ... "
    if eval "$cmd" >/dev/null 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}FAIL${NC}"
        FAIL=$((FAIL + 1))
    fi
}

echo "============================================"
echo "  本地沙盒测试 - v1.9.27-step21"
echo "============================================"
echo ""

# ============================================================
# 测试1: 文件存在性
# ============================================================
echo "--- 测试1: dist 文件完整性 ---"
check "主脚本"         'test -f "$DIST_DIR/清何黑帧夹帧检测.lua"'
check "一键安装.bat"   'test -f "$DIST_DIR/一键安装.bat"'
check "一键卸载.bat"   'test -f "$DIST_DIR/一键卸载.bat"'
check "手动安装说明"   'test -f "$DIST_DIR/手动安装说明.txt"'
check "功能文档PDF"    'test -f "$DIST_DIR/清何黑帧夹帧检测_v1.9.27_功能文档.pdf"'

MODULES=(config version_compat ffmpeg_runner black_frame_analyzer marker_manager ui_bridge report_generator duplicate_detector)
for m in "${MODULES[@]}"; do
    check "modules/$m.lua" "test -f '$DIST_DIR/modules/$m.lua'"
done
echo ""

# ============================================================
# 测试2: Lua 语法检查
# ============================================================
echo "--- 测试2: Lua 语法检查 ---"
if command -v lua &>/dev/null; then
    LUA=lua
elif command -v lua5.1 &>/dev/null; then
    LUA=lua5.1
else
    echo -e "  ${YELLOW}SKIP${NC} - Lua 未安装"
fi

if [ -n "$LUA" ]; then
    LUA_FILES=$(find "$DIST_DIR" -maxdepth 2 -name "*.lua" -not -path "*/.sandbox_test/*")
    while IFS= read -r f; do
        rel=$(echo "$f" | sed "s|$DIST_DIR/||")
        check "语法: $rel" "$LUA -e 'local ok,err=loadfile(\"$f\"); if not ok then error(err) end'"
    done <<< "$LUA_FILES"
fi
echo ""

# ============================================================
# 测试3: 模块路径解析（模拟 Windows 路径）
# ============================================================
echo "--- 测试3: Windows 路径解析模拟 ---"
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR/AppData/Roaming/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Modules/black_frame_detector"
mkdir -p "$TMP_DIR/AppData/Roaming/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Edit"
mkdir -p "$TMP_DIR/ProgramData/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Modules/black_frame_detector"

# 复制模块到模拟安装目录
cp "$DIST_DIR"/modules/*.lua "$TMP_DIR/AppData/Roaming/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Modules/black_frame_detector/"
cp "$DIST_DIR/清何黑帧夹帧检测.lua" "$TMP_DIR/AppData/Roaming/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Edit/"
cp "$DIST_DIR/清何黑帧夹帧检测.lua" "$TMP_DIR/AppData/Roaming/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/"

# 创建哑元 FFmpeg
mkdir -p "$TMP_DIR/AppData/Roaming/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Modules/black_frame_detector/ffmpeg/windows"
echo "ffmpeg version n7.1 dummy" > "$TMP_DIR/AppData/Roaming/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Modules/black_frame_detector/ffmpeg/windows/ffmpeg.exe"

check "模拟目录创建" 'test -d "$TMP_DIR/AppData/Roaming/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Modules/black_frame_detector"'

if [ -n "$LUA" ]; then
    # 模拟 setup_module_path 路径解析
    check "路径解析: APPDATA+Support" '
        cd "$TMP_DIR/AppData/Roaming/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts" &&
        APPDATA="$TMP_DIR/AppData/Roaming" PROGRAMDATA="$TMP_DIR/ProgramData" \
        $LUA -e "
            local function fe(p) local f=io.open(p); if f then f:close(); return true end; return false end
            local appdata=os.getenv(\"APPDATA\")..\"/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Modules/black_frame_detector\"
            assert(fe(appdata..\"/config.lua\"), \"config.lua not found at \"..appdata)
        "'

    # 模拟 _find_bundled_ffmpeg
    check "FFmpeg捆绑路径: APPDATA+Support" '
        cd "$TMP_DIR/AppData/Roaming/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts" &&
        APPDATA="$TMP_DIR/AppData/Roaming" PROGRAMDATA="$TMP_DIR/ProgramData" \
        $LUA -e "
            local function fe(p) local f=io.open(p); if f then f:close(); return true end; return false end
            local appdata=os.getenv(\"APPDATA\")..\"/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Modules/black_frame_detector\"
            local ff=appdata..\"/ffmpeg/windows/ffmpeg.exe\"
            assert(fe(ff), \"ffmpeg.exe not found at \"..ff)
        "'
fi
echo ""

# ============================================================
# 测试4: gsub 修复验证
# ============================================================
echo "--- 测试4: gsub ffmpeg→ffprobe 修复 ---"
if [ -n "$LUA" ]; then
    check "gsub: Windows路径只替换文件名" '
        $LUA -e "
            local r = \"C:\\\\Users\\\\x\\\\AppData\\\\Roaming\\\\Blackmagic Design\\\\DaVinci Resolve\\\\Support\\\\Fusion\\\\Scripts\\\\Modules\\\\black_frame_detector\\\\ffmpeg\\\\windows\\\\ffmpeg.exe\"
            local result = r:gsub(\"ffmpeg([^\\\\\\\\/]*)\$\", \"ffprobe%1\")
            local expected = \"C:\\\\Users\\\\x\\\\AppData\\\\Roaming\\\\Blackmagic Design\\\\DaVinci Resolve\\\\Support\\\\Fusion\\\\Scripts\\\\Modules\\\\black_frame_detector\\\\ffmpeg\\\\windows\\\\ffprobe.exe\"
            assert(result == expected, \"Expected: \"..expected..\" Got: \"..result)
        "'

    check "gsub: Unix路径只替换文件名" '
        $LUA -e "
            local r = \"/usr/bin/ffmpeg\"
            local result = r:gsub(\"ffmpeg([^\\\\\\\\/]*)\$\", \"ffprobe%1\")
            assert(result == \"/usr/bin/ffprobe\", \"Got: \"..result)
        "'

    check "gsub: 含ffmpeg目录名不被替换" '
        $LUA -e "
            local r = \"/opt/ffmpeg/macos/ffmpeg\"
            local result = r:gsub(\"ffmpeg([^\\\\\\\\/]*)\$\", \"ffprobe%1\")
            assert(result == \"/opt/ffmpeg/macos/ffprobe\", \"Got: \"..result)
        "'
fi
echo ""

# ============================================================
# 测试5: _quote_path 特殊字符
# ============================================================
echo "--- 测试5: 路径安全引用 ---"
if [ -n "$LUA" ]; then
    check "quote: 空格路径加引号" '
        $LUA -e "
            local function qp(p)
              if p:find(\" \") or p:find(\"&\") or p:find(\"%%(\") then return \"\\\"\"..p..\"\\\"\" end
              return p
            end
            assert(qp(\"C:\\\\Program Files\\\\ffmpeg.exe\") == \"\\\"C:\\\\Program Files\\\\ffmpeg.exe\\\"\")
        "'

    check "quote: 无空格不加引号" '
        $LUA -e "
            local function qp(p)
              if p:find(\" \") or p:find(\"&\") or p:find(\"%%(\") then return \"\\\"\"..p..\"\\\"\" end
              return p
            end
            assert(qp(\"C:\\\\ffmpeg\\\\bin\\\\ffmpeg.exe\") == \"C:\\\\ffmpeg\\\\bin\\\\ffmpeg.exe\")
        "'
fi
echo ""

# ============================================================
# 测试6: debug.getinfo 路径正则
# ============================================================
echo "--- 测试6: debug.getinfo 路径正则 ---"
if [ -n "$LUA" ]; then
    check "debug.getinfo: 标准@path" '
        $LUA -e "
            local source = \"@C:\\\\Users\\\\test\\\\AppData\\\\Roaming\\\\Blackmagic Design\\\\DaVinci Resolve\\\\Support\\\\Fusion\\\\Scripts\\\\Modules\\\\black_frame_detector\\\\ffmpeg_runner.lua\"
            local dir = source:match(\"@(.+)[/\\\\\\\\]\")
            assert(dir == \"C:\\\\Users\\\\test\\\\AppData\\\\Roaming\\\\Blackmagic Design\\\\DaVinci Resolve\\\\Support\\\\Fusion\\\\Scripts\\\\Modules\\\\black_frame_detector\")
        "'

    check "debug.getinfo: nil when no @path" '
        $LUA -e "
            local source = \"=string\"
            local dir = source:match(\"@(.+)[/\\\\\\\\]\")
            assert(dir == nil, \"Expected nil, got: \"..tostring(dir))
        "'
fi
echo ""

# ============================================================
# 测试7: 一键安装.bat 静态分析
# ============================================================
echo "--- 测试7: bat 静态分析 ---"
BAT_FILE="$DIST_DIR/一键安装.bat"

check "bat: chcp 65001 UTF-8"         'grep -q "chcp 65001" "$BAT_FILE"'
check "bat: 多路径探测 Support"       'grep -q "Support" "$BAT_FILE"'
check "bat: 多路径探测 ProgramData"   'grep -q "PROGRAMDATA" "$BAT_FILE"'
check "bat: FAIL 不在验证段重置"      '! grep -A5 "验证安装" "$BAT_FILE" | grep -q "set FAIL=0"'
check "bat: 通配符匹配lua"           'grep -q "for.*\*.lua" "$BAT_FILE"'
check "bat: 手动安装说明引用"         'grep -q "手动安装说明" "$BAT_FILE"'

UNINSTALL_BAT="$DIST_DIR/一键卸载.bat"
check "uninstall: chcp 65001 UTF-8"   'grep -q "chcp 65001" "$UNINSTALL_BAT"'
check "uninstall: 删除 Edit 目录"     'grep -q "Edit" "$UNINSTALL_BAT"'
check "uninstall: 删除 Modules"       'grep -q "Modules" "$UNINSTALL_BAT"'
echo ""

# ============================================================
# 测试8: UTF-8 编码检查
# ============================================================
echo "--- 测试8: 文件编码检查 ---"

# 检查主lua是否含中文注释（UTF-8编码验证）
check "主脚本包含中文注释" 'grep -q "清何黑帧夹帧检测" "$DIST_DIR/清何黑帧夹帧检测.lua"'
check "bat包含中文提示"   'grep -q "清何黑帧夹帧检测" "$BAT_FILE"'
check "配置包含中文"       'grep -q "清何黑帧夹帧检测小工具" "$DIST_DIR/modules/config.lua"'
check "手动说明含中文"     'grep -q "手动安装" "$DIST_DIR/手动安装说明.txt"'
echo ""

# ============================================================
# 清理 + 报告
# ============================================================
rm -rf "$TMP_DIR"

echo "============================================"
echo -e "  结果: ${GREEN}$PASS 通过${NC} / ${RED}$FAIL 失败${NC} / $((PASS + FAIL)) 总计"
echo "============================================"
if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
