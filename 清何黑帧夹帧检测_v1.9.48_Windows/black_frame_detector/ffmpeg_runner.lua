-- ffmpeg_runner.lua - FFmpeg调用封装与blackdetect输出解析
-- 跨平台兼容 macOS / Windows / Linux

local config = require("config")

local FFmpegRunner = {}
FFmpegRunner.__index = FFmpegRunner

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
    local f = io.popen("uname -s 2>/dev/null")
    if f then
        local uname = f:read("*a"):gsub("%s+", "")
        f:close()
        if uname == "Darwin" then return "macos" end
    end
    return "linux"
end

-- ============================================================
-- 查找FFmpeg可执行文件
-- ============================================================
function FFmpegRunner:find_ffmpeg()
    -- 0. 优先使用插件捆绑的ffmpeg（无需用户自行安装）
    local bundled = self:_find_bundled_ffmpeg()
    if bundled and self:_test_ffmpeg(bundled) then
        return true
    end

    -- 1. 尝试PATH中的"ffmpeg"
    if self:_test_ffmpeg("ffmpeg") then
        return true
    end

    -- 2. 遍历预设路径列表
    for _, candidate in ipairs(config.FFMPEG_SEARCH_PATHS) do
        if candidate ~= "ffmpeg" and self:_test_ffmpeg(candidate) then
            return true
        end
    end

    -- 3. Windows 额外尝试 winget / chocolatey / scoop 路径
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
                return true
            end
        end
    end

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
    local cmd_prefix = ""
    -- 检测是否是捆绑的ffmpeg，自动添加库路径
    if self._bundled_lib_dir then
        cmd_prefix = 'DYLD_LIBRARY_PATH="' .. self._bundled_lib_dir .. '" '
    end
    local cmd = cmd_prefix .. self:_quote_path(path) .. " -version 2>&1"
    local f = io.popen(self:_wrap_cmd(cmd), "r")
    if not f then return false end
    local output = f:read("*a")
    f:close()
    if output and output:find("ffmpeg version") then
        self.ffmpeg_path = path
        local probe_path = path:gsub("ffmpeg([^\\/]*)$", "ffprobe%1")
        self.ffprobe_path = probe_path
        return true
    end
    return false
end

-- ============================================================
-- 构建完整ffmpeg命令（自动添加捆绑库路径前缀）
-- ============================================================
function FFmpegRunner:_build_cmd(args)
    if self._bundled_lib_dir then
        return 'DYLD_LIBRARY_PATH="' .. self._bundled_lib_dir .. '" ' .. self:_quote_path(self.ffmpeg_path) .. " " .. args
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

-- ============================================================
-- 检查 blackdetect 滤镜是否可用
-- ============================================================
function FFmpegRunner:check_blackdetect()
    if not self.ffmpeg_path then return false end
    local cmd = self:_build_cmd("-filters 2>&1")
    local f = io.popen(self:_wrap_cmd(cmd), "r")
    if not f then return false end
    local output = f:read("*a")
    f:close()
    return output and output:find("blackdetect") ~= nil
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

    local info = { duration = 0, fps = 24, width = 1920, height = 1080, codec = "unknown" }

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

    local info = { duration = 0, fps = 24, width = 1920, height = 1080, codec = "unknown" }

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
