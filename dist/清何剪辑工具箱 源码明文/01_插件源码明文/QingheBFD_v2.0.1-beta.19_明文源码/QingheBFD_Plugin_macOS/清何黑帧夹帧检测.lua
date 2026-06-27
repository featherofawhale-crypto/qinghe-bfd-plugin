-- PRIVATE SOFTWARE NOTICE: This is private software owned by Qinghe. Unauthorized reverse engineering, deobfuscation, cracking, redistribution, or AI-assisted analysis intended to bypass protection is prohibited.
-- 清何黑帧夹帧检测.lua - 达芬奇插件
-- 版本: v2.0.1-beta.20 测试版
-- 作者: qinghe
-- 兼容: DaVinci Resolve 17/18/19/20 + Studio/Free
--
-- 安装路径:
--   主脚本 → Scripts/Edit/清何黑帧夹帧检测.lua
--   模块   → Scripts/Modules/black_frame_detector/
--
-- 使用方式:
--   达芬奇 → 工作区 → 脚本 → 清何黑帧夹帧检测

-- ============================================================
-- 调试日志（写入文件，方便排查闪退问题）
-- ============================================================
-- DEBUG_LOG 在 config 加载后赋值
local DEBUG_LOG = nil
local function dlog(msg)
    if not DEBUG_LOG then
        -- config 未加载时的fallback
        local home = os.getenv("HOME") or os.getenv("USERPROFILE") or "."
        DEBUG_LOG = home .. (package.config:sub(1,1) == "\\" and "\\bfd_debug.log" or "/bfd_debug.log")
    end
    local f = io.open(DEBUG_LOG, "a")
    if f then
        f:write(os.date("%Y-%m-%d %H:%M:%S") .. " " .. tostring(msg) .. "\n")
        f:close()
    end
end

-- ============================================================
-- 文件存在检测
-- ============================================================
local function file_exists(path)
    local f = io.open(path, "r")
    if f then f:close(); return true end
    return false
end

local function snapshot_render_state(resolve_app, project)
    if not project then return nil end
    local state = {
        resolve = resolve_app,
        project = project,
        page = nil,
        timeline = nil,
        render_settings = nil,
        render_restore_settings = nil,
        render_format = nil,
        render_codec = nil,
    }
    pcall(function()
        if resolve_app and resolve_app.GetCurrentPage then
            state.page = resolve_app:GetCurrentPage()
        end
    end)
    pcall(function()
        if project.GetCurrentTimeline then
            state.timeline = project:GetCurrentTimeline()
        end
    end)
    pcall(function()
        if project.GetRenderSettings then
            state.render_settings = project:GetRenderSettings()
            if type(state.render_settings) == "table" then
                state.render_restore_settings = {}
                for _, key in ipairs({
                    "TargetDir", "CustomName", "SelectAllFrames", "MarkIn", "MarkOut",
                    "ExportVideo", "ExportAudio", "VideoQuality", "Quality",
                }) do
                    if state.render_settings[key] ~= nil then
                        state.render_restore_settings[key] = state.render_settings[key]
                    end
                end
                dlog("Render snapshot: TargetDir=" .. tostring(state.render_restore_settings.TargetDir)
                    .. " CustomName=" .. tostring(state.render_restore_settings.CustomName))
            end
        end
    end)
    if not state.render_restore_settings
        and project.AddRenderJob and project.GetRenderJobList and project.DeleteRenderJob then
        pcall(function()
            local snapshot_job = project:AddRenderJob()
            if not snapshot_job then return end
            pcall(function()
                local jobs = project:GetRenderJobList()
                if type(jobs) == "table" then
                    for _, job in ipairs(jobs) do
                        if type(job) == "table" and tostring(job.JobId) == tostring(snapshot_job) then
                            local custom_name = job.OutputFilename
                            if type(custom_name) == "string" then
                                custom_name = custom_name:gsub("%.[^%.]+$", "")
                            end
                            state.render_restore_settings = {
                                TargetDir = job.TargetDir,
                                CustomName = custom_name,
                                SelectAllFrames = false,
                                MarkIn = job.MarkIn,
                                MarkOut = job.MarkOut,
                                ExportVideo = job.IsExportVideo,
                                ExportAudio = job.IsExportAudio,
                            }
                            dlog("Render snapshot via temp job: TargetDir=" .. tostring(job.TargetDir)
                                .. " CustomName=" .. tostring(custom_name))
                            break
                        end
                    end
                end
            end)
            pcall(function() project:DeleteRenderJob(snapshot_job) end)
        end)
    end
    pcall(function()
        if project.GetCurrentRenderFormatAndCodec then
            local fmt, codec = project:GetCurrentRenderFormatAndCodec()
            if type(fmt) == "table" then
                state.render_format = fmt.format or fmt.Format or fmt[1]
                state.render_codec = fmt.codec or fmt.Codec or fmt[2]
            else
                state.render_format = fmt
                state.render_codec = codec
            end
        end
    end)
    pcall(function()
        if project.GetRenderMode then
            state.render_mode = project:GetRenderMode()
        end
    end)
    return state
end

local function restore_render_state(state)
    if type(state) ~= "table" then return end
    local project = state.project
    if project then
        if type(state.render_settings) == "table" then
            pcall(function() project:SetRenderSettings(state.render_settings) end)
        end
        if type(state.render_restore_settings) == "table" then
            pcall(function() project:SetRenderSettings(state.render_restore_settings) end)
            dlog("Render restore requested: TargetDir=" .. tostring(state.render_restore_settings.TargetDir)
                .. " CustomName=" .. tostring(state.render_restore_settings.CustomName))
        end
        if state.render_format and state.render_codec and project.SetCurrentRenderFormatAndCodec then
            pcall(function()
                project:SetCurrentRenderFormatAndCodec(state.render_format, state.render_codec)
            end)
        end
        if state.render_mode ~= nil and project.SetRenderMode then
            pcall(function() project:SetRenderMode(state.render_mode) end)
        end
        if state.timeline and project.SetCurrentTimeline then
            pcall(function() project:SetCurrentTimeline(state.timeline) end)
        end
    end
    if state.resolve and state.page and state.resolve.OpenPage then
        pcall(function() state.resolve:OpenPage(state.page) end)
    end
end

local function remove_complex_render_cache(cache_dir, sep)
    if not cache_dir or cache_dir == "" then return end
    os.remove(cache_dir .. sep .. "bfd_temp_render.mp4")
    os.remove(cache_dir .. sep .. "bfd_temp_render.mov")
end

local function ensure_dir(path, sep)
    if not path or path == "" then return end
    if sep == "\\" then
        os.execute('mkdir "' .. path .. '" >nul 2>nul')
    else
        os.execute('mkdir -p "' .. path .. '" >/dev/null 2>&1')
    end
end

local function trim_string(value)
    return tostring(value or ""):gsub("^%s+", ""):gsub("%s+$", "")
end

local function sanitize_file_stem(value)
    value = trim_string(value)
    if value == "" then value = "timeline" end
    value = value:gsub("[%s/\\:%*%?\"<>|]+", "_"):gsub("[^%w%._%-\128-\255]", "_")
    if #value > 60 then
        value = value:sub(1, 60)
    end
    return value
end

local function complex_render_meta_path(render_path)
    return tostring(render_path or "") .. ".qinghe_bfd_meta.lua"
end

local function write_complex_render_meta(render_path, meta)
    if not render_path or render_path == "" then return false end
    local f = io.open(complex_render_meta_path(render_path), "w")
    if not f then return false end
    f:write("-- Qinghe BFD complex render cache metadata\n")
    f:write("return {\n")
    for key, value in pairs(meta or {}) do
        if type(value) == "number" or type(value) == "boolean" then
            f:write(string.format("  %s = %s,\n", key, tostring(value)))
        else
            f:write(string.format("  %s = %q,\n", key, tostring(value or "")))
        end
    end
    f:write("}\n")
    f:close()
    return true
end

local function load_complex_render_meta(render_path)
    local meta_path = complex_render_meta_path(render_path)
    if not file_exists(meta_path) then
        return nil, "缺少清何缓存匹配文件: " .. meta_path
    end
    local chunk, err = loadfile(meta_path)
    if not chunk then return nil, err end
    local ok, meta = pcall(chunk)
    if not ok then return nil, meta end
    if type(meta) ~= "table" then return nil, "缓存匹配文件格式错误" end
    return meta, nil
end

local function get_timeline_unique_id(timeline)
    local uid = ""
    pcall(function()
        if timeline and timeline.GetUniqueId then
            uid = tostring(timeline:GetUniqueId() or "")
        end
    end)
    return uid
end

local function build_complex_render_meta(timeline, timeline_name, timeline_fps, io_in, io_out)
    return {
        meta_version = 1,
        plugin = "QingheBFD",
        timeline_name = tostring(timeline_name or ""),
        timeline_uid = get_timeline_unique_id(timeline),
        timeline_fps = tonumber(timeline_fps or 0) or 0,
        io_in = math.floor(tonumber(io_in or 0) or 0),
        io_out = math.floor(tonumber(io_out or 0) or 0),
        duration_frames = math.max(0, math.floor((tonumber(io_out or 0) or 0) - (tonumber(io_in or 0) or 0))),
        created_at = os.time(),
    }
end

local function validate_complex_render_meta(meta, expected)
    if type(meta) ~= "table" then return false, "缓存匹配文件为空" end
    if tostring(meta.plugin or "") ~= "QingheBFD" then return false, "不是清何工具箱保存的复杂模式缓存" end
    local meta_uid = tostring(meta.timeline_uid or "")
    local expected_uid = tostring(expected.timeline_uid or "")
    if meta_uid ~= "" and expected_uid ~= "" and meta_uid ~= expected_uid then
        return false, "缓存所属时间线与当前时间线不一致"
    end
    if meta_uid == "" or expected_uid == "" then
        if tostring(meta.timeline_name or "") ~= tostring(expected.timeline_name or "") then
            return false, "缓存所属时间线名称与当前时间线不一致"
        end
    end
    if math.floor(tonumber(meta.io_in or -1) or -1) ~= math.floor(tonumber(expected.io_in or -2) or -2) then
        return false, "缓存入点与当前入点不一致"
    end
    if math.floor(tonumber(meta.io_out or -1) or -1) ~= math.floor(tonumber(expected.io_out or -2) or -2) then
        return false, "缓存出点与当前出点不一致"
    end
    if math.abs((tonumber(meta.timeline_fps or 0) or 0) - (tonumber(expected.timeline_fps or 0) or 0)) > 0.01 then
        return false, "缓存帧率与当前时间线帧率不一致"
    end
    local meta_duration = math.floor(tonumber(meta.duration_frames or 0) or 0)
    local expected_duration = math.floor(tonumber(expected.duration_frames or 0) or 0)
    if math.abs(meta_duration - expected_duration) > 1 then
        return false, "缓存时长与当前IO范围不一致"
    end
    return true, nil
end

local function should_keep_complex_render(params)
    return params.keep_complex_cache == true or params.complex_render_keep_path == true
end

local function render_timeline_interval_for_analysis(resolve_app, project, timeline, cache_dir, sep, name, start_frame, end_frame, fps)
    if not resolve_app or not project or not timeline then
        return nil, "Resolve项目或时间线不可用"
    end
    start_frame = math.floor(tonumber(start_frame or 0) or 0)
    end_frame = math.floor(tonumber(end_frame or 0) or 0)
    if end_frame <= start_frame then
        return nil, "渲染区间为空"
    end

    ensure_dir(cache_dir, sep)
    name = tostring(name or "bfd_nested_render"):gsub("[^%w_%-]", "_")
    local mp4_path = cache_dir .. sep .. name .. ".mp4"
    local mov_path = cache_dir .. sep .. name .. ".mov"
    os.remove(mp4_path)
    os.remove(mov_path)

    local render_state = snapshot_render_state(resolve_app, project)
    local job_id = nil
    local out_path = mp4_path
    local ok, err = pcall(function()
        pcall(function() project:SetCurrentTimeline(timeline) end)

        local fmt_ok = pcall(function()
            project:SetCurrentRenderFormatAndCodec("mp4", "H264")
        end)
        if not fmt_ok then
            pcall(function()
                project:SetCurrentRenderFormatAndCodec("mov", "H264")
            end)
            out_path = mov_path
        end

        project:SetRenderSettings({
            CustomName = name,
            TargetDir = cache_dir,
            SelectAllFrames = false,
            MarkIn = start_frame,
            MarkOut = math.max(start_frame, end_frame - 1),
            ExportVideo = true,
            ExportAudio = false,
            VideoQuality = "Restrict to",
            Quality = 3500,
        })

        job_id = project:AddRenderJob()
        if not job_id then error("AddRenderJob返回nil") end
        local started = project:StartRendering({ job_id })
        if not started then error("StartRendering返回false") end

        local duration_sec = (end_frame - start_frame) / (fps or 25)
        local wait_max = math.max(45, math.min(420, math.ceil(duration_sec * 12) + 30))
        local waited = 0
        while waited < wait_max do
            local in_progress = true
            pcall(function() in_progress = project:IsRenderingInProgress() end)
            if not in_progress then break end

            local status = nil
            pcall(function() status = project:GetRenderJobStatus(job_id) end)
            if status and status.JobStatus == "Failed" then
                error("渲染任务失败")
            end

            local t = os.clock()
            while os.clock() - t < 0.5 do end
            waited = waited + 0.5
        end

        if waited >= wait_max then
            error("渲染超时(" .. tostring(wait_max) .. "秒)")
        end
    end)

    pcall(function()
        if job_id then project:DeleteRenderJob(job_id) end
    end)
    restore_render_state(render_state)

    if not ok then
        os.remove(mp4_path)
        os.remove(mov_path)
        return nil, tostring(err)
    end
    if file_exists(out_path) then return out_path, nil end
    if file_exists(mp4_path) then return mp4_path, nil end
    if file_exists(mov_path) then return mov_path, nil end
    return nil, "渲染文件不存在: " .. tostring(out_path)
end

local function read_text_file(path)
    local f = io.open(path, "r")
    if not f then return nil end
    local data = f:read("*a")
    f:close()
    return data
end

local function parse_fcpxml_seconds(value)
    if not value then return nil end
    value = tostring(value):gsub("^%s+", ""):gsub("%s+$", ""):gsub("s$", "")
    if value == "" then return nil end
    local num, den = value:match("^([%-%.%d]+)/([%.%d]+)$")
    if num and den then
        den = tonumber(den)
        if den and den ~= 0 then return (tonumber(num) or 0) / den end
    end
    return tonumber(value)
end

local function export_timeline_time_map_ranges(resolve_app, timeline, cache_dir, sep, fps)
    local ranges = {}
    if not resolve_app or not timeline or not timeline.Export then
        return ranges, "当前 Resolve API 不支持 Timeline.Export"
    end

    ensure_dir(cache_dir, sep)
    local export_path = cache_dir .. sep .. "bfd_retime_probe.fcpxml"
    os.remove(export_path)
    os.remove(export_path .. sep .. "Info.fcpxml")
    if sep == "\\" then
        os.execute('rmdir /s /q "' .. export_path .. '" >nul 2>nul')
    else
        os.execute('rm -rf "' .. export_path .. '" >/dev/null 2>&1')
    end

    local export_type = resolve_app.EXPORT_FCPXML_1_10
        or resolve_app.EXPORT_FCPXML_1_9
        or resolve_app.EXPORT_FCPXML_1_8
    local ok, exported = pcall(function()
        return timeline:Export(export_path, export_type, nil)
    end)
    if (not ok) or not exported then
        return ranges, "FCPXML导出失败"
    end

    local content = read_text_file(export_path)
        or read_text_file(export_path .. sep .. "Info.fcpxml")
    if not content then
        return ranges, "FCPXML文件不存在"
    end

    for block in content:gmatch("(<[%w%-]*clip[^>]->.-<timeMap.-</timeMap>.-</[%w%-]*clip>)") do
        local open_tag = block:match("^(<[^>]+>)") or ""
        local offset = open_tag:match('offset="([^"]+)"')
        local duration = open_tag:match('duration="([^"]+)"')
        local name = open_tag:match('name="([^"]+)"') or ""
        local start_sec = parse_fcpxml_seconds(offset)
        local dur_sec = parse_fcpxml_seconds(duration)
        if start_sec and dur_sec and dur_sec > 0 then
            local timepoint_count = 0
            for _ in block:gmatch("<timept%s") do timepoint_count = timepoint_count + 1 end
            local has_curve = block:match('interp="smooth') ~= nil or timepoint_count > 2
            table.insert(ranges, {
                start_frame = math.floor(start_sec * fps + 0.5),
                end_frame = math.floor((start_sec + dur_sec) * fps + 0.5),
                duration_frames = math.max(1, math.floor(dur_sec * fps + 0.5)),
                name = name,
                has_curve = has_curve,
                timepoint_count = timepoint_count,
            })
        end
    end

    return ranges, nil
end

local function annotate_retimed_clips_from_fcpxml(resolve_app, timeline, clips, cache_dir, sep, fps, start_offset)
    local ranges, err = export_timeline_time_map_ranges(resolve_app, timeline, cache_dir, sep, fps)
    if err then
        dlog("变速探针跳过: " .. tostring(err))
        return 0, err
    end
    local matched = 0
    start_offset = tonumber(start_offset or 0) or 0
    for _, range in ipairs(ranges or {}) do
        for _, clip in ipairs(clips or {}) do
            local cs = tonumber(clip.timeline_start_frame or 0) or 0
            local ce = cs + (tonumber(clip.source_duration_frames or 0) or 0)
            local candidates = { cs, cs - start_offset }
            for _, candidate in ipairs(candidates) do
                if math.abs(candidate - range.start_frame) <= 2 then
                    clip.has_timeline_retime = true
                    clip.retime_requires_visible_render = true
                    clip.retime_has_curve = range.has_curve
                    clip.retime_timepoint_count = range.timepoint_count
                    clip.retime_fcpxml_start_frame = range.start_frame
                    clip.retime_fcpxml_end_frame = range.end_frame
                    matched = matched + 1
                    goto matched_clip
                end
            end
            if range.start_frame < ce and range.end_frame > cs then
                clip.has_timeline_retime = true
                clip.retime_requires_visible_render = true
                clip.retime_has_curve = range.has_curve
                clip.retime_timepoint_count = range.timepoint_count
                clip.retime_fcpxml_start_frame = range.start_frame
                clip.retime_fcpxml_end_frame = range.end_frame
                matched = matched + 1
                goto matched_clip
            end
        end
        ::matched_clip::
    end
    if matched > 0 then
        dlog("变速探针: FCPXML timeMap命中 " .. tostring(matched) .. " 个片段")
        print(string.format("[BFD] 变速探针: 发现 %d 个变速片段，成片检测将按时间线可见画面分析", matched))
    end
    return matched, nil
end

-- 素材扩展名分类（非视频素材不应参与FFmpeg黑帧检测）
-- 视频文件：完整检测流程（FFmpeg + 夹帧 + 叠加）
local VIDEO_EXTENSIONS = {
    mov = true, mp4 = true, mxf = true, avi = true, mkv = true,
    mts = true, m2ts = true, r3d = true, braw = true, ari = true,
    arx = true, dng = true, cin = true, rmf = true, wmv = true,
    flv = true, m4v = true, mpg = true, mpeg = true, ts = true,
    webm = true, vob = true, m2v = true, dv = true, h264 = true,
    hevc = true, prores = true, ["3gp"] = true, ogv = true,
}
-- 静态图片（可能带Alpha通道）：跳过FFmpeg + 跳过夹帧检测，但参与多轨道叠加遮挡
local ALPHA_IMAGE_EXTENSIONS = {
    png = true, psd = true, tiff = true, tif = true, exr = true,
}
-- 静态图片（无通道）：跳过FFmpeg，但参与夹帧检测 + 多轨道叠加
local STILL_IMAGE_EXTENSIONS = {
    jpg = true, jpeg = true, bmp = true, gif = true, webp = true,
}

-- 返回素材类型: "video" / "still_image" / "alpha_image" / nil(非支持格式)
local function classify_media_type(path)
    if not path then return nil end
    local ext = path:match("%.([^%.]+)$")
    if not ext then return nil end
    local lower = ext:lower()
    if VIDEO_EXTENSIONS[lower] then return "video" end
    if ALPHA_IMAGE_EXTENSIONS[lower] then return "alpha_image" end
    if STILL_IMAGE_EXTENSIONS[lower] then return "still_image" end
    return nil
end

local function is_text_or_generator_label(value)
    local text = tostring(value or ""):lower()
    return text:match("text%+")
        or text:match("text")
        or text:match("title")
        or text:match("subtitle")
        or text:match("caption")
        or text:match("generator")
        or text:match("文本")
        or text:match("字幕")
        or text:match("标题")
        or text:match("生成器")
end

local function is_adjustment_layer_label(value)
    local text = tostring(value or ""):lower()
    return text:match("adjustment")
        or text:match("adjustment clip")
        or text:match("adjustment layer")
        or text:match("调整片段")
        or text:match("调整图层")
        or text:match("调节图层")
end

-- ============================================================
-- 模块路径设置（多重回退策略）
-- ============================================================
local BFD_MODULE_DIR = nil

local function setup_module_path()
    local home = os.getenv("HOME") or os.getenv("USERPROFILE")
    local sep = package.config:sub(1, 1)
    local is_win = (sep == "\\")

    -- 方案1: 已知安装路径（最可靠，不依赖 debug.getinfo）
    local known_paths = {}
    if is_win then
        local appdata = os.getenv("APPDATA") or (home and home .. "\\AppData\\Roaming")
        if appdata then
            table.insert(known_paths, appdata .. "\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts\\Modules\\black_frame_detector")
        end
    else
        if home then
            table.insert(known_paths, home .. "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Modules/black_frame_detector")
            table.insert(known_paths, home .. "/.local/share/DaVinciResolve/Fusion/Scripts/Modules/black_frame_detector")
        end
    end

    for _, p in ipairs(known_paths) do
        local fname = is_win and (p .. "\\config.lua") or (p .. "/config.lua")
        if file_exists(fname) then
            BFD_MODULE_DIR = p
            package.path = p .. (is_win and "\\?.lua;" or "/?.lua;") .. package.path
            dlog("模块路径(已知): " .. p)
            return true
        end
    end

    -- 方案2: debug.getinfo 动态解析
    local script_dir = debug.getinfo(1, "S").source:match("@(.+)[/\\]")
    dlog("debug.getinfo script_dir: " .. tostring(script_dir))

    if script_dir then
        local scripts_dir = script_dir:match("^(.+)[/\\][Ee]dit$") or script_dir
        local module_dir = scripts_dir .. (is_win and "\\Modules\\black_frame_detector" or "/Modules/black_frame_detector")
        local fname = is_win and (module_dir .. "\\config.lua") or (module_dir .. "/config.lua")
        if file_exists(fname) then
            BFD_MODULE_DIR = module_dir
            package.path = module_dir .. (is_win and "\\?.lua;" or "/?.lua;") .. package.path
            dlog("模块路径(动态): " .. module_dir)
            return true
        end
    end

    -- 方案3: 相对路径（脚本工作目录）
    BFD_MODULE_DIR = is_win and ".\\Modules\\black_frame_detector" or "./Modules/black_frame_detector"
    package.path = (is_win and ".\\Modules\\black_frame_detector\\?.lua;" or "./Modules/black_frame_detector/?.lua;") .. package.path
    dlog("模块路径(相对): " .. (is_win and ".\\Modules\\black_frame_detector\\" or "./Modules/black_frame_detector/"))
    return true
end

dlog("=== BFD v2.0.1-beta.20 启动 ===")
setup_module_path()

local MODULES_TO_RELOAD = {
    "config",
    "version_compat",
    "ffmpeg_runner",
    "black_frame_analyzer",
    "marker_manager",
    "ui_bridge",
    "progress_bridge",
    "report_generator",
    "duplicate_detector",
    "py_params_bridge",
}
for _, module_name in ipairs(MODULES_TO_RELOAD) do
    package.loaded[module_name] = nil
end

-- ============================================================
-- 安全加载模块（pcall 保护，避免静默崩溃）
-- ============================================================
local function safe_require(name)
    local ok, result = pcall(require, name)
    if not ok then
        dlog("ERROR require(" .. name .. "): " .. tostring(result))
        print("[BFD] 错误: 加载模块 " .. name .. " 失败: " .. tostring(result))
        return nil
    end
    return result
end

local config = safe_require("config")
if not config then dlog("FATAL: config 加载失败，退出"); return end
dlog("Watermark: " .. config.get_watermark_label())

local VersionCompat = safe_require("version_compat")
local FFmpegRunner = safe_require("ffmpeg_runner")
local Analyzer = safe_require("black_frame_analyzer")
local MarkerManager = safe_require("marker_manager")
local UIBridge = safe_require("ui_bridge")
local ProgressBridge = safe_require("progress_bridge")
local ReportGenerator = safe_require("report_generator")
local DuplicateDetector = safe_require("duplicate_detector")

local function append_unique_number(list, value, fps)
    if not value then return end
    local frame = math.floor(value * fps + 0.5)
    for _, existing in ipairs(list) do
        if math.abs(math.floor(existing * fps + 0.5) - frame) <= 1 then
            return
        end
    end
    table.insert(list, value)
end

local function source_fps_for_clip(ffmpeg, clip, timeline_fps)
    if ffmpeg and clip and clip.file_path and clip.file_path ~= "" then
        local ok, info = pcall(function() return ffmpeg:get_video_info(clip.file_path) end)
        if ok and info and tonumber(info.fps) and tonumber(info.fps) > 0 then
            clip.source_fps = tonumber(info.fps)
            return clip.source_fps
        end
    end
    if clip and tonumber(clip.source_fps) and tonumber(clip.source_fps) > 0 then
        return tonumber(clip.source_fps)
    end
    return timeline_fps
end

local function add_mixed_cut_record(records, seen, clip, key_suffix, source_start, source_end, tl_start, timeline_fps, scene_score, reason, visual_window_start, visual_window_end)
    local key = tostring(clip.file_path) .. ":" .. tostring(tl_start)
    if seen[key] then return end
    seen[key] = true
    table.insert(records, {
        clip = clip,
        segments = {{
            start = source_start,
            end_ = source_end,
            duration = math.max(1 / timeline_fps, source_end - source_start),
            timeline_frame = tl_start,
            is_mixed_cut = true,
            edge_visible = reason == "edge",
            final_visible_fragment = reason == "visible_fragment",
            single_scene_candidate = reason == "single_scene",
            scene_score = scene_score or 0,
            visual_window_start_frame = visual_window_start,
            visual_window_end_frame = visual_window_end,
        }},
        is_mixed_cut = true,
    })
end

local function detect_source_mixed_cuts(ffmpeg, ffmpeg_clips, all_clips, timeline_fps, params)
    local records = {}
    if not ffmpeg or not ffmpeg.ffmpeg_path then return records end
    -- 普通模式下，源内切点只能作为黑帧、短片段和遮挡夹帧的辅助证据；
    -- 不能因为勾选“夹帧错误”就把源素材里的正常镜头切换全部打成 BFD-MIX。
    local explicit_mixed_cut = params and (
        params.detect_mixed_cut == true
        or params.enable_timeline_mixed_cut == true
    )
    local implicit_internal_flash = (not explicit_mixed_cut)
        and params
        and params.marker_types
        and params.marker_types.error == true
    local mixed_cut_enabled = explicit_mixed_cut or implicit_internal_flash
    if not mixed_cut_enabled then
        return records
    end

    local stuck_frames = params.stuck_frames or config.CLASSIFICATION.STUCK_FRAMES
    local threshold = params.mixed_cut_scene_threshold or 0.04
    local internal_flash_score = params.mixed_cut_internal_flash_score or 0.16
    local edge_scene_score = params.mixed_cut_edge_scene_score or threshold
    local single_scene_score = params.mixed_cut_single_scene_score or math.max(threshold, 0.16)
    local timeout = params.mixed_cut_timeout or 12
    local max_duration_sec = params.mixed_cut_max_clip_sec or (implicit_internal_flash and 3600 or 180)
    -- 默认普通模式里的源内夹帧只服务于“混剪成片/长片段自带问题”。
    -- 时间线上很短的正常镜头变化，不能因为内部 scene cut 被当成夹帧。
    local implicit_min_duration_sec = tonumber(params.mixed_cut_implicit_min_clip_sec or 1) or 1
    local scanned, nested_skipped = 0, 0
    local seen = {}
    local overlay_config = config.OVERLAY_STUCK_DETECTION or {}
    local full_threshold = overlay_config.FULLY_OPAQUE_THRESHOLD or 95
    local boundary_threshold = params.mixed_cut_overlay_threshold or
        overlay_config.PARTIALLY_OPAQUE_THRESHOLD or full_threshold
    local clips_by_track = {}
    local max_track = 0
    for _, c in ipairs(all_clips or ffmpeg_clips or {}) do
        local t = c.track_index or 1
        if t > max_track then max_track = t end
        if not clips_by_track[t] then clips_by_track[t] = {} end
        table.insert(clips_by_track[t], c)
    end
    local function top_covering_clip_at(frame, target_clip)
        if not target_clip then return nil end
        local target_track = tonumber(target_clip.track_index or 1) or 1
        local best, best_track = nil, target_track
        for track = target_track + 1, max_track do
            local track_clips = clips_by_track[track]
            if track_clips then
                for _, other in ipairs(track_clips) do
                    local os = tonumber(other.timeline_start_frame or 0) or 0
                    local od = tonumber(other.source_duration_frames or 0) or 0
                    if od > 0
                        and frame >= os and frame < os + od
                        and other.is_enabled ~= false
                        and (other.opacity or 100) > 0
                        and Analyzer.is_fully_opaque(other, overlay_config, boundary_threshold)
                        and track >= best_track
                    then
                        best = other
                        best_track = track
                    end
                end
            end
        end
        return best
    end
    local function same_source_boundary_is_continuous(clip, boundary_frame, side)
        local cover = nil
        if side == "start" then
            cover = top_covering_clip_at(boundary_frame - 1, clip)
        else
            cover = top_covering_clip_at(boundary_frame, clip)
        end
        if not cover then return false end
        if tostring(cover.file_path or "") == "" or tostring(cover.file_path or "") ~= tostring(clip.file_path or "") then
            return false
        end
        local min_jump = tonumber(params.mixed_cut_overlay_min_source_jump or 48) or 48
        local clip_start = tonumber(clip.timeline_start_frame or 0) or 0
        local clip_left = tonumber(clip.left_offset or 0) or 0
        local cover_start = tonumber(cover.timeline_start_frame or 0) or 0
        local cover_left = tonumber(cover.left_offset or 0) or 0
        local clip_source_at_boundary = clip_left + (boundary_frame - clip_start)
        local cover_source_at_boundary = cover_left + (boundary_frame - cover_start)
        local jump = math.abs(clip_source_at_boundary - cover_source_at_boundary)
        return jump < min_jump
    end
    local filter_script_path = nil
    local cache_dir = nil
    do
        local sep = package.config:sub(1, 1)
        local home = os.getenv("USERPROFILE") or os.getenv("HOME") or "."
        cache_dir = home .. sep .. ".qinghe_bfd"
        local path = cache_dir .. sep .. "mixed_cut_scene_filter.txt"
        local f = io.open(path, "w")
        if f then
            f:write(string.format("select='gt(scene\\,%.3f)',metadata=print", threshold))
            f:close()
            filter_script_path = path
        end
    end

    for _, clip in ipairs(all_clips or ffmpeg_clips or {}) do
        if clip.is_enabled == false then goto continue_clip end
        if (clip.opacity or 100) <= 0 then goto continue_clip end
        if clip.media_type == "nested" then
            nested_skipped = nested_skipped + 1
            goto continue_clip
        end
        if clip.retime_requires_visible_render then
            goto continue_clip
        end
        if clip.skip_ffmpeg or not clip.file_path or clip.file_path == "" then goto continue_clip end

        local source_fps = source_fps_for_clip(ffmpeg, clip, timeline_fps)
        local dur_frames = clip.source_duration_frames or 0
        local left_offset = clip.left_offset or 0
        if dur_frames <= stuck_frames then goto continue_clip end

        local start_sec = left_offset / source_fps
        local duration_sec = dur_frames / source_fps
        if implicit_internal_flash and duration_sec < implicit_min_duration_sec then
            goto continue_clip
        end
        local scan_duration = math.min(duration_sec, max_duration_sec)
        if scan_duration <= 0 then goto continue_clip end
        local visible_intervals = {{
            start = clip.timeline_start_frame or 0,
            end_ = (clip.timeline_start_frame or 0) + dur_frames,
        }}
        if Analyzer and Analyzer.compute_visible_intervals and max_track > 0 then
            local ok_vis, vis_result = pcall(function()
                return Analyzer.compute_visible_intervals(clip, clips_by_track, max_track, overlay_config, boundary_threshold)
            end)
            if ok_vis and vis_result and vis_result.intervals then
                visible_intervals = vis_result.intervals
            end
        end
        if #visible_intervals <= 0 then goto continue_clip end

        scanned = scanned + 1
        local scene_times = {0, scan_duration}
        local scene_scores = {}
        local prefix = ""
        if ffmpeg._bundled_lib_dir then
            prefix = 'DYLD_LIBRARY_PATH="' .. ffmpeg._bundled_lib_dir .. '" '
        end
        local filter_arg = filter_script_path and
            ("-filter_script:v " .. ffmpeg:_quote_path(filter_script_path)) or
            string.format("-vf \"select='gt(scene\\,%.3f)',metadata=print\"", threshold)
        local cmd = string.format(
            "%s%s -timelimit %d -ss %.3f -t %.3f -i %s %s -an -f null - 2>&1",
            prefix,
            ffmpeg:_quote_path(ffmpeg.ffmpeg_path),
            timeout,
            start_sec,
            scan_duration,
            ffmpeg:_quote_path(clip.file_path),
            filter_arg
        )
        local run_cmd = cmd
        if ffmpeg.os == "windows" and cache_dir then
            local bat_path = cache_dir .. "\\mixed_cut_scene_run.bat"
            local bf = io.open(bat_path, "w")
            if bf then
                bf:write("@echo off\r\n")
                bf:write(cmd .. "\r\n")
                bf:close()
                run_cmd = 'cmd /S /C "' .. bat_path .. '"'
            end
        end
        local handle = io.popen(run_cmd, "r")
        local stderr_samples = {}
        if handle then
            local last_scene_frame = nil
            for line in handle:lines() do
                if #stderr_samples < 4 then
                    table.insert(stderr_samples, line)
                end
                local t = line:match("pts_time:(%d+%.?%d*)")
                local score = line:match("lavfi%.scene_score=(%d+%.?%d*)") or line:match("scene_score[:=](%d+%.?%d*)")
                if t then
                    local raw_rel = tonumber(t)
                    local candidates = {}
                    if raw_rel and raw_rel >= 0 and raw_rel < scan_duration then
                        table.insert(candidates, raw_rel)
                    end
                    for _, rel in ipairs(candidates) do
                        append_unique_number(scene_times, rel, source_fps)
                        last_scene_frame = math.floor(rel * source_fps + 0.5)
                        scene_scores[last_scene_frame] = tonumber(score or "0") or scene_scores[last_scene_frame] or 0
                    end
                elseif score and last_scene_frame then
                    scene_scores[last_scene_frame] = tonumber(score or "0") or scene_scores[last_scene_frame] or 0
                end
            end
            handle:close()
        else
            dlog("混剪源内场景扫描: io.popen failed")
        end

        table.sort(scene_times)
        local real_scene_count = math.max(0, #scene_times - 2)
        -- 普通模式源内短闪只要求短段两端都是强切点；测试片段可能只有这一组切点。
        if implicit_internal_flash and real_scene_count < (tonumber(params.mixed_cut_implicit_min_scene_count or 2) or 2) then
            goto continue_clip
        end
        if #scene_times > 2 then
            dlog(string.format("混剪源内场景点: track=%s start=%s scenes=%d intervals=%d first=%.3f",
                tostring(clip.track_index or "?"),
                tostring(clip.timeline_start_frame or "?"),
                real_scene_count,
                #visible_intervals,
                scene_times[2] or 0))
        elseif scanned <= 2 and #stderr_samples > 0 then
            dlog("混剪源内场景点为空: " .. table.concat(stderr_samples, " | "))
        end
        for i = 1, #scene_times - 1 do
            local rel_start = scene_times[i]
            local rel_end = scene_times[i + 1]
            local span_frames = math.max(1, math.floor((rel_end - rel_start) * source_fps + 0.5))
            local rel_start_frame = math.floor(rel_start * source_fps + 0.5)
            local rel_end_frame = math.floor(rel_end * source_fps + 0.5)
            local tl_start = (clip.timeline_start_frame or 0) + rel_start_frame
            local tl_end = math.max(tl_start + 1, (clip.timeline_start_frame or 0) + rel_end_frame)
            if (rel_start > 0 or rel_end < scan_duration) and tl_end > tl_start then
                for _, iv in ipairs(visible_intervals) do
                    local iv_start = tonumber(iv.start or 0) or 0
                    local iv_end = tonumber(iv.end_ or iv["end"] or iv_start) or iv_start
                    local overlap_start = math.max(tl_start, iv_start)
                    local overlap_end = math.min(tl_end, iv_end)
                    local exposed_frames = overlap_end - overlap_start
                    if exposed_frames > 0 and exposed_frames <= stuck_frames then
                        local touches_start = overlap_start == iv_start and top_covering_clip_at(iv_start - 1, clip) ~= nil
                        local touches_end = overlap_end == iv_end and top_covering_clip_at(iv_end, clip) ~= nil
                        local skip_same_source = (touches_start and same_source_boundary_is_continuous(clip, iv_start, "start"))
                            or (touches_end and same_source_boundary_is_continuous(clip, iv_end, "end"))
                        local scene_score = math.max(
                            tonumber(scene_scores[rel_start_frame] or 0) or 0,
                            tonumber(scene_scores[rel_end_frame] or 0) or 0
                        )
                        local min_visible_fragment_score = tonumber(params.mixed_cut_visible_fragment_scene_score
                            or params.mixed_cut_internal_flash_score
                            or 0.16) or 0.16
                        if (touches_start or touches_end) and not skip_same_source
                            and scene_score >= min_visible_fragment_score
                        then
                            local source_start = (left_offset + (overlap_start - (clip.timeline_start_frame or 0))) / source_fps
                            local source_end = (left_offset + (overlap_end - (clip.timeline_start_frame or 0))) / source_fps
                            add_mixed_cut_record(records, seen, clip, "visible_fragment",
                                source_start, source_end, overlap_start, timeline_fps, scene_score, "visible_fragment",
                                iv_start, iv_end)
                        end
                    end
                end
            end
            if span_frames > 0 and span_frames <= stuck_frames then
                if implicit_internal_flash then
                    local start_score = scene_scores[rel_start_frame] or 0
                    local end_score = scene_scores[rel_end_frame] or 0
                    local has_two_real_cuts = rel_start > 0 and rel_end < scan_duration
                        and start_score >= internal_flash_score
                        and end_score >= internal_flash_score
                    if not has_two_real_cuts then
                        goto continue_span
                    end
                end
                local span_visible = false
                for _, iv in ipairs(visible_intervals) do
                    local iv_start = iv.start or 0
                    local iv_end = iv.end_ or iv["end"] or iv_start
                    if tl_end > iv_start and tl_start < iv_end then
                        span_visible = true
                        break
                    end
                end
                if span_visible then
                    local source_start = start_sec + rel_start
                    local source_end = start_sec + rel_end
                    local mark_frame = implicit_internal_flash and math.max(clip.timeline_start_frame or 0, tl_start - 1) or tl_start
                    add_mixed_cut_record(records, seen, clip, "span", source_start, source_end, mark_frame, timeline_fps,
                        scene_scores[math.floor(rel_start * source_fps + 0.5)] or
                        scene_scores[math.floor(rel_end * source_fps + 0.5)] or 0, "span")
                end
            end
            ::continue_span::
        end
        for _, rel_cut in ipairs(scene_times) do
            if rel_cut > 0 and rel_cut < scan_duration then
                if implicit_internal_flash then goto continue_scene_cut end
                local source_frame = math.floor(rel_cut * source_fps + 0.5)
                local score_for_cut = scene_scores[source_frame] or 0
                local tl_cut = (clip.timeline_start_frame or 0) + source_frame
                local clip_start = clip.timeline_start_frame or 0
                local clip_end = clip_start + (clip.source_duration_frames or 0)
                local matched_visible = false
                for _, iv in ipairs(visible_intervals) do
                    local iv_start = iv.start or 0
                    local iv_end = iv.end_ or iv["end"] or iv_start
                    if tl_cut >= clip_start and tl_cut <= clip_end and tl_cut >= iv_start and tl_cut <= iv_end then
                        matched_visible = true
                        local edge_distance = math.min(math.abs(tl_cut - iv_start), math.abs(iv_end - tl_cut))
                        local edge_guard_frames = stuck_frames + 1
                        if edge_distance <= edge_guard_frames and score_for_cut >= edge_scene_score then
                            local source_start = start_sec + rel_cut
                            local edge_frame = (math.abs(tl_cut - iv_start) <= math.abs(iv_end - tl_cut))
                                and (iv_start - 1)
                                or math.min(clip_end - 1, iv_end)
                            add_mixed_cut_record(records, seen, clip, "edge", source_start,
                                source_start + (1 / source_fps), edge_frame, timeline_fps, score_for_cut, "edge")
                        elseif explicit_mixed_cut and score_for_cut >= single_scene_score then
                            local source_start = start_sec + rel_cut
                            add_mixed_cut_record(records, seen, clip, "single", source_start,
                                source_start + (1 / source_fps), tl_cut - 1, timeline_fps, score_for_cut, "single_scene")
                        end
                        break
                    end
                end
                if explicit_mixed_cut and (not matched_visible) and score_for_cut >= single_scene_score then
                    if tl_cut >= clip_start and tl_cut <= clip_end then
                        local source_start = start_sec + rel_cut
                        add_mixed_cut_record(records, seen, clip, "single_fallback", source_start,
                            source_start + (1 / source_fps), tl_cut - 1, timeline_fps, score_for_cut, "single_scene")
                    end
                end
                ::continue_scene_cut::
            end
        end
        ::continue_clip::
    end

    dlog(string.format("混剪源内筛查: scanned=%d records=%d nested_skipped=%d threshold=%.3f internal_score=%.3f edge_score=%.3f single_scene_score=%.3f internal_flash=%s explicit=%s",
        scanned, #records, nested_skipped, threshold, internal_flash_score, edge_scene_score, single_scene_score,
        tostring(implicit_internal_flash), tostring(explicit_mixed_cut)))
    if nested_skipped > 0 then
        print(string.format("[BFD] 混剪筛查: %d 个复合/Fusion片段无源文件路径，需用复杂模式渲染检查", nested_skipped))
    end
    return records
end

-- 检查关键模块
if not UIBridge then dlog("FATAL: ui_bridge 加载失败，退出"); return end
if not VersionCompat then dlog("FATAL: version_compat 加载失败，退出"); return end

dlog("所有模块加载完成")

-- ============================================================
-- 主函数
-- ============================================================
local function read_first_line(path)
    local f = io.open(path, "r")
    if not f then return nil end
    local line = f:read("*l")
    f:close()
    if line then
        line = line:gsub("^\239\187\191", "")
        line = line:gsub("^%s+", ""):gsub("%s+$", "")
    end
    if line == "" then return nil end
    return line
end

local function json_escape(value)
    value = tostring(value or "")
    value = value:gsub("\\", "\\\\"):gsub('"', '\\"'):gsub("\r", "\\r"):gsub("\n", "\\n")
    return value
end

local function quick_resolve_app()
    if type(resolve) == "userdata" or type(resolve) == "table" then
        return resolve
    end
    if bmd and bmd.scriptapp then
        local ok, app = pcall(function() return bmd.scriptapp("Resolve") end)
        if ok and app then return app end
    end
    if fusion and fusion.GetResolve then
        local ok, app = pcall(function() return fusion:GetResolve() end)
        if ok and app then return app end
    end
    if bmd and bmd.scriptapp then
        local ok, app = pcall(function()
            local fu = bmd.scriptapp("Fusion")
            if fu and fu.GetResolve then
                return fu:GetResolve()
            end
            return nil
        end)
        if ok and app then return app end
    end
    return nil
end

local function write_timeline_state_snapshot()
    local app = quick_resolve_app()
    if not app then
        dlog("PySide timeline snapshot skipped: no fast Resolve handle")
        return
    end
    local ok, err = pcall(function()
        local pm = app:GetProjectManager()
        local project = pm and pm:GetCurrentProject()
        if not project then return end
        local current = project:GetCurrentTimeline()
        local current_name = current and current:GetName() or ""
        local count = tonumber(project:GetTimelineCount() or 0) or 0
        local timelines = {}
        local seen = {}
        for index = 1, count do
            local tl = project:GetTimelineByIndex(index)
            if tl then
                local name = tl:GetName() or ("Timeline " .. tostring(index))
                local uid = name
                pcall(function()
                    uid = tl:GetUniqueId() or name
                end)
                if not seen[uid] then
                    seen[uid] = true
                    local fps = tonumber(tl:GetSetting("timelineFrameRate") or 25) or 25
                    if name == current_name then name = name .. "  (当前)" end
                    table.insert(timelines, string.format(
                        '{"index":%d,"name":"%s","fps":%s,"uid":"%s"}',
                        index, json_escape(name), tostring(fps), json_escape(uid)
                    ))
                end
            end
        end
        if #timelines == 0 then return end
        local sep = package.config:sub(1, 1)
        local home = os.getenv("USERPROFILE") or os.getenv("HOME") or "."
        local state_dir = home .. sep .. ".qinghe_bfd"
        if sep == "\\" then
            os.execute('mkdir "' .. state_dir .. '" >nul 2>nul')
        else
            os.execute('mkdir -p "' .. state_dir .. '" >/dev/null 2>&1')
        end
        local f = io.open(state_dir .. sep .. "current_timeline_state.json", "w")
        if f then
            f:write('{"ok":true,"timelines":[' .. table.concat(timelines, ",") .. ']}\n')
            f:close()
            dlog("PySide timeline snapshot written: " .. tostring(#timelines))
        end
    end)
    if not ok then
        dlog("PySide timeline snapshot failed: " .. tostring(err))
    end
end

local function try_launch_external_ui()
    if os.getenv("BFD_PARAMS_FILE") or os.getenv("BFD_DISABLE_EXTERNAL_UI") then
        return false
    end
    local bridge_ok, PyParamsBridge = pcall(require, "py_params_bridge")
    if bridge_ok and PyParamsBridge and PyParamsBridge.has_pending_params then
        local has_pending = false
        pcall(function() has_pending = PyParamsBridge.has_pending_params() end)
        if has_pending then
            dlog("Recent PySide params found; skip launching UI and run detection")
            return false
        end
    end
    if not BFD_MODULE_DIR then
        dlog("PySide UI launcher skipped: module dir unknown")
        return false
    end

    local sep = package.config:sub(1, 1)
    local launcher = read_first_line(BFD_MODULE_DIR .. sep .. "ui_launcher_path.txt")
    if not launcher or not file_exists(launcher) then
        dlog("PySide UI launcher missing: " .. tostring(launcher))
        return false
    end

    -- PySide 会在窗口打开后后台同步时间线。这里不再预先扫描全部时间线，
    -- 否则复杂工程会在菜单点击阶段先卡住，用户会误以为插件没反应。
    print("[BFD] Opening PySide UI control panel...")
    dlog("Launching PySide UI: " .. launcher)
    local ok = false
    if sep == "\\" then
        ok = os.execute('wscript.exe //B "' .. launcher .. '"')
    else
        ok = os.execute('sh "' .. launcher .. '" >/dev/null 2>&1 &')
    end
    dlog("PySide UI launch result: " .. tostring(ok))
    return ok ~= false and ok ~= nil
end

function Main()
    dlog("Main() 进入")
    print("\n" .. string.rep("=", 55))
    print("  [BFD] 清何黑帧夹帧检测小工具 v" .. config.PLUGIN_VERSION)
    print(string.rep("=", 55))

    if try_launch_external_ui() then
        print("[BFD] PySide UI opened; start detection in the external control panel.")
        dlog("Menu launch handed off to PySide UI")
        return
    end

    -- ----------------------------------------------------------
    -- 阶段1: 版本检测与兼容性适配
    -- ----------------------------------------------------------
    print("[BFD] 正在初始化...")
    dlog("阶段1: 版本检测...")
    local compat = VersionCompat:new()
    dlog("VersionCompat:new() OK")
    local ok, err = compat:init()
    dlog("compat:init() -> ok=" .. tostring(ok) .. " err=" .. tostring(err))
    if not ok then
        dlog("FATAL: 初始化失败 - " .. tostring(err))
        UIBridge.show_error(nil, "初始化失败: " .. (err or "未知错误"))
        return
    end

    if not compat:is_supported() then
        dlog("FATAL: 版本过低 - " .. compat.version_string)
        UIBridge.show_error(compat,
            "DaVinci Resolve 版本过低，需要 v17.0 或更高版本。\n当前版本: " .. compat.version_string)
        return
    end

    print("[BFD] " .. compat:get_info_string())
    dlog("阶段1完成: " .. compat:get_info_string())

    -- ----------------------------------------------------------
    -- 阶段2: 获取项目中所有时间线列表
    -- ----------------------------------------------------------
    print("[BFD] 正在获取时间线列表...")
    dlog("阶段2: 获取时间线...")
    local timeline_list, tl_err = compat:get_all_timelines()
    dlog("get_all_timelines -> count=" .. tostring(timeline_list and #timeline_list or "nil") .. " err=" .. tostring(tl_err))
    if not timeline_list then
        dlog("FATAL: 无法获取时间线 - " .. tostring(tl_err))
        UIBridge.show_error(compat, tl_err or "无法获取时间线列表")
        return
    end

    print(string.format("[BFD] 找到 %d 条时间线:", #timeline_list))
    for _, tl in ipairs(timeline_list) do
        print(string.format("[BFD]   [%d] %s (%.0f fps)", tl.index, tl.name, tl.fps))
    end

    -- ----------------------------------------------------------
    -- 阶段3-10 循环：检测完成后可重新测试
    while true do
    -- 清理上一轮残留的参数窗口
    if UIBridge._param_win then
        pcall(function() UIBridge._param_win:Hide() end)
        UIBridge._param_win = nil
    end

    -- 阶段3: UI交互 - 获取检测参数（含时间线选择）
    -- ----------------------------------------------------------
    print("[BFD] 等待用户配置检测参数...")
    dlog("阶段3: 等待UI参数...")
    local params, ui_err = UIBridge.get_detection_params(compat, timeline_list)
    dlog("get_detection_params -> params=" .. tostring(params ~= nil) .. " err=" .. tostring(ui_err))
    if not params then
        dlog("用户取消或参数获取失败: " .. tostring(ui_err))
        print("[BFD] 用户取消或无参数返回: " .. (ui_err or "取消"))
        break
    end
    dlog("阶段3完成: 用户已配置参数")
    if params.complex_mode and params.render_nested_segments then
        params.render_nested_segments = false
        dlog("参数修正: 复杂模式已开启，跳过复合/Fusion片段精查，避免重复渲染")
    end
    local external_single_run = params.external_params_path ~= nil and params.external_params_path ~= ""

    -- 使用用户选择的时间线（或fallback到当前）
    local timeline = params.timeline_obj
    local timeline_name = params.timeline_name or "未命名"
    local timeline_fps = tonumber(params.timeline_fps)
    dlog("阶段4入口: timeline_obj=" .. tostring(timeline) .. " name=" .. timeline_name .. " fps=" .. timeline_fps)

    if not timeline then
        dlog("timeline_obj为nil，进入fallback获取当前时间线")
        -- 未选择具体时间线，用当前时间线
        local _, current_tl, err = compat:get_current_project_and_timeline()
        dlog("fallback: current_tl=" .. tostring(current_tl) .. " err=" .. tostring(err))
        if not current_tl then
            dlog("FATAL: fallback也失败，返回 - " .. tostring(err))
            UIBridge.show_error(compat, err or "请先打开一个时间线")
            return
        end
        timeline = current_tl
        timeline_name = current_tl:GetName() or "未命名"
        dlog("fallback成功: " .. timeline_name)
    end
    local api_timeline_fps = nil
    pcall(function()
        api_timeline_fps = tonumber(timeline:GetSetting("timelineFrameRate"))
    end)
    if api_timeline_fps and api_timeline_fps > 0 then
        if timeline_fps and math.abs(api_timeline_fps - timeline_fps) > 0.001 then
            dlog(string.format("时间线帧率以Resolve实际值为准: params=%.3f actual=%.3f", timeline_fps, api_timeline_fps))
        end
        timeline_fps = api_timeline_fps
    end
    if not timeline_fps or timeline_fps <= 0 then
        timeline_fps = 25
        dlog("WARN: 无法读取时间线帧率，使用25fps兜底")
    end

    dlog("时间线已确认: " .. timeline_name .. " (" .. timeline_fps .. "fps)")
    print(string.format("[BFD] 已选择时间线: %s (%.2f fps)", timeline_name, timeline_fps))
    params.timeline_obj = timeline  -- 确保结果窗口可跳转

    -- 进度横幅
    local default_merge_mode = (params.merge_mode ~= false)
    local mode_label = default_merge_mode and "成片模式" or "逐文件模式"
    print("")
    print(string.rep("=", 55))
    print("  [BFD] 检测开始 - 共7步，进度见下方")
    print(string.format("  时间线: %s (%.0ffps)  模式: %s", timeline_name, timeline_fps, mode_label))
    print("  请保持 Console 窗口可见（工作区 > Console）")
    print(string.rep("=", 55))

    -- 进度输出（仅在Console打印，保留参数窗口显示）
    local detect_start_time = os.clock()
    local progress_percent = 8
    if ProgressBridge then ProgressBridge.update(params, progress_percent, "检测开始") end
    local function check_progress_panel(stage_name, percent)
        if percent then
            progress_percent = percent
        else
            progress_percent = math.min(progress_percent + 8, 92)
        end
        if ProgressBridge then ProgressBridge.update(params, progress_percent, stage_name or "处理中") end
        local elapsed = os.clock() - detect_start_time
        print(string.format("[BFD] 进度: %s (已耗时%.0f秒)", stage_name or "处理中", elapsed))
    end

    -- ----------------------------------------------------------
    -- 阶段3.5: 读取时间线入出点范围
    -- ----------------------------------------------------------
    local function parse_tc_to_frames(tc_str, fps)
        if not tc_str or tc_str == "" then return nil end
        -- 支持 HH:MM:SS:FF 格式
        local h, m, s, f = tc_str:match("(%d+):(%d+):(%d+):(%d+)")
        if h and m and s and f then
            return (tonumber(h) * 3600 + tonumber(m) * 60 + tonumber(s)) * fps + tonumber(f)
        end
        -- 支持 HH:MM:SS 格式（无帧号）
        h, m, s = tc_str:match("(%d+):(%d+):(%d+)")
        if h and m and s then
            return (tonumber(h) * 3600 + tonumber(m) * 60 + tonumber(s)) * fps
        end
        return nil
    end

    dlog("阶段3.5: 读取IO范围...")
    local io_in, io_out = nil, nil
    -- 优先使用手动输入的时间码
    if params.manual_io_in and params.manual_io_in ~= "" then
        io_in = parse_tc_to_frames(params.manual_io_in, timeline_fps)
        dlog("阶段3.5: 手动入点=" .. params.manual_io_in .. " → " .. tostring(io_in) .. "帧")
    end
    if params.manual_io_out and params.manual_io_out ~= "" then
        io_out = parse_tc_to_frames(params.manual_io_out, timeline_fps)
        dlog("阶段3.5: 手动出点=" .. params.manual_io_out .. " → " .. tostring(io_out) .. "帧")
    end
    -- 手动未提供则尝试API
    if io_in == nil or io_out == nil then
        local api_in, api_out = compat:get_in_out_range(timeline)
        if io_in == nil then io_in = api_in end
        if io_out == nil then io_out = api_out end
    end
    dlog("阶段3.5: io_in=" .. tostring(io_in) .. " io_out=" .. tostring(io_out))
    local has_io_range = (io_in ~= nil) and (io_out ~= nil)
    if has_io_range then
        print(string.format("[BFD] 检测范围: 入点帧%d → 出点帧%d (%.1fs - %.1fs)",
            io_in, io_out, io_in / timeline_fps, io_out / timeline_fps))
        params.in_point = io_in
        params.out_point = io_out
    else
        print("[BFD] 检测范围: 全时间线（未设置入出点，可在参数窗口手动输入限定范围）")
    end

    dlog("阶段3.5完成: has_io_range=" .. tostring(has_io_range) .. " io_in=" .. tostring(io_in) .. " io_out=" .. tostring(io_out))

    -- ----------------------------------------------------------
    -- 阶段4: 收集视频片段（建立时间线覆盖表用于空位检测）
    -- ----------------------------------------------------------
    dlog("阶段4: 收集视频片段...")
    print("[BFD] [1/7] 正在收集时间线上的视频片段...")
    local all_items, item_to_track = compat:get_video_items(timeline)
    dlog("阶段4: all_items count=" .. #all_items)

    if #all_items == 0 then
        dlog("FATAL: 时间线没有视频片段，返回")
        UIBridge.show_error(compat, "当前时间线没有视频片段，请先导入视频素材。")
        return
    end
    dlog("阶段4: 收集到 " .. #all_items .. " 个视频项")
    dlog("阶段4 DEBUG: 前3个item的GetStart/GetLeftOffset/GetDuration:")
    for idx = 1, math.min(3, #all_items) do
        local item = all_items[idx]
        local sf, lo, dur = 0, 0, 0
        pcall(function() sf = item:GetStart() end)
        pcall(function() lo = item:GetLeftOffset() end)
        pcall(function() dur = item:GetDuration() end)
        sf = tonumber(sf) or 0
        lo = tonumber(lo) or 0
        dur = tonumber(dur) or 0
        dlog(string.format("  item[%d]: GetStart=%d, GetLeftOffset=%d, GetDuration=%d", idx, sf, lo, dur))
    end
    local clips = {}
    -- 缓存轨道启用状态，避免重复API调用
    local track_enabled_cache = {}
    for _, item in ipairs(all_items) do
        local file_path = compat:get_clip_property(item, "File Path")
        local media_type = classify_media_type(file_path)
        local item_label = compat:get_clip_property(item, "File Name")
            or compat:get_clip_property(item, "Clip Name")
            or compat:get_clip_property(item, "Name")
            or ""
        if item_label == "" then
            pcall(function() item_label = tostring(item:GetName() or "") end)
        end
        -- 复合片段/Fusion片段：没有文件路径，需通过MediaPoolItem Type识别
        -- 支持: "复合"/"Compound"/"Fusion"/"Fusion Clip"/"Fusion Composition"
        -- 跳过: 文本层/字幕/生成器/调整图层等效果层
        local is_nested = false
        local nested_type = nil
        if (not file_path or file_path == "" or not media_type) and is_adjustment_layer_label(item_label) then
            media_type = "adjustment_layer"
            local tk = item_to_track[item] or item._track_index or 0
            local sf = 0
            pcall(function() sf = item:GetStart() end)
            file_path = "[ADJUSTMENT]" .. (item_label ~= "" and item_label or "调整图层") .. "@T" .. tk .. "F" .. sf
        elseif (not file_path or file_path == "" or not media_type) then
            local item_dur = 0
            pcall(function() item_dur = item:GetDuration() end)
            if item_dur > 0 then
                local mpi_item = nil
                pcall(function() mpi_item = item:GetMediaPoolItem() end)
                if mpi_item then
                    local ctype = nil
                    pcall(function() ctype = mpi_item:GetClipProperty("Type") end)
                    local name = item_label
                    if ctype then
                        local ct_lower = ctype:lower()
                        local is_text_generator = is_text_or_generator_label(ctype) or is_text_or_generator_label(name)
                        -- 中英文兼容: 复合(复合片段), Fusion/合成(Fusion), 时间线(嵌套时间线)
                        if (not is_text_generator) and (
                           ct_lower == "复合" or ct_lower == "compound"
                           or ct_lower:match("fusion") or ct_lower:match("合成")
                           or ct_lower:match("composition")
                           or ct_lower == "时间线" or ct_lower == "timeline"
                        ) then
                            is_nested = true
                            nested_type = ctype
                            media_type = "nested"
                            -- 生成唯一伪路径（避免去重表中空路径冲突）
                            if name == "" then name = "嵌套" end
                            -- track_idx/start_frame 在后面才赋值，这里直接用item获取
                            local tk = item_to_track[item] or item._track_index or 0
                            local sf = 0
                            pcall(function() sf = item:GetStart() end)
                            file_path = "[NESTED]" .. name .. "@T" .. tk .. "F" .. sf
                        end
                    end
                end
            end
        end
        -- 只收集视频文件、静态图片和复合片段，跳过生成器/文字层/SRT等
        if file_path and file_path ~= "" and media_type then
            local track_idx = item_to_track[item] or item._track_index or 1

            -- 检查轨道是否启用（禁用轨道上的素材全部跳过）
            if track_enabled_cache[track_idx] == nil then
                track_enabled_cache[track_idx] = compat:get_track_enabled(timeline, "video", track_idx)
            end
            if not track_enabled_cache[track_idx] then
                goto continue_item
            end

            local normalized_path = compat:normalize_path(file_path)
            local start_frame = 0
            pcall(function() start_frame = item:GetStart() end)

            local left_offset = 0
            local source_dur = 0
            pcall(function() left_offset = item:GetLeftOffset() end)
            pcall(function() source_dur = item:GetDuration() end)

            -- 透明度/合成属性（秒级读取，无需FFmpeg）
            local opacity = compat:get_clip_opacity(item)
            local composite_mode = compat:get_clip_composite_mode(item)
            local is_enabled = compat:get_clip_enabled(item)
            local transform = compat:get_clip_transform(item)
            local crop = compat:get_clip_crop(item)
            local alpha_mode = tostring(compat:get_clip_property(item, "Alpha mode") or "")
            local alpha_mode_lower = alpha_mode:lower()
            if media_type == "video"
                and alpha_mode ~= ""
                and alpha_mode_lower ~= "none"
                and alpha_mode_lower ~= "无"
                and alpha_mode_lower ~= "0" then
                media_type = "alpha_video"
            end
            local source_fps = nil
            local source_width = nil
            local source_height = nil
            pcall(function()
                local media_item = item:GetMediaPoolItem()
                if media_item then
                    source_fps = tonumber(media_item:GetClipProperty("FPS"))
                        or tonumber(media_item:GetClipProperty("Shot Frame Rate"))
                        or tonumber(media_item:GetClipProperty("Video Frame Rate"))
                    local resolution = tostring(media_item:GetClipProperty("Resolution") or "")
                    local rw, rh = resolution:match("(%d+)%s*x%s*(%d+)")
                    source_width = tonumber(media_item:GetClipProperty("Width")) or tonumber(rw)
                    source_height = tonumber(media_item:GetClipProperty("Height")) or tonumber(rh)
                end
            end)

            -- 静态图片跳过FFmpeg；带通道图片额外跳过夹帧检测
            -- 嵌套片段(复合/Fusion)跳过FFmpeg(无实际文件)，但作为时间线素材参与遮挡/叠加判断；
            -- 它们内部的问题交给复杂/精查渲染，外部造成普通镜头只露几帧时普通模式必须能标。
            -- 调整图层不直接参与FFmpeg分析，也不当作遮挡源；只在基础黑边几何里叠加缩放/位移。
            local skip_ffmpeg = (media_type == "still_image" or media_type == "alpha_image" or media_type == "nested" or media_type == "adjustment_layer")
            local skip_stuck = (media_type == "alpha_image" or media_type == "adjustment_layer")

            table.insert(clips, {
                item = item,
                file_path = normalized_path,
                name = item_label ~= "" and item_label or "未知",
                timeline_start_frame = start_frame,
                left_offset = left_offset,
                source_duration_frames = source_dur,
                source_fps = source_fps,
                track_index = track_idx,
                opacity = opacity,
                composite_mode = composite_mode,
                is_enabled = is_enabled,
                transform = transform,
                crop = crop,
                source_width = source_width,
                source_height = source_height,
                media_type = media_type,
                alpha_mode = alpha_mode,
                skip_ffmpeg = skip_ffmpeg,
                skip_stuck = skip_stuck,
            })
        end
        ::continue_item::
    end

    -- 构建 file_dedup 表：按唯一文件路径分组
    local file_dedup = {}
    for _, clip in ipairs(clips) do
        local fp = clip.file_path
        if fp then
            if not file_dedup[fp] then file_dedup[fp] = {} end
            table.insert(file_dedup[fp], clip)
        end
    end

    -- I/O 范围是用户本次检测的边界。重复检测不能拿 I/O 外片段作参照，
    -- 否则会把圈外复用误判成圈内重复。

    -- 入出点范围过滤：裁剪片段范围和跳过不在范围内的片段
    if has_io_range then
        local filtered_clips = {}
        for _, clip in ipairs(clips) do
            local clip_end = clip.timeline_start_frame + clip.source_duration_frames
            -- 判断片段是否与入出点范围有重叠
            if clip_end > io_in and clip.timeline_start_frame < io_out then
                table.insert(filtered_clips, clip)
            end
        end
        print(string.format("[BFD] 入出点范围内: %d/%d 个片段", #filtered_clips, #clips))
        clips = filtered_clips
    end

    if default_merge_mode or params.enable_timeline_mixed_cut or params.detect_mixed_cut then
        local sep = package.config:sub(1, 1)
        local cache_dir = params.complex_cache_dir
        if not cache_dir or cache_dir == "" then
            cache_dir = config.get_home() .. sep .. ".qinghe_bfd" .. sep .. "render_cache"
        end
        local probe_resolve = compat.resolve
        local start_offset_for_probe = 0
        pcall(function()
            start_offset_for_probe = compat:get_timeline_start_offset(timeline, timeline_fps)
        end)
        annotate_retimed_clips_from_fcpxml(
            probe_resolve, timeline, clips, cache_dir, sep, timeline_fps, start_offset_for_probe
        )
    end

    print(string.format("[BFD] 找到 %d 个视频片段（含轨道排布信息）", #clips))

    -- 统计唯一源文件数
    local unique_files = {}
    for path, _ in pairs(file_dedup) do table.insert(unique_files, path) end
    print(string.format("[BFD] 其中 %d 个唯一源文件（场景探测后同源多镜头）", #unique_files))
    dlog("阶段4完成: " .. #clips .. " 个视频片段, " .. #unique_files .. " 个唯一源文件")
    check_progress_panel("片段收集完成", 20)

    -- 复杂工程模式：渲染→FFmpeg分析→标记映射
    local ffmpeg_results = {}   -- 提前声明，复杂模式和普通模式共用
    local ffmpeg_errors = {}
    local complex_render_done = false
    local shared_ffmpeg_for_late_pass = nil
    local corrupt_frame_records = {}  -- 渲染坏帧检测（signalstats ABC三方案）

    local function read_timeline_geometry()
        local width, height = nil, nil
        local mismatch = nil
        local function read_setting(obj, key)
            if not obj then return nil end
            local value = nil
            pcall(function() value = obj:GetSetting(key) end)
            if value == "" then value = nil end
            return value
        end

        width = tonumber(read_setting(timeline, "timelineResolutionWidth"))
            or tonumber(read_setting(timeline, "timelineOutputResolutionWidth"))
        height = tonumber(read_setting(timeline, "timelineResolutionHeight"))
            or tonumber(read_setting(timeline, "timelineOutputResolutionHeight"))
        mismatch = read_setting(timeline, "timelineInputResMismatchBehavior")

        pcall(function()
            if (not width or not height or not mismatch) and compat.resolve then
                local pm = compat.resolve:GetProjectManager()
                local project = pm and pm:GetCurrentProject()
                if project then
                    width = width
                        or tonumber(read_setting(project, "timelineResolutionWidth"))
                        or tonumber(read_setting(project, "timelineOutputResolutionWidth"))
                    height = height
                        or tonumber(read_setting(project, "timelineResolutionHeight"))
                        or tonumber(read_setting(project, "timelineOutputResolutionHeight"))
                    mismatch = mismatch or read_setting(project, "timelineInputResMismatchBehavior")
                end
            end
        end)

        return {
            width = width or 1920,
            height = height or 1080,
            mismatch = tostring(mismatch or "scaleToFit"),
        }
    end

    local timeline_geom = read_timeline_geometry()
    dlog(string.format("黑边检测画布: %dx%d mismatch=%s",
        timeline_geom.width, timeline_geom.height, tostring(timeline_geom.mismatch)))

    local function build_clips_by_track(all_clips)
        local by_track = {}
        local max_track = 0
        for _, clip in ipairs(all_clips or {}) do
            local track = tonumber(clip.track_index or 1) or 1
            if not by_track[track] then by_track[track] = {} end
            table.insert(by_track[track], clip)
            if track > max_track then max_track = track end
        end
        return by_track, max_track
    end

    local clips_by_track_for_border, max_track_for_border = build_clips_by_track(clips)
    local border_bounds_cache = {}

    local function explicit_black_border_enabled()
        return params.detect_black_border == true
            and params.marker_types
            and params.marker_types.black_border == true
    end

    local function black_border_enabled()
        local aspect = tonumber(params.black_border_matte_aspect or 0) or 0
        if aspect > 0 then
            return explicit_black_border_enabled()
        end
        return explicit_black_border_enabled() or params.basic_black_border_enabled ~= false
    end

    local function blocks_basic_black_border(clip)
        if not clip or clip.skip_ffmpeg ~= true then return false end
        local mt = tostring(clip.media_type or "")
        -- 文字/标题/普通生成器不阻止基础黑边判断；它们通常不负责遮住画面四边。
        -- 真正会让几何黑边不可靠的是图片遮幅、带Alpha素材、复合/Fusion等不可解析覆盖层。
        if mt == "still_image" or mt == "alpha_image" then
            return params.png_as_opaque == true
        end
        return mt == "alpha_video" or mt == "nested"
    end

    local function adjustment_signature(effects)
        if not effects or #effects == 0 then return "" end
        local parts = {}
        for _, effect in ipairs(effects) do
            local transform = effect.transform or {}
            table.insert(parts, string.format("%d:%.6f:%.6f:%.3f:%.3f:%.3f",
                tonumber(effect.track_index or 0) or 0,
                tonumber(transform.ZoomX or transform.zoom_x or 1) or 1,
                tonumber(transform.ZoomY or transform.zoom_y or 1) or 1,
                tonumber(transform.Pan or transform.pan or 0) or 0,
                tonumber(transform.Tilt or transform.tilt or 0) or 0,
                tonumber(transform.RotationAngle or transform.rotation_angle or 0) or 0
            ))
        end
        return table.concat(parts, "|")
    end

    local function adjustment_effects_for_span(all_clips, start_frame, end_frame, base_track)
        local effects = {}
        base_track = tonumber(base_track or 1) or 1
        for _, clip in ipairs(all_clips or {}) do
            if clip.media_type == "adjustment_layer"
                and clip.is_enabled ~= false
                and (clip.opacity or 100) > 0
            then
                local cs = tonumber(clip.timeline_start_frame or 0) or 0
                local ce = cs + (tonumber(clip.source_duration_frames or 0) or 0)
                local track = tonumber(clip.track_index or 1) or 1
                if track > base_track and cs < end_frame and ce > start_frame then
                    table.insert(effects, {
                        track_index = track,
                        transform = clip.transform or {},
                    })
                end
            end
        end
        table.sort(effects, function(a, b) return (a.track_index or 0) < (b.track_index or 0) end)
        return effects
    end

    local function adjustment_transform_active(transform)
        transform = transform or {}
        local zoom_x = tonumber(transform.ZoomX or transform.zoom_x or 1) or 1
        local zoom_y = tonumber(transform.ZoomY or transform.zoom_y or 1) or 1
        if math.abs(zoom_x - 1) > 0.001 or math.abs(zoom_y - 1) > 0.001 then return true end
        if math.abs(tonumber(transform.Pan or transform.pan or 0) or 0) > 0.001 then return true end
        if math.abs(tonumber(transform.Tilt or transform.tilt or 0) or 0) > 0.001 then return true end
        if math.abs(tonumber(transform.RotationAngle or transform.rotation_angle or 0) or 0) > 0.001 then return true end
        return false
    end

    local function border_scale_for_behavior(src_w, src_h)
        local canvas_w = tonumber(timeline_geom.width or 1920) or 1920
        local canvas_h = tonumber(timeline_geom.height or 1080) or 1080
        local sx = canvas_w / math.max(1, src_w)
        local sy = canvas_h / math.max(1, src_h)
        local mode = tostring(timeline_geom.mismatch or ""):lower()
        if mode:match("stretch") then
            return sx, sy
        end
        if mode:match("crop") or mode:match("fill") or mode:match("full") then
            local s = math.max(sx, sy)
            return s, s
        end
        local s = math.min(sx, sy)
        return s, s
    end

    local function estimate_presented_border(bounds, clip, opts)
        opts = opts or {}
        if not bounds then return nil, "无源内容框" end
        local src_w = tonumber(clip.source_width or bounds.source_width or bounds.w or 0) or 0
        local src_h = tonumber(clip.source_height or bounds.source_height or bounds.h or 0) or 0
        if src_w <= 0 or src_h <= 0 then
            return nil, "无法读取源分辨率"
        end

        local crop = clip.crop or {}
        local crop_l = math.max(0, tonumber(crop.CropLeft or crop.crop_left or 0) or 0)
        local crop_r = math.max(0, tonumber(crop.CropRight or crop.crop_right or 0) or 0)
        local crop_t = math.max(0, tonumber(crop.CropTop or crop.crop_top or 0) or 0)
        local crop_b = math.max(0, tonumber(crop.CropBottom or crop.crop_bottom or 0) or 0)

        local left = math.max(tonumber(bounds.x or 0) or 0, crop_l)
        local top = math.max(tonumber(bounds.y or 0) or 0, crop_t)
        local right = math.min((tonumber(bounds.x or 0) or 0) + (tonumber(bounds.w or src_w) or src_w), src_w - crop_r)
        local bottom = math.min((tonumber(bounds.y or 0) or 0) + (tonumber(bounds.h or src_h) or src_h), src_h - crop_b)
        if right <= left or bottom <= top then
            return nil, "裁切后无有效内容"
        end

        local scale_x, scale_y = border_scale_for_behavior(src_w, src_h)
        local transform = clip.transform or {}
        local zoom_x = tonumber(transform.ZoomX or transform.zoom_x or 1) or 1
        local zoom_y = tonumber(transform.ZoomY or transform.zoom_y or 1) or 1
        local pan = tonumber(transform.Pan or transform.pan or 0) or 0
        local tilt = tonumber(transform.Tilt or transform.tilt or 0) or 0
        local rotation = tonumber(transform.RotationAngle or transform.rotation_angle or 0) or 0
        scale_x = scale_x * zoom_x
        scale_y = scale_y * zoom_y

        local canvas_w = tonumber(timeline_geom.width or 1920) or 1920
        local canvas_h = tonumber(timeline_geom.height or 1080) or 1080
        local content_cx = ((left + right) / 2) - (src_w / 2)
        local content_cy = ((top + bottom) / 2) - (src_h / 2)
        local canvas_cx = (canvas_w / 2) + pan
        local canvas_cy = (canvas_h / 2) - tilt
        local displayed_cx = canvas_cx + content_cx * scale_x
        local displayed_cy = canvas_cy + content_cy * scale_y
        local displayed_w = (right - left) * scale_x
        local displayed_h = (bottom - top) * scale_y
        local disp_left = displayed_cx - displayed_w / 2
        local disp_right = displayed_cx + displayed_w / 2
        local disp_top = displayed_cy - displayed_h / 2
        local disp_bottom = displayed_cy + displayed_h / 2
        local adjustment_count = 0
        local adjustment_canvas_base_applied = false

        for _, effect in ipairs(opts.adjustment_effects or {}) do
            local adjust = effect.transform or {}
            local adj_zoom_x = tonumber(adjust.ZoomX or adjust.zoom_x or 1) or 1
            local adj_zoom_y = tonumber(adjust.ZoomY or adjust.zoom_y or 1) or 1
            local adj_pan = tonumber(adjust.Pan or adjust.pan or 0) or 0
            local adj_tilt = tonumber(adjust.Tilt or adjust.tilt or 0) or 0
            local adj_rotation = tonumber(adjust.RotationAngle or adjust.rotation_angle or 0) or 0
            -- Resolve 的调整图层变换作用在已经合成好的时间线画面上。
            -- 下层素材即使放大到画布外，进入调整图层前也已经被画布裁切；
            -- 因此 adjustment Zoom 0.99 应该缩小整张画面并露边，不能被下层素材放大抵消。
            if adjustment_transform_active(adjust) and not adjustment_canvas_base_applied then
                disp_left, disp_right = 0, canvas_w
                disp_top, disp_bottom = 0, canvas_h
                adjustment_canvas_base_applied = true
            else
                local clipped_left = math.max(0, disp_left)
                local clipped_right = math.min(canvas_w, disp_right)
                local clipped_top = math.max(0, disp_top)
                local clipped_bottom = math.min(canvas_h, disp_bottom)
                if clipped_right <= clipped_left or clipped_bottom <= clipped_top then
                    disp_left, disp_right = 0, 0
                    disp_top, disp_bottom = 0, 0
                else
                    disp_left, disp_right = clipped_left, clipped_right
                    disp_top, disp_bottom = clipped_top, clipped_bottom
                end
            end
            local cx = (disp_left + disp_right) / 2
            local cy = (disp_top + disp_bottom) / 2
            local w = math.abs(disp_right - disp_left) * math.abs(adj_zoom_x)
            local h = math.abs(disp_bottom - disp_top) * math.abs(adj_zoom_y)
            cx = (canvas_w / 2) + (cx - (canvas_w / 2)) * adj_zoom_x + adj_pan
            cy = (canvas_h / 2) + (cy - (canvas_h / 2)) * adj_zoom_y - adj_tilt
            disp_left = cx - w / 2
            disp_right = cx + w / 2
            disp_top = cy - h / 2
            disp_bottom = cy + h / 2
            rotation = rotation + adj_rotation
            adjustment_count = adjustment_count + 1
        end

        local gaps = {
            left = math.max(0, disp_left),
            right = math.max(0, canvas_w - disp_right),
            top = math.max(0, disp_top),
            bottom = math.max(0, canvas_h - disp_bottom),
            disp_left = disp_left,
            disp_right = disp_right,
            disp_top = disp_top,
            disp_bottom = disp_bottom,
            rotation = rotation,
            canvas_w = canvas_w,
            canvas_h = canvas_h,
            source_w = src_w,
            source_h = src_h,
            content_left = left,
            content_top = top,
            content_right = right,
            content_bottom = bottom,
            adjustment_count = adjustment_count,
        }
        gaps.max_gap = math.max(gaps.left, gaps.right, gaps.top, gaps.bottom)
        return gaps, nil
    end

    local function append_black_border_results(ffmpeg, file_path, clip, opts)
        if not black_border_enabled() then
            return 0
        end
        if (tonumber(params.black_border_matte_aspect or 0) or 0) > 0 then
            return 0
        end
        opts = opts or {}
        if not file_path or file_path == "" or tostring(file_path):match("^%[NESTED%]") then
            return 0
        end

        local cache_key = string.format("%s|%.3f|%.3f",
            tostring(file_path), tonumber(opts.clip_start_sec or 0) or 0, tonumber(opts.clip_duration_sec or 0) or 0)
        local bounds = border_bounds_cache[cache_key]
        local border_err = nil
        if not bounds then
            bounds, border_err = ffmpeg:detect_content_bounds(file_path, {
            black_border_px = params.black_border_px or 3,
            black_border_limit = params.black_border_limit or math.max(params.pix_th or 0.01, 0.02),
            clip_start_sec = opts.clip_start_sec,
            clip_duration_sec = opts.clip_duration_sec,
            timeout = opts.timeout or 45,
        })
            if bounds then border_bounds_cache[cache_key] = bounds end
        end
        if border_err then
            dlog("黑边内容框探测警告: " .. tostring(border_err))
        end
        if not bounds then return 0 end

        local gaps, calc_err = estimate_presented_border(bounds, clip, opts)
        if calc_err then
            dlog("黑边几何计算跳过: " .. tostring(calc_err))
            return 0
        end

        local threshold = tonumber(params.black_border_px or 3) or 3
        if (gaps.max_gap or 0) < threshold then
            return 0
        end

        local timeline_frame = opts.timeline_start_frame or clip.timeline_start_frame or 0
        local uncertain = ""
        if math.abs(tonumber(gaps.rotation or 0) or 0) > 0.01 then
            uncertain = "\n注意: 当前片段带旋转，几何黑边可能需要复杂模式复查最终像素。"
        end
        local adjustment_note = ""
        if tonumber(gaps.adjustment_count or 0) > 0 then
            adjustment_note = string.format("\n已叠加上方调整图层的缩放/位移几何: %d 层。", gaps.adjustment_count)
        end

        table.insert(ffmpeg_results, {
            clip = clip,
            segments = {{
                start = opts.clip_start_sec or ((clip.left_offset or 0) / timeline_fps),
                end_ = (opts.clip_start_sec or ((clip.left_offset or 0) / timeline_fps)) + (1 / timeline_fps),
                duration = 1 / timeline_fps,
                timeline_frame = timeline_frame,
                force_classification = "black_border",
                force_marker_name = config.MARKER_NAMES.BLACK_BORDER,
                force_marker_color = config.MARKER_COLORS.BLACK_BORDER,
                force_note = string.format(
                    "实际画面边缘黑边: 左%.1fpx 右%.1fpx 上%.1fpx 下%.1fpx，阈值%dpx。\n依据: 源素材非黑内容框 + 时间线分辨率 + 缩放/平移/裁切几何计算。\n说明: 源素材自带黑边不会直接报警；只有放到时间线后仍露出黑边才标记。达芬奇遮罩/Power Window/Fusion任意遮罩若API不公开形状，建议用复杂模式复查最终画面。%s%s",
                    gaps.left or 0, gaps.right or 0, gaps.top or 0, gaps.bottom or 0,
                    threshold, adjustment_note, uncertain
                ),
            }},
            source_file = file_path,
            is_black_border = true,
        })
        return 1
    end

    local function has_nonzero_transform_value(value, epsilon)
        return math.abs(tonumber(value or 0) or 0) > (epsilon or 0.001)
    end

    local function transform_has_border_risk(transform)
        transform = transform or {}
        local zoom_x = tonumber(transform.ZoomX or transform.zoom_x or 1) or 1
        local zoom_y = tonumber(transform.ZoomY or transform.zoom_y or 1) or 1
        if zoom_x < 0.999 or zoom_y < 0.999 then return true end
        if has_nonzero_transform_value(transform.Pan or transform.pan) then return true end
        if has_nonzero_transform_value(transform.Tilt or transform.tilt) then return true end
        if has_nonzero_transform_value(transform.RotationAngle or transform.rotation_angle) then return true end
        return false
    end

    local function clip_has_basic_border_risk(clip, adjustment_effects)
        if not clip then return false end
        if transform_has_border_risk(clip.transform or {}) then return true end

        local crop = clip.crop or {}
        if has_nonzero_transform_value(crop.CropLeft or crop.crop_left)
            or has_nonzero_transform_value(crop.CropRight or crop.crop_right)
            or has_nonzero_transform_value(crop.CropTop or crop.crop_top)
            or has_nonzero_transform_value(crop.CropBottom or crop.crop_bottom)
        then
            return true
        end

        for _, effect in ipairs(adjustment_effects or {}) do
            if adjustment_transform_active(effect.transform or {}) then
                return true
            end
        end

        local src_w = tonumber(clip.source_width or 0) or 0
        local src_h = tonumber(clip.source_height or 0) or 0
        local canvas_w = tonumber(timeline_geom.width or 1920) or 1920
        local canvas_h = tonumber(timeline_geom.height or 1080) or 1080
        if src_w > 0 and src_h > 0 and canvas_w > 0 and canvas_h > 0 then
            local src_aspect = src_w / src_h
            local canvas_aspect = canvas_w / canvas_h
            if math.abs(src_aspect - canvas_aspect) > 0.01 then
                return true
            end
        end

        return false
    end

    local function expected_black_border_active_rect(bounds)
        local canvas_w = tonumber(bounds and bounds.source_width or timeline_geom.width or 1920) or 1920
        local canvas_h = tonumber(bounds and bounds.source_height or timeline_geom.height or 1080) or 1080
        local aspect = tonumber(params.black_border_matte_aspect or 0) or 0
        if canvas_w <= 0 or canvas_h <= 0 then
            canvas_w, canvas_h = 1920, 1080
        end
        if aspect <= 0 then
            return {
                x = 0,
                y = 0,
                w = canvas_w,
                h = canvas_h,
                label = "不忽略遮幅",
            }
        end

        local canvas_aspect = canvas_w / math.max(1, canvas_h)
        local rect = { x = 0, y = 0, w = canvas_w, h = canvas_h, label = string.format("%.2f", aspect) }
        if aspect < canvas_aspect then
            rect.w = math.floor(canvas_h * aspect + 0.5)
            rect.x = math.floor((canvas_w - rect.w) / 2 + 0.5)
        elseif aspect > canvas_aspect then
            rect.h = math.floor(canvas_w / aspect + 0.5)
            rect.y = math.floor((canvas_h - rect.h) / 2 + 0.5)
        end
        return rect
    end

    local function append_rendered_black_border_results(ffmpeg, rendered_path, timeline_start_frame, source_clip, opts)
        if not black_border_enabled() then return 0 end
        if not rendered_path or rendered_path == "" or not file_exists(rendered_path) then return 0 end
        opts = opts or {}
        local bounds, border_err = ffmpeg:detect_content_bounds(rendered_path, {
            black_border_px = params.black_border_px or 3,
            black_border_limit = params.black_border_limit or math.max(params.pix_th or 0.01, 0.02),
            clip_start_sec = 0,
            clip_duration_sec = opts.duration_sec,
            timeout = opts.timeout or 45,
        })
        if border_err then
            dlog("最终画面黑边探测警告: " .. tostring(border_err))
        end
        if not bounds then return 0 end

        local active = expected_black_border_active_rect(bounds)
        local content_l = tonumber(bounds.x or 0) or 0
        local content_t = tonumber(bounds.y or 0) or 0
        local content_r = content_l + (tonumber(bounds.w or 0) or 0)
        local content_b = content_t + (tonumber(bounds.h or 0) or 0)
        local active_l = tonumber(active.x or 0) or 0
        local active_t = tonumber(active.y or 0) or 0
        local active_r = active_l + (tonumber(active.w or 0) or 0)
        local active_b = active_t + (tonumber(active.h or 0) or 0)
        local threshold = tonumber(params.black_border_px or 3) or 3

        local edge_hits, edge_err = ffmpeg:detect_edge_black_frames(rendered_path, active, {
            black_border_px = threshold,
            amount = 92,
            threshold = 32,
            timeout = opts.timeout or 45,
        })
        if edge_err then
            dlog("最终画面边缘条带黑边探测警告: " .. tostring(edge_err))
        end
        if edge_hits and #edge_hits > 0 then
            local first = edge_hits[1]
            local sides = {}
            local side_seen = {}
            for _, hit in ipairs(edge_hits) do
                if not side_seen[hit.side] then
                    side_seen[hit.side] = true
                    table.insert(sides, string.format("%s@%d帧 %.1f%%", tostring(hit.side), tonumber(hit.frame or 0) or 0, tonumber(hit.pblack or 0) or 0))
                end
            end
            local hit_frame = tonumber(first.frame or 0) or 0
            local dummy_clip = {
                timeline_start_frame = (timeline_start_frame or 0) + hit_frame,
                left_offset = 0,
                file_path = rendered_path,
                name = "最终画面黑边检测",
            }
            table.insert(ffmpeg_results, {
                clip = dummy_clip,
                segments = {{
                    start = hit_frame / timeline_fps,
                    end_ = (hit_frame + 1) / timeline_fps,
                    duration = 1 / timeline_fps,
                    timeline_frame = (timeline_start_frame or 0) + hit_frame,
                    force_classification = "black_border",
                    force_marker_name = config.MARKER_NAMES.BLACK_BORDER,
                    force_marker_color = config.MARKER_COLORS.BLACK_BORDER,
                    force_note = string.format(
                        "最终画面边缘黑边: %s。\n检测方式: 复杂模式渲染后，直接检查有效画面四边条带是否为黑。\n预期遮幅: %s；有效区域: x=%d y=%d w=%d h=%d。\n说明: 正常遮幅会先被忽略；这里标记的是有效画面边缘额外露黑。",
                        table.concat(sides, " / "),
                        tostring(active.label),
                        active_l, active_t, active.w or 0, active.h or 0
                    ),
                }},
                source_file = rendered_path,
                is_black_border = true,
            })
            return 1
        end

        local gaps = {
            left = math.max(0, content_l - active_l),
            right = math.max(0, active_r - content_r),
            top = math.max(0, content_t - active_t),
            bottom = math.max(0, active_b - content_b),
        }
        gaps.max_gap = math.max(gaps.left, gaps.right, gaps.top, gaps.bottom)
        if (gaps.max_gap or 0) < threshold then
            dlog(string.format(
                "最终画面黑边：未超过阈值，active=%s content=%d,%d,%d,%d gaps=%.1f/%.1f/%.1f/%.1f",
                tostring(active.label), content_l, content_t, content_r, content_b,
                gaps.left, gaps.right, gaps.top, gaps.bottom
            ))
            return 0
        end

        local dummy_clip = {
            timeline_start_frame = timeline_start_frame or 0,
            left_offset = 0,
            file_path = rendered_path,
            name = "最终画面黑边检测",
        }
        table.insert(ffmpeg_results, {
            clip = dummy_clip,
            segments = {{
                start = 0,
                end_ = 1 / timeline_fps,
                duration = 1 / timeline_fps,
                timeline_frame = timeline_start_frame or 0,
                force_classification = "black_border",
                force_marker_name = config.MARKER_NAMES.BLACK_BORDER,
                force_marker_color = config.MARKER_COLORS.BLACK_BORDER,
                force_note = string.format(
                    "最终画面额外黑边: 左%.1fpx 右%.1fpx 上%.1fpx 下%.1fpx，阈值%dpx。\n检测方式: 复杂模式渲染后的最终画面像素分析。\n预期遮幅: %s；有效区域: x=%d y=%d w=%d h=%d。\n说明: 正常遮幅会先被忽略；如果遮幅来自 Resolve 自带遮幅、PNG、Fusion 或复合片段，只要最终画面符合预期比例，都按最终画面统一判断。",
                    gaps.left, gaps.right, gaps.top, gaps.bottom,
                    threshold,
                    tostring(active.label),
                    active_l, active_t, active.w or 0, active.h or 0
                ),
            }},
            source_file = rendered_path,
            is_black_border = true,
        })
        return 1
    end
    if params.complex_mode then
        dlog("复杂工程模式启用：渲染管线")
        print("[BFD] 复杂工程模式：渲染IO范围→FFmpeg分析→标记映射")
        if not has_io_range then
            print("[BFD] ⚠ 复杂模式需要IO出入点，请在参数窗口填写后重新检测")
            dlog("复杂模式：IO为空，跳过本次检测")
        else
            dlog("复杂模式：开始渲染管线, io_in=" .. io_in .. " io_out=" .. io_out)
            local render_state = nil
            local render_ok, render_err = pcall(function()
                local sep = package.config:sub(1, 1)
                local cache_dir = params.complex_cache_dir
                if not cache_dir or cache_dir == "" then
                    cache_dir = config.get_home() .. sep .. ".qinghe_bfd" .. sep .. "render_cache"
                end
                if sep == "\\" then
                    os.execute('mkdir "' .. cache_dir .. '" >nul 2>nul')
                else
                    os.execute('mkdir -p "' .. cache_dir .. '" >/dev/null 2>&1')
                end
                local imported_path = trim_string(params.imported_complex_render_path or "")
                local expected_meta = build_complex_render_meta(timeline, timeline_name, timeline_fps, io_in, io_out)
                local render_name = "bfd_temp_render"
                if params.keep_complex_cache == true then
                    render_name = "bfd_complex_" .. sanitize_file_stem(timeline_name) .. "_" .. tostring(io_in) .. "_" .. tostring(io_out) .. "_" .. tostring(os.time())
                end
                local temp_path = cache_dir .. sep .. render_name .. ".mp4"

                if imported_path ~= "" then
                    dlog("复杂模式：使用已保存成片候选=" .. imported_path)
                    if not file_exists(imported_path) then
                        error("已保存成片不存在: " .. imported_path)
                    end
                    local meta, meta_err = load_complex_render_meta(imported_path)
                    if not meta then
                        error("拒绝使用已保存成片: " .. tostring(meta_err))
                    end
                    local valid, valid_err = validate_complex_render_meta(meta, expected_meta)
                    if not valid then
                        error("拒绝使用已保存成片: " .. tostring(valid_err))
                    end
                    temp_path = imported_path
                    params.complex_render_keep_path = true
                    print("[BFD] 已验证复杂模式缓存成片，跳过本次整段渲染。")
                    dlog("复杂模式：缓存成片验证通过，跳过渲染")
                else
                    if params.keep_complex_cache ~= true then
                        remove_complex_render_cache(cache_dir, sep)  -- 清理旧文件/上次中断残留
                    end
                    dlog("复杂模式：临时文件路径=" .. temp_path)

                    -- 获取Project用于渲染
                    local r_resolve = compat.resolve
                    if not r_resolve then error("Resolve()返回nil") end
                    local r_pm = r_resolve:GetProjectManager()
                    if not r_pm then error("GetProjectManager()返回nil") end
                    local r_project = r_pm:GetCurrentProject()
                    if not r_project then error("GetCurrentProject()返回nil") end
                    render_state = snapshot_render_state(r_resolve, r_project)
                    dlog("复杂模式：获取Project成功")

                    -- 设置渲染输出路径（尝试多种方式）
                    pcall(function()
                        r_project:SetRenderSettings({
                            CustomName = render_name,
                            TargetDir = cache_dir,
                            VideoQuality = "Restrict to",
                            Quality = 3500,
                        })
                    end)
                    dlog("复杂模式：SetRenderSettings完成")

                    -- 尝试设置mp4格式
                    local fmt_ok = pcall(function()
                        r_project:SetCurrentRenderFormatAndCodec("mp4", "H264")
                    end)
                    if not fmt_ok then
                        pcall(function()
                            r_project:SetCurrentRenderFormatAndCodec("mov", "H264")
                        end)
                        temp_path = cache_dir .. sep .. render_name .. ".mov"
                    end
                    dlog("复杂模式：设置格式/编码完成")

                    -- 设置渲染范围到IO出入点
                    pcall(function()
                        r_project:SetRenderSettings({
                            CustomName = render_name,
                            TargetDir = cache_dir,
                            SelectAllFrames = false,
                            MarkIn = io_in,
                            MarkOut = io_out,
                            VideoQuality = "Restrict to",
                            Quality = 3500,
                        })
                    end)

                    -- 添加并启动渲染任务
                    local job_id = r_project:AddRenderJob()
                    if not job_id then error("AddRenderJob返回nil") end
                    dlog("复杂模式：渲染任务已添加, job_id=" .. tostring(job_id))

                    local started = r_project:StartRendering({job_id})
                    if not started then
                        r_project:DeleteRenderJob(job_id)
                        error("StartRendering返回false")
                    end
                    dlog("复杂模式：渲染已启动")

                    -- 等待渲染完成（最多15分钟）
                    local wait_max = 900
                    local waited = 0
                    while waited < wait_max do
                        local in_progress = true
                        pcall(function() in_progress = r_project:IsRenderingInProgress() end)
                        if not in_progress then dlog("复杂模式：IsRenderingInProgress=false，渲染完成"); break end

                        -- 检查是否失败
                        local status = nil
                        pcall(function() status = r_project:GetRenderJobStatus(job_id) end)
                        if status and status.JobStatus == "Failed" then
                            r_project:DeleteRenderJob(job_id)
                            error("渲染任务失败: " .. (status.CompletionPercentage or "?"))
                        end

                        -- sleep ~1秒
                        local t = os.clock()
                        while os.clock() - t < 1 do end
                        waited = waited + 1
                        if waited % 5 == 0 then
                            print(string.format("[BFD] 渲染中... %d秒", waited))
                            dlog(string.format("复杂模式：渲染等待 %d秒", waited))
                        end
                    end

                    if waited >= wait_max then
                        pcall(function() r_project:DeleteRenderJob(job_id) end)
                        error("渲染超时(" .. wait_max .. "秒)")
                    end
                    pcall(function() r_project:DeleteRenderJob(job_id) end)
                    restore_render_state(render_state)
                    render_state = nil
                    if params.keep_complex_cache == true then
                        write_complex_render_meta(temp_path, expected_meta)
                        params.complex_render_keep_path = true
                        print("[BFD] 已保存复杂模式缓存视频: " .. temp_path)
                    end
                end
                dlog("复杂模式：成片已准备，开始FFmpeg分析")
                print("[BFD] 成片已准备，开始FFmpeg blackdetect分析...")

                -- FFmpeg blackdetect 分析渲染文件
                if not file_exists(temp_path) then
                    error("渲染文件不存在: " .. temp_path)
                end

	                local ffmpeg = FFmpegRunner:new()
	                if not ffmpeg:find_ffmpeg() then
	                    error("未找到FFmpeg")
	                end
                    shared_ffmpeg_for_late_pass = ffmpeg
                    config._cached_ffmpeg_path = ffmpeg.ffmpeg_path

	                if black_border_enabled() then
	                    local border_count = append_rendered_black_border_results(ffmpeg, temp_path, io_in, nil, {
	                        duration_frames = io_out - io_in,
	                        duration_sec = (io_out - io_in) / timeline_fps,
	                        timeout = 120,
	                    })
	                    print(string.format("[BFD] 最终画面黑边检测完成: %d 处", border_count))
	                end

	                local dark_stats, dark_err = ffmpeg:parse_blackframe_stats(temp_path, {
	                    threshold = 32,
                    amount = 1,
                    timeout = 120,
                })
                if dark_err then
                    dlog("复杂模式：blackframe统计警告: " .. tostring(dark_err))
                end
                dark_stats = dark_stats or {}
                local dark_stat_count = 0
                for _ in pairs(dark_stats) do dark_stat_count = dark_stat_count + 1 end
                local function max_dark_pblack(start_frame, end_frame, pad)
                    pad = pad or 1
                    start_frame = math.max(0, math.floor((start_frame or 0) - pad))
                    end_frame = math.max(start_frame, math.floor((end_frame or start_frame) + pad))
                    local max_p = 0
                    for f = start_frame, end_frame do
                        local p = dark_stats[f]
                        if p and p > max_p then max_p = p end
                    end
                    return max_p
                end
                dlog("复杂模式：blackframe统计完成, frames=" .. tostring(dark_stat_count))

                local pix_th = params.pix_th or config.FFMPEG.PIXEL_THRESHOLD
                local min_dur = params.min_duration or config.FFMPEG.MIN_BLACK_DURATION
                -- 复杂模式是最终画面，不能把暗部/转场边缘都当黑帧。
                -- 0.60 保留大面积黑/暗帧，再由 blackframe 统计兜底确认短暗帧。
                local pic_th = 0.60
                dlog(string.format("复杂模式blackdetect参数: pix_th=%.3f pic_th=%.2f min_dur=%.3f",
                    pix_th, pic_th, min_dur))
                local analyzed, analyze_err = ffmpeg:detect_black_frames(temp_path, {
                    pix_th = pix_th,
                    pic_th = pic_th,
                    min_duration = min_dur,
                    timeout = 120,
                })
                dlog("复杂模式：FFmpeg分析完成, segments=" .. (#(analyzed or {})))
                print(string.format("[BFD] FFmpeg分析完成: 检测到 %d 个黑帧段", #(analyzed or {})))

                -- 映射帧号回时间线（渲染文件帧0 = io_in时间线帧）
                -- 创建虚拟clip供analyze_results做帧号映射（黑帧和夹帧共用）
                local dummy_clip = {
                    timeline_start_frame = io_in,
                    left_offset = 0,
                    file_path = temp_path,
                }
                if analyzed and #analyzed > 0 then
                    local filtered_analyzed = {}
                    for _, seg in ipairs(analyzed) do
                        local s_frame = math.floor((seg.start or 0) * timeline_fps + 0.5)
                        local e_frame = math.floor((seg.end_ or seg.start or 0) * timeline_fps + 0.5)
                        local pblack = max_dark_pblack(s_frame, e_frame, 1)
                        if pblack >= 55 then
                            table.insert(filtered_analyzed, seg)
                            table.insert(ffmpeg_results, {
                                clip = dummy_clip,
                                segments = {{
                                    start = seg.start,
                                    end_ = seg.end_,
                                    duration = seg.duration,
                                    dark_pblack = pblack,
                                }},
                                source_file = temp_path,
                                is_render_result = true,
                            })
                        end
                    end
                    dlog(string.format("复杂模式：blackdetect二次验证保留 %d/%d 段", #filtered_analyzed, #analyzed))
                elseif analyze_err then
                    dlog("复杂模式：FFmpeg分析警告: " .. tostring(analyze_err))
                end

	                -- 场景检测抓夹帧（极短画面闪现，非黑帧，blackdetect抓不到）
                -- 用select+showinfo替代scdet（更通用，所有FFmpeg版本支持）
                dlog("复杂模式：开始场景检测抓夹帧...")
                local function hex_hamming_distance(h1, h2)
                    if type(h1) ~= "string" or type(h2) ~= "string" or #h1 ~= #h2 then return 9999 end
                    local dist = 0
                    for i = 1, #h1 do
                        local a = tonumber(h1:sub(i, i), 16)
                        local b = tonumber(h2:sub(i, i), 16)
                        if not a or not b then return 9999 end
                        local x = math.abs(a - b)
                        for bit = 0, 3 do
                            local aa = math.floor(a / (2 ^ bit)) % 2
                            local bb = math.floor(b / (2 ^ bit)) % 2
                            if aa ~= bb then dist = dist + 1 end
                        end
                    end
                    return dist
                end

                local function bits_to_hex(bits)
                    local parts = {}
                    for i = 1, #bits, 4 do
                        local n = (bits[i] or 0) * 8 + (bits[i + 1] or 0) * 4
                            + (bits[i + 2] or 0) * 2 + (bits[i + 3] or 0)
                        table.insert(parts, string.format("%x", n))
                    end
                    return table.concat(parts)
                end

                local function frame_hash_from_rgb(data, thumb_size)
                    thumb_size = thumb_size or 16
                    local pixel_count = thumb_size * thumb_size
                    if type(data) ~= "string" or #data < pixel_count * 3 then return nil end
                    local values = {}
                    local min_g, max_g, sum = 255, 0, 0
                    local gi = 1
                    for i = 1, pixel_count * 3, 3 do
                        local g = math.floor(((data:byte(i) or 0) + (data:byte(i + 1) or 0) + (data:byte(i + 2) or 0)) / 3)
                        values[gi] = g
                        if g < min_g then min_g = g end
                        if g > max_g then max_g = g end
                        sum = sum + g
                        gi = gi + 1
                    end
                    local range = max_g - min_g
                    local avg = 0
                    for i = 1, pixel_count do
                        local v = values[i] or 0
                        if range > 8 then
                            v = math.floor(((v - min_g) * 255) / range)
                        end
                        values[i] = v
                        avg = avg + v
                    end
                    avg = avg / pixel_count
                    local bits = {}
                    for i = 1, pixel_count do
                        bits[i] = ((values[i] or 0) >= avg) and 1 or 0
                    end
                    return {
                        gray_hash = bits_to_hex(bits),
                        avg = sum / pixel_count,
                        range = range,
                    }
                end

                local function extract_render_frame_hashes(frame_numbers)
                    local unique = {}
                    for _, f in ipairs(frame_numbers or {}) do
                        f = tonumber(f)
                        if f and f >= 0 then unique[math.floor(f + 0.5)] = true end
                    end
                    local frames = {}
                    for f, _ in pairs(unique) do table.insert(frames, f) end
                    table.sort(frames)
                    local hashes = {}
                    local thumb_size = 16
                    local frame_size = thumb_size * thumb_size * 3
                    local chunk_size = 80
                    for pos = 1, #frames, chunk_size do
                        local chunk = {}
                        local expr = {}
                        for i = pos, math.min(#frames, pos + chunk_size - 1) do
                            table.insert(chunk, frames[i])
                            table.insert(expr, string.format("eq(n\\,%d)", frames[i]))
                        end
                        local filter = string.format("select='%s',scale=%d:%d", table.concat(expr, "+"), thumb_size, thumb_size)
                        local cmd = ffmpeg:_build_cmd(string.format(
                            '-i %s -vf "%s" -vsync 0 -an -f rawvideo -pix_fmt rgb24 - 2>/dev/null',
                            ffmpeg:_quote_path(temp_path), filter
                        ))
                        local pipe = io.popen(ffmpeg:_wrap_cmd(cmd), "r")
                        if pipe then
                            for idx, frame_no in ipairs(chunk) do
                                local data = pipe:read(frame_size)
                                if not data or #data < frame_size then break end
                                hashes[frame_no] = frame_hash_from_rgb(data, thumb_size)
                            end
                            pipe:close()
                        end
                    end
                    return hashes
                end

                local function best_hash_distance(frame_hashes, frames_a, frames_b)
                    local best = 9999
                    for _, fa in ipairs(frames_a or {}) do
                        local ha = frame_hashes[fa]
                        for _, fb in ipairs(frames_b or {}) do
                            local hb = frame_hashes[fb]
                            if ha and hb and ha.gray_hash and hb.gray_hash then
                                local d = hex_hamming_distance(ha.gray_hash, hb.gray_hash)
                                if d < best then best = d end
                            end
                        end
                    end
                    return best
                end

                local scene_change_frames_full = {}  -- 所有场景切换帧号(用于快切过滤)
                local scene_times = {}
                local scene_seen = {}
                local scene_scores = {}
                local raw_lines = 0
                -- 0.04 在压缩成片上会把正常快速剪辑放大成大量误报；保留 0.08 作为弱边缘补充。
                for _, threshold in ipairs({0.15, 0.08}) do
                    local scene_cmd = ffmpeg:_build_cmd(string.format(
                        '-i %s -vf "select=\'gt(scene\\,%.2f)\',metadata=mode=print" -an -f null - 2>&1',
                        ffmpeg:_quote_path(temp_path), threshold
                    ))
                    local sf = io.popen(scene_cmd, "r")
                    if sf then
                        local last_frame_key = nil
                        for line in sf:lines() do
                            raw_lines = raw_lines + 1
                            local t = line:match("pts_time:(%d+%.?%d*)")
                            if t then
                                local sec = tonumber(t)
                                local frame_key = tostring(math.floor(sec * timeline_fps + 0.5))
                                last_frame_key = frame_key
                                if not scene_seen[frame_key] then
                                    scene_seen[frame_key] = true
                                    table.insert(scene_times, sec)
                                end
                            end
                            local score = line:match("lavfi%.scene_score=(%d+%.?%d*)")
                            if score and last_frame_key then
                                local v = tonumber(score) or 0
                                scene_scores[last_frame_key] = math.max(scene_scores[last_frame_key] or 0, v)
                            end
                        end
                        sf:close()
                    end
                end
                table.sort(scene_times)
                if #scene_times > 0 then
                    dlog(string.format("复杂模式：场景检测原始输出 %d 行", raw_lines))
                    dlog(string.format("复杂模式：场景检测完成, 检测到 %d 个场景切换点", #scene_times))

                    -- 保存所有场景切换帧号（用于快切区域过滤）
                    for _, st in ipairs(scene_times) do
                        scene_change_frames_full[#scene_change_frames_full + 1] = math.floor(st * timeline_fps)
                    end

                    -- 找极短场景（相邻切换点间隔≤夹帧阈值）
                    local stuck_f = params.stuck_frames or config.CLASSIFICATION.STUCK_FRAMES
                    local min_gap = stuck_f / timeline_fps
                    local flash_count = 0
                    local skipped_dark_flash = 0
                    local skipped_no_hash = 0
                    local skipped_not_returning = 0
                    local flash_candidates = {}
                    local frames_to_hash = {}
                    local render_max_frame = math.max(0, math.floor((io_out or 0) - (io_in or 0)))
                    local function add_frame(list, frame)
                        frame = tonumber(frame)
                        if frame and frame >= 0 and frame <= render_max_frame then
                            frame = math.floor(frame + 0.5)
                            table.insert(list, frame)
                            table.insert(frames_to_hash, frame)
                        end
                    end
                    for i = 1, #scene_times - 1 do
                        local gap = scene_times[i+1] - scene_times[i]
                        if gap > 0 and gap <= min_gap then
                            local start_frame = math.floor(scene_times[i] * timeline_fps + 0.5)
                            local end_frame = math.floor(scene_times[i + 1] * timeline_fps + 0.5)
                            local scene_score = math.max(
                                scene_scores[tostring(start_frame)] or 0,
                                scene_scores[tostring(end_frame)] or 0
                            )
                            local pblack = max_dark_pblack(start_frame, end_frame, 1)
                            local dense_count = 0
                            local dense_start = start_frame - (stuck_f * 3)
                            local dense_end = end_frame + (stuck_f * 3)
                            for _, st in ipairs(scene_times) do
                                local sf = math.floor(st * timeline_fps + 0.5)
                                if sf >= dense_start and sf <= dense_end then
                                    dense_count = dense_count + 1
                                end
                            end
                            if pblack >= 55 then
                                skipped_dark_flash = skipped_dark_flash + 1
                            else
                                local pre_frames, mid_frames, post_frames = {}, {}, {}
                                for back = 3, 1, -1 do add_frame(pre_frames, start_frame - back) end
                                local mid_start = math.max(0, start_frame)
                                local mid_end = math.max(mid_start, end_frame - 1)
                                add_frame(mid_frames, math.floor((mid_start + mid_end) / 2 + 0.5))
                                if end_frame - start_frame > 1 then
                                    add_frame(mid_frames, start_frame)
                                    add_frame(mid_frames, end_frame - 1)
                                end
                                for forward = 1, 3 do add_frame(post_frames, end_frame + forward) end
                                if #pre_frames > 0 and #mid_frames > 0 and #post_frames > 0 then
                                    table.insert(flash_candidates, {
                                        scene_start_sec = scene_times[i],
                                        scene_end_sec = scene_times[i + 1],
                                        start_frame = start_frame,
                                        end_frame = end_frame,
                                        gap = gap,
                                        scene_score = scene_score,
                                        pblack = pblack,
                                        dense_count = dense_count,
                                        pre_frames = pre_frames,
                                        mid_frames = mid_frames,
                                        post_frames = post_frames,
                                    })
                                else
                                    skipped_no_hash = skipped_no_hash + 1
                                end
                            end
                        end
                    end
                    local frame_hashes = {}
                    if #flash_candidates > 0 then
                        frame_hashes = extract_render_frame_hashes(frames_to_hash)
                    end
                    local same_threshold = tonumber(params.render_flash_same_hash_distance or 96) or 96
                    local diff_threshold = tonumber(params.render_flash_diff_hash_distance or 80) or 80
                    local diff_margin = tonumber(params.render_flash_diff_margin or 16) or 16
                    local accepted_flash_results = {}
                    local merged_nearby_flash = 0
                    local merge_flash_window = math.max(stuck_f * 3, 6)
                    for _, cand in ipairs(flash_candidates) do
                        local pre_post_dist = best_hash_distance(frame_hashes, cand.pre_frames, cand.post_frames)
                        local pre_mid_dist = best_hash_distance(frame_hashes, cand.pre_frames, cand.mid_frames)
                        local post_mid_dist = best_hash_distance(frame_hashes, cand.post_frames, cand.mid_frames)
                        local mid_diff = math.min(pre_mid_dist, post_mid_dist)
                        local returning_same_shot = pre_post_dist <= same_threshold
                        local middle_is_different = mid_diff >= math.max(diff_threshold, pre_post_dist + diff_margin)
                        if pre_post_dist >= 9999 or mid_diff >= 9999 then
                            skipped_no_hash = skipped_no_hash + 1
                        elseif returning_same_shot and middle_is_different then
                            local flash_result = {
                                clip = dummy_clip,
                                segments = {{
                                    start = cand.start_frame / timeline_fps,
                                    end_ = cand.end_frame / timeline_fps,
                                    duration = math.max(1, cand.end_frame - cand.start_frame) / timeline_fps,
                                    scene_score = cand.scene_score,
                                    dark_pblack = cand.pblack,
                                    timeline_frame = io_in + cand.start_frame,
                                    force_classification = "error",
                                    force_marker_name = "[BFD-MIX] 真实画面短镜头夹帧",
                                    force_note = string.format(
                                        "最终渲染画面短镜头夹帧\n持续: %d帧\n切点: %d → %d\nscene score: %.3f\n成片结构验证: 前后相似距离=%d，中段差异距离=%d\n判定: 短段前后回到同一画面结构，中间闪入不同画面；不依赖时间线 Fusion/复合片段信息。",
                                        math.max(1, cand.end_frame - cand.start_frame), cand.start_frame, cand.end_frame,
                                        cand.scene_score, pre_post_dist, mid_diff
                                    ),
                                }},
                                source_file = temp_path,
                                is_render_result = true,
                                is_flash_frame = true,
                                is_mixed_cut = true,
                                _render_start_frame = cand.start_frame,
                                _scene_score = cand.scene_score,
                            }
                            local last_flash = accepted_flash_results[#accepted_flash_results]
                            if last_flash and math.abs((last_flash._render_start_frame or 0) - cand.start_frame) <= merge_flash_window then
                                if (cand.scene_score or 0) > (last_flash._scene_score or 0) then
                                    accepted_flash_results[#accepted_flash_results] = flash_result
                                end
                                merged_nearby_flash = merged_nearby_flash + 1
                            else
                                table.insert(accepted_flash_results, flash_result)
                            end
                        else
                            skipped_not_returning = skipped_not_returning + 1
                        end
                    end
                    for _, flash_result in ipairs(accepted_flash_results) do
                        flash_result._render_start_frame = nil
                        flash_result._scene_score = nil
                        table.insert(ffmpeg_results, flash_result)
                    end
                    flash_count = #accepted_flash_results
                    dlog(string.format("复杂模式：夹帧检测完成, 候选 %d 个, 验证通过 %d 个(≤%d帧), 合并近邻 %d 个, 跳过黑帧候选 %d 个, 跳过非回环快切 %d 个, 跳过无hash %d 个",
                        #flash_candidates, flash_count, stuck_f, merged_nearby_flash, skipped_dark_flash, skipped_not_returning, skipped_no_hash))
                    print(string.format("[BFD] 场景检测完成: 发现 %d 个极短场景(≤%d帧)", flash_count, stuck_f))
                else
                    dlog("复杂模式：未检测到场景切点")
                end

                -- 【ABC三方案结合】signalstats 渲染坏帧检测
                if params.detect_corrupt and config.CORRUPT_DETECTION then
                    dlog("复杂模式：开始 signalstats 渲染坏帧检测（ABC三方案）...")
                    print("[BFD] 正在检测渲染坏帧（entropy+signalstats离群值分析）...")
                    local sig_frames, sig_err = ffmpeg:parse_signalstats(temp_path, { timeout = 120 })
                    if sig_frames and #sig_frames > 0 then
                        dlog(string.format("signalstats: 采集到 %d 帧数据", #sig_frames))

                        -- 收集已知黑帧段和场景切换帧号（用于过滤）
                        local known_scene_frames = {}
                        for _, result in ipairs(ffmpeg_results) do
                            if result.segments then
                                for _, seg in ipairs(result.segments) do
                                    for f = math.floor(seg.start * timeline_fps),
                                            math.floor(seg.end_ * timeline_fps) do
                                        known_scene_frames[#known_scene_frames + 1] = f
                                    end
                                end
                            end
                        end

                        -- 执行ABC三方案离群值检测
                        local corrupt_frames = Analyzer.detect_corrupt_frames(
                            sig_frames, timeline_fps, known_scene_frames, config.CORRUPT_DETECTION,
                            scene_change_frames_full
                        )

                        -- 合并相邻坏帧
                        if #corrupt_frames > 0 then
                            local merge_gap = (config.CORRUPT_DETECTION.MERGE_GAP_SEC or 0.5) * timeline_fps
                            local merged = {}
                            local cur = {
                                start_frame = corrupt_frames[1].frame,
                                end_frame = corrupt_frames[1].frame,
                                max_votes = corrupt_frames[1].votes,
                            }
                            for k = 2, #corrupt_frames do
                                local cf = corrupt_frames[k]
                                if cf.frame - cur.end_frame <= merge_gap then
                                    cur.end_frame = cf.frame
                                    cur.max_votes = math.max(cur.max_votes, cf.votes)
                                else
                                    table.insert(merged, cur)
                                    cur = {
                                        start_frame = cf.frame,
                                        end_frame = cf.frame,
                                        max_votes = cf.votes,
                                    }
                                end
                            end
                            table.insert(merged, cur)

                            -- 转换为 marker records
                            for _, cr in ipairs(merged) do
                                local tl_start = io_in + cr.start_frame
                                local tl_end = io_in + cr.end_frame
                                local dur = cr.end_frame - cr.start_frame + 1
                                table.insert(corrupt_frame_records, {
                                    classification = "error",
                                    marker_color = config.MARKER_COLORS.CORRUPT,
                                    marker_name = config.MARKER_NAMES.CORRUPT,
                                    timeline_start_frame = tl_start,
                                    timeline_end_frame = tl_end,
                                    timeline_start_tc = Analyzer.frame_to_timecode(tl_start, timeline_fps),
                                    note = string.format(
                                        "渲染坏帧（ABC三方案检测）\n"
                                        .. "异常帧数: %d, 最高投票: %d/3\n"
                                        .. "方案A(信号): 亮度/饱和度/范围离群\n"
                                        .. "方案B(突变): 帧间亮度差值超阈值\n"
                                        .. "方案C(熵值): 图像熵异常(花屏/噪点)",
                                        dur, cr.max_votes
                                    ),
                                    source_file = temp_path,
                                    duration_frames = dur,
                                })
                            end
                            dlog(string.format("坏帧检测: %d个异常帧 → %d个区域", #corrupt_frames, #merged))
                            print(string.format("[BFD] 渲染坏帧检测完成: 发现 %d 处异常区域 (%d个坏帧)",
                                #merged, #corrupt_frames))
                        else
                            print("[BFD] 渲染坏帧检测完成: 未发现异常")
                        end
                    elseif sig_err then
                        dlog("signalstats分析失败: " .. tostring(sig_err))
                        print("[BFD] 渲染坏帧检测跳过: " .. tostring(sig_err))
                    end
                end

                -- 保留渲染文件用于帧指纹内容重复检测（阶段8b后清理）
                params.complex_render_path = temp_path
                dlog("复杂模式：渲染文件保留用于帧指纹检测: " .. temp_path)
                complex_render_done = true
            end)  -- pcall end

            restore_render_state(render_state)

            if not render_ok then
                local imported_render_requested = trim_string(params.imported_complex_render_path or "") ~= ""
                dlog("复杂模式渲染失败: " .. tostring(render_err))
                print("[BFD] ⚠ 复杂模式渲染失败: " .. tostring(render_err))
                if imported_render_requested then
                    print("[BFD] 已保存成片与当前时间线/IO不匹配，本次检测已终止，未降级普通模式。")
                    if ProgressBridge then
                        ProgressBridge.complete(params, "已保存成片不匹配", {
                            counts = { total = 0, error = 0, suspect = 0, scene = 0, gap = 0, duplicate = 0, content_dup = 0, opacity = 0, corrupt = 0, black_border = 0 },
                            records = {},
                            error = tostring(render_err),
                        })
                    end
                    if external_single_run then
                        pcall(function()
                            local PyParamsBridge = require("py_params_bridge")
                            if PyParamsBridge and PyParamsBridge.disable_pending_params then
                                PyParamsBridge.disable_pending_params()
                            end
                        end)
                    end
                    return
                end
                print("[BFD] 降级为正常模式分析...")
                -- 清理可能的残留临时文件
                pcall(function()
                    local sep = package.config:sub(1, 1)
                    local cache_dir = params.complex_cache_dir
                    if not cache_dir or cache_dir == "" then
                        cache_dir = config.get_home() .. sep .. ".qinghe_bfd" .. sep .. "render_cache"
                    end
                    remove_complex_render_cache(cache_dir, sep)
                end)
            end
        end
    else
        dlog("普通模式：complex_mode=false")
    end

    -- ----------------------------------------------------------
    -- 阶段4.5: 透明度/合成快速扫描（秒级，无需FFmpeg）
    -- ----------------------------------------------------------
    local opacity_results = {}  -- 直接生成的标记记录，跳过FFmpeg
    if params.marker_types and params.marker_types.opacity then
        dlog("阶段4.5: 开始透明度扫描, clips=" .. #clips .. " opacity_enabled=" .. tostring(params.marker_types and params.marker_types.opacity) .. " mark_hidden=" .. tostring(params.mark_hidden_clips) .. " mark_partial=" .. tostring(params.mark_partial_opacity))
        print("[BFD] [2/7] 正在扫描透明度/合成属性...")
        local opacity_config = config.OPACITY_DETECTION
        local opacity_count = 0

        -- 构建下层轨道覆盖索引：用于判断隐藏素材下方是否有内容
        -- 排除禁用素材：它们不渲染，不能作为有效下层覆盖
        -- lower_coverage[track] = {{start_frame, end_frame}, ...}
        local lower_coverage = {}
        for _, clip in ipairs(clips) do
            if clip.is_enabled ~= false then  -- 禁用的素材不渲染，不构成下层覆盖
                local t = clip.track_index or 1
                if not lower_coverage[t] then lower_coverage[t] = {} end
                table.insert(lower_coverage[t], {
                    s = clip.timeline_start_frame,
                    e = clip.timeline_start_frame + (clip.source_duration_frames or 0),
                })
            end
        end

        -- 辅助函数：检查指定时间范围内，更低轨道是否有内容覆盖
        local function has_lower_track_content(track, start_f, end_f)
            for t = 1, track - 1 do
                local ranges = lower_coverage[t]
                if ranges then
                    for _, r in ipairs(ranges) do
                        if start_f < r.e and end_f > r.s then
                            return true  -- 下层有内容
                        end
                    end
                end
            end
            return false
        end

        dlog("阶段4.5: 开始逐片段扫描, mark_hidden_clips=" .. tostring(params.mark_hidden_clips))
        for _, clip in ipairs(clips) do
            local ts = clip.timeline_start_frame
            local te = ts + (clip.source_duration_frames or 0)
            local note_parts = {}
            local category = nil
            local color = nil
            local marker_name = nil

            -- 未勾选"标记隐藏/禁用素材"时，跳过禁用和隐藏素材
            if not params.mark_hidden_clips then
                if clip.is_enabled == false then goto continue_opacity end
                if (clip.opacity or 100) <= (opacity_config.HIDDEN_THRESHOLD or 0) then goto continue_opacity end
            end

            -- 检查顺序: 禁用优先 → 透明度 → 合成模式
            -- 禁用的素材不渲染，opacity/composite都无意义
            if clip.is_enabled == false then
                category = "clip_disabled"
                color = config.MARKER_COLORS.CLIP_DISABLED or "Cyan"
                marker_name = config.MARKER_NAMES.CLIP_DISABLED
                table.insert(note_parts, "素材已禁用")

            -- 检查透明度
            elseif clip.opacity <= opacity_config.HIDDEN_THRESHOLD then
                -- 不透明度=0：隐藏素材
                if opacity_config.CHECK_LOWER_TRACKS and has_lower_track_content(clip.track_index, ts, te) then
                    -- 下层有内容，隐藏素材不造成黑帧，仅提示
                    category = "opacity_hidden_covered"
                    color = config.MARKER_COLORS.INFO or "Cyan"
                    marker_name = "[BFD-OPC] 隐藏素材(下层有内容)"
                    table.insert(note_parts, "不透明度=0，但下层轨道有内容覆盖")
                else
                    -- 下层无内容，隐藏素材直接导致黑帧
                    category = "opacity_hidden"
                    color = config.MARKER_COLORS.OPACITY_HIDDEN or "Red"
                    marker_name = config.MARKER_NAMES.OPACITY_HIDDEN
                    table.insert(note_parts, "素材不透明度=0，下方无内容→导致黑帧")
                end
            elseif clip.opacity < opacity_config.LOW_OPACITY_THRESHOLD then
                category = "opacity_low"
                color = config.MARKER_COLORS.OPACITY_LOW or "Orange"
                marker_name = config.MARKER_NAMES.OPACITY_LOW
                table.insert(note_parts, string.format("不透明度=%.0f%%", clip.opacity))
            elseif clip.opacity < opacity_config.PARTIAL_OPACITY_THRESHOLD then
                if params.mark_partial_opacity ~= false then
                    category = "opacity_partial"
                    color = config.MARKER_COLORS.OPACITY_PARTIAL or "Yellow"
                    marker_name = config.MARKER_NAMES.OPACITY_PARTIAL
                    table.insert(note_parts, string.format("不透明度=%.0f%%", clip.opacity))
                end

            -- 检查合成模式：读不到(nil)不能当成非标准合成，否则会吞掉其它真实标记。
            elseif opacity_config.MARK_COMPOSITE_NONORMAL == true
                and tonumber(clip.composite_mode) ~= nil
                and tonumber(clip.composite_mode) ~= 0 then
                category = "composite_nonormal"
                color = config.MARKER_COLORS.COMPOSITE_NONORMAL or "Green"
                marker_name = config.MARKER_NAMES.COMPOSITE_NONORMAL
                local mode_names = {
                    [0]="正常", [1]="相加", [2]="相减", [3]="差值",
                    [4]="相乘", [5]="滤色", [6]="叠加"
                }
                local composite_mode = tonumber(clip.composite_mode)
                local mode_str = mode_names[composite_mode] or ("模式" .. composite_mode)
                table.insert(note_parts, "合成模式: " .. mode_str)
            end

            if category then
                table.insert(note_parts, string.format("素材: %s", clip.name or "未知"))
                table.insert(note_parts, string.format("轨道: %d", clip.track_index or 1))

                table.insert(opacity_results, {
                    clip = clip,
                    category = category,
                    marker_name = marker_name,
                    color = color,
                    note = table.concat(note_parts, "\n"),
                    timeline_start_frame = ts,
                    timeline_end_frame = te,
                    source_file = clip.file_path,
                })
                opacity_count = opacity_count + 1
            end
            ::continue_opacity::
        end

        dlog("阶段4.5: 扫描完成, opacity_count=" .. opacity_count)
        print(string.format("[BFD] 透明度扫描完成: 发现 %d 个问题素材（秒级检测）", opacity_count))
    else
        dlog("阶段4.5: 透明度检测已跳过")
        print("[BFD] 透明度检测已跳过（未启用）")
    end

    local final_visibility_config = config.OVERLAY_STUCK_DETECTION or {}
    final_visibility_config.png_as_opaque = params.png_as_opaque
    local final_clips_by_track = {}
    local final_max_track = 0
    for _, c in ipairs(clips) do
        local t = c.track_index or 1
        if t > final_max_track then final_max_track = t end
        if not final_clips_by_track[t] then final_clips_by_track[t] = {} end
        table.insert(final_clips_by_track[t], c)
    end
    local final_visible_cache = {}
    local final_full_threshold = final_visibility_config.FULLY_OPAQUE_THRESHOLD or 95
    local function get_final_visible_intervals(clip)
        if final_visible_cache[clip] then return final_visible_cache[clip] end
        local intervals = {}
        if clip and clip.is_enabled ~= false and (clip.opacity or 100) > 0 then
            local cs = tonumber(clip.timeline_start_frame or 0) or 0
            local dur = tonumber(clip.source_duration_frames or 0) or 0
            if dur > 0 then
                intervals = {{ start = cs, end_ = cs + dur }}
                if Analyzer and Analyzer.compute_visible_intervals and final_max_track > 0 then
                    local ok_vis, vis_result = pcall(function()
                        return Analyzer.compute_visible_intervals(
                            clip, final_clips_by_track, final_max_track, final_visibility_config, final_full_threshold
                        )
                    end)
                    if ok_vis and vis_result and vis_result.intervals then
                        intervals = {}
                        for _, iv in ipairs(vis_result.intervals) do
                            local s = tonumber(iv.start or 0) or 0
                            local e = tonumber(iv.end_ or iv["end"] or s) or s
                            if e > s then
                                table.insert(intervals, { start = s, end_ = e })
                            end
                        end
                    end
                end
            end
        end
        final_visible_cache[clip] = intervals
        return intervals
    end
    local function has_final_visible_frames(clip)
        return #(get_final_visible_intervals(clip) or {}) > 0
    end
    local function is_same_source_continuous_micro_split(clip)
        if not clip or not clip.file_path or clip.file_path == "" then return false end
        local cs = tonumber(clip.timeline_start_frame or 0) or 0
        local cd = tonumber(clip.source_duration_frames or 0) or 0
        local ce = cs + cd
        local clo = tonumber(clip.left_offset or 0) or 0
        local cend = clo + cd
        local prev_clip = nil
        local next_clip = nil
        for _, other in ipairs(clips or {}) do
            if other ~= clip
                and other.track_index == clip.track_index
                and tostring(other.file_path or "") == tostring(clip.file_path or "")
                and other.is_enabled ~= false
                and (other.opacity or 100) > 0 then
                local os = tonumber(other.timeline_start_frame or 0) or 0
                local od = tonumber(other.source_duration_frames or 0) or 0
                local oe = os + od
                if oe == cs then prev_clip = other end
                if os == ce then next_clip = other end
            end
        end
        if not (prev_clip and next_clip) then return false end
        local prev_end = (tonumber(prev_clip.left_offset or 0) or 0) + (tonumber(prev_clip.source_duration_frames or 0) or 0)
        local next_start = tonumber(next_clip.left_offset or 0) or 0
        local source_tolerance = 1
        return math.abs(prev_end - clo) <= source_tolerance
            and math.abs(cend - next_start) <= source_tolerance
    end

    -- 根据透明度和最终可见性筛选：完全被上层盖住的素材不参与黑帧/夹帧判断。
    local ffmpeg_clips = {}
    local skip_count = 0
    local hidden_by_cover_count = 0
    for _, clip in ipairs(clips) do
        if clip.skip_ffmpeg then
            skip_count = skip_count + 1
        elseif clip.opacity >= (config.OPACITY_DETECTION.MIN_OPACITY_FOR_FFMPEG or 100) and clip.is_enabled ~= false then
            if has_final_visible_frames(clip) then
                table.insert(ffmpeg_clips, clip)
            else
                skip_count = skip_count + 1
                hidden_by_cover_count = hidden_by_cover_count + 1
            end
        else
            skip_count = skip_count + 1
        end
    end
    if skip_count > 0 then
        print(string.format("[BFD] 跳过 %d 个素材的FFmpeg分析（静态图片/不透明度不足/已禁用）", skip_count))
    end
    if hidden_by_cover_count > 0 then
        print(string.format("[BFD] 跳过 %d 个被上层完全覆盖的素材（最终画面不可见）", hidden_by_cover_count))
    end

    dlog("阶段4.5完成: 跳过 " .. skip_count .. " 个素材的FFmpeg分析, ffmpeg_clips=" .. #ffmpeg_clips)
    check_progress_panel("透明度扫描完成", 32)

    -- ----------------------------------------------------------
    -- 阶段4.6: 真正的夹帧检测（基于片段时长，与画面颜色无关）
    -- 直接扫描时间线上每个clip的时长，≤夹帧阈值的标记为夹帧
    -- 补充FFmpeg blackdetect只能抓"黑色"夹帧的局限性
    -- ----------------------------------------------------------
    local timeline_stuck_records = {}
    if params.marker_types and params.marker_types.error then
        local stuck_frames = params.stuck_frames or config.CLASSIFICATION.STUCK_FRAMES
        for _, clip in ipairs(clips) do
            -- 跳过禁用和隐藏素材（不渲染，不算夹帧）
            if clip.is_enabled == false then goto continue_stuck end
            if (clip.opacity or 100) <= 0 then goto continue_stuck end
            -- 带通道静态图片（PNG/PSD等）是设计元素，不算夹帧
            if clip.skip_stuck then goto continue_stuck end
            local tl_dur = clip.source_duration_frames or 0
            if tl_dur > 0 and tl_dur <= stuck_frames then
                if is_same_source_continuous_micro_split(clip) then
                    dlog(string.format(
                        "阶段4.6: 跳过连续同源微切片干扰 frame=%s clip=%s",
                        tostring(clip.timeline_start_frame or "?"), tostring(clip.name or "")
                    ))
                    goto continue_stuck
                end
                local final_intervals = get_final_visible_intervals(clip)
                if #final_intervals <= 0 then goto continue_stuck end
                local first_visible = final_intervals[1]
                local sf = first_visible.start or clip.timeline_start_frame
                local ef = math.min(first_visible.end_ or (sf + tl_dur), sf + tl_dur)
                local dur_sec = tl_dur / timeline_fps
                table.insert(timeline_stuck_records, {
                    classification = "error",
                    marker_color = config.MARKER_COLORS.ERROR,
                    marker_name = "[BFD-ERR] 夹帧(片段异常短)",
                    timeline_start_frame = sf,
                    timeline_end_frame = ef,
                    timeline_start_tc = Analyzer.frame_to_timecode(sf, timeline_fps),
                    timeline_end_tc = Analyzer.frame_to_timecode(ef, timeline_fps),
                    source_file = clip.file_path,
                    source_start_sec = (clip.left_offset or 0) / timeline_fps,
                    source_duration_sec = dur_sec,
                    duration_frames = tl_dur,
                    note = string.format(
                        "片段异常短\n时间线时长: %d帧 (%.3fs)\n最终可见: %d帧\n来源: %s\n夹帧判定: ≤%d帧（必须在最终画面可见）",
                        tl_dur, dur_sec, math.max(1, ef - sf), clip.name, stuck_frames
                    ),
                })
            end
            ::continue_stuck::
        end
        if #timeline_stuck_records > 0 then
            dlog("阶段4.6: 发现 " .. #timeline_stuck_records .. " 个异常短片段(≤" .. stuck_frames .. "帧)")
            print(string.format("[BFD] 夹帧检测(片段时长): 发现 %d 个异常短片段 (≤%d帧)", #timeline_stuck_records, stuck_frames))
        else
            dlog("阶段4.6: 未发现异常短片段")
        end
    end

    -- ----------------------------------------------------------
    -- 阶段4.7: 多轨道叠加可见帧检测（方案B）
    -- 逐片段计算被上层不透明轨道遮挡后的"实际可见帧数"
    -- 复合/Fusion片段作为外部遮挡层参与计算；不拆它们内部画面，但不能漏掉它们造成的普通镜头短曝光。
    -- 可见帧数 ≤ 夹帧阈值 → 标记为叠加夹帧
    -- ----------------------------------------------------------
    local overlay_stuck_records = {}
    if params.marker_types and params.marker_types.error then
        local overlay_config = config.OVERLAY_STUCK_DETECTION
        overlay_config.png_as_opaque = params.png_as_opaque  -- 用户选择：PNG/PSD是否视为遮挡层
        local stuck_frames = params.stuck_frames or config.CLASSIFICATION.STUCK_FRAMES

        local clips_by_track = {}
        local max_track = 0
        for _, c in ipairs(clips) do
            local t = c.track_index or 1
            if t > max_track then max_track = t end
            if not clips_by_track[t] then clips_by_track[t] = {} end
            table.insert(clips_by_track[t], c)
        end

        local overlay_count = 0
        local overlay_soft_count = 0
        local overlay_boundary_count = 0
        local full_threshold = overlay_config.FULLY_OPAQUE_THRESHOLD or 95
        local partial_threshold = overlay_config.PARTIALLY_OPAQUE_THRESHOLD or 50
        for _, clip in ipairs(clips) do
            -- 跳过禁用和隐藏素材（不渲染）
            if clip.is_enabled == false then goto continue_overlay end
            if (clip.opacity or 100) <= 0 then goto continue_overlay end
            -- 普通模式不拆复合/Fusion内部，也不把调整图层自身当成可见内容。
            -- 它们仍可作为上层关系参与普通镜头“只露几帧”的外部可见判断。
            if clip.media_type == "nested" or clip.media_type == "adjustment_layer" then goto continue_overlay end

            local tl_dur = clip.source_duration_frames or 0
            -- 片段本身≤夹帧阈值的由阶段4.6负责，4.7只处理"长片段被遮挡露出短可见区"
            if tl_dur > stuck_frames and tl_dur > 0 and Analyzer.is_fully_opaque(clip, overlay_config) then
                -- 第一轮：完全遮挡检测 (opacity ≥ 95)
                local result = Analyzer.compute_visible_intervals(clip, clips_by_track, max_track, overlay_config, full_threshold)
                -- 第二轮：半透明遮挡检测 (opacity ≥ 50)
                local soft_result = nil

                for _, iv in ipairs(result.intervals) do
                    local vis_dur = iv.end_ - iv.start
                    -- 逐区间判断：每个可见区间单独检查是否≤夹帧阈值
                    if vis_dur > 0 and vis_dur <= stuck_frames then
                        -- 延迟加载第二轮结果
                        if soft_result == nil then
                            soft_result = Analyzer.compute_visible_intervals(clip, clips_by_track, max_track, overlay_config, partial_threshold)
                        end
                        -- 计算该区间在50%阈值下的可见帧数
                        local soft_vis_dur = 0
                        for _, siv in ipairs(soft_result.intervals) do
                            local overlap_start = math.max(iv.start, siv.start)
                            local overlap_end = math.min(iv.end_, siv.end_)
                            if overlap_end > overlap_start then
                                soft_vis_dur = soft_vis_dur + (overlap_end - overlap_start)
                            end
                        end
                        local is_soft_occluded = (soft_vis_dur <= 0 or soft_vis_dur > stuck_frames)

                        local clip_source_fps = tonumber(clip.source_fps or 0) or 0
                        if clip_source_fps <= 0 then clip_source_fps = timeline_fps end
                        local source_start_frame = (tonumber(clip.left_offset or 0) or 0)
                            + (iv.start - (tonumber(clip.timeline_start_frame or 0) or 0))
                        local source_dur_sec = vis_dur / clip_source_fps
                        local dur_sec = vis_dur / timeline_fps
                        if is_soft_occluded then
                            table.insert(overlay_stuck_records, {
                                classification = "suspect",
                                marker_color = config.MARKER_COLORS.OVERLAY_STUCK_SOFT or "Yellow",
                                marker_name = "[BFD-OVL] 夹帧(半透明遮挡)",
                                timeline_start_frame = iv.start,
                                timeline_end_frame = iv.end_,
                                timeline_start_tc = Analyzer.frame_to_timecode(iv.start, timeline_fps),
                                timeline_end_tc = Analyzer.frame_to_timecode(iv.end_, timeline_fps),
                                source_file = clip.file_path,
                                source_start_sec = source_start_frame / clip_source_fps,
                                source_duration_sec = source_dur_sec,
                                duration_frames = vis_dur,
                                visual_window_start_frame = iv.start,
                                visual_window_end_frame = iv.end_,
                                note = string.format(
                                    "多轨道叠加夹帧(半透明遮挡)\n片段总长: %d帧, 可见: %d帧\n轨道%d: %s\n上层%d%%-%d%%半透明素材遮挡，肉眼可能不明显",
                                    tl_dur, vis_dur, clip.track_index or 1, clip.name, partial_threshold, full_threshold
                                ),
                            })
                            overlay_soft_count = overlay_soft_count + 1
                        else
                            table.insert(overlay_stuck_records, {
                                classification = "error",
                                marker_color = config.MARKER_COLORS.OVERLAY_STUCK or "Red",
                                marker_name = "[BFD-OVL] 夹帧(被上层遮挡)",
                                timeline_start_frame = iv.start,
                                timeline_end_frame = iv.end_,
                                timeline_start_tc = Analyzer.frame_to_timecode(iv.start, timeline_fps),
                                timeline_end_tc = Analyzer.frame_to_timecode(iv.end_, timeline_fps),
                                source_file = clip.file_path,
                                source_start_sec = source_start_frame / clip_source_fps,
                                source_duration_sec = source_dur_sec,
                                duration_frames = vis_dur,
                                visual_window_start_frame = iv.start,
                                visual_window_end_frame = iv.end_,
                                note = string.format(
                                    "多轨道叠加夹帧\n片段总长: %d帧, 可见: %d帧\n轨道%d: %s\n被上层不透明轨道遮挡，仅曝光%d帧",
                                    tl_dur, vis_dur, clip.track_index or 1, clip.name, vis_dur
                                ),
                            })
                            overlay_count = overlay_count + 1
                        end
                    end
                end
            end
            ::continue_overlay::
        end

        -- 上层长片段开始覆盖下层长片段时，覆盖开始前一帧很容易成为最终画面里的“露底夹帧”。
        -- 这类问题不是短片段本身，也不是黑帧；必须基于最终可见轨道切换来补一层边界检测。
        local min_upper_frames = tonumber(params.overlay_boundary_min_upper_frames or 24) or 24
        local boundary_seen = {}
        local function clip_active_at(clip, frame)
            local cs = tonumber(clip.timeline_start_frame or 0) or 0
            local ce = cs + (tonumber(clip.source_duration_frames or 0) or 0)
            return cs <= frame and frame < ce
        end
        local function top_opaque_clip_at(frame)
            local top_clip = nil
            local top_track = -1
            for _, c in ipairs(clips) do
                if c.is_enabled ~= false
                    and (c.opacity or 100) > 0
                    and clip_active_at(c, frame)
                    and Analyzer.is_fully_opaque(c, overlay_config, full_threshold)
                then
                    local tr = tonumber(c.track_index or 1) or 1
                    if tr >= top_track then
                        top_track = tr
                        top_clip = c
                    end
                end
            end
            return top_clip, top_track
        end
        local function is_nested_clip(clip)
            return clip and clip.media_type == "nested"
        end
        local function is_regular_visible_video(clip)
            return clip
                and clip.media_type ~= "nested"
                and clip.media_type ~= "adjustment_layer"
                and clip.is_enabled ~= false
                and (clip.opacity or 100) > 0
                and tostring(clip.file_path or "") ~= ""
        end
        local function same_file_pair(a, b)
            return is_regular_visible_video(a)
                and is_regular_visible_video(b)
                and tostring(a.file_path or "") == tostring(b.file_path or "")
        end
        local function boundary_reason_for(exposed_clip, cover_clip, default_reason, source_jump)
            if is_nested_clip(cover_clip) then
                return "复合/Fusion外部覆盖边界，普通镜头短暂露出"
            end
            if same_file_pair(exposed_clip, cover_clip) then
                local jump = tonumber(source_jump or 0) or 0
                local max_jump = tonumber(params.mixed_cut_overlay_max_source_jump or 600) or 600
                if jump > max_jump then
                    return nil
                end
                local min_jump = tonumber(params.mixed_cut_overlay_min_source_jump or 48) or 48
                if jump >= min_jump then
                    return default_reason .. "，源帧跳跃" .. tostring(math.floor(jump + 0.5)) .. "帧"
                end
                return nil
            end
            if is_regular_visible_video(exposed_clip) and is_regular_visible_video(cover_clip) then
                return "不同素材覆盖边界，普通镜头短暂露出"
            end
            return nil
        end
        local function boundary_needs_short_visible_run(exposed_clip, cover_clip)
            -- 复合/Fusion遮挡普通镜头：问题点就是切入/切出边界的那一帧，
            -- 不能因为下层普通镜头前后可见时间较长就过滤掉。
            if is_nested_clip(cover_clip) then return false end
            -- 普通素材覆盖边界必须真的只短暂露出，避免正常叠层/同源覆盖被误报。
            return true
        end
        local function visible_run_before(edge_frame, clip, max_frames)
            local count = 0
            local max_scan = math.max(1, (tonumber(max_frames) or 1) + 1)
            for f = edge_frame - 1, edge_frame - max_scan, -1 do
                local top = top_opaque_clip_at(f)
                if top ~= clip then break end
                count = count + 1
            end
            return count, edge_frame - count
        end
        local function visible_run_after(edge_frame, clip, max_frames)
            local count = 0
            local max_scan = math.max(1, (tonumber(max_frames) or 1) + 1)
            for f = edge_frame, edge_frame + max_scan - 1 do
                local top = top_opaque_clip_at(f)
                if top ~= clip then break end
                count = count + 1
            end
            return count, edge_frame
        end
        local function is_fusion_nested_clip(clip)
            if not is_nested_clip(clip) then return false end
            local text = tostring(clip.nested_type or clip.name or ""):lower()
            return text:find("fusion", 1, true) ~= nil
                or text:find("合成", 1, true) ~= nil
                or text:find("composition", 1, true) ~= nil
        end
        local boundary_scene_ffmpeg = nil
        local boundary_scene_ffmpeg_checked = false
        local function get_boundary_scene_ffmpeg()
            if boundary_scene_ffmpeg_checked then return boundary_scene_ffmpeg end
            boundary_scene_ffmpeg_checked = true
            local ok, runner = pcall(function() return FFmpegRunner:new() end)
            if ok and runner and runner:find_ffmpeg() then
                boundary_scene_ffmpeg = runner
                config._cached_ffmpeg_path = runner.ffmpeg_path
            end
            return boundary_scene_ffmpeg
        end
        local function source_short_run_after_boundary(edge_frame, clip, max_frames)
            if not clip or clip.media_type == "nested" or clip.media_type == "adjustment_layer" then return nil end
            if clip.is_enabled == false or (clip.opacity or 100) <= 0 then return nil end
            if not clip.file_path or clip.file_path == "" then return nil end
            local clip_start = tonumber(clip.timeline_start_frame or 0) or 0
            local clip_dur = tonumber(clip.source_duration_frames or 0) or 0
            local clip_end = clip_start + clip_dur
            if edge_frame < clip_start or edge_frame >= clip_end then return nil end

            local ffmpeg = get_boundary_scene_ffmpeg()
            if not ffmpeg or not ffmpeg.ffmpeg_path or not ffmpeg.first_scene_cut_after then return nil end

            local source_fps = source_fps_for_clip(ffmpeg, clip, timeline_fps)
            local left_offset = tonumber(clip.left_offset or 0) or 0
            local source_frame = left_offset + (edge_frame - clip_start)
            if source_frame < 0 then return nil end

            local probe_frames = math.max((tonumber(max_frames) or 1) + 2, 4)
            local denominators = { source_fps }
            if math.abs((timeline_fps or source_fps) - source_fps) > 0.01 then
                table.insert(denominators, timeline_fps)
            end
            for _, denom in ipairs(denominators) do
                denom = tonumber(denom) or source_fps
                if denom > 0 then
                    local cut, err = ffmpeg:first_scene_cut_after(
                        clip.file_path,
                        source_frame / denom,
                        {
                            window_sec = probe_frames / denom,
                            scene_threshold = params.nested_boundary_scene_threshold
                                or params.mixed_cut_internal_flash_score
                                or 0.16,
                            timeout = params.nested_boundary_probe_timeout or 8,
                        }
                    )
                    if err then
                        dlog("复合/Fusion边界源内短镜头确认: " .. tostring(err))
                    end
                    if cut and cut.relative_sec then
                        local frames = math.max(1, math.floor(cut.relative_sec * denom + 0.5))
                        if frames > 0 and frames <= (tonumber(max_frames) or frames) then
                            dlog(string.format(
                                "复合/Fusion边界源内短镜头确认: edge=%d rel=%.4f frames=%d denom=%.3f source_fps=%.3f",
                                edge_frame, cut.relative_sec, frames, denom, source_fps
                            ))
                            return frames, cut.score
                        end
                    end
                end
            end
            return nil
        end
        local source_scene_near_cache = {}
        local function source_scene_cut_near_boundary(edge_frame, clip, max_frames, direction)
            if not clip or clip.media_type == "nested" or clip.media_type == "adjustment_layer" then return nil end
            if clip.is_enabled == false or (clip.opacity or 100) <= 0 then return nil end
            if not clip.file_path or clip.file_path == "" then return nil end

            local clip_start = tonumber(clip.timeline_start_frame or 0) or 0
            local clip_dur = tonumber(clip.source_duration_frames or 0) or 0
            local clip_end = clip_start + clip_dur
            if edge_frame < clip_start or edge_frame >= clip_end then return nil end

            local ffmpeg = get_boundary_scene_ffmpeg()
            if not ffmpeg or not ffmpeg.ffmpeg_path then return nil end

            local source_fps = source_fps_for_clip(ffmpeg, clip, timeline_fps)
            local source_frame = (tonumber(clip.left_offset or 0) or 0) + (edge_frame - clip_start)
            if source_frame < 0 or source_fps <= 0 then return nil end

            local tolerance_frames = math.max((tonumber(max_frames) or 1) + 3, 12)
            local start_frame = math.max(0, source_frame - tolerance_frames)
            local window_frames = tolerance_frames * 2 + 1
            local threshold = tonumber(params.mixed_cut_overlay_scene_threshold
                or params.mixed_cut_scene_threshold
                or 0.04) or 0.04
            local key = table.concat({
                tostring(clip.file_path),
                tostring(math.floor(start_frame + 0.5)),
                tostring(window_frames),
                string.format("%.3f", threshold),
                tostring(direction or ""),
            }, "|")
            if source_scene_near_cache[key] ~= nil then
                local cached = source_scene_near_cache[key]
                if cached then
                    return cached.distance, cached.score, cached.kind
                end
                return nil
            end

            local prefix = ""
            if ffmpeg._bundled_lib_dir then
                prefix = 'DYLD_LIBRARY_PATH="' .. ffmpeg._bundled_lib_dir .. '" '
            end
            local filter = string.format("select='gt(scene\\,%.3f)',metadata=print", threshold)
            local cmd = string.format(
                '%s%s -timelimit %d -ss %.6f -t %.6f -i %s -vf "%s" -an -f null - 2>&1',
                prefix,
                ffmpeg:_quote_path(ffmpeg.ffmpeg_path),
                tonumber(params.nested_boundary_probe_timeout or 8) or 8,
                start_frame / source_fps,
                window_frames / source_fps,
                ffmpeg:_quote_path(clip.file_path),
                filter
            )
            local best_distance, best_score, best_tl_frame, best_kind = nil, nil, nil, nil
            local handle = io.popen(ffmpeg:_wrap_cmd(cmd), "r")
            if handle then
                local last_distance = nil
                local start_time = os.time()
                for line in handle:lines() do
                    local t = line:match("pts_time:([%d%.%-]+)")
                    if t then
                        local rel = tonumber(t)
                        if rel then
                            local cut_frame = start_frame + math.floor(rel * source_fps + 0.5)
                            local cut_tl_frame = clip_start + (cut_frame - (tonumber(clip.left_offset or 0) or 0))
                            local distance = math.abs(cut_frame - source_frame)
                            local edge_visible = top_opaque_clip_at(edge_frame) == clip
                            local cut_visible = cut_tl_frame >= clip_start
                                and cut_tl_frame < clip_end
                                and top_opaque_clip_at(cut_tl_frame) == clip
                            local hidden_boundary_cut = edge_visible
                                and cut_tl_frame >= clip_start
                                and cut_tl_frame < clip_end
                                and top_opaque_clip_at(cut_tl_frame) ~= clip
                                and (
                                    (direction == "before" and cut_tl_frame > edge_frame)
                                    or (direction == "after" and cut_tl_frame < edge_frame)
                                )
                            if direction == "before" and cut_tl_frame > edge_frame and not hidden_boundary_cut then
                                cut_visible = false
                            elseif direction == "after" and cut_tl_frame < edge_frame and not hidden_boundary_cut then
                                cut_visible = false
                            end
                            local valid_cut = cut_visible or hidden_boundary_cut
                            if valid_cut and distance <= tolerance_frames and (not best_distance or distance < best_distance) then
                                best_distance = distance
                                best_tl_frame = cut_tl_frame
                                best_kind = hidden_boundary_cut and "hidden_boundary_cut" or "visible_cut"
                                last_distance = distance
                            else
                                last_distance = nil
                            end
                        end
                    end
                    local score = line:match("lavfi%.scene_score=([%d%.%-]+)") or line:match("scene_score[:=]([%d%.%-]+)")
                    if score and last_distance and last_distance == best_distance then
                        best_score = tonumber(score) or best_score
                    end
                    if os.time() - start_time > (tonumber(params.nested_boundary_probe_timeout or 8) or 8) * 3 then
                        break
                    end
                end
                pcall(function() handle:close() end)
            end

            if best_distance then
                dlog(string.format(
                    "覆盖边界短镜头候选: edge=%d source_frame=%d distance=%d score=%.3f fps=%.3f kind=%s",
                    edge_frame,
                    math.floor(source_frame + 0.5),
                    best_distance,
                    tonumber(best_score or 0) or 0,
                    source_fps,
                    tostring(best_kind or "visible_cut")
                ))
                source_scene_near_cache[key] = {
                    distance = best_distance,
                    score = best_score or 0,
                    timeline_frame = best_tl_frame,
                    kind = best_kind or "visible_cut",
                }
                return best_distance, best_score or 0, best_kind or "visible_cut"
            end
            source_scene_near_cache[key] = false
            return nil
        end
        local function add_overlay_boundary_record(frame, lower_clip, upper_clip, reason, duration_frames)
            if frame == nil or frame < 0 or boundary_seen[frame] then return end
            if has_io_range and (frame < io_in or frame >= io_out) then return end
            if not is_regular_visible_video(lower_clip) then
                -- 露出来的是复合/Fusion本身时，普通模式不猜内部画面；交给精查/复杂模式。
                return
            end
            duration_frames = math.max(1, tonumber(duration_frames or 1) or 1)
            boundary_seen[frame] = true
            local upper_name = upper_clip and upper_clip.name or "上层片段"
            local lower_name = lower_clip and lower_clip.name or "下层片段"
            local is_nested_boundary = tostring(reason or ""):find("复合/Fusion", 1, true) ~= nil
            local marker_name = is_nested_boundary
                and "[BFD-MIX] 复合/Fusion外部覆盖边界"
                or "[BFD-MIX] 上层覆盖边界夹帧"
            local boundary_explain = is_nested_boundary
                and "判定: 这是顶层片段之间的外部覆盖边界，普通模式未进入复合/Fusion内部；上层边界让下层短暂露出，疑似漏帧/夹帧。"
                or "判定: 上层较长片段边界让下层最后/最前一帧仍在最终画面露出，疑似漏帧/夹帧。"
            local lower_source_fps = lower_clip and tonumber(lower_clip.source_fps or 0) or 0
            if lower_source_fps <= 0 then lower_source_fps = timeline_fps end
            local lower_source_start_frame = lower_clip
                and ((tonumber(lower_clip.left_offset or 0) or 0)
                    + (frame - (tonumber(lower_clip.timeline_start_frame or 0) or 0)))
                or 0
            table.insert(overlay_stuck_records, {
                classification = "error",
                marker_color = config.MARKER_COLORS.ERROR,
                marker_name = marker_name,
                timeline_start_frame = frame,
                timeline_end_frame = frame + duration_frames,
                timeline_start_tc = Analyzer.frame_to_timecode(frame, timeline_fps),
                timeline_end_tc = Analyzer.frame_to_timecode(frame + duration_frames, timeline_fps),
                source_file = lower_clip and lower_clip.file_path or nil,
                source_start_sec = lower_clip and (lower_source_start_frame / lower_source_fps) or 0,
                source_duration_sec = duration_frames / lower_source_fps,
                duration_frames = duration_frames,
                visual_window_start_frame = frame,
                visual_window_end_frame = frame + duration_frames,
                note = string.format(
                    "%s\n位置: %s\n普通镜头实际露出: %d帧\n下层: 轨道%d %s\n上层: 轨道%d %s\n%s",
                    marker_name:gsub("^%[BFD%-MIX%]%s*", ""),
                    reason or "覆盖开始前一帧",
                    duration_frames,
                    lower_clip and (lower_clip.track_index or 1) or 1,
                    lower_name,
                    upper_clip and (upper_clip.track_index or 1) or 1,
                    upper_name,
                    boundary_explain
                ),
            })
            overlay_boundary_count = overlay_boundary_count + 1
        end
        for _, upper in ipairs(clips) do
            if upper.is_enabled == false then goto continue_overlay_boundary end
            if (upper.opacity or 100) <= 0 then goto continue_overlay_boundary end
            local upper_dur = tonumber(upper.source_duration_frames or 0) or 0
            local upper_track = tonumber(upper.track_index or 1) or 1
            if upper_track <= 1 or upper_dur < min_upper_frames then goto continue_overlay_boundary end
            if not Analyzer.is_fully_opaque(upper, overlay_config, full_threshold) then goto continue_overlay_boundary end

            local edge = tonumber(upper.timeline_start_frame or 0) or 0
            local before = edge - 1
            local after = edge
            local top_before, before_track = top_opaque_clip_at(before)
            local top_after = top_opaque_clip_at(after)
            if top_after == upper and top_before and top_before ~= upper then
                local lower_track = tonumber(top_before.track_index or 1) or 1
                if lower_track < upper_track and clip_active_at(top_before, after) then
                    local reason = nil
                    local source_jump = nil
                    if same_file_pair(top_before, upper) then
                        local lower_start = tonumber(top_before.timeline_start_frame or 0) or 0
                        local lower_left = tonumber(top_before.left_offset or 0) or 0
                        local lower_source_next = lower_left + (before - lower_start) + 1
                        local upper_left = tonumber(upper.left_offset or 0) or 0
                        source_jump = math.abs(upper_left - lower_source_next)
                    end
                    reason = boundary_reason_for(top_before, upper, "同源素材覆盖边界", source_jump)
                    if reason then
                        if boundary_needs_short_visible_run(top_before, upper) then
                            local exposure_frames, exposure_start = visible_run_before(edge, top_before, stuck_frames)
                            if exposure_frames > 0 and exposure_frames <= stuck_frames then
                                add_overlay_boundary_record(exposure_start, top_before, upper, reason, exposure_frames)
                            else
                                local distance, score, cut_kind = source_scene_cut_near_boundary(before, top_before, stuck_frames, "before")
                                if distance then
                                    local extra_reason = (cut_kind == "hidden_boundary_cut")
                                        and ("，下层源内镜头切换被上层遮挡，边界前只露出±" .. tostring(distance) .. "帧")
                                        or ("，下层露出帧附近存在源内镜头切换±" .. tostring(distance) .. "帧")
                                    add_overlay_boundary_record(
                                        before,
                                        top_before,
                                        upper,
                                        reason .. extra_reason,
                                        1
                                    )
                                end
                            end
                        else
                            local mark_frame = before
                            local mark_duration = 1
                            if is_nested_clip(upper) then
                                local lower_start = tonumber(top_before.timeline_start_frame or 0) or 0
                                mark_frame = math.max(lower_start, edge - math.max(1, stuck_frames))
                                mark_duration = math.max(1, before - mark_frame + 1)
                            end
                            add_overlay_boundary_record(mark_frame, top_before, upper, reason, mark_duration)
                        end
                    end
                end
            end

            local upper_end = edge + upper_dur
            local before_end = upper_end - 1
            local after_end = upper_end
            local top_before_end = top_opaque_clip_at(before_end)
            local top_after_end, after_end_track = top_opaque_clip_at(after_end)
            if top_before_end == upper and top_after_end and top_after_end ~= upper then
                local lower_track = tonumber(top_after_end.track_index or 1) or 1
                if lower_track < upper_track and clip_active_at(top_after_end, before_end) then
                    local reason = nil
                    local source_jump = nil
                    if same_file_pair(top_after_end, upper) then
                        local lower_start = tonumber(top_after_end.timeline_start_frame or 0) or 0
                        local lower_left = tonumber(top_after_end.left_offset or 0) or 0
                        local lower_source_after = lower_left + (after_end - lower_start)
                        local upper_left = tonumber(upper.left_offset or 0) or 0
                        local upper_source_next = upper_left + upper_dur
                        source_jump = math.abs(lower_source_after - upper_source_next)
                    end
                    reason = boundary_reason_for(top_after_end, upper, "同源素材覆盖结束边界", source_jump)
                    if reason then
                        if boundary_needs_short_visible_run(top_after_end, upper) then
                            local exposure_frames, exposure_start = visible_run_after(after_end, top_after_end, stuck_frames)
                            if exposure_frames > 0 and exposure_frames <= stuck_frames then
                                add_overlay_boundary_record(exposure_start, top_after_end, upper, reason, exposure_frames)
                            else
                                local distance, score, cut_kind = source_scene_cut_near_boundary(after_end, top_after_end, stuck_frames, "after")
                                if distance then
                                    local extra_reason = (cut_kind == "hidden_boundary_cut")
                                        and ("，下层源内镜头切换被上层遮挡，边界后只露出±" .. tostring(distance) .. "帧")
                                        or ("，下层露出帧附近存在源内镜头切换±" .. tostring(distance) .. "帧")
                                    add_overlay_boundary_record(
                                        after_end,
                                        top_after_end,
                                        upper,
                                        reason .. extra_reason,
                                        1
                                    )
                                end
                            end
		                        else
		                            local exposure_frames, exposure_start = visible_run_after(after_end, top_after_end, stuck_frames)
		                            local source_short_frames = nil
	                            if is_nested_clip(upper) and not is_fusion_nested_clip(upper) then
	                                source_short_frames = source_short_run_after_boundary(after_end, top_after_end, stuck_frames)
	                            end
	                            if source_short_frames then
	                                add_overlay_boundary_record(
	                                    after_end,
	                                    top_after_end,
	                                    upper,
	                                    reason .. "，下层源内" .. tostring(source_short_frames) .. "帧后切走",
	                                    source_short_frames
	                                )
	                            elseif exposure_frames and exposure_frames > 0 and exposure_frames <= stuck_frames then
	                                add_overlay_boundary_record(exposure_start, top_after_end, upper, reason, exposure_frames)
	                            else
	                                dlog(string.format(
	                                    "跳过复合/Fusion结束边界: frame=%d lower_visible_run=%s upper=%s lower=%s",
	                                    after_end,
	                                    tostring(exposure_frames),
	                                    tostring(upper.name or "?"),
	                                    tostring(top_after_end and top_after_end.name or "?")
	                                ))
	                            end
	                        end
	                    end
	                end
	            end
            ::continue_overlay_boundary::
        end

        if overlay_count > 0 or overlay_soft_count > 0 or overlay_boundary_count > 0 then
            dlog(string.format("阶段4.7: 发现 %d 个叠加夹帧(error) + %d 个半透明遮挡(suspect) + %d 个覆盖边界夹帧", overlay_count, overlay_soft_count, overlay_boundary_count))
            print(string.format("[BFD] 多轨道叠加检测: %d 个夹帧(完全可见) + %d 个半透明遮挡 + %d 个覆盖边界夹帧", overlay_count, overlay_soft_count, overlay_boundary_count))
        else
            dlog("阶段4.7: 未发现叠加夹帧")
        end
    end

    -- 重建 file_dedup，仅包含需要FFmpeg分析的素材
    local ffmpeg_file_dedup = {}
    for _, clip in ipairs(ffmpeg_clips) do
        local fp = clip.file_path
        if fp then
            if not ffmpeg_file_dedup[fp] then ffmpeg_file_dedup[fp] = {} end
            table.insert(ffmpeg_file_dedup[fp], clip)
        end
    end
    local ffmpeg_unique_files = {}
    for path, _ in pairs(ffmpeg_file_dedup) do table.insert(ffmpeg_unique_files, path) end

    if complex_render_done then
        local ffmpeg = shared_ffmpeg_for_late_pass
        if not (ffmpeg and ffmpeg.ffmpeg_path) then
            ffmpeg = FFmpegRunner:new()
            if ffmpeg:find_ffmpeg() then
                shared_ffmpeg_for_late_pass = ffmpeg
                config._cached_ffmpeg_path = ffmpeg.ffmpeg_path
            else
                ffmpeg = nil
            end
        end

        if ffmpeg then
            if black_border_enabled() and (tonumber(params.black_border_matte_aspect or 0) or 0) <= 0 then
                local explicit_border = explicit_black_border_enabled()
                local border_count = 0
                for file_path, file_clips in pairs(ffmpeg_file_dedup) do
                    for _, clip in ipairs(file_clips) do
                        local lo = tonumber(clip.left_offset or 0) or 0
                        local dur = tonumber(clip.source_duration_frames or 0) or 0
                        local clip_start_frame = tonumber(clip.timeline_start_frame or 0) or 0
                        local clip_end_frame = clip_start_frame + dur
                        local local_start_frame = lo
                        local local_duration_frames = dur
                        local timeline_start_frame = clip_start_frame
                        if has_io_range then
                            local visible_start = math.max(clip_start_frame, io_in)
                            local visible_end = math.min(clip_end_frame, io_out)
                            if visible_end <= visible_start then
                                local_duration_frames = 0
                            else
                                local_start_frame = lo + (visible_start - clip_start_frame)
                                local_duration_frames = visible_end - visible_start
                                timeline_start_frame = visible_start
                            end
                        end
                        if local_duration_frames > 0 then
                            local adjustment_effects = adjustment_effects_for_span(
                                clips,
                                timeline_start_frame,
                                timeline_start_frame + local_duration_frames,
                                clip.track_index or 1
                            )
                            local should_probe_border = explicit_border
                                or clip_has_basic_border_risk(clip, adjustment_effects)
                            if should_probe_border then
                                border_count = border_count + append_black_border_results(ffmpeg, file_path, clip, {
                                    clip_start_sec = local_start_frame / timeline_fps,
                                    clip_duration_sec = local_duration_frames / timeline_fps,
                                    timeline_start_frame = timeline_start_frame,
                                    adjustment_effects = adjustment_effects,
                                    timeout = 45,
                                })
                            end
                        end
                    end
                end
                if border_count > 0 then
                    dlog("复杂模式补充普通黑边检测命中 " .. tostring(border_count))
                    print(string.format("[BFD] 复杂模式补充: 普通黑边检测发现 %d 处", border_count))
                end
            end

            local mixed_cut_records = detect_source_mixed_cuts(ffmpeg, ffmpeg_clips, clips, timeline_fps, params)
            if #mixed_cut_records > 0 then
                for _, mixed in ipairs(mixed_cut_records) do
                    table.insert(ffmpeg_results, mixed)
                end
                print(string.format("[BFD] 复杂模式补充: 混剪源内夹帧发现 %d 个可见短镜头", #mixed_cut_records))
            else
                dlog("复杂模式补充: 混剪源内夹帧未发现可见短镜头")
            end
        else
            dlog("复杂模式补充普通检测: FFmpeg不可用，跳过普通黑边/源内短镜头补充")
        end
    end

    if not complex_render_done then
    -- ----------------------------------------------------------
    -- 阶段5: 检查FFmpeg
    -- ----------------------------------------------------------
    dlog("阶段5: 检查FFmpeg...")
    print("[BFD] [3/7] 正在检查 FFmpeg...")
    local ffmpeg = FFmpegRunner:new()
    if not ffmpeg:find_ffmpeg() then
        dlog("FATAL: 未找到FFmpeg，返回")
        UIBridge.show_error(compat, "未找到 FFmpeg。\n\n" .. ffmpeg:get_install_hint())
        return
    end
    dlog("阶段5: FFmpeg找到: " .. tostring(ffmpeg:get_version_string()))
    config._cached_ffmpeg_path = ffmpeg.ffmpeg_path  -- 缓存给帧指纹提取用
    print("[BFD] FFmpeg: " .. ffmpeg:get_version_string())

    if not ffmpeg:check_blackdetect() then
        dlog("FATAL: blackdetect滤镜不可用，返回")
        UIBridge.show_error(compat,
            "当前 FFmpeg 版本不支持 blackdetect 滤镜，请升级 FFmpeg 到更新版本。")
        return
    end
    dlog("阶段5: blackdetect可用")
    print("[BFD] blackdetect 滤镜可用 ✓")
    check_progress_panel("FFmpeg就绪", 42)

    -- 日志输出检测参数
    local marker_type_info = ""
    for k, v in pairs(params.marker_types or {}) do
        if v then marker_type_info = marker_type_info .. k .. " " end
    end
    print(string.format(
        "[BFD] 参数: 夹帧≤%d帧 可疑≤%d帧 pix_th=%.3f 标记类型: %s",
        params.stuck_frames or config.CLASSIFICATION.STUCK_FRAMES,
        params.suspect_frames or config.CLASSIFICATION.SUSPECT_FRAMES,
        params.pix_th,
        marker_type_info
    ))

    -- ----------------------------------------------------------
    -- 阶段6: FFmpeg分析
    -- ----------------------------------------------------------

    local nested_render_cleanup = {}
    local function build_visible_merge_segments(all_clips, eligible_clips)
        local eligible = {}
        for _, c in ipairs(eligible_clips or {}) do
            eligible[c] = true
        end

        local boundaries = {}
        local function add_boundary(frame)
            frame = tonumber(frame)
            if frame then
                boundaries[frame] = true
            end
        end

        for _, clip in ipairs(all_clips or {}) do
            local cs = tonumber(clip.timeline_start_frame or 0) or 0
            local ce = cs + (tonumber(clip.source_duration_frames or 0) or 0)
            if has_io_range then
                cs = math.max(cs, io_in)
                ce = math.min(ce, io_out)
            end
            if ce > cs then
                add_boundary(cs)
                add_boundary(ce)
            end
        end

        local points = {}
        for frame, _ in pairs(boundaries) do
            table.insert(points, frame)
        end
        table.sort(points)

        local segments = {}
        local skipped_by_cover = 0
        local skipped_uncertain = 0
        local nested_candidates = 0
        local nested_rendered = 0
        local nested_failed = 0
        local retime_candidates = 0
        local retime_rendered = 0
        local retime_failed = 0

        for i = 1, #points - 1 do
            local s = points[i]
            local e = points[i + 1]
            if e > s then
                local top_clip = nil
                local top_track = -1
                local skipped_uncertain_here = false
                for _, clip in ipairs(all_clips or {}) do
                    if clip.is_enabled ~= false and (clip.opacity or 100) > 0 then
                        local cs = tonumber(clip.timeline_start_frame or 0) or 0
                        local ce = cs + (tonumber(clip.source_duration_frames or 0) or 0)
                        if cs < e and ce > s then
                            local track = tonumber(clip.track_index or 1) or 1
                            local analyzable = eligible[clip]
                                or (params.render_nested_segments and clip.media_type == "nested")
                            if analyzable and track >= top_track then
                                top_track = track
                                top_clip = clip
                            elseif not analyzable and blocks_basic_black_border(clip) then
                                skipped_uncertain_here = true
                            end
                        end
                    end
                end

                if top_clip then
                    if eligible[top_clip] then
                        local clip_start = tonumber(top_clip.timeline_start_frame or 0) or 0
                        local left_offset = tonumber(top_clip.left_offset or 0) or 0
                        local source_start = left_offset + (s - clip_start)
                        local source_dur = e - s
                        local top_track = tonumber(top_clip.track_index or 1) or 1
                        local adjustment_effects = adjustment_effects_for_span(all_clips, s, e, top_track)
                        local adjustment_sig = adjustment_signature(adjustment_effects)
                        if top_clip.retime_requires_visible_render and source_dur > 0 then
                            retime_candidates = retime_candidates + 1
                            local prev = segments[#segments]
                            if prev and prev.needs_timeline_render and prev.clip == top_clip
                                and (prev.adjustment_signature or "") == adjustment_sig
                                and math.abs((prev.timeline_start_frame + prev.duration_frames) - s) < 0.001 then
                                prev.duration_frames = prev.duration_frames + source_dur
                                prev.duration_sec = prev.duration_frames / timeline_fps
                            else
                                table.insert(segments, {
                                    needs_timeline_render = true,
                                    render_reason = top_clip.retime_has_curve and "变速曲线timeMap" or "变速timeMap",
                                    clip = top_clip,
                                    timeline_start_frame = s,
                                    duration_frames = source_dur,
                                    duration_sec = source_dur / timeline_fps,
                                    adjustment_effects = adjustment_effects,
                                    adjustment_signature = adjustment_sig,
                                })
                            end
                        elseif source_start >= 0 and source_dur > 0 and top_clip.file_path and top_clip.file_path ~= "" then
                            local prev = segments[#segments]
                            if prev and prev.clip == top_clip
                                and (prev.adjustment_signature or "") == adjustment_sig
                                and math.abs((prev.timeline_start_frame + prev.duration_frames) - s) < 0.001
                                and math.abs((prev.source_start_frame + prev.duration_frames) - source_start) < 0.001 then
                                prev.duration_frames = prev.duration_frames + source_dur
                                prev.duration_sec = prev.duration_frames / timeline_fps
                                prev.uncertain_upper = prev.uncertain_upper or skipped_uncertain_here
                            else
                                table.insert(segments, {
                                    file_path = top_clip.file_path,
                                    start_sec = source_start / timeline_fps,
                                    duration_sec = source_dur / timeline_fps,
                                    clip = top_clip,
                                    timeline_start_frame = s,
                                    source_start_frame = source_start,
                                    source_fps = timeline_fps,
                                    duration_frames = source_dur,
                                    uncertain_upper = skipped_uncertain_here,
                                    adjustment_effects = adjustment_effects,
                                    adjustment_signature = adjustment_sig,
                                })
                            end
                        end
                    elseif params.render_nested_segments and top_clip.media_type == "nested" then
                        local source_dur = e - s
                        if source_dur > 0 then
                            nested_candidates = nested_candidates + 1
                            local prev = segments[#segments]
                            if prev and prev.needs_nested_render and prev.clip == top_clip
                                and math.abs((prev.timeline_start_frame + prev.duration_frames) - s) < 0.001 then
                                prev.duration_frames = prev.duration_frames + source_dur
                                prev.duration_sec = prev.duration_frames / timeline_fps
                            else
                                table.insert(segments, {
                                    needs_nested_render = true,
                                    clip = top_clip,
                                    timeline_start_frame = s,
                                    duration_frames = source_dur,
                                    duration_sec = source_dur / timeline_fps,
                                })
                            end
                        end
                    elseif top_clip.skip_ffmpeg then
                        skipped_uncertain = skipped_uncertain + 1
                    else
                        skipped_by_cover = skipped_by_cover + 1
                    end
                elseif skipped_uncertain_here then
                    skipped_uncertain = skipped_uncertain + 1
                end
            end
        end

        if params.render_nested_segments then
            local edge_guard = tonumber(params.nested_render_guard_frames or 3) or 3
            local edge_limit = tonumber(params.nested_edge_probe_limit or 40) or 40
            local edge_seen = {}
            local edge_added = 0
            local function clip_bounds(clip)
                local cs = tonumber(clip.timeline_start_frame or 0) or 0
                local ce = cs + (tonumber(clip.source_duration_frames or 0) or 0)
                return cs, ce
            end
            local function clip_active_at(clip, frame)
                local cs, ce = clip_bounds(clip)
                return cs <= frame and frame < ce
            end
            local function top_clip_at(frame)
                local top_clip = nil
                local top_track = -1
                for _, clip in ipairs(all_clips or {}) do
                    if clip.is_enabled ~= false and (clip.opacity or 100) > 0 and clip_active_at(clip, frame) then
                        local track = tonumber(clip.track_index or 1) or 1
                        if track >= top_track then
                            top_track = track
                            top_clip = clip
                        end
                    end
                end
                return top_clip, top_track
            end
            local function has_nested_under(frame, upper_track)
                for _, clip in ipairs(all_clips or {}) do
                    if clip.is_enabled ~= false and (clip.opacity or 100) > 0
                        and clip.media_type == "nested"
                        and (tonumber(clip.track_index or 1) or 1) < upper_track
                        and clip_active_at(clip, frame)
                    then
                        return true
                    end
                end
                return false
            end
            local candidate_edges = {}
            for _, clip in ipairs(all_clips or {}) do
                if clip.is_enabled ~= false and (clip.opacity or 100) > 0 and clip.media_type ~= "nested" then
                    local cs, ce = clip_bounds(clip)
                    local upper_track = tonumber(clip.track_index or 1) or 1
                    for _, edge in ipairs({ cs, ce }) do
                        if (not has_io_range or (edge >= io_in and edge <= io_out)) then
                            local before = edge - 1
                            local after = edge
                            local top_before = top_clip_at(before)
                            local top_after = top_clip_at(after)
                            local nested_switch = (top_before and top_before.media_type == "nested" and top_after == clip)
                                or (top_before == clip and top_after and top_after.media_type == "nested")
                            local edge_is_visible = nested_switch
                            local covers_nested = has_nested_under(before, upper_track) or has_nested_under(after, upper_track)
                            if edge_is_visible and covers_nested then
                                candidate_edges[edge] = true
                            end
                        end
                    end
                end
            end
            for point, _ in pairs(candidate_edges) do
                if edge_added >= edge_limit then break end
                local s = math.floor(point - edge_guard)
                local e = math.floor(point + edge_guard + 1)
                if has_io_range then
                    s = math.max(s, io_in)
                    e = math.min(e, io_out)
                end
                local key = tostring(s) .. ":" .. tostring(e)
                if e > s + 1 and not edge_seen[key] then
                    edge_seen[key] = true
                    edge_added = edge_added + 1
                    table.insert(segments, {
                        needs_nested_render = true,
                        nested_edge_probe = true,
                        clip = { name = "上层遮挡复合/Fusion边界", media_type = "nested" },
                        timeline_start_frame = s,
                        duration_frames = e - s,
                        duration_sec = (e - s) / timeline_fps,
                        nested_scene_min_frame = 1,
                    })
                end
            end
            if edge_added > 0 then
                nested_candidates = nested_candidates + edge_added
                dlog(string.format("阶段6(成片): 追加复合/Fusion邻接边界精查窗口 %d 个", edge_added))
            end
        end

        if params.render_nested_segments or retime_candidates > 0 then
            local rendered_segments = {}
            local sep = package.config:sub(1, 1)
            local cache_dir = params.complex_cache_dir
            if not cache_dir or cache_dir == "" then
                cache_dir = config.get_home() .. sep .. ".qinghe_bfd" .. sep .. "render_cache"
            end
            local r_resolve = compat.resolve
            local r_project = nil
            pcall(function()
                if r_resolve then
                    local pm = r_resolve:GetProjectManager()
                    if pm then r_project = pm:GetCurrentProject() end
                end
            end)
            for index, segment in ipairs(segments) do
                if segment.needs_nested_render or segment.needs_timeline_render then
                    local original_s = segment.timeline_start_frame or 0
                    local original_e = original_s + (segment.duration_frames or 0)
                    local guard = segment.needs_timeline_render and 0
                        or (tonumber(params.nested_render_guard_frames or 3) or 3)
                    local s = math.max(has_io_range and io_in or 0, original_s - guard)
                    local e = original_e + guard
                    if has_io_range then e = math.min(io_out, e) end
                    local prefix = segment.needs_timeline_render and "bfd_retime" or "bfd_nested"
                    local render_name = string.format("%s_%04d_%d_%d", prefix, index, s, e)
                    if segment.needs_timeline_render then
                        print(string.format("[BFD] 变速成片精查: 渲染可见区间 %d-%d 帧", s, e))
                    else
                        print(string.format("[BFD] 复合/Fusion精查: 渲染边缘小段 %d-%d 帧", s, e))
                    end
                    local path, render_err = render_timeline_interval_for_analysis(
                        r_resolve, r_project, timeline, cache_dir, sep, render_name, s, e, timeline_fps
                    )
                    if path then
                        segment.file_path = path
                        segment.start_sec = 0
                        segment.source_start_frame = 0
                        segment.timeline_start_frame = s
                        segment.duration_frames = math.max(1, e - s)
                        segment.duration_sec = segment.duration_frames / timeline_fps
                        segment.nested_guard_frames = guard
                        if segment.nested_scene_min_frame then
                            segment.nested_scene_min_frame = math.max(0, math.floor(tonumber(segment.nested_scene_min_frame) or 0))
                        end
                        segment.rendered_nested = true
                        segment.rendered_timeline = segment.needs_timeline_render == true
                        segment.cleanup_path = path
                        segment.needs_nested_render = nil
                        segment.needs_timeline_render = nil
                        table.insert(nested_render_cleanup, path)
                        table.insert(rendered_segments, segment)
                        if segment.rendered_timeline then
                            retime_rendered = retime_rendered + 1
                        else
                            nested_rendered = nested_rendered + 1
                        end
                    else
                        if segment.needs_timeline_render then
                            retime_failed = retime_failed + 1
                            dlog("变速成片精查渲染失败: " .. tostring(render_err))
                        else
                            nested_failed = nested_failed + 1
                            dlog("复合/Fusion精查渲染失败: " .. tostring(render_err))
                        end
                    end
                else
                    table.insert(rendered_segments, segment)
                end
            end
            segments = rendered_segments
        end

        dlog(string.format(
            "阶段6(成片): 顶层可见区间=%d, 遮挡跳过=%d, 非FFmpeg顶层跳过=%d, 复合候选=%d, 复合渲染=%d, 复合失败=%d, 变速候选=%d, 变速渲染=%d, 变速失败=%d",
            #segments, skipped_by_cover, skipped_uncertain, nested_candidates, nested_rendered, nested_failed,
            retime_candidates, retime_rendered, retime_failed
        ))
        return segments
    end

    if default_merge_mode then
        -- ============================================================
        -- 成片模式：合并所有片段为一个连续流，一次FFmpeg blackdetect
        -- 优势：一次分析代替N次逐文件分析，速度快数倍，尤其适合多源文件项目
        -- ============================================================
        dlog("阶段6(成片): 构建合并片段列表, ffmpeg_clips=" .. #ffmpeg_clips)
        print(string.format("[BFD] 成片模式: 合并 %d 个片段，一次FFmpeg分析", #ffmpeg_clips))

        -- 构建concat输入列表 + 累计时长映射表
        local segment_list = {}     -- {file_path, start_sec, duration_sec}
        local seg_clips = {}        -- 对应的clip引用（用于结果映射）
        local cum_end = {}          -- 每个segment结束时的累计concat时长(秒)
        local cum_total = 0

        segment_list = build_visible_merge_segments(clips, ffmpeg_clips)
        table.sort(segment_list, function(a, b)
            return (a.timeline_start_frame or 0) < (b.timeline_start_frame or 0)
        end)

        for _, segment in ipairs(segment_list) do
            local dur_sec = segment.duration_sec or 0
            if dur_sec > 0 then
                table.insert(seg_clips, segment.clip)
                cum_total = cum_total + dur_sec
                table.insert(cum_end, cum_total)
            end
        end

        dlog("阶段6(成片): " .. #segment_list .. " 个有效片段, 总时长="
            .. string.format("%.1f", cum_total) .. "秒")

        if #segment_list > 0 then
            local border_count = 0
            local nested_direct_count = 0
            local nested_flash_count = 0
            if black_border_enabled() and (tonumber(params.black_border_matte_aspect or 0) or 0) <= 0 then
                local explicit_border = explicit_black_border_enabled()
                for _, segment in ipairs(segment_list) do
                    if segment.file_path and segment.clip and (explicit_border or not segment.uncertain_upper) then
                        local should_probe_border = explicit_border
                            or clip_has_basic_border_risk(segment.clip, segment.adjustment_effects)
                        if not should_probe_border then
                            goto continue_basic_border_segment
                        end
		                        border_count = border_count + append_black_border_results(ffmpeg, segment.file_path, segment.clip, {
		                            clip_start_sec = segment.start_sec,
		                            clip_duration_sec = segment.duration_sec,
		                            timeline_start_frame = segment.timeline_start_frame,
		                            adjustment_effects = segment.adjustment_effects,
		                            timeout = 45,
		                        })
                    end
                    ::continue_basic_border_segment::
                end
            end
            for _, segment in ipairs(segment_list) do
                if segment.rendered_nested and segment.file_path then
                    local nested_segs, _, nested_err = ffmpeg:detect_black_frames(segment.file_path, {
                        pix_th = params.pix_th,
                        pic_th = params.nested_render_pic_th or 0.60,
                        min_duration = params.min_duration,
                        timeout = 60,
                    })
                    if nested_segs and #nested_segs > 0 then
                        local direct_segments = {}
                        for _, seg in ipairs(nested_segs) do
                            table.insert(direct_segments, {
                                start = seg.start or 0,
                                end_ = seg.end_ or seg.start or 0,
                                duration = seg.duration or 0,
                                timeline_frame = (segment.timeline_start_frame or 0)
                                    + math.floor((seg.start or 0) * timeline_fps + 0.5),
                            })
                            nested_direct_count = nested_direct_count + 1
                        end
                        table.insert(ffmpeg_results, {
                            clip = segment.clip,
                            segments = direct_segments,
                            source_file = segment.file_path,
                            rendered_nested_direct = true,
                        })
                    elseif nested_err then
                        dlog("复合/Fusion精查直接分析警告: " .. tostring(nested_err))
                    end

                    local flash_segs, flash_err = ffmpeg:detect_short_scene_segments(segment.file_path, {
                        fps = timeline_fps,
                        timeout = 60,
                        min_frame = tonumber(segment.nested_scene_min_frame or segment.nested_guard_frames or 0) or 0,
                        max_frame = math.max(0, (tonumber(segment.duration_frames or 0) or 0) - 1),
                        max_span = tonumber(params.nested_scene_max_span or 3) or 3,
                        scene_threshold = tonumber(params.nested_scene_threshold or 0.20) or 0.20,
                    })
                    if flash_segs and #flash_segs > 0 then
                        local flash_segments = {}
                        for _, seg in ipairs(flash_segs) do
                            local frame_index = tonumber(seg.scene_cut_start_frame)
                                or tonumber(seg.flash_frame_index)
                                or math.floor((seg.start or 0) * timeline_fps + 0.5)
                            table.insert(flash_segments, {
                                start = seg.start or 0,
                                end_ = seg.end_ or seg.start or 0,
                                duration = seg.duration or (1 / timeline_fps),
                                timeline_frame = (segment.timeline_start_frame or 0) + frame_index,
                                nested_short_scene = true,
                                is_mixed_cut = true,
                                force_classification = seg.force_classification,
                                force_marker_name = seg.force_marker_name,
                                force_note = string.format(
                                    "%s\n来源: %s",
                                    seg.force_note or "复合/Fusion内部短镜头夹帧",
                                    (segment.clip and segment.clip.name) or segment.file_path or "复合/Fusion片段"
                                ),
                            })
                            nested_flash_count = nested_flash_count + 1
                        end
                        table.insert(ffmpeg_results, {
                            clip = segment.clip,
                            segments = flash_segments,
                            source_file = segment.file_path,
                            rendered_nested_scene_flash = true,
                        })
                    elseif flash_err then
                        dlog("复合/Fusion精查内部短镜头分析警告: " .. tostring(flash_err))
                    end
                end
            end
            if nested_direct_count > 0 then
                dlog("阶段6(成片): 复合/Fusion精查直接命中黑帧段 " .. tostring(nested_direct_count))
            end
            if nested_flash_count > 0 then
                dlog("阶段6(成片): 复合/Fusion精查命中内部短镜头夹帧 " .. tostring(nested_flash_count))
            end
            if border_count > 0 then
                dlog("阶段6(成片): 黑边检测命中 " .. tostring(border_count))
                print(string.format("[BFD] 黑边检测: 发现 %d 处边缘黑边", border_count))
            end

            check_progress_panel("成片合并分析中", 55)
            local all_segs, concat_err = ffmpeg:detect_black_frames_concat(segment_list, params)
            if concat_err then
                table.insert(ffmpeg_errors, { name = "成片合并", error = concat_err })
            end

            all_segs = all_segs or {}
            dlog("阶段6(成片): 检测到 " .. #all_segs .. " 个黑帧段")

            -- 将concat时间映射回每个clip的source时间 + timeline位置
            for _, seg in ipairs(all_segs) do
                local b_start = seg.start
                local b_end = seg.end_

                for i = 1, #seg_clips do
                    local seg_dur = segment_list[i].duration_sec
                    local seg_cum_start = cum_end[i] - seg_dur

                    -- 检查黑帧段与当前片段是否有重叠
                    if seg_cum_start < b_end and cum_end[i] > b_start then
                        local overlap_start = math.max(b_start, seg_cum_start)
                        local overlap_end = math.min(b_end, cum_end[i])
                        local clip = seg_clips[i]

                        -- 以source文件时间存储(兼容下游分析器)
                        -- source_time = left_offset/fps + 片段内偏移
                        local segment = segment_list[i]
                        local segment_source_fps = (segment and segment.source_fps) or source_fps_for_clip(ffmpeg, clip, timeline_fps)
                        local source_base = (segment and segment.source_start_frame or clip.left_offset or 0) / segment_source_fps
                        local src_start = source_base + (overlap_start - seg_cum_start)
                        local src_end = source_base + (overlap_end - seg_cum_start)
                        local timeline_frame = nil
                        if segment then
                            timeline_frame = (segment.timeline_start_frame or 0)
                                + math.floor((overlap_start - seg_cum_start) * timeline_fps + 0.5)
                        end
                        local duration_frames = math.max(1, math.floor((overlap_end - overlap_start) * timeline_fps + 0.5))

                        local found = false
                        for _, fr in ipairs(ffmpeg_results) do
                            if fr.clip == clip then
                                table.insert(fr.segments, {
                                    start = src_start,
                                    end_ = src_end,
                                    duration = src_end - src_start,
                                    timeline_frame = timeline_frame,
                                    timeline_end_frame = timeline_frame and (timeline_frame + duration_frames) or nil,
                                    duration_frames = duration_frames,
                                    source_fps = segment_source_fps,
                                    concat_black = true,
                                })
                                found = true
                                break
                            end
                        end
                        if not found then
                            table.insert(ffmpeg_results, {
                                clip = clip,
                                segments = {{
                                    start = src_start,
                                    end_ = src_end,
                                    duration = src_end - src_start,
                                    timeline_frame = timeline_frame,
                                    timeline_end_frame = timeline_frame and (timeline_frame + duration_frames) or nil,
                                    duration_frames = duration_frames,
                                    source_fps = segment_source_fps,
                                    concat_black = true,
                                }},
                            })
                        end
                    end
                end
            end
        end
        if #nested_render_cleanup > 0 then
            for _, path in ipairs(nested_render_cleanup) do
                pcall(function() os.remove(path) end)
            end
            dlog("阶段6(成片): 已清理复合/Fusion精查临时文件 " .. #nested_render_cleanup .. " 个")
        end
        print(string.format("[BFD] 成片模式完成: %d个合并片段, 发现 %d 个黑帧段",
            #segment_list, #ffmpeg_results))
    else
        -- ============================================================
        -- 逐文件模式（原逻辑）：每个唯一源文件分析一次
        -- ============================================================
        dlog("阶段6(逐文件): FFmpeg分析, " .. #ffmpeg_unique_files .. " 个唯一源文件")
        print(string.format("[BFD] 开始分析 %d 个唯一源文件（已过滤低透明度素材）...", #ffmpeg_unique_files))
        local file_count = 0
        local source_black_confirm_cache = {}
        local function source_frame_is_black(file_path, source_frame, source_fps)
            if not ffmpeg or not ffmpeg.ffmpeg_path or not file_path or file_path == "" then return true end
            source_fps = tonumber(source_fps or 0) or 0
            if source_fps <= 0 then return true end
            local frame_index = math.max(0, math.floor(tonumber(source_frame or 0) or 0))
            local key = table.concat({ tostring(file_path), tostring(frame_index), string.format("%.3f", source_fps) }, "|")
            if source_black_confirm_cache[key] ~= nil then
                return source_black_confirm_cache[key]
            end

            local amount = math.max(1, math.min(100, math.floor(((tonumber(params.pic_th or 0.95) or 0.95) * 100) + 0.5)))
            local threshold = tonumber(params.black_confirm_threshold or 32) or 32
            local filter = string.format("blackframe=amount=%d:threshold=%d", amount, threshold)
            local prefix = ""
            if ffmpeg._bundled_lib_dir then
                prefix = 'DYLD_LIBRARY_PATH="' .. ffmpeg._bundled_lib_dir .. '" '
            end
            local cmd = string.format(
                '%s%s -timelimit %d -i %s -ss %.6f -frames:v 1 -vf "%s" -an -f null - 2>&1',
                prefix,
                ffmpeg:_quote_path(ffmpeg.ffmpeg_path),
                tonumber(params.black_confirm_timeout or 6) or 6,
                ffmpeg:_quote_path(file_path),
                frame_index / source_fps,
                filter
            )
            local confirmed = false
            local handle = io.popen(ffmpeg:_wrap_cmd(cmd), "r")
            if handle then
                local start_time = os.time()
                for line in handle:lines() do
                    local pblack = line:match("pblack:%s*([%d%.]+)") or line:match("pblack:([%d%.]+)")
                    if pblack and (tonumber(pblack) or 0) >= amount then
                        confirmed = true
                        break
                    end
                    if os.time() - start_time > (tonumber(params.black_confirm_timeout or 6) or 6) * 3 then
                        break
                    end
                end
                pcall(function() handle:close() end)
            else
                confirmed = true
            end
            source_black_confirm_cache[key] = confirmed
            return confirmed
        end

        for file_path, file_clips in pairs(ffmpeg_file_dedup) do
            file_count = file_count + 1
            local clip_name = file_clips[1] and file_clips[1].name or "未知"
            print(string.format("[BFD] 分析进度: %d/%d - %s (%d个镜头引用)",
                file_count, #ffmpeg_unique_files, clip_name, #file_clips))
            local ffmpeg_percent = 45
            if #ffmpeg_unique_files > 0 then
                ffmpeg_percent = 45 + math.floor((file_count / #ffmpeg_unique_files) * 25)
            end
            check_progress_panel(string.format("FFmpeg %d/%d", file_count, #ffmpeg_unique_files), ffmpeg_percent)

            -- 计算剪辑范围用于ffmpeg -ss/-to加速（取所有引用此文件剪辑的并集）
            local min_lo, max_end = nil, nil
            for _, c in ipairs(file_clips) do
                local lo = c.left_offset or 0
                local dur = c.source_duration_frames or 0
                if dur > 0 then
                    if not min_lo or lo < min_lo then min_lo = lo end
                    if not max_end or (lo + dur) > max_end then max_end = lo + dur end
                end
            end
            if min_lo and max_end then
                local file_source_fps = source_fps_for_clip(ffmpeg, file_clips[1], timeline_fps)
                params.clip_start_sec = min_lo / file_source_fps
                params.clip_duration_sec = (max_end - min_lo) / file_source_fps
            else
                params.clip_start_sec = nil
                params.clip_duration_sec = nil
            end

            -- 只分析一次该源文件
            local segments, _, err = ffmpeg:detect_black_frames(file_path, params)
            if err then
                table.insert(ffmpeg_errors, { name = clip_name, error = err })
            end

            if segments and #segments > 0 then
                -- 将同一个源文件的检测结果分发给所有引用该文件的镜头
                -- 同时根据每个镜头的裁剪范围过滤
                for _, clip in ipairs(file_clips) do
                    local clip_segments = {}
                    local lo = clip.left_offset or 0
                    local dur = clip.source_duration_frames or 0
                    local source_end_frame = lo + dur
                    local clip_source_fps = source_fps_for_clip(ffmpeg, clip, timeline_fps)

                    for _, seg in ipairs(segments) do
                        local seg_start_f = math.floor(seg.start * clip_source_fps)
                        local seg_end_f = math.floor(seg.end_ * clip_source_fps)

                        -- 黑帧/夹帧必须在最终画面可见；同源逐文件分析也要按时间线可见区间二次裁剪。
                        if dur == 0 or (seg_end_f > lo and seg_start_f < source_end_frame) then
                            local local_start_f = dur == 0 and seg_start_f or math.max(seg_start_f, lo)
                            local local_end_f = dur == 0 and seg_end_f or math.min(seg_end_f, source_end_frame)
                            local clip_start_frame = tonumber(clip.timeline_start_frame or 0) or 0
                            local visible_tl_start = clip_start_frame + (local_start_f - lo)
                            local visible_tl_end = clip_start_frame + (local_end_f - lo)
                            for _, iv in ipairs(get_final_visible_intervals(clip)) do
                                local iv_start = tonumber(iv.start or 0) or 0
                                local iv_end = tonumber(iv.end_ or iv["end"] or iv_start) or iv_start
                                local overlap_start = math.max(visible_tl_start, iv_start)
                                local overlap_end = math.min(visible_tl_end, iv_end)
                                if overlap_end > overlap_start then
                                    local clipped_source_start = lo + (overlap_start - clip_start_frame)
                                    local clipped_source_end = lo + (overlap_end - clip_start_frame)
                                    if source_frame_is_black(clip.file_path, clipped_source_start, clip_source_fps) then
                                        table.insert(clip_segments, {
                                            start = clipped_source_start / clip_source_fps,
                                            end_ = clipped_source_end / clip_source_fps,
                                            duration = (overlap_end - overlap_start) / timeline_fps,
                                            duration_frames = math.max(1, overlap_end - overlap_start),
                                            source_fps = clip_source_fps,
                                            timeline_frame = overlap_start,
                                            timeline_end_frame = overlap_end,
                                        })
                                    else
                                        dlog(string.format(
                                            "逐文件黑帧回填跳过: %s tl=%d source_frame=%d 非黑帧确认",
                                            tostring(clip.name or clip.file_path),
                                            overlap_start,
                                            math.floor(clipped_source_start + 0.5)
                                        ))
                                    end
                                end
                            end
                        end
                    end

                    if #clip_segments > 0 then
                        table.insert(ffmpeg_results, {
                            clip = clip,
                            segments = clip_segments,
                        })
                    end
                end
            end

            if explicit_black_border_enabled() and (tonumber(params.black_border_matte_aspect or 0) or 0) <= 0 then
                for _, clip in ipairs(file_clips) do
                    local lo = tonumber(clip.left_offset or 0) or 0
                    local dur = tonumber(clip.source_duration_frames or 0) or 0
                    local clip_start_frame = tonumber(clip.timeline_start_frame or 0) or 0
                    local clip_end_frame = clip_start_frame + dur
                    local local_start_frame = lo
                    local local_duration_frames = dur
                    local timeline_start_frame = clip_start_frame
                    if has_io_range then
                        local visible_start = math.max(clip_start_frame, io_in)
                        local visible_end = math.min(clip_end_frame, io_out)
                        if visible_end <= visible_start then
                            local_duration_frames = 0
                        else
                            local_start_frame = lo + (visible_start - clip_start_frame)
                            local_duration_frames = visible_end - visible_start
                            timeline_start_frame = visible_start
                        end
                    end
                    if local_duration_frames > 0 then
                        append_black_border_results(ffmpeg, file_path, clip, {
                            clip_start_sec = local_start_frame / timeline_fps,
                            clip_duration_sec = local_duration_frames / timeline_fps,
                            timeline_start_frame = timeline_start_frame,
                            adjustment_effects = adjustment_effects_for_span(clips, timeline_start_frame, timeline_start_frame + local_duration_frames, clip.track_index or 1),
                            timeout = 45,
                        })
                    end
                end
            end
        end
    end  -- else: 逐文件模式结束

    local mixed_cut_records = detect_source_mixed_cuts(ffmpeg, ffmpeg_clips, clips, timeline_fps, params)
    if #mixed_cut_records > 0 then
        for _, mixed in ipairs(mixed_cut_records) do
            table.insert(ffmpeg_results, mixed)
        end
        print(string.format("[BFD] 混剪源内夹帧: 发现 %d 个可见短镜头", #mixed_cut_records))
    else
        dlog("混剪源内夹帧: 未发现可见短镜头")
    end

    if #ffmpeg_errors > 0 then
        print(string.format("[BFD] 警告: %d 个文件分析失败", #ffmpeg_errors))
        for _, e in ipairs(ffmpeg_errors) do
            print(string.format("[BFD]   - %s: %s", e.name or "未知", e.error or "未知错误"))
        end
    end

    end  -- not complex_render_done: 复杂模式已通过渲染管道完成FFmpeg分析

    local has_problems = true
    if #ffmpeg_results == 0 and #opacity_results == 0 and #timeline_stuck_records == 0
       and #overlay_stuck_records == 0 and #corrupt_frame_records == 0 then
        -- 即使黑帧/夹帧/叠加/坏帧检测都为空，如果启用了重复检测，仍需继续
        local need_dup = (params.detect_duplicate ~= false and config.DUPLICATE.ENABLED)
        if not need_dup then
            has_problems = false
            dlog("未检测到任何问题(黑帧/透明度/夹帧/叠加/坏帧)")
            print("[BFD] 未检测到任何问题（含黑帧、透明度、夹帧、叠加、坏帧检测）")
            print("[BFD] 可能原因: 素材无黑帧、参数过于严格、文件路径不可访问")
        else
            dlog("FFmpeg/透明度/夹帧无结果，但重复检测已启用，继续阶段7-11")
        end
    end
    dlog("阶段6完成: ffmpeg_results=" .. #ffmpeg_results .. " opacity_results=" .. #opacity_results .. " corrupt=" .. #corrupt_frame_records)

    if has_problems then

    if #ffmpeg_results == 0 and #opacity_results > 0 then
        print("[BFD] FFmpeg未检测到黑帧，但透明度扫描发现 " .. #opacity_results .. " 个问题")
    end

    -- ----------------------------------------------------------
    -- 阶段7: 分类算法 - 区分夹帧/可疑/转场/空位
    -- 传入 clips 用于时间线空位检测 + start_offset 修正达芬奇时间码
    -- ----------------------------------------------------------
    dlog("阶段7: 分类算法...")
    print("[BFD] [4/7] 正在分类检测结果（含空位检测）...")
    local start_offset = compat:get_timeline_start_offset(timeline, timeline_fps)
    dlog("阶段7: start_offset=" .. start_offset .. "帧 (" .. string.format("%.0f", start_offset/timeline_fps) .. "s) 时间线起始偏移")
    params.start_offset = start_offset
    local analyzed_results = Analyzer.analyze_results(ffmpeg_results, timeline_fps, params, clips)
    dlog("阶段7完成: errors=" .. (analyzed_results.summary.error_count or 0) .. " suspects=" .. (analyzed_results.summary.suspect_count or 0))

    local s = analyzed_results.summary
    print(string.format(
        "[BFD] 分类完成: %d 夹帧, %d 可疑, %d 转场, %d 空位, %d 忽略",
        s.error_count, s.suspect_count, s.scene_count, s.gap_count, s.ignored_count
    ))
    check_progress_panel("分类完成", 74)

    -- ----------------------------------------------------------
    -- 阶段8: 重复片段检测（基于路径 + 基于帧指纹内容）
    -- ----------------------------------------------------------
    local dup_results = nil
    local content_dup_results = nil
    local function duplicate_clip_allowed_by_io(clip)
        if not has_io_range then return true end
        local clip_start = clip.timeline_start_frame or 0
        local duration = clip.source_duration_frames or 0
        if duration <= 0 and clip.item then
            pcall(function() duration = clip.item:GetDuration() end)
        end
        local clip_end = clip_start + duration
        return clip_end > io_in and clip_start < io_out
    end
    dlog(string.format("阶段8入口: detect_duplicate=%s ENABLED=%s clips=%d",
        tostring(params.detect_duplicate), tostring(config.DUPLICATE.ENABLED), #clips))
    if params.detect_duplicate ~= false and config.DUPLICATE.ENABLED then
        -- 8a: 基于文件路径的重复检测
        print("[BFD] [5/7] 正在检测重复片段（路径比对）...")
        check_progress_panel("重复片段检测", 82)
        -- 过滤隐藏/禁用素材：不参与重复检测（有意隐藏的副本不算重复）
        local dup_source_clips = clips
        local dup_clips = {}
        for _, c in ipairs(dup_source_clips) do
            if c.is_enabled ~= false and (c.opacity or 100) > 0 and duplicate_clip_allowed_by_io(c) then
                table.insert(dup_clips, c)
            end
        end
        if has_io_range then
            print("[BFD] 路径重复: 仅比较入出点范围内的片段。")
            dlog(string.format("阶段8a: IO范围重复检测仅使用IO内片段 source_clips=%d dup_clips=%d", #dup_source_clips, #dup_clips))
        end
        dlog(string.format("阶段8a: 路径重复检测开始, clips=%d dup_clips=%d", #dup_source_clips, #dup_clips))
        dup_results = DuplicateDetector.detect(dup_clips, timeline_fps, params)
        local ds = dup_results.summary
        dlog(string.format("阶段8a完成: groups=%d near=%d far=%d distant=%d",
            ds.total_groups or 0, ds.near_count or 0, ds.far_count or 0, ds.distant_count or 0))
        print(string.format(
            "[BFD] 路径重复: %d 组重复, %d 近距(高嫌疑), %d 远距(需确认), %d 远距复用",
            ds.total_groups, ds.near_count, ds.far_count, ds.distant_count
        ))
        print(DuplicateDetector.generate_summary(dup_results))

        -- 8b: 基于帧指纹的内容重复检测
        local content_requested = params.detect_content_dup == true
            or (params.marker_types and params.marker_types.content_dup == true)
        local content_detect_enabled = config.DUPLICATE.CONTENT_DETECT_ENABLED and content_requested
        dlog(string.format("阶段8b入口: CONTENT_DETECT_ENABLED=%s requested=%s complex_render=%s",
            tostring(config.DUPLICATE.CONTENT_DETECT_ENABLED), tostring(content_requested), tostring(complex_render_done)))
        if content_detect_enabled then
            local sample_int = params.content_sample_interval or config.DUPLICATE.CONTENT_SAMPLE_INTERVAL
            if complex_render_done and params.complex_render_path then
                -- 复杂模式：直接对渲染文件做帧指纹（真正的画面内容比对）
                print(string.format("[BFD] 正在检测内容重复（复杂模式·渲染文件帧指纹）..."))
                dlog("阶段8b: 复杂模式帧指纹, render_path=" .. params.complex_render_path)
                content_dup_results = DuplicateDetector.detect_content_render(
                    params.complex_render_path, io_in, timeline_fps, params
                )
                if not should_keep_complex_render(params) then
                    pcall(function() os.remove(params.complex_render_path) end)
                    pcall(function() os.remove(complex_render_meta_path(params.complex_render_path)) end)
                    dlog("阶段8b: 复杂模式渲染文件已清理")
                else
                    dlog("阶段8b: 复杂模式渲染文件按用户设置保留")
                end
            else
                -- 普通模式：逐文件帧指纹（用全量clips，隐藏素材也参与内容比对）
                print(string.format("[BFD] 正在检测内容重复（帧指纹，间隔%d帧）...", sample_int))
                dlog("阶段8b: 帧指纹提取开始, clips=" .. #clips)
                content_dup_results = DuplicateDetector.detect_content(clips, timeline_fps, params)
            end
            local cs = content_dup_results and content_dup_results.summary
            if cs then
                dlog(string.format("阶段8b完成: scanned=%d fps=%d files_with_dup=%d",
                    cs.files_scanned or 0, cs.total_fingerprints or 0, cs.files_with_duplicates or 0))
                print(string.format(
                    "[BFD] 内容重复: 扫描%d文件, %d指纹, 发现%d处重复",
                    cs.files_scanned, cs.total_fingerprints, cs.files_with_duplicates
                ))
                if cs.files_with_duplicates > 0 then
                    print(DuplicateDetector.generate_content_summary(content_dup_results))
                end
            end
        else
            dlog("阶段8b: 内容重复帧指纹未启用，跳过")
        end
    else
        dlog("阶段8: 重复检测已跳过 (detect_duplicate=" .. tostring(params.detect_duplicate) .. " ENABLED=" .. tostring(config.DUPLICATE.ENABLED) .. ")")
        print("[BFD] 重复片段检测已跳过")
    end

    if complex_render_done and params.complex_render_path and not should_keep_complex_render(params) then
        pcall(function() os.remove(params.complex_render_path) end)
        pcall(function() os.remove(complex_render_meta_path(params.complex_render_path)) end)
        dlog("复杂模式：临时渲染文件已清理: " .. tostring(params.complex_render_path))
        params.complex_render_path = nil
    end

    -- ----------------------------------------------------------
    -- 阶段9: 清除旧标记 + 按用户选择添加新标记
    -- ----------------------------------------------------------
    dlog("阶段9: 标记管理, clear_old=" .. tostring(params.clear_old))
    check_progress_panel("标记写入准备", 88)
    if params.clear_old then
        print("[BFD] [6/7] 正在清除旧的检测标记...")
        local removed = MarkerManager.clear_detection_markers(timeline, compat)
        print(string.format("[BFD] 已清除 %d 个旧标记", removed))
    end

    -- 根据用户选择的标记类型过滤
    local marker_types = params.marker_types or config.DEFAULT_MARKER_TYPES

    -- 合并真正的夹帧检测结果（基于片段时长，与黑帧无关）
    if #timeline_stuck_records > 0 then
        -- 去重：与已有FFmpeg error记录位置重叠>80%则跳过
        for _, tsr in ipairs(timeline_stuck_records) do
            local dup = false
            for _, existing in ipairs(analyzed_results.errors) do
                local overlap_start = math.max(tsr.timeline_start_frame, existing.timeline_start_frame)
                local overlap_end = math.min(tsr.timeline_end_frame, existing.timeline_end_frame)
                if overlap_end > overlap_start then
                    local tsr_len = tsr.timeline_end_frame - tsr.timeline_start_frame
                    if tsr_len > 0 and (overlap_end - overlap_start) / tsr_len > 0.8 then
                        dup = true
                        break
                    end
                end
            end
            if not dup then
                table.insert(analyzed_results.errors, tsr)
                analyzed_results.summary.error_count = analyzed_results.summary.error_count + 1
            end
        end
    end

    -- 合并多轨道叠加夹帧检测结果（阶段4.7）
    if #overlay_stuck_records > 0 then
        for _, ovr in ipairs(overlay_stuck_records) do
            local dup = false
            local target_list = (ovr.classification == "suspect") and analyzed_results.suspects or analyzed_results.errors
            for _, tsr in ipairs(timeline_stuck_records) do
                local ovs = math.max(ovr.timeline_start_frame, tsr.timeline_start_frame)
                local ove = math.min(ovr.timeline_end_frame, tsr.timeline_end_frame)
                if ove > ovs then
                    local ovr_len = ovr.timeline_end_frame - ovr.timeline_start_frame
                    if ovr_len > 0 and (ove - ovs) / ovr_len > 0.8 then dup = true; break end
                end
            end
            if not dup then
                for _, existing in ipairs(target_list) do
                    local ovs = math.max(ovr.timeline_start_frame, existing.timeline_start_frame)
                    local ove = math.min(ovr.timeline_end_frame, existing.timeline_end_frame)
                    if ove > ovs then
                        local ovr_len = ovr.timeline_end_frame - ovr.timeline_start_frame
                        if ovr_len > 0 and (ove - ovs) / ovr_len > 0.8 then dup = true; break end
                    end
                end
            end
            if not dup then
                table.insert(target_list, ovr)
                if ovr.classification == "suspect" then
                    analyzed_results.summary.suspect_count = analyzed_results.summary.suspect_count + 1
                else
                    analyzed_results.summary.error_count = analyzed_results.summary.error_count + 1
                end
            end
        end
    end

    -- 合并渲染坏帧检测结果（signalstats ABC三方案，仅复杂模式）
    if #corrupt_frame_records > 0 then
        for _, cfr in ipairs(corrupt_frame_records) do
            local dup = false
            for _, existing in ipairs(analyzed_results.errors) do
                local ovs = math.max(cfr.timeline_start_frame, existing.timeline_start_frame)
                local ove = math.min(cfr.timeline_end_frame, existing.timeline_end_frame)
                if ove > ovs then
                    local cfr_len = cfr.timeline_end_frame - cfr.timeline_start_frame
                    if cfr_len > 0 and (ove - ovs) / cfr_len > 0.8 then
                        dup = true; break
                    end
                end
            end
            if not dup then
                table.insert(analyzed_results.errors, cfr)
                analyzed_results.summary.error_count = analyzed_results.summary.error_count + 1
            end
        end
        dlog(string.format("阶段9: 合并 %d 个渲染坏帧标记", #corrupt_frame_records))
    end

    local selected_records = Analyzer.get_filtered_marker_records(analyzed_results, marker_types)

    -- 基础黑边属于普通交付风险，即使用户没有勾选“画面黑边”高级项也默认提示；
    -- 只有指定遮幅比例的最终画面黑边检测仍由黑边开关控制，避免误把正常遮幅当问题。
    if marker_types.black_border ~= true
        and (tonumber(params.black_border_matte_aspect or 0) or 0) <= 0
        and params.basic_black_border_enabled ~= false
    then
        local basic_border_count = 0
        for _, r in ipairs(analyzed_results.black_borders or {}) do
            table.insert(selected_records, r)
            basic_border_count = basic_border_count + 1
        end
        if basic_border_count > 0 then
            print(string.format("[BFD] 已添加 %d 个基础黑边标记（普通模式默认检测）", basic_border_count))
        end
    end

    -- 合并透明度检测标记（秒级扫描，无需FFmpeg）
    if #opacity_results > 0 and marker_types.opacity ~= false then
        for _, r in ipairs(opacity_results) do
            if r.timeline_start_frame then
                r.timeline_start_tc = Analyzer.frame_to_timecode(r.timeline_start_frame, timeline_fps)
            end
            if not r.classification then r.classification = "opacity" end
            table.insert(selected_records, r)
        end
        print(string.format("[BFD] 已添加 %d 个透明度/合成标记", #opacity_results))
    end

    -- 合并路径重复检测标记
    if dup_results and marker_types.duplicate ~= false then
        local dup_records = DuplicateDetector.to_marker_records(dup_results, timeline_fps, params)
        for _, r in ipairs(dup_records) do
            table.insert(selected_records, r)
        end
        print(string.format("[BFD] 已添加 %d 个路径重复标记", #dup_records))
    end

    -- 合并帧指纹内容重复检测标记（含per-file和跨文件）
    if content_dup_results and marker_types.content_dup ~= false then
        local content_records = DuplicateDetector.content_to_marker_records(content_dup_results, timeline_fps)
        for _, r in ipairs(content_records) do
            table.insert(selected_records, r)
        end
        print(string.format("[BFD] 已添加 %d 个内容重复标记", #content_records))

        -- 跨文件内容重复（调色后不同文件但画面相同）
        if content_dup_results.cross_file_pairs then
            for _, pair in ipairs(content_dup_results.cross_file_pairs) do
                local dur_a = pair.clip_a.source_duration_frames or 0
                local dur_b = pair.clip_b.source_duration_frames or 0
                table.insert(selected_records, {
                    classification = "content_dup",
                    marker_color = config.MARKER_COLORS.CONTENT_DUP or "Fuchsia",
                    marker_name = "[BFD-FP] 内容重复A(跨文件)",
                    timeline_start_frame = pair.clip_a.timeline_start_frame,
                    timeline_end_frame = (pair.clip_a.timeline_start_frame or 0) + dur_a,
                    timeline_start_tc = Analyzer.frame_to_timecode(pair.clip_a.timeline_start_frame, timeline_fps),
                    note = pair.reason or "跨文件内容重复",
                    source_file = pair.clip_a.file_path,
                    duration_frames = dur_a,
                    duration_sec = dur_a / timeline_fps,
                })
                table.insert(selected_records, {
                    classification = "content_dup",
                    marker_color = config.MARKER_COLORS.CONTENT_DUP or "Fuchsia",
                    marker_name = "[BFD-FP] 内容重复B(跨文件)",
                    timeline_start_frame = pair.clip_b.timeline_start_frame,
                    timeline_end_frame = (pair.clip_b.timeline_start_frame or 0) + dur_b,
                    timeline_start_tc = Analyzer.frame_to_timecode(pair.clip_b.timeline_start_frame, timeline_fps),
                    note = pair.reason or "跨文件内容重复",
                    source_file = pair.clip_b.file_path,
                    duration_frames = dur_b,
                    duration_sec = dur_b / timeline_fps,
                })
            end
            print(string.format("[BFD] 已添加 %d 个跨文件内容重复标记", #content_dup_results.cross_file_pairs * 2))
        end
    end

    -- 最终可见总闸：所有能映射到源素材的问题，都必须真的出现在最终画面上。
    -- 下层素材被上层完全覆盖时，它自己的黑帧、夹帧、坏帧、重复等都不应该提示。
    do
        local visible_filtered = {}
        local hidden_problem_count = 0
        local function same_source(a, b)
            a = tostring(a or "")
            b = tostring(b or "")
            return a ~= "" and b ~= "" and a == b
        end
        local function record_is_final_visible(r)
            local name = tostring(r.marker_name or "")
            if name:find("%[BFD%-OVL%]") then return true end
            if r.nested_short_scene or (r.segment and r.segment.nested_short_scene) then return true end
            local src = tostring(r.source_file or "")
            if src == "" or src:find("bfd_temp_render", 1, true) then return true end
            local rs = tonumber(r.timeline_start_frame or 0) or 0
            local re = tonumber(r.timeline_end_frame or rs + 1) or (rs + 1)
            if re <= rs then re = rs + 1 end
            local matched_source = false
            for _, clip in ipairs(clips or {}) do
                if same_source(clip.file_path, src) then
                    matched_source = true
                    for _, iv in ipairs(get_final_visible_intervals(clip)) do
                        local iv_start = tonumber(iv.start or 0) or 0
                        local iv_end = tonumber(iv.end_ or iv["end"] or iv_start) or iv_start
                        if re > iv_start and rs < iv_end then
                            return true
                        end
                    end
                end
            end
            return not matched_source
        end
        for _, r in ipairs(selected_records) do
            if record_is_final_visible(r) then
                table.insert(visible_filtered, r)
            else
                hidden_problem_count = hidden_problem_count + 1
            end
        end
        if hidden_problem_count > 0 then
            print(string.format("[BFD] 最终可见过滤: 跳过 %d 个被上层完全覆盖的问题", hidden_problem_count))
            dlog("最终可见过滤: hidden_problem_count=" .. tostring(hidden_problem_count))
            selected_records = visible_filtered
        end
    end

    if has_io_range then
        local filtered_records = {}
        local skipped_by_io = 0
        for _, r in ipairs(selected_records) do
            local rs = r.timeline_start_frame or 0
            local re = r.timeline_end_frame or rs + (r.duration_frames or 1)
            if re > io_in and rs < io_out then
                table.insert(filtered_records, r)
            else
                skipped_by_io = skipped_by_io + 1
            end
        end
        if skipped_by_io > 0 then
            print(string.format("[BFD] IO range filter: skipped %d out-of-range markers", skipped_by_io))
            dlog(string.format("IO range filter: skipped=%d io_in=%s io_out=%s", skipped_by_io, tostring(io_in), tostring(io_out)))
        end
        selected_records = filtered_records
    end

    do
        local function is_external_overlay_short_record(r)
            local name = tostring(r and r.marker_name or "")
            return name:find("%[BFD%-MIX%]%s*复合/Fusion外部覆盖边界") ~= nil
                or name:find("%[BFD%-MIX%]%s*上层覆盖边界夹帧") ~= nil
                or name:find("%[BFD%-OVL%]%s*夹帧%(") ~= nil
        end
        local function is_visible_fragment_mixed_record(r)
            local name = tostring(r and r.marker_name or "")
            local seg = r and r.segment or nil
            return name:find("%[BFD%-MIX%]%s*混剪源内夹帧") ~= nil
                and seg
                and seg.final_visible_fragment == true
        end
        local function short_visual_window(r)
            local s = tonumber(r and r.visual_window_start_frame)
            local e = tonumber(r and r.visual_window_end_frame)
            if not s or not e then
                s = tonumber(r and r.timeline_start_frame)
                e = tonumber(r and r.timeline_end_frame)
            end
            if not s or not e then return nil end
            s = math.floor(s + 0.5)
            e = math.floor(e + 0.5)
            if e <= s then return nil end
            local max_window = tonumber(params.stuck_frames or config.CLASSIFICATION.STUCK_FRAMES) or 3
            if (e - s) > max_window then return nil end
            return s, e
        end
        local function record_start_frame(r)
            local f = tonumber(r and r.timeline_start_frame)
            if not f then return nil end
            return math.floor(f + 0.5)
        end
        local function same_nonempty_source(a, b)
            local sa = tostring(a and a.source_file or "")
            local sb = tostring(b and b.source_file or "")
            return sa ~= "" and sb ~= "" and sa == sb
        end
        local function source_time_range(r)
            local s = tonumber(r and r.source_start_sec)
            if not s then return nil end
            local dur = tonumber(r and r.source_duration_sec)
                or tonumber(r and r.duration_sec)
                or ((tonumber(r and r.duration_frames) or 0) / timeline_fps)
            if not dur or dur <= 0 then return nil end
            return s, s + dur
        end
        local function source_ranges_overlap(a, b)
            local as, ae = source_time_range(a)
            local bs, be = source_time_range(b)
            if not as or not ae or not bs or not be then return false end
            local tol = math.max(2 / timeline_fps, 0.001)
            return ae + tol > bs and be + tol > as
        end
        local function choose_visible_window_anchor(records, window_start)
            local anchor = nil
            for _, candidate in ipairs(records) do
                local f = record_start_frame(candidate)
                if f == window_start then return candidate end
                if not anchor or (f and f < (record_start_frame(anchor) or f + 1)) then
                    anchor = candidate
                end
            end
            return anchor
        end

        local specific_records = {}
        for _, r in ipairs(selected_records) do
            if is_visible_fragment_mixed_record(r) then
                table.insert(specific_records, r)
            end
        end

        local merged_records = {}
        local merged_overlay_evidence = 0
        local skipped_ambiguous_overlay = 0
        for _, r in ipairs(selected_records) do
            if is_external_overlay_short_record(r) then
                local ws, we = short_visual_window(r)
                local contained_specifics = {}
                if ws and we then
                    for _, specific in ipairs(specific_records) do
                        local f = record_start_frame(specific)
                        if f and f >= ws and f < we
                            and same_nonempty_source(r, specific)
                            and source_ranges_overlap(r, specific)
                        then
                            table.insert(contained_specifics, specific)
                        end
                    end
                end
                if #contained_specifics == 1 then
                    merged_overlay_evidence = merged_overlay_evidence + 1
                    local last_frame = math.max(ws, we - 1)
                    local anchor = choose_visible_window_anchor(contained_specifics, ws)
                    if anchor then
                        local original_frame = record_start_frame(anchor) or ws
                        anchor.timeline_start_frame = ws
                        anchor.timeline_end_frame = we
                        anchor.timeline_start_tc = Analyzer.frame_to_timecode(ws, timeline_fps)
                        anchor.timeline_end_tc = Analyzer.frame_to_timecode(we, timeline_fps)
                        anchor.duration_frames = math.max(1, we - ws)
                        anchor.source_duration_sec = anchor.duration_frames / timeline_fps
                        anchor.duration_sec = anchor.source_duration_sec
                        anchor.note = tostring(anchor.note or "") .. string.format(
                            "\n合并证据: 同一最终可见短窗口且底层源时间重叠 %s-%s (%d帧) 也命中外部覆盖/叠加短段证据；标记已放到该短段第一帧，原源内证据帧为 %s。若同一短段内还有其他混剪源内证据，外部证据不会被折叠，避免不同镜头问题被合并。",
                            Analyzer.frame_to_timecode(ws, timeline_fps),
                            Analyzer.frame_to_timecode(last_frame, timeline_fps),
                            we - ws,
                            Analyzer.frame_to_timecode(original_frame, timeline_fps)
                        )
                    end
                elseif #contained_specifics > 1 then
                    skipped_ambiguous_overlay = skipped_ambiguous_overlay + 1
                    table.insert(merged_records, r)
                else
                    table.insert(merged_records, r)
                end
            else
                table.insert(merged_records, r)
            end
        end
        if merged_overlay_evidence > 0 then
            print(string.format("[BFD] 最终可见短段证据合并: 合并 %d 条外部覆盖/叠加重复证据", merged_overlay_evidence))
            dlog("阶段9: 最终可见短段证据合并 merged_overlay_evidence="
                .. tostring(merged_overlay_evidence)
                .. " skipped_ambiguous=" .. tostring(skipped_ambiguous_overlay))
            selected_records = merged_records
        end
    end

    do
        local function duplicate_should_yield(r)
            local cls = tostring(r and r.classification or "")
            local name = tostring(r and r.marker_name or "")
            return cls == "duplicate"
                or cls == "content_dup"
                or name:find("%[BFD%-DUP%]") ~= nil
                or name:find("%[BFD%-FP%]") ~= nil
        end
        local function conflict_priority(r)
            if r and (r.nested_short_scene or (r.segment and r.segment.nested_short_scene)) then return 100 end
            local name = r and tostring(r.marker_name or "") or ""
            if name:find("%[BFD%-OVL%]") then return 90 end
            if name:find("%[BFD%-MIX%].-真实画面短镜头夹帧") then return 85 end
            if name:find("%[BFD%-ERR%]") then return 75 end
            if r and r.classification == "error" then return 70 end
            if name:find("%[BFD%-SUS%]") then return 65 end
            if r and (r.is_mixed_cut or (r.segment and r.segment.is_mixed_cut)) then return 65 end
            if name:find("%[BFD%-MIX%]") then return 65 end
            if r and r.classification == "opacity" then return 60 end
            if name:find("%[BFD%-BDR%]") or (r and r.classification == "black_border") then return 55 end
            if r and r.classification == "gap" then return 50 end
            if duplicate_should_yield(r) then return 30 end
            return 10
        end

        local blocking_frames = {}
        for _, r in ipairs(selected_records) do
            if not duplicate_should_yield(r) and conflict_priority(r) > 30 then
                local f = tonumber(r.timeline_start_frame or 0)
                if f then blocking_frames[math.floor(f + 0.5)] = true end
            end
        end

        local function choose_open_duplicate_span(record)
            local start_frame = tonumber(record.timeline_start_frame or 0) or 0
            local end_frame = tonumber(record.timeline_end_frame or (start_frame + (record.duration_frames or 1))) or (start_frame + 1)
            start_frame = math.floor(start_frame + 0.5)
            end_frame = math.floor(end_frame + 0.5)
            if end_frame <= start_frame then
                end_frame = start_frame + math.max(1, tonumber(record.duration_frames or 1) or 1)
            end

            local conflicts = {}
            for frame, _ in pairs(blocking_frames) do
                -- Resolve 的区间标记在 UI 上会盖到尾帧附近，所以尾帧也避让。
                if frame >= start_frame and frame <= end_frame then
                    table.insert(conflicts, frame)
                end
            end
            if #conflicts == 0 then return record, false end
            table.sort(conflicts)

            local best = nil
            local cursor = start_frame
            local function consider(s, e)
                local len = e - s
                if len > 0 and (not best or len > best.len) then
                    best = { start_frame = s, end_frame = e, len = len }
                end
            end
            for _, blocked in ipairs(conflicts) do
                consider(cursor, blocked - 1)
                cursor = blocked + 1
            end
            consider(cursor, end_frame)
            if not best then
                return nil, true
            end

            record.timeline_start_frame = best.start_frame
            record.timeline_end_frame = best.end_frame
            record.duration_frames = math.max(1, best.end_frame - best.start_frame)
            record.source_duration_sec = record.duration_frames / timeline_fps
            record.duration_sec = record.source_duration_sec
            record.timeline_start_tc = Analyzer.frame_to_timecode(record.timeline_start_frame, timeline_fps)
            record.timeline_end_tc = Analyzer.frame_to_timecode(record.timeline_end_frame, timeline_fps)
            record.note = tostring(record.note or "") .. string.format(
                "\n重复/复用区间已避让高优先级标记，实际标记区间调整为: %d-%d帧 (%d帧)，避免盖住黑帧、夹帧、黑边、透明度或空隙提示。",
                record.timeline_start_frame,
                record.timeline_end_frame,
                record.duration_frames
            )
            return record, true
        end

        local yielded_records = {}
        local adjusted_duplicate_regions = 0
        local skipped_duplicate_regions = 0
        for _, r in ipairs(selected_records) do
            if duplicate_should_yield(r) then
                local adjusted, changed = choose_open_duplicate_span(r)
                if adjusted then
                    table.insert(yielded_records, adjusted)
                    if changed then adjusted_duplicate_regions = adjusted_duplicate_regions + 1 end
                else
                    skipped_duplicate_regions = skipped_duplicate_regions + 1
                end
            else
                table.insert(yielded_records, r)
            end
        end
        if adjusted_duplicate_regions > 0 or skipped_duplicate_regions > 0 then
            print(string.format(
                "[BFD] 重复/复用标记避让: 调整 %d 条, 跳过 %d 条",
                adjusted_duplicate_regions,
                skipped_duplicate_regions
            ))
            dlog(string.format(
                "阶段9: 重复/复用标记避让 adjusted=%d skipped=%d",
                adjusted_duplicate_regions,
                skipped_duplicate_regions
            ))
            selected_records = yielded_records
        end
    end

    do
        table.sort(selected_records, function(a, b)
            return (a.timeline_start_frame or 0) < (b.timeline_start_frame or 0)
        end)
        local merged_records = {}
        local merged_adjacent = 0
        local function is_render_black_record(r)
            local src = tostring(r.source_file or "")
            local name = tostring(r.marker_name or "")
            return src:find("bfd_temp_render", 1, true) ~= nil
                and (name:find("BFD%-ERR") ~= nil or name:find("BFD%-SUS") ~= nil)
        end
        for _, r in ipairs(selected_records) do
            local last = merged_records[#merged_records]
            if last and is_render_black_record(last) and is_render_black_record(r)
                and tostring(last.marker_name or "") == tostring(r.marker_name or "")
                and tostring(last.classification or "") == tostring(r.classification or "")
                and (r.timeline_start_frame or 0) <= ((last.timeline_end_frame or last.timeline_start_frame or 0) + 2)
            then
                last.timeline_end_frame = math.max(last.timeline_end_frame or last.timeline_start_frame or 0, r.timeline_end_frame or r.timeline_start_frame or 0)
                last.duration_frames = math.max(1, (last.timeline_end_frame or 0) - (last.timeline_start_frame or 0))
                last.source_duration_sec = (last.duration_frames or 1) / timeline_fps
                last.timeline_end_tc = Analyzer.frame_to_timecode(last.timeline_end_frame, timeline_fps)
                merged_adjacent = merged_adjacent + 1
            else
                table.insert(merged_records, r)
            end
        end
        if merged_adjacent > 0 then
            dlog("阶段9: 合并相邻复杂模式黑帧标记 " .. tostring(merged_adjacent) .. " 条")
            selected_records = merged_records
        end
    end

    do
        local unique_records = {}
        local seen_records = {}
        local deduped_count = 0
        local function record_priority(r)
            if r and (r.nested_short_scene or (r.segment and r.segment.nested_short_scene)) then return 100 end
            local name = r and tostring(r.marker_name or "") or ""
            if name:find("%[BFD%-OVL%]") then return 90 end
            if name:find("%[BFD%-MIX%].-真实画面短镜头夹帧") then return 85 end
            if name:find("%[BFD%-ERR%]") then return 75 end
            if r and r.classification == "error" then return 70 end
            if name:find("%[BFD%-SUS%]") then return 65 end
            if r and (r.is_mixed_cut or (r.segment and r.segment.is_mixed_cut)) then return 65 end
            if name:find("%[BFD%-MIX%]") then return 65 end
            if r and r.classification == "opacity" then return 60 end
            if name:find("%[BFD%-BDR%]") or (r and r.classification == "black_border") then return 55 end
            if r and r.classification == "gap" then return 50 end
            if r and r.classification == "duplicate" then return 30 end
            if r and r.classification == "content_dup" then return 30 end
            return 10
        end
        for _, r in ipairs(selected_records) do
            local key = tostring(r.timeline_start_frame or "")
            local existing_index = seen_records[key]
            if existing_index then
                if record_priority(r) > record_priority(unique_records[existing_index]) then
                    unique_records[existing_index] = r
                end
                deduped_count = deduped_count + 1
            else
                seen_records[key] = #unique_records + 1
                table.insert(unique_records, r)
            end
        end
        if deduped_count > 0 then
            dlog("阶段9: 结果去重，合并重复记录 " .. tostring(deduped_count) .. " 条")
            selected_records = unique_records
        end
    end

    if #selected_records == 0 then
        print("[BFD] 根据用户选择的标记类型，没有需要添加的标记")
    else
        print(string.format("[BFD] 正在时间线上添加 %d 个标记（已按类型筛选）...", #selected_records))
        local added, failed = MarkerManager.apply_markers(
            timeline, selected_records, compat,
            function(current, total, added_count, failed_count)
                if current % 10 == 0 or current == total then
                    print(string.format("[BFD] 标记进度: %d/%d (成功:%d 失败:%d)",
                        current, total, added_count, failed_count))
                end
            end,
            start_offset  -- AddMarker使用显示帧号 = 绝对帧号 - 时间线起始偏移
        )
        print(string.format("[BFD] 标记完成: 成功添加 %d 个, 失败 %d 个", added, failed))
    end

    -- ----------------------------------------------------------
    -- 阶段10: 显示结果浏览窗口（含时间码列表+跳转功能）
    -- ----------------------------------------------------------
    print("[BFD] >>>>> 进入阶段10，准备显示结果窗口...")
    dlog("阶段10: 显示结果窗口, total_problems=" .. #selected_records)
    -- 将selected_records合并到analyzed_results中，使结果窗口能展示重复检测等非FFmpeg结果
    analyzed_results.selected_records = selected_records
    analyzed_results.total_all = #selected_records
    if params.headless == true then
        dlog("阶段10: headless模式，跳过结果窗口")
        print("[BFD] Headless模式：跳过结果窗口")
        check_progress_panel("结果窗口跳过", 96)
    else
        UIBridge.show_results(compat, analyzed_results, params)
        dlog("阶段10完成: 结果窗口已关闭")
        print("[BFD] >>>>> 阶段10完成")
        check_progress_panel("结果窗口完成", 96)
    end

    -- HTML报告（仅当用户勾选时生成）
    if params.html_report then
        dlog("阶段11: 生成HTML报告...")
        local ReportGen = require("report_generator")
        local extra = {
            opacity_count = #opacity_results,
            duplicate_count = dup_results and #dup_results or 0,
            content_dup_count = content_dup_results and #content_dup_results or 0,
            selected_count = #selected_records,
            detect_duration = string.format("%.0f秒", os.clock() - detect_start_time),
        }
        local report_params = {}
        for k, v in pairs(params) do report_params[k] = v end
        report_params.html_report = true
        local report_paths = ReportGen.generate_and_save(analyzed_results, timeline_name, report_params, extra)
        if report_paths.html then
            print("[BFD] HTML报告已保存: " .. report_paths.html)
            config.open_file(report_paths.html)
        elseif report_paths.txt then
            print("[BFD] TXT报告已保存: " .. report_paths.txt)
            config.open_file(report_paths.txt)
        end
    else
        dlog("阶段11: HTML报告已跳过（用户未勾选）")
    end

    local function build_progress_payload(records)
        table.sort(records, function(a, b)
            return (a.timeline_start_frame or 0) < (b.timeline_start_frame or 0)
        end)
        local counts = {
            total = #records,
            error = 0,
            suspect = 0,
            scene = 0,
            gap = 0,
            duplicate = 0,
            content_dup = 0,
            opacity = 0,
            corrupt = 0,
            black_border = 0,
        }
        local compact_records = {}
        for i, r in ipairs(records) do
            local cls = r.classification or "info"
            local marker_name = r.marker_name or cls
            if tostring(marker_name):find("%[BFD%-COR%]") then
                counts.corrupt = counts.corrupt + 1
            elseif cls == "error" then
                counts.error = counts.error + 1
            elseif cls == "suspect" then
                counts.suspect = counts.suspect + 1
            elseif cls == "scene" then
                counts.scene = counts.scene + 1
            elseif cls == "gap" then
                counts.gap = counts.gap + 1
            elseif cls == "duplicate" then
                counts.duplicate = counts.duplicate + 1
            elseif cls == "content_dup" then
                counts.content_dup = counts.content_dup + 1
                counts.duplicate = counts.duplicate + 1
            elseif cls == "opacity" then
                counts.opacity = counts.opacity + 1
            elseif cls == "black_border" then
                counts.black_border = counts.black_border + 1
            end
            if i <= 500 then
                table.insert(compact_records, {
                    timecode = r.timeline_start_tc or "",
                    frame = r.timeline_start_frame or 0,
                    timeline_start_frame = r.timeline_start_frame or 0,
                    classification = cls,
                    name = marker_name,
                    color = r.marker_color or "",
                    note = r.note or "",
                })
            end
        end
        return {
            counts = counts,
            records = compact_records,
        }
    end

    print("========== 检测完成 ==========")
    if ProgressBridge then ProgressBridge.complete(params, "检测完成", build_progress_payload(selected_records)) end
    print(string.format("  共 %d 个问题（夹帧:%d 可疑:%d 转场:%d 空位:%d）",
        #selected_records,
        analyzed_results.summary.error_count or 0,
        analyzed_results.summary.suspect_count or 0,
        analyzed_results.summary.scene_count or 0,
        analyzed_results.summary.gap_count or 0))
    print("  时间线标记已添加（红/黄/蓝/紫），按 ; 键逐个跳转")
    print("================================")
    print("")

    end  -- has_problems: 有问题时执行阶段7-11
    if complex_render_done and params.complex_render_path and not should_keep_complex_render(params) then
        pcall(function() os.remove(params.complex_render_path) end)
        pcall(function() os.remove(complex_render_meta_path(params.complex_render_path)) end)
        dlog("复杂模式：最终兜底清理临时渲染文件: " .. tostring(params.complex_render_path))
        params.complex_render_path = nil
    end
    if not has_problems and ProgressBridge then
        ProgressBridge.complete(params, "未检测到问题", {
            counts = { total = 0, error = 0, suspect = 0, scene = 0, gap = 0, duplicate = 0, content_dup = 0, opacity = 0, corrupt = 0, black_border = 0 },
            records = {},
        })
    end
    if external_single_run then
        pcall(function()
            local PyParamsBridge = require("py_params_bridge")
            if PyParamsBridge and PyParamsBridge.disable_pending_params then
                PyParamsBridge.disable_pending_params()
            end
        end)
        print("[BFD] 外部参数模式：单次检测完成，退出")
    else
        print("[BFD] 菜单启动模式：单次检测完成，退出")
    end
    break
    end  -- while true: 循环回阶段3，重新打开参数窗口
end  -- Main()

-- ============================================================
-- 异常保护
-- ============================================================
dlog("调用 Main()...")
local success, err = pcall(Main)
dlog("Main() pcall结果: success=" .. tostring(success) .. " err=" .. tostring(err))
if not success then
    local error_msg = tostring(err)
    dlog("FATAL: " .. error_msg)
    dlog("traceback: " .. debug.traceback())
    print("\n[BFD FATAL] 插件运行异常: " .. error_msg)
    print("[BFD FATAL] 请将以上错误信息反馈给开发者")
    print("[BFD FATAL] 调试信息: " .. debug.traceback())

    pcall(function()
        local fusion = Fusion()
        if fusion then
            fusion:AskUser("插件错误", {
                {"msg", "Text", { Wrap = true, Lines = 8,
                    Default = "插件运行异常:\n" .. error_msg }},
            })
        end
    end)
end
dlog("=== BFD 脚本执行完毕 ===")
