-- config.lua - 清何黑帧夹帧检测小工具 全局配置
-- 版本: v1.9.104

local config = {}

-- ============================================================
-- 插件元信息
-- ============================================================
config.PLUGIN_NAME = "清何黑帧夹帧检测小工具"
config.PLUGIN_VERSION = "1.9.104"
config.PLUGIN_AUTHOR = "qinghe"
config.MARKER_PREFIX = "[BFD]"  -- Black Frame Detection 标记前缀

config.WATERMARK = {
    product = "QH-BFD",
    owner = "清何",
    channel = "private",
    schema = "wm-20260603",
}

function config.get_watermark_label()
    return string.format("%s:%s:%s:v%s",
        config.WATERMARK.product,
        config.WATERMARK.owner,
        config.WATERMARK.schema,
        config.PLUGIN_VERSION
    )
end

function config.build_watermark_payload(record, frame, name)
    record = record or {}
    return {
        watermark = config.get_watermark_label(),
        product = config.WATERMARK.product,
        owner = config.WATERMARK.owner,
        schema = config.WATERMARK.schema,
        version = config.PLUGIN_VERSION,
        marker = tostring(name or record.marker_name or ""),
        classification = tostring(record.classification or ""),
        frame = tonumber(frame) or tonumber(record.timeline_start_frame) or 0,
    }
end

-- ============================================================
-- FFmpeg blackdetect 默认参数
-- ============================================================
config.FFMPEG = {
    -- 最小黑帧检测时长（秒），低于此值的黑帧不报告
    MIN_BLACK_DURATION = 0.04,   -- d参数兜底；UI/Lua会按实际时间线帧率换算帧数

    -- 黑色像素亮度阈值 (0.0-1.0)，值越小越严格
    PIXEL_THRESHOLD = 0.01,

    -- 画面中黑像素占比阈值 (0.0-1.0)
    PICTURE_RATIO = 0.95,

    -- 每个片段的 FFmpeg 分析超时时间（秒）
    TIMEOUT_PER_CLIP = 60,
}

-- ============================================================
-- 夹帧分类阈值
-- 支持两种模式：帧数模式（use_frames=true）和秒数模式
-- 用户可在UI中切换
-- ============================================================
config.CLASSIFICATION = {
    -- 是否使用帧数阈值（true=帧数, false=秒数）
    USE_FRAMES = true,

    -- 帧数模式阈值（当 USE_FRAMES=true 时使用）
    -- ≤此帧数为夹帧错误 (Red)
    STUCK_FRAMES = 3,        -- 默认 ≤3帧 = 夹帧错误

    -- ≤此帧数为可疑黑帧 (Yellow)，大于此值 = 场景转场 (Blue)
    SUSPECT_FRAMES = 12,     -- 默认 ≤12帧 = 可疑

    -- 秒数模式阈值（当 USE_FRAMES=false 时使用，作为fallback）
    STUCK_FRAME_THRESHOLD = 0.12,   -- 秒数模式兜底；帧数模式按实际时间线帧率换算
    SUSPECT_THRESHOLD = 0.50,       -- 秒数模式兜底；帧数模式按实际时间线帧率换算

    -- 超过此值的黑帧视为纯黑素材，不标记（单位：秒）
    IGNORE_ABOVE = 30.0,
}

-- ============================================================
-- 标记颜色定义
-- ============================================================
config.MARKER_COLORS = {
    ERROR   = "Red",      -- 夹帧错误
    SUSPECT = "Yellow",   -- 可疑黑帧
    SCENE   = "Blue",     -- 正常场景转场
    GAP     = "Purple",   -- 时间线空位（片段间隙）
    DUPLICATE_NEAR  = "Rose",    -- 近距重复（高嫌疑）
    DUPLICATE_FAR   = "Sand",    -- 远距重复（需确认）
    DUPLICATE_DISTANT = "Cyan",  -- 跨轨道/远距复用（提示）
    INFO    = "Cyan",     -- 信息性标记
    -- 透明度/合成检测
    OPACITY_HIDDEN   = "Mint",     -- 隐藏素材（与Red区分，避免和夹帧错误混淆）
    OPACITY_LOW      = "Cocoa",    -- 低透明度（与Rose区分）
    OPACITY_PARTIAL  = "Lavender", -- 部分透明（与Yellow区分）
    CLIP_DISABLED    = "Cyan",     -- 已禁用
    COMPOSITE_NONORMAL = "Green",  -- 非标准合成
    OVERLAY_STUCK     = "Pink",   -- 多轨道叠加夹帧(完全可见)
    OVERLAY_STUCK_SOFT = "Yellow", -- 多轨道叠加夹帧(半透明遮挡)
    CONTENT_DUP       = "Fuchsia", -- 帧指纹内容重复
    CORRUPT           = "Sky",     -- 渲染坏帧（ABC三方案结合）
}

-- 标记名称模板
config.MARKER_NAMES = {
    ERROR   = "[BFD-ERR] 夹帧错误",
    SUSPECT = "[BFD-SUS] 可疑黑帧",
    SCENE   = "[BFD-SCN] 场景转场",
    GAP     = "[BFD-GAP] 时间线空位",
    DUP_NEAR = "[BFD-DUP] 疑似误复制",
    DUP_FAR  = "[BFD-DUP] 远距重复",
    DUP_DISTANT = "[BFD-DUP] 远距复用(跨轨道)",
    -- 透明度/合成检测
    OPACITY_HIDDEN   = "[BFD-OPC] 隐藏素材(不透明度=0)",
    OPACITY_LOW      = "[BFD-OPC] 低透明度素材",
    OPACITY_PARTIAL  = "[BFD-OPC] 部分透明素材",
    CLIP_DISABLED    = "[BFD-DIS] 已禁用素材",
    COMPOSITE_NONORMAL = "[BFD-CMP] 非标准合成",
    OVERLAY_STUCK     = "[BFD-OVL] 夹帧(被上层遮挡)",
    OVERLAY_STUCK_SOFT = "[BFD-OVL] 夹帧(半透明遮挡)",
    CONTENT_DUP       = "[BFD-FP] 帧指纹内容重复",
    CORRUPT           = "[BFD-COR] 渲染坏帧",
}

-- ============================================================
-- 默认启用的标记类型（用户可在UI中修改）
-- ============================================================
config.DEFAULT_MARKER_TYPES = {
    error     = true,     -- 夹帧错误 - 默认启用
    suspect   = true,     -- 可疑黑帧 - 默认启用
    scene     = false,    -- 场景转场 - 默认关闭（太多会乱）
    gap       = true,     -- 时间线空位 - 默认启用
    duplicate = true,     -- 重复片段 - 默认启用
    opacity   = true,     -- 透明度检测 - 默认启用
}

-- ============================================================
-- 重复片段检测参数
-- ============================================================
config.DUPLICATE = {
    -- 是否启用重复检测
    ENABLED = true,

    -- 近距重复阈值（秒）：两个同源片段间距 ≤ 此值 → 标记为高嫌疑
    NEAR_THRESHOLD_SEC = 2.0,

    -- 远距重复阈值（秒）：间距 ≤ 此值 → 标记为需确认
    FAR_THRESHOLD_SEC = 120.0,

    -- 远距复用跳过条件：两个重复片段之间需同时满足
    -- 1. 间隔中有 ≥GAP_EMPTY_SEC 秒的连续空档（无镜头覆盖）
    -- 2. 总距离 > GAP_TOTAL_SEC 秒
    DISTANT_SKIP_EMPTY_SEC = 10,   -- 连续空档 ≥ 此值
    DISTANT_SKIP_TOTAL_SEC = 60,   -- 总间隔 > 此值

    -- 是否同时检测同名+同时长的素材（非同一文件但可能同内容）
    DETECT_SIMILAR = true,

    -- ========== 帧指纹内容重复检测 ==========
    -- 是否启用帧指纹比对（检测视频内部重复画面）
    CONTENT_DETECT_ENABLED = true,

    -- 采样间隔（帧数），默认每3帧采样一次
    -- 按实际时间线帧率换算，例如3帧@25fps≈0.12s，3帧@30fps≈0.1s
    CONTENT_SAMPLE_INTERVAL = 3,

    -- 指纹缩略图尺寸（像素），16x16用于分块均值哈希
    CONTENT_THUMB_SIZE = 16,

    -- 内容重复检测：帧对最小索引间隔（秒），仅用于跳过相邻帧，真正去重靠合并后重叠判断
    CONTENT_MIN_GAP_SEC = 0.5,
}

-- ============================================================
-- 渲染坏帧检测参数（ABC三方案结合，仅复杂模式）
-- A: signalstats信号统计离群值（YAVG/BRNG/SATAVG）
-- B: 帧间亮度突变（相邻帧YAVG差值超阈值）
-- C: 图像熵异常（高熵=花屏/马赛克/噪点）
-- 多数投票: ≥2/3方案认定异常 → 确认坏帧
-- ============================================================
config.CORRUPT_DETECTION = {
    -- 滑动窗口大小：前后各取N帧，窗口总大小 = 2*N + 1
    WINDOW_SIZE = 5,

    -- 离群值标准差阈值：偏离局部均值超过此倍数 → 异常
    -- 2.5: 复杂模式增强灵敏度，覆盖光流/OFX插件造成的细微异常
    SIGMA_THRESHOLD = 2.5,

    -- 最少方案数认定异常（多数投票）
    MIN_VOTES = 2,

    -- 场景切换保护帧数：距切换点N帧内跳过
    SCENE_CHANGE_GUARD = 2,

    -- 相邻坏帧合并间隔（秒）
    MERGE_GAP_SEC = 0.5,

    -- 快切区域过滤：窗口内场景切换点过多=正常快切，跳过检测
    FAST_CUT_WINDOW = 15,        -- 检查窗口（帧数，前后各15帧）
    FAST_CUT_MIN_SWITCHES = 3,   -- 窗口内≥3个切换点 → 快切区域，跳过

    -- 方案A指标: signalstats
    -- YAVG(平均亮度)/BRNG(亮度范围)/SATAVG(平均饱和度)
    -- YDIF(帧内亮度差异: 光流撕裂/扭曲)/SATDIF(帧内饱和度差异: 插件色块异常)
    METRICS_A = { "YAVG", "BRNG", "SATAVG", "YDIF", "SATDIF" },
}

-- ============================================================
-- 透明度检测参数（秒级时间线属性扫描，无需FFmpeg）
-- ============================================================
config.OPACITY_DETECTION = {
    -- 是否启用透明度/合成检测
    ENABLED = true,

    -- 透明度阈值：不透明度≤此值 = 完全隐藏 (Red标记)
    HIDDEN_THRESHOLD = 0,

    -- 0 < 不透明度 < 此值 = 低透明度 (Orange标记)
    LOW_OPACITY_THRESHOLD = 50,

    -- 低透明度 ≤ 不透明度 < 此值 = 部分透明 (Yellow标记)
    PARTIAL_OPACITY_THRESHOLD = 100,

    -- FFmpeg深度分析最低不透明度要求（低于此值跳过FFmpeg）
    MIN_OPACITY_FOR_FFMPEG = 100,

    -- 隐藏素材下层是否必须无内容才算黑帧（true=检查下层轨道）
    CHECK_LOWER_TRACKS = true,
}

-- ============================================================
-- 时间线空位检测参数
-- ============================================================
-- ============================================================
-- 成片模式（合并渲染分析）
-- 将时间线所有片段合并为一个连续流，一次FFmpeg分析
-- 适用于最终成片检测，速度显著快于逐文件分析
-- ============================================================
config.MERGE_MODE = {
    -- 是否默认启用成片模式
    ENABLED = true,
}

-- ============================================================
-- 时间线空位检测参数
-- ============================================================
config.GAP_DETECTION = {
    -- 是否检测时间线空位（片段之间的间隙）
    ENABLED = true,

    -- 容差帧数：空位判定时允许的误差范围（帧）
    TOLERANCE_FRAMES = 2,

    -- 超过此时长的空位视为"空白区域"(Cyan标记)，非夹帧问题
    MAX_GAP_MARK_SEC = 10.0,

    -- 超过此时长的空位不标记（纯空白，无关紧要）
    IGNORE_GAP_ABOVE_SEC = 60.0,
}

-- ============================================================
-- 多轨道叠加可见帧检测（方案B）
-- 计算每个片段被上层不透明轨道遮挡后的"实际可见帧数"
-- 可见帧数 ≤ 夹帧阈值 → 标记为叠加夹帧
-- ============================================================
config.OVERLAY_STUCK_DETECTION = {
    -- 是否启用多轨道叠加夹帧检测
    ENABLED = true,

    -- 完全遮挡不透明度阈值 (0-100)：≥此值视为完全遮挡，下面内容不可见
    -- 默认95：考虑达芬奇渲染精度，95%不透明肉眼已无法察觉下方内容
    FULLY_OPAQUE_THRESHOLD = 95,

    -- 部分遮挡不透明度阈值 (0-100)：FULLY_OPAQUE > opacity ≥ 此值 → 半透明遮挡
    -- 半透明遮挡下夹帧可能可见也可能不可见，标记为可疑(yellow)而非错误(red)
    PARTIALLY_OPAQUE_THRESHOLD = 50,

    -- 是否将非Normal合成模式的片段视为不透明（默认false）
    NON_NORMAL_AS_OPAQUE = false,
}

-- ============================================================
-- 达芬奇标记导航提示
-- 由于达芬奇脚本API不直接支持时间线跳转，
-- 用户可借助标记系统导航：
--   ;  (分号)     → 跳转到下一个标记
--   Shift+;       → 跳转到上一个标记
--   Shift+F       → 打开时间码输入框，手动输入跳转
-- ============================================================
config.NAVIGATION_HINT = [[
时间线导航提示:
  达芬奇标记导航: 按 ; 跳转到下一个标记
  手动跳转: 按 Shift+F 输入时间码
]]

-- ============================================================
-- FFmpeg 多平台路径探测列表
-- ============================================================
config.FFMPEG_SEARCH_PATHS = {
    "ffmpeg",
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/usr/bin/ffmpeg",
    "C:\\ffmpeg\\bin\\ffmpeg.exe",
    "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
    "/usr/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
}

-- ============================================================
-- 跨平台工具函数
-- ============================================================
local function detect_platform()
    if package.config:sub(1,1) == "\\" then return "windows" end
    local f = io.popen("uname -s 2>/dev/null")
    if f then
        local u = f:read("*a"):gsub("%s+", "")
        f:close()
        if u == "Darwin" then return "macos" end
    end
    return "linux"
end

local PLATFORM = detect_platform()

function config.get_platform()
    return PLATFORM
end

function config.get_home()
    if PLATFORM == "windows" then
        return os.getenv("USERPROFILE") or os.getenv("HOMEDRIVE") .. (os.getenv("HOMEPATH") or "") or ""
    end
    return os.getenv("HOME") or os.getenv("USERPROFILE") or ""
end

function config.get_debug_log_path()
    return config.get_home() .. (PLATFORM == "windows" and "\\bfd_debug.log" or "/bfd_debug.log")
end

function config.get_io_cache_path()
    return config.get_home() .. (PLATFORM == "windows" and "\\.bfd_io_cache.lua" or "/.bfd_io_cache.lua")
end

function config.get_desktop_path()
    local home = config.get_home()
    if PLATFORM == "windows" then
        return home .. "\\Desktop"
    end
    return home .. "/Desktop"
end

function config.open_file(path)
    if not path then return end
    if PLATFORM == "windows" then
        os.execute('start "" "' .. path .. '"')
    elseif PLATFORM == "macos" then
        os.execute("open '" .. path .. "'")
    else
        os.execute("xdg-open '" .. path .. "' 2>/dev/null")
    end
end

function config.get_davinci_scripts_path()
    local home = config.get_home()
    if PLATFORM == "windows" then
        local appdata = os.getenv("APPDATA") or (home .. "\\AppData\\Roaming")
        return appdata .. "\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts"
    elseif PLATFORM == "macos" then
        return home .. "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts"
    else
        return home .. "/.local/share/DaVinciResolve/Fusion/Scripts"
    end
end

function config.get_module_dir()
    return config.get_davinci_scripts_path() .. (PLATFORM == "windows" and "\\Modules\\black_frame_detector" or "/Modules/black_frame_detector")
end

function config.get_path_sep()
    return PLATFORM == "windows" and "\\" or "/"
end

-- 轻量级调试日志（无需完整dlog，仅用于config自身错误）
function config._trace(msg)
    local f = io.open(config.get_debug_log_path(), "a")
    if f then f:write(os.date("%Y-%m-%d %H:%M:%S") .. " [CFG] " .. msg .. "\n"); f:close() end
end

-- ============================================================
-- 反馈通道
-- ============================================================
config.FEISHU_WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/c533d532-4041-4e58-abd5-6f9eb924d58c"

-- ============================================================
-- 输出设置
-- ============================================================
config.OUTPUT = {
    REPORT_DIR = nil,
    LOG_FILE = nil,
    HTML_REPORT = false,
    VERBOSE_CONSOLE = true,
}

-- ============================================================
-- 预设参数组合（以帧数表示，便于用户理解）
-- ============================================================
config.PRESETS = {
    high = {
        name = "高灵敏度 - 精检（1帧夹帧）",
        pix_th = 0.005,
        min_duration = 0.02,
        stuck_frames = 1,
        suspect_frames = 6,
    },
    normal = {
        name = "标准 - 推荐（3帧夹帧）",
        pix_th = 0.01,
        min_duration = 0.04,
        stuck_frames = 3,
        suspect_frames = 12,
    },
    low = {
        name = "低灵敏度 - 快速（5帧夹帧）",
        pix_th = 0.02,
        min_duration = 0.06,
        stuck_frames = 5,
        suspect_frames = 15,
    },
}

return config
