-- PRIVATE SOFTWARE NOTICE: This is private software owned by Qinghe. Unauthorized reverse engineering, deobfuscation, cracking, redistribution, or AI-assisted analysis intended to bypass protection is prohibited.
-- ffmpeg_runner.lua - FFmpeg调用封装与blackdetect输出解析
-- 跨平台兼容 macOS / Windows / Linux

local config = require("config")

local FFmpegRunner = {}
FFmpegRunner.__index = FFmpegRunner

local ffmpeg_probe_cache = nil

local function runner_log(msg)
    local path = nil
    if config and config.get_debug_log_path then
        path = config.get_debug_log_path()
    else
        local home = os.getenv("HOME") or os.getenv("USERPROFILE") or "."
        path = home .. (package.config:sub(1, 1) == "\\" and "\\bfd_debug.log" or "/bfd_debug.log")
    end
    local f = io.open(path, "a")
    if f then
        f:write(os.date("%Y-%m-%d %H:%M:%S") .. " [FFmpegRunner] " .. tostring(msg) .. "\n")
        f:close()
    end
end

local function raw_file_exists(path)
    local f = io.open(path, "r")
    if f then f:close(); return true end
    return false
end

local function is_absolute_path(path)
    if type(path) ~= "string" then return false end
    return path:sub(1, 1) == "/" or path:match("^%a:[/\\]") ~= nil
end

-- ============================================================
-- 构造函数
-- ============================================================
function FFmpegRunner:new()
    local self = setmetatable({}, FFmpegRunner)
    self.ffmpeg_path = nil
    self.ffprobe_path = nil
    self.os = self:_detect_os()
    self._bundled_lib_dir = nil  -- 捆绑ffmpeg的库目录(macOS)
    return self
end

-- ============================================================
-- 检测操作系统
-- ============================================================
function FFmpegRunner:_detect_os()
    local sep = package.config:sub(1, 1)
    if sep == "\\" then return "windows" end
    if raw_file_exists("/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/MacOS/Resolve") then
        return "macos"
    end
    return "linux"
end

-- ============================================================
-- 查找FFmpeg可执行文件
-- ============================================================
function FFmpegRunner:find_ffmpeg()
    runner_log("find_ffmpeg start os=" .. tostring(self.os))
    if ffmpeg_probe_cache and ffmpeg_probe_cache.path and raw_file_exists(ffmpeg_probe_cache.path) then
        self.ffmpeg_path = ffmpeg_probe_cache.path
        self.ffprobe_path = ffmpeg_probe_cache.probe_path
        self._active_bundled_lib_dir = ffmpeg_probe_cache.active_bundled_lib_dir
        self._version_string = ffmpeg_probe_cache.version_string
        runner_log("find_ffmpeg cache OK: " .. tostring(self.ffmpeg_path))
        return true
    end

    -- 1. macOS 先走系统/绝对路径。随包 dylib 可能被 Gatekeeper 隔离，
    --    若先探测随包 ffmpeg，系统安全弹窗会让 Resolve 的 io.popen 卡死。
    if self.os ~= "macos" and self:_test_ffmpeg("ffmpeg") then
        runner_log("find_ffmpeg PATH OK")
        return true
    end

    -- 2. 遍历预设路径列表
    for _, candidate in ipairs(config.FFMPEG_SEARCH_PATHS) do
        if self.os == "macos" and is_absolute_path(candidate) and raw_file_exists(candidate) then
            self.ffmpeg_path = candidate
            self.ffprobe_path = candidate:gsub("ffmpeg([^\\/]*)$", "ffprobe%1")
            self._active_bundled_lib_dir = nil
            self._version_string = "ffmpeg (" .. candidate .. ")"
            ffmpeg_probe_cache = {
                path = self.ffmpeg_path,
                probe_path = self.ffprobe_path,
                active_bundled_lib_dir = nil,
                version_string = self._version_string,
            }
            runner_log("find_ffmpeg absolute path OK: " .. tostring(candidate))
            return true
        end
        if candidate ~= "ffmpeg" and self:_test_ffmpeg(candidate) then
            runner_log("find_ffmpeg candidate OK: " .. tostring(candidate))
            return true
        end
    end

    if self.os == "macos" and self:_test_ffmpeg("ffmpeg") then
        runner_log("find_ffmpeg PATH OK")
        return true
    end

    -- 3. 最后再使用插件捆绑的 ffmpeg（无需用户自行安装）。
    local bundled = self:_find_bundled_ffmpeg()
    if bundled and self:_test_ffmpeg(bundled) then
        runner_log("find_ffmpeg bundled OK: " .. tostring(bundled))
        return true
    end

    -- 4. Windows 额外尝试 winget / chocolatey / scoop 路径
    if self.os == "windows" then
        local extra_paths = {
            os.getenv("LOCALAPPDATA") and (os.getenv("LOCALAPPDATA") .. "\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\\ffmpeg.exe"),
            os.getenv("LOCALAPPDATA") and (os.getenv("LOCALAPPDATA") .. "\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\\ffmpeg.exe"),
            os.getenv("PROGRAMFILES") and (os.getenv("PROGRAMFILES") .. "\\ffmpeg\\bin\\ffmpeg.exe"),
            os.getenv("ProgramFiles(x86)") and (os.getenv("ProgramFiles(x86)") .. "\\ffmpeg\\bin\\ffmpeg.exe"),
            os.getenv("USERPROFILE") and (os.getenv("USERPROFILE") .. "\\scoop\\apps\\ffmpeg\\current\\ffmpeg.exe"),
        }
        for _, p in ipairs(extra_paths) do
            if p and self:_test_ffmpeg(p) then
                runner_log("find_ffmpeg windows extra OK: " .. tostring(p))
                return true
            end
        end
    end

    runner_log("find_ffmpeg failed")
    return false
end

-- ============================================================
-- 查找插件目录下捆绑的ffmpeg
-- ============================================================
function FFmpegRunner:_find_bundled_ffmpeg()
    -- 尝试从 debug.getinfo 解析脚本目录
    local script_path = debug.getinfo(1, "S").source:match("@(.+)[/\\]")

    -- 构建候选根目录列表
    local candidate_roots = {}
    if script_path then
        table.insert(candidate_roots, script_path)
    end

    -- 已知路径回退（debug.getinfo 在某些 LuaJIT 环境可能不返回 @path）
    if self.os == "windows" then
        local appdata = os.getenv("APPDATA") or ""
        local progdata = os.getenv("PROGRAMDATA") or "C:\\ProgramData"
        if appdata ~= "" then
            table.insert(candidate_roots, appdata .. "\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts\\Modules\\black_frame_detector")
            table.insert(candidate_roots, appdata .. "\\Blackmagic Design\\DaVinci Resolve\\Fusion\\Scripts\\Modules\\black_frame_detector")
        end
        table.insert(candidate_roots, progdata .. "\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts\\Modules\\black_frame_detector")
        table.insert(candidate_roots, progdata .. "\\Blackmagic Design\\DaVinci Resolve\\Fusion\\Scripts\\Modules\\black_frame_detector")
    elseif self.os == "macos" then
        local home = os.getenv("HOME") or ""
        if home ~= "" then
            table.insert(candidate_roots, home .. "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Modules/black_frame_detector")
        end
    end

    -- 去重后逐一探测
    local seen = {}
    for _, plugin_root in ipairs(candidate_roots) do
        if not seen[plugin_root] then
            seen[plugin_root] = true
            if self.os == "windows" then
                local candidate = plugin_root .. "\\ffmpeg\\windows\\ffmpeg.exe"
                if self:_file_exists(candidate) then return candidate end
                candidate = plugin_root .. "\\ffmpeg\\bin\\ffmpeg.exe"
                if self:_file_exists(candidate) then return candidate end
            elseif self.os == "macos" then
                local candidate = plugin_root .. "/ffmpeg/macos/ffmpeg"
                local lib_dir = plugin_root .. "/ffmpeg/macos/lib"
                if self:_file_exists(candidate) then
                    self._bundled_lib_dir = lib_dir
                    self._bundled_ffmpeg_path = candidate
                    return candidate
                end
            else
                local candidate = plugin_root .. "/ffmpeg/linux/ffmpeg"
                if self:_file_exists(candidate) then return candidate end
            end
        end
    end

    return nil
end

-- ============================================================
-- 检查文件是否存在
-- ============================================================
function FFmpegRunner:_file_exists(path)
    local f = io.open(path, "r")
    if f then f:close(); return true end
    return false
end

-- ============================================================
-- 测试指定路径的ffmpeg是否可用
-- ============================================================
function FFmpegRunner:_test_ffmpeg(path)
    runner_log("test_ffmpeg: " .. tostring(path))
    local cmd_prefix = ""
    -- 检测是否是捆绑的ffmpeg，自动添加库路径
    local is_bundled = self._bundled_ffmpeg_path and path == self._bundled_ffmpeg_path
    if is_bundled and self._bundled_lib_dir then
        cmd_prefix = 'DYLD_LIBRARY_PATH="' .. self._bundled_lib_dir .. '" '
    end
    local cmd = cmd_prefix .. self:_quote_path(path) .. " -version 2>&1"
    if self.os ~= "windows" then
        cmd = self:_with_timeout(cmd, 8)
    end
    local f = io.popen(self:_wrap_cmd(cmd), "r")
    if not f then
        runner_log("test_ffmpeg popen failed: " .. tostring(path))
        return false
    end
    local output = f:read("*a")
    f:close()
    if output and output:find("ffmpeg version") then
        self.ffmpeg_path = path
        local probe_path = path:gsub("ffmpeg([^\\/]*)$", "ffprobe%1")
        self.ffprobe_path = probe_path
        self._active_bundled_lib_dir = is_bundled and self._bundled_lib_dir or nil
        self._version_string = output:match("([^\r\n]+)") or "ffmpeg"
        ffmpeg_probe_cache = {
            path = path,
            probe_path = probe_path,
            active_bundled_lib_dir = self._active_bundled_lib_dir,
            version_string = self._version_string,
        }
        runner_log("test_ffmpeg OK: " .. tostring(path))
        return true
    end
    runner_log("test_ffmpeg no version: " .. tostring(path))
    return false
end

-- ============================================================
-- 构建完整ffmpeg命令（自动添加捆绑库路径前缀）
-- ============================================================
function FFmpegRunner:_build_cmd(args)
    if self._active_bundled_lib_dir then
        return 'DYLD_LIBRARY_PATH="' .. self._active_bundled_lib_dir .. '" ' .. self:_quote_path(self.ffmpeg_path) .. " " .. args
    end
    return self:_quote_path(self.ffmpeg_path) .. " " .. args
end

-- ============================================================
-- 路径安全引用（处理空格和特殊字符）
-- ============================================================
function FFmpegRunner:_quote_path(path)
    if not path then return "" end
    if path:find(" ") or path:find("&") or path:find("%(") then
        return '"' .. path .. '"'
    end
    return path
end

function FFmpegRunner:_wrap_cmd(cmd)
    if self.os == "windows" then
        return 'cmd /S /C "' .. cmd .. '"'
    end
    return cmd
end

function FFmpegRunner:_with_timeout(cmd, seconds)
    seconds = tonumber(seconds) or 8
    local safe = tostring(cmd):gsub("'", "'\\''")
    return "/bin/sh -c '" .. safe .. " & pid=$!; " ..
        "(sleep " .. tostring(seconds) .. "; kill $pid 2>/dev/null) & killer=$!; " ..
        "wait $pid; status=$?; kill $killer 2>/dev/null; exit $status'"
end

-- ============================================================
-- 检查 blackdetect 滤镜是否可用
-- ============================================================
function FFmpegRunner:check_blackdetect()
    if not self.ffmpeg_path then return false end
    if self._blackdetect_ok ~= nil then return self._blackdetect_ok end
    local cmd = self:_build_cmd("-filters 2>&1")
    local f = io.popen(self:_wrap_cmd(cmd), "r")
    if not f then return false end
    local output = f:read("*a")
    f:close()
    self._blackdetect_ok = output and output:find("blackdetect") ~= nil
    return self._blackdetect_ok
end

-- ============================================================
-- 获取视频文件信息（优先ffprobe JSON，回退ffmpeg -i stderr解析）
-- ============================================================
function FFmpegRunner:get_video_info(file_path)
    if not self.ffprobe_path then
        self.ffprobe_path = self.ffmpeg_path:gsub("ffmpeg([^\\/]*)$", "ffprobe%1")
    end

    -- 检查ffprobe是否可用，不可用则回退到ffmpeg -i
    if self.ffprobe_path and self:_file_exists(self.ffprobe_path) then
        return self:_get_video_info_ffprobe(file_path)
    else
        return self:_get_video_info_ffmpeg_fallback(file_path)
    end
end

-- ffprobe JSON方式获取视频信息
function FFmpegRunner:_get_video_info_ffprobe(file_path)
    local prefix = ""
    if self._bundled_lib_dir then
        prefix = 'DYLD_LIBRARY_PATH="' .. self._bundled_lib_dir .. '" '
    end

    local cmd = string.format(
        '%s%s -v quiet -print_format json -show_format -show_streams %s 2>&1',
        prefix,
        self:_quote_path(self.ffprobe_path),
        self:_quote_path(file_path)
    )

    local f = io.popen(self:_wrap_cmd(cmd), "r")
    if not f then return nil end
    local output = f:read("*a")
    f:close()

    local info = { duration = 0, fps = 25, width = 1920, height = 1080, codec = "unknown" }

    local duration_str = output:match('"duration"%s*:%s*"([%d%.]+)"')
    if duration_str then
        info.duration = tonumber(duration_str)
    end

    local num, den = output:match('"r_frame_rate"%s*:%s*"(%d+)/(%d+)"')
    if num and den then
        info.fps = tonumber(num) / tonumber(den)
    end

    local w = output:match('"width"%s*:%s*(%d+)')
    if w then info.width = tonumber(w) end
    local h = output:match('"height"%s*:%s*(%d+)')
    if h then info.height = tonumber(h) end

    local codec = output:match('"codec_name"%s*:%s*"([%w_]+)"')
    if codec then info.codec = codec end

    if info.duration == 0 then
        local alt_dur = output:match('"duration"%s*:%s*"([%d%.e%+]+)"')
        if alt_dur then
            info.duration = tonumber(alt_dur)
        end
    end

    return info
end

-- ffmpeg -i stderr解析方式获取视频信息（ffprobe不可用时的回退方案）
function FFmpegRunner:_get_video_info_ffmpeg_fallback(file_path)
    local prefix = ""
    if self._bundled_lib_dir then
        prefix = 'DYLD_LIBRARY_PATH="' .. self._bundled_lib_dir .. '" '
    end

    -- ffmpeg -i 输出信息到stderr，用 2>&1 重定向
    local cmd = string.format(
        '%s%s -i %s 2>&1',
        prefix,
        self:_quote_path(self.ffmpeg_path),
        self:_quote_path(file_path)
    )

    local f = io.popen(self:_wrap_cmd(cmd), "r")
    if not f then return nil end
    local output = f:read("*a")
    f:close()

    local info = { duration = 0, fps = 25, width = 1920, height = 1080, codec = "unknown" }

    -- 解析 Duration: 00:01:23.45
    local h, m, s = output:match("Duration:%s*(%d+):(%d+):([%d%.]+)")
    if h and m and s then
        info.duration = tonumber(h) * 3600 + tonumber(m) * 60 + tonumber(s)
    end

    -- 解析分辨率: 1920x1080
    local w, h2 = output:match("(%d+)x(%d+)")
    if w then info.width = tonumber(w) end
    if h2 then info.height = tonumber(h2) end

    -- 解析帧率: "23.98 fps" 或 "24 fps"
    local fps_val = output:match("(%d+%.?%d*)%s*fps")
    if fps_val then
        info.fps = tonumber(fps_val)
    end

    -- 解析编码: Video: h264
    local codec = output:match("Video:%s*(%w+)")
    if codec then info.codec = codec end

    return info
end

-- ============================================================
-- 运行blackdetect检测（核心方法）
-- ============================================================
function FFmpegRunner:detect_black_frames(file_path, params)
    if not self.ffmpeg_path then
        return nil, "FFmpeg 路径未设置，请先调用 find_ffmpeg()"
    end
    params = params or {}
    local d = params.min_duration or config.FFMPEG.MIN_BLACK_DURATION
    local pix_th = params.pix_th or config.FFMPEG.PIXEL_THRESHOLD
    local pic_th = params.pic_th or config.FFMPEG.PICTURE_RATIO
    local timeout = params.timeout or config.FFMPEG.TIMEOUT_PER_CLIP
    local clip_start_sec = params.clip_start_sec  -- 可选：限定分析起始时间
    local clip_duration_sec = params.clip_duration_sec  -- 可选：限定分析时长

    -- 构建blackdetect滤镜参数
    local filter = string.format(
        "blackdetect=d=%.4f:pix_th=%.4f:pic_th=%.2f",
        d, pix_th, pic_th
    )

    -- 构建范围限制参数（-ss/-to在前加快seek速度）
    local range_args = ""
    if clip_start_sec and clip_start_sec > 0 then
        range_args = range_args .. string.format(" -ss %.3f", clip_start_sec)
    end
    if clip_duration_sec and clip_duration_sec > 0 then
        range_args = range_args .. string.format(" -to %.3f", clip_duration_sec)
    end

    -- 完整命令：-an跳过音频加速处理，-f null - 不生成输出文件
    -- -timelimit 防止FFmpeg无限挂起（CPU时间限制，秒）
    local prefix = ""
    if self._bundled_lib_dir then
        prefix = 'DYLD_LIBRARY_PATH="' .. self._bundled_lib_dir .. '" '
    end
    local cmd = string.format(
        '%s%s -timelimit %d%s -i %s -vf "%s" -an -f null - 2>&1',
        prefix,
        self:_quote_path(self.ffmpeg_path),
        timeout,
        range_args,
        self:_quote_path(file_path),
        filter
    )

    local segments = {}
    local stderr_lines = {}

    local f = io.popen(self:_wrap_cmd(cmd), "r")
    if not f then
        return nil, "无法启动 FFmpeg 进程"
    end

    -- 读取输出（带简单超时控制）
    local start_time = os.time()
    for line in f:lines() do
        table.insert(stderr_lines, line)

        -- 解析 blackdetect 输出
        -- 格式: [blackdetect @ 0x...] black_start:10.0 black_end:12.5 black_duration:2.5
        local bstart, bend, bdur = line:match(
            "black_start:(%d+%.?%d*)%s+black_end:(%d+%.?%d*)%s+black_duration:(%d+%.?%d*)"
        )
        if bstart then
            local offset = clip_start_sec or 0
            table.insert(segments, {
                start = tonumber(bstart) + offset,
                end_ = tonumber(bend) + offset,
                duration = tonumber(bdur),
            })
        end

        -- 超时检查
        if os.time() - start_time > timeout then
            f:close()
            return segments, nil, "分析超时（" .. timeout .. "秒），返回已完成的结果"
        end
    end

    local ok, exit_type, exit_code = f:close()
    -- exit_code 非0可能表示被中断或文件问题
    -- 我们已有解析到的segments，所以即使非零退出也不太影响

    return segments, nil, nil
end

-- ============================================================
-- 估算源素材非黑内容框（只作为几何计算输入，不直接作为黑边报警）
-- ============================================================
function FFmpegRunner:detect_content_bounds(file_path, params)
    if not self.ffmpeg_path then
        return nil, "FFmpeg 路径未设置，请先调用 find_ffmpeg()"
    end
    params = params or {}
    local cfg = config.BLACK_BORDER_DETECTION or {}
    local limit = tonumber(params.black_border_limit or cfg.LIMIT or 0.02) or 0.02
    local sample_fps = tonumber(params.black_border_sample_fps or cfg.SAMPLE_FPS or 2) or 2
    local timeout = tonumber(params.timeout or config.FFMPEG.TIMEOUT_PER_CLIP) or config.FFMPEG.TIMEOUT_PER_CLIP
    local clip_start_sec = tonumber(params.clip_start_sec or 0) or 0
    local clip_duration_sec = tonumber(params.clip_duration_sec or 0) or 0

    local info = self:get_video_info(file_path) or {}
    local src_w = tonumber(info.width or 0) or 0
    local src_h = tonumber(info.height or 0) or 0
    if src_w <= 0 or src_h <= 0 then
        return nil, "无法读取视频分辨率"
    end

    local range_args = ""
    if clip_start_sec > 0 then
        range_args = range_args .. string.format(" -ss %.3f", clip_start_sec)
    end
    if clip_duration_sec > 0 then
        range_args = range_args .. string.format(" -to %.3f", clip_duration_sec)
    end

    local filter = string.format("fps=%.3f,cropdetect=limit=%.4f:round=2:reset=1", sample_fps, limit)
    local prefix = ""
    if self._active_bundled_lib_dir then
        prefix = 'DYLD_LIBRARY_PATH="' .. self._active_bundled_lib_dir .. '" '
    end
    local cmd = string.format(
        '%s%s -timelimit %d%s -i %s -vf "%s" -an -f null - 2>&1',
        prefix,
        self:_quote_path(self.ffmpeg_path),
        timeout,
        range_args,
        self:_quote_path(file_path),
        filter
    )

    local f = io.popen(self:_wrap_cmd(cmd), "r")
    if not f then
        return nil, "无法启动 FFmpeg 内容框探测进程"
    end

    local best = nil
    local samples = 0
    local start_time = os.time()
    for line in f:lines() do
        local cw, ch, cx, cy = line:match("crop=(%d+):(%d+):(%d+):(%d+)")
        if cw and ch and cx and cy then
            cw, ch, cx, cy = tonumber(cw), tonumber(ch), tonumber(cx), tonumber(cy)
            local area = (cw or 0) * (ch or 0)
            if area > 0 and (not best or area > best.area) then
                best = { x = cx or 0, y = cy or 0, w = cw or src_w, h = ch or src_h, area = area }
            end
            samples = samples + 1
        end
        if os.time() - start_time > timeout then
            f:close()
            break
        end
    end
    pcall(function() f:close() end)

    if not best then
        best = { x = 0, y = 0, w = src_w, h = src_h, area = src_w * src_h }
    end
    best.source_width = src_w
    best.source_height = src_h
    best.samples = samples
    return best, nil
end

-- ============================================================
-- 检测最终画面有效区域四边是否出现黑边
-- 用于复杂模式：不再依赖 cropdetect 的“最大内容框”，而是直接看边缘条带。
-- ============================================================
function FFmpegRunner:detect_edge_black_frames(file_path, active_rect, params)
    if not self.ffmpeg_path then
        return nil, "FFmpeg 路径未设置，请先调用 find_ffmpeg()"
    end
    params = params or {}
    active_rect = active_rect or {}
    local timeout = tonumber(params.timeout or 45) or 45
    local amount = tonumber(params.amount or 95) or 95
    local threshold = tonumber(params.threshold or 32) or 32
    local border_px = math.max(2, tonumber(params.black_border_px or 3) or 3)
    -- 黑边可能只有 3-5 像素；采样条不能过宽，否则会被正常画面稀释。
    local probe_px = math.max(2, math.min(24, border_px))

    local info = self:get_video_info(file_path) or {}
    local src_w = tonumber(info.width or active_rect.w or 0) or 0
    local src_h = tonumber(info.height or active_rect.h or 0) or 0
    if src_w <= 0 or src_h <= 0 then
        return nil, "无法读取视频分辨率"
    end

    local ax = math.max(0, math.floor(tonumber(active_rect.x or 0) or 0))
    local ay = math.max(0, math.floor(tonumber(active_rect.y or 0) or 0))
    local aw = math.max(1, math.floor(tonumber(active_rect.w or src_w) or src_w))
    local ah = math.max(1, math.floor(tonumber(active_rect.h or src_h) or src_h))
    if ax + aw > src_w then aw = src_w - ax end
    if ay + ah > src_h then ah = src_h - ay end
    if aw <= 1 or ah <= 1 then
        return nil, "有效画面区域过小"
    end
    probe_px = math.max(2, math.min(probe_px, math.floor(math.min(aw, ah) / 2)))

    local crops = {
        { side = "left", x = ax, y = ay, w = probe_px, h = ah },
        { side = "right", x = ax + aw - probe_px, y = ay, w = probe_px, h = ah },
        { side = "top", x = ax, y = ay, w = aw, h = probe_px },
        { side = "bottom", x = ax, y = ay + ah - probe_px, w = aw, h = probe_px },
    }
    local prefix = ""
    if self._active_bundled_lib_dir then
        prefix = 'DYLD_LIBRARY_PATH="' .. self._active_bundled_lib_dir .. '" '
    end

    local hits = {}
    for _, crop in ipairs(crops) do
        local filter = string.format(
            "crop=%d:%d:%d:%d,blackframe=amount=%.2f:threshold=%.2f",
            crop.w, crop.h, crop.x, crop.y, amount, threshold
        )
        local cmd = string.format(
            '%s%s -timelimit %d -i %s -vf "%s" -an -f null - 2>&1',
            prefix,
            self:_quote_path(self.ffmpeg_path),
            timeout,
            self:_quote_path(file_path),
            filter
        )
        local f = io.popen(self:_wrap_cmd(cmd), "r")
        if f then
            local start_time = os.time()
            for line in f:lines() do
                local frame, pblack = line:match("frame:%s*(%d+)%s+pblack:%s*([%d%.]+)")
                if not frame then
                    frame, pblack = line:match("frame:(%d+)%s+pblack:([%d%.]+)")
                end
                if frame and pblack then
                    table.insert(hits, {
                        side = crop.side,
                        frame = tonumber(frame) or 0,
                        pblack = tonumber(pblack) or 0,
                        width = crop.w,
                        height = crop.h,
                    })
                    break
                end
                if os.time() - start_time > timeout then
                    break
                end
            end
            pcall(function() f:close() end)
        end
    end
    table.sort(hits, function(a, b)
        if (a.frame or 0) == (b.frame or 0) then
            return tostring(a.side) < tostring(b.side)
        end
        return (a.frame or 0) < (b.frame or 0)
    end)
    return hits, nil
end

-- ============================================================
-- 成片模式：合并所有片段，一次blackdetect分析
-- segment_list: {{file_path, start_sec, duration_sec}, ...}
-- 返回: segments, error  (segments为{{start, end_, duration}, ...}数组，时间从0开始连续)
-- ============================================================
function FFmpegRunner:detect_black_frames_concat(segment_list, params)
    if not self.ffmpeg_path then
        return nil, "FFmpeg 路径未设置"
    end
    if not segment_list or #segment_list == 0 then
        return {}, nil
    end

    params = params or {}
    local d = params.min_duration or config.FFMPEG.MIN_BLACK_DURATION
    local pix_th = params.pix_th or config.FFMPEG.PIXEL_THRESHOLD
    local pic_th = params.pic_th or config.FFMPEG.PICTURE_RATIO
    local timeout = params.timeout or config.FFMPEG.TIMEOUT_PER_CLIP

    -- 构建FFmpeg concat输入文件列表（转义路径中的单引号）
    local concat_lines = {}
    for _, seg in ipairs(segment_list) do
        if seg.duration_sec and seg.duration_sec > 0 then
            local safe_path = seg.file_path:gsub("'", "'\\''")
            table.insert(concat_lines, string.format("file '%s'", safe_path))
            table.insert(concat_lines, string.format("inpoint %.4f", seg.start_sec))
            table.insert(concat_lines, string.format("outpoint %.4f", seg.start_sec + seg.duration_sec))
        end
    end

    if #concat_lines == 0 then
        return {}, nil
    end

    -- 写入临时concat列表文件
    local tmpname = os.tmpname()
    if not tmpname then
        return nil, "无法生成临时文件名"
    end
    local list_path = tmpname .. "_bfd_concat.txt"
    local f = io.open(list_path, "w")
    if not f then
        return nil, "无法创建临时concat列表文件"
    end
    f:write(table.concat(concat_lines, "\n"))
    f:close()

    -- 构建命令
    local filter = string.format(
        "blackdetect=d=%.4f:pix_th=%.4f:pic_th=%.2f",
        d, pix_th, pic_th
    )

    local prefix = ""
    if self._bundled_lib_dir then
        prefix = 'DYLD_LIBRARY_PATH="' .. self._bundled_lib_dir .. '" '
    end

    local cmd = string.format(
        '%s%s -timelimit %d -f concat -safe 0 -i %s -vf "%s" -an -f null - 2>&1',
        prefix,
        self:_quote_path(self.ffmpeg_path),
        timeout,
        self:_quote_path(list_path),
        filter
    )

    local segments = {}
    local f2 = io.popen(self:_wrap_cmd(cmd), "r")
    if not f2 then
        os.remove(list_path)
        return nil, "无法启动 FFmpeg 进程"
    end

    local start_time = os.time()
    for line in f2:lines() do
        local bstart, bend, bdur = line:match(
            "black_start:(%d+%.?%d*)%s+black_end:(%d+%.?%d*)%s+black_duration:(%d+%.?%d*)"
        )
        if bstart then
            table.insert(segments, {
                start = tonumber(bstart),
                end_ = tonumber(bend),
                duration = tonumber(bdur),
            })
        end

        if os.time() - start_time > timeout * 3 then
            f2:close()
            os.remove(list_path)
            return segments, "分析超时，返回已完成的结果"
        end
    end

    f2:close()
    os.remove(list_path)

    return segments, nil
end

-- ============================================================
-- 渲染坏帧检测：entropy + signalstats + metadata 三合一采集
-- 一次FFmpeg调用获取每帧的熵值+信号统计数据
-- 滤镜链: entropy → signalstats → metadata=mode=print
-- 返回: {{frame=n, YAVG=v, BRNG=v, SATAVG=v, entropy=v}, ...}
-- ============================================================
function FFmpegRunner:parse_signalstats(file_path, params)
    if not self.ffmpeg_path then
        return nil, "FFmpeg 路径未设置"
    end
    params = params or {}
    local timeout = params.timeout or config.FFMPEG.TIMEOUT_PER_CLIP

    -- 滤镜链: entropy(帧熵值) → signalstats(信号统计) → metadata(打印到stderr)
    local filter = "entropy=mode=normal,signalstats,metadata=mode=print"
    local prefix = ""
    if self._bundled_lib_dir then
        prefix = 'DYLD_LIBRARY_PATH="' .. self._bundled_lib_dir .. '" '
    end
    local cmd = string.format(
        '%s%s -timelimit %d -i %s -vf "%s" -an -f null - 2>&1',
        prefix,
        self:_quote_path(self.ffmpeg_path),
        timeout,
        self:_quote_path(file_path),
        filter
    )

    local frames = {}
    local current_frame = nil
    local f = io.popen(self:_wrap_cmd(cmd), "r")
    if not f then
        return nil, "无法启动 signalstats FFmpeg 进程"
    end

    local start_time = os.time()
    for line in f:lines() do
        -- 解析帧头: "frame:0    pts:0       pts_time:0"
        local frame_num = line:match("frame:(%d+)")
        if frame_num then
            if current_frame then
                table.insert(frames, current_frame)
            end
            current_frame = { frame = tonumber(frame_num) }
        end

        if current_frame then
            -- 解析signalstats指标
            local yavg = line:match("lavfi%.signalstats%.YAVG=([%d%.%-]+)")
            if yavg then current_frame.YAVG = tonumber(yavg) end
            local brng = line:match("lavfi%.signalstats%.BRNG=([%d%.%-]+)")
            if brng then current_frame.BRNG = tonumber(brng) end
            local satavg = line:match("lavfi%.signalstats%.SATAVG=([%d%.%-]+)")
            if satavg then current_frame.SATAVG = tonumber(satavg) end
            local ydif = line:match("lavfi%.signalstats%.YDIF=([%d%.%-]+)")
            if ydif then current_frame.YDIF = tonumber(ydif) end
            local satdif = line:match("lavfi%.signalstats%.SATDIF=([%d%.%-]+)")
            if satdif then current_frame.SATDIF = tonumber(satdif) end

            -- 解析entropy值
            local ent = line:match("lavfi%.entropy%.normal%.entropy=([%d%.%-]+)")
            if ent then current_frame.entropy = tonumber(ent) end
        end

        -- 超时检查
        if os.time() - start_time > timeout * 3 then
            f:close()
            if current_frame then table.insert(frames, current_frame) end
            return frames, "signalstats 分析超时"
        end
    end
    f:close()

    if current_frame then
        table.insert(frames, current_frame)
    end

    return frames, nil
end

-- ============================================================
-- 采集每帧黑像素比例，用于复杂模式的场景候选二次验证
-- 返回: { [frame_index] = pblack_percent }
-- ============================================================
function FFmpegRunner:parse_blackframe_stats(file_path, params)
    if not self.ffmpeg_path then
        return nil, "FFmpeg 路径未设置"
    end
    params = params or {}
    local timeout = params.timeout or config.FFMPEG.TIMEOUT_PER_CLIP
    local threshold = params.threshold or 32
    local amount = params.amount or 1

    local filter = string.format("blackframe=amount=%d:threshold=%d", amount, threshold)
    local cmd = self:_build_cmd(string.format(
        '-timelimit %d -i %s -vf "%s" -an -f null - 2>&1',
        timeout,
        self:_quote_path(file_path),
        filter
    ))

    local stats = {}
    local f = io.popen(self:_wrap_cmd(cmd), "r")
    if not f then
        return nil, "无法启动 blackframe FFmpeg 进程"
    end

    local start_time = os.time()
    for line in f:lines() do
        local frame, pblack = line:match("frame:(%d+)%s+pblack:(%d+)")
        if frame and pblack then
            stats[tonumber(frame)] = tonumber(pblack)
        end
        if os.time() - start_time > timeout * 3 then
            f:close()
            return stats, "blackframe 分析超时"
        end
    end
    f:close()
    return stats, nil
end

-- 小窗口查找指定源时间后的第一个强场景切点。
-- 用于 Resolve GetLeftOffset 单位不稳定时，在源 FPS / 时间线 FPS 两种解释下确认边界后是否只露出极短镜头。
function FFmpegRunner:first_scene_cut_after(file_path, start_sec, params)
    if not file_path or file_path == "" then return nil, "无效文件路径" end
    params = params or {}
    if not self.ffmpeg_path and not self:find_ffmpeg() then
        return nil, "未找到FFmpeg"
    end

    local timeout = params.timeout or 8
    local window_sec = params.window_sec or 0.35
    local threshold = params.scene_threshold or 0.18
    local start = math.max(0, tonumber(start_sec or 0) or 0)
    local duration = math.max(0.08, tonumber(window_sec) or 0.35)
    local filter = string.format("select='gt(scene,%.3f)',metadata=print", threshold)
    local cmd = self:_build_cmd(string.format(
        '-timelimit %d -ss %.6f -t %.6f -i %s -vf "%s" -an -f null - 2>&1',
        timeout,
        start,
        duration,
        self:_quote_path(file_path),
        filter
    ))

    local f = io.popen(self:_wrap_cmd(cmd), "r")
    if not f then
        return nil, "无法启动 scene FFmpeg 进程"
    end

    local first = nil
    local first_score = nil
    local start_time = os.time()
    for line in f:lines() do
        local pts_time = line:match("pts_time:([%d%.%-]+)")
        local score = line:match("lavfi%.scene_score=([%d%.%-]+)")
        if pts_time then
            local rel = tonumber(pts_time)
            if rel and rel >= 0 then
                first = rel
                if score then first_score = tonumber(score) end
                break
            end
        end
        if os.time() - start_time > timeout * 3 then
            f:close()
            return nil, "scene 分析超时"
        end
    end
    f:close()

    if first then
        return {
            relative_sec = first,
            absolute_sec = start + first,
            score = first_score,
        }, nil
    end
    return nil, nil
end

-- ============================================================
-- 复合/Fusion内部短镜头检测
-- 使用FFmpeg scene切点探测，找两个切点之间只有1-3帧的最终画面短镜头。
-- 适合“复合片段/上下层漏出几帧别的画面”的夹帧，不依赖黑帧阈值。
-- ============================================================
function FFmpegRunner:detect_short_scene_segments(file_path, params)
    if not self.ffmpeg_path then
        return nil, "FFmpeg 路径未设置"
    end
    params = params or {}
    local fps = params.fps or 25
    local timeout = params.timeout or config.FFMPEG.TIMEOUT_PER_CLIP
    local threshold = params.scene_threshold or 0.20
    local min_frame = params.min_frame or 1
    local max_frame = params.max_frame
    local max_span = params.max_span or 3

    local filter = string.format("select='gt(scene,%.3f)',showinfo", threshold)
    local cmd = self:_build_cmd(string.format(
        '-timelimit %d -i %s -vf "%s" -an -f null - 2>&1',
        timeout,
        self:_quote_path(file_path),
        filter
    ))

    local cuts = {}
    local f = io.popen(self:_wrap_cmd(cmd), "r")
    if not f then
        return nil, "无法启动 scene FFmpeg 进程"
    end

    local start_time = os.time()
    for line in f:lines() do
        local pts_time = line:match("pts_time:([%d%.%-]+)")
        if pts_time then
            local frame_index = math.floor((tonumber(pts_time) or 0) * fps + 0.5)
            if frame_index >= min_frame and (not max_frame or frame_index <= max_frame) then
                if #cuts == 0 or cuts[#cuts] ~= frame_index then
                    table.insert(cuts, frame_index)
                end
            end
        end
        if os.time() - start_time > timeout * 3 then
            f:close()
            return {}, "scene 分析超时"
        end
    end
    f:close()

    table.sort(cuts)
    local segments = {}
    local seen = {}
    for i = 1, #cuts - 1 do
        local a = cuts[i]
        local b = cuts[i + 1]
        local span = b - a
        if span >= 1 and span <= max_span and not seen[a] then
            table.insert(segments, {
                start = a / fps,
                end_ = b / fps,
                duration = span / fps,
                scene_cut_start_frame = a,
                scene_cut_end_frame = b,
                nested_short_scene = true,
                force_classification = "error",
                force_marker_name = "[BFD-MIX] 真实画面短镜头夹帧",
                force_note = string.format(
                    "复合/Fusion内部短镜头夹帧\n持续: %d帧\n内部切点: %d → %d\n来源: 复合/Fusion渲染精查\n判定: 渲染后的最终画面里出现极短镜头",
                    span, a, b
                ),
            })
            seen[a] = true
        end
    end

    return segments, nil
end

-- ============================================================
-- 批量检测（返回带片段信息的完整结果）
-- ============================================================
function FFmpegRunner:detect_clips(clips, params, progress_callback)
    local all_results = {}
    local errors = {}

    for i, clip in ipairs(clips) do
        local file_path = clip.file_path
        if not file_path then
            table.insert(errors, { index = i, name = clip.name or "未知", error = "无法获取文件路径" })
            goto continue
        end

        -- 进度回调
        if progress_callback then
            progress_callback(i, #clips, clip.name or file_path, "正在分析...")
        end

        local segments, err = self:detect_black_frames(file_path, params)

        if err then
            table.insert(errors, { index = i, name = clip.name or file_path, error = err })
        end

        if segments and #segments > 0 then
            table.insert(all_results, {
                clip = clip,
                segments = segments,
                file_path = file_path,
            })
        end

        ::continue::
    end

    return all_results, errors
end

-- ============================================================
-- 获取FFmpeg版本信息
-- ============================================================
function FFmpegRunner:get_version_string()
    if not self.ffmpeg_path then return "未找到" end
    if self._version_string then return self._version_string end
    local cmd = self:_build_cmd("-version 2>&1")
    local f = io.popen(self:_wrap_cmd(cmd), "r")
    if not f then return "无法获取" end
    local first_line = f:read("*l")
    f:close()
    return first_line or "未知版本"
end

-- ============================================================
-- 获取安装建议（当FFmpeg未找到时）
-- ============================================================
function FFmpegRunner:get_install_hint()
    local hints = {
        macos = [[
FFmpeg 未安装。请执行以下命令安装：
  brew install ffmpeg

或从官网下载: https://ffmpeg.org/download.html]],
        windows = [[
FFmpeg 未安装。请通过以下方式安装：
  winget install ffmpeg

或从官网下载: https://ffmpeg.org/download.html
下载后将 ffmpeg.exe 所在目录添加到系统 PATH 环境变量]],
        linux = [[
FFmpeg 未安装。请执行以下命令安装：
  Ubuntu/Debian: sudo apt install ffmpeg
  CentOS/RHEL:   sudo yum install ffmpeg
  Arch:          sudo pacman -S ffmpeg

或从官网下载: https://ffmpeg.org/download.html]],
    }
    return hints[self.os] or hints.linux
end

return FFmpegRunner
