-- version_compat.lua - 达芬奇版本检测与API兼容适配层
-- 支持 DaVinci Resolve 17 / 18 / 19 / 20，跨平台(macOS/Windows/Linux)
-- v1.9.22: IO缓存Lua格式+SpinBox修复+版本号修正

local config = require("config")
local VersionCompat = {}
VersionCompat.__index = VersionCompat

local function compat_log(msg)
    local home = os.getenv("HOME") or os.getenv("USERPROFILE") or "."
    local sep = package.config:sub(1, 1)
    local path = home .. (sep == "\\" and "\\bfd_debug.log" or "/bfd_debug.log")
    local f = io.open(path, "a")
    if f then
        f:write(os.date("%Y-%m-%d %H:%M:%S") .. " [VersionCompat] " .. tostring(msg) .. "\n")
        f:close()
    end
end

local function try_resolve_source(label, fn)
    local ok, app = pcall(fn)
    if ok and app then
        compat_log("Resolve source OK: " .. label)
        return app, label
    end
    compat_log("Resolve source failed: " .. label .. " ok=" .. tostring(ok) .. " value=" .. tostring(app))
    return nil, nil
end

local function get_resolve_app()
    compat_log("global types: Resolve=" .. tostring(type(Resolve)) ..
        " Fusion=" .. tostring(type(Fusion)) ..
        " fusion=" .. tostring(type(fusion)) ..
        " bmd=" .. tostring(type(bmd)) ..
        " bmd.scriptapp=" .. tostring(bmd and type(bmd.scriptapp) or nil) ..
        " resolve=" .. tostring(type(resolve)))

    local app, label = try_resolve_source("global resolve", function() return resolve end)
    if app then return app, label end

    app, label = try_resolve_source("fusion:GetResolve()", function()
        if fusion and fusion.GetResolve then
            return fusion:GetResolve()
        end
        return nil
    end)
    if app then return app, label end

    app, label = try_resolve_source("global Resolve()", function() return Resolve() end)
    if app then return app, label end

    app, label = try_resolve_source("bmd.scriptapp('Resolve')", function()
        if bmd and bmd.scriptapp then
            return bmd.scriptapp("Resolve")
        end
        return nil
    end)
    if app then return app, label end

    app, label = try_resolve_source("Fusion():GetResolve()", function()
        local fu = Fusion and Fusion()
        if fu and fu.GetResolve then
            return fu:GetResolve()
        end
        return nil
    end)
    if app then return app, label end

    app, label = try_resolve_source("bmd.scriptapp('Fusion'):GetResolve()", function()
        if bmd and bmd.scriptapp then
            local fu = bmd.scriptapp("Fusion")
            if fu and fu.GetResolve then
                return fu:GetResolve()
            end
        end
        return nil
    end)
    if app then return app, label end

    return nil, nil
end

-- ============================================================
-- 构造函数
-- ============================================================
function VersionCompat:new()
    local self = setmetatable({}, VersionCompat)
    self.os = self:_detect_os()
    self.resolve = nil
    self.fusion = nil
    self.major = 0
    self.minor = 0
    self.patch = 0
    self.is_studio = false
    self.capabilities = {}
    return self
end

-- ============================================================
-- 初始化：连接达芬奇API并检测版本
-- ============================================================
function VersionCompat:init()
    local resolve_or_err, resolve_source = get_resolve_app()
    if not resolve_or_err then
        compat_log("Resolve connection unavailable after all probes")
        return false, "无法连接到 DaVinci Resolve，请确保在达芬奇内部运行此脚本"
    end
    self.resolve = resolve_or_err
    compat_log("Using Resolve source: " .. tostring(resolve_source))

    -- 获取版本号
    local version = self.resolve:GetVersion()
    if not version or #version < 3 then
        return false, "无法获取 DaVinci Resolve 版本信息"
    end
    self.major = version[1] or 0
    self.minor = version[2] or 0
    self.patch = version[3] or 0
    self.version_string = self.resolve:GetVersionString() or "Unknown"

    -- 尝试获取Fusion对象
    ok, fusion_or_err = pcall(function() return Fusion() end)
    if ok and fusion_or_err then
        self.fusion = fusion_or_err
    end

    -- 检测Studio版本
    self:_detect_studio()

    -- 探测可用功能
    self:_probe_capabilities()

    return true, nil
end

-- ============================================================
-- 检测操作系统
-- ============================================================
function VersionCompat:_detect_os()
    -- Lua 5.1 没有内置os检测，通过路径分隔符判断
    local sep = package.config:sub(1, 1)
    if sep == "\\" then
        return "windows"
    end

    -- 通过uname命令检测（macOS vs Linux）
    local f = io.popen("uname -s 2>/dev/null")
    if f then
        local uname = f:read("*a"):gsub("%s+", "")
        f:close()
        if uname == "Darwin" then
            return "macos"
        end
    end
    return "linux"
end

-- ============================================================
-- 检测是否为Studio版本
-- ============================================================
function VersionCompat:_detect_studio()
    -- 方法1: 尝试检测UIManager（仅Studio版本可用）
    if self.fusion then
        local ok, _ = pcall(function() return self.fusion.UIManager end)
        if ok then
            self.is_studio = true
            return
        end
    end

    -- 方法2: 尝试读取特定setting
    local ok, _ = pcall(function()
        local pm = self.resolve:GetProjectManager()
        if pm then
            local proj = pm:GetCurrentProject()
            if proj then
                proj:GetSetting("superScale")
            end
        end
    end)
    if ok then
        self.is_studio = true
        return
    end

    self.is_studio = false
end

-- ============================================================
-- 功能探测：用pcall检测API是否可用
-- ============================================================
function VersionCompat:_probe_capabilities()
    local cap = {}

    -- UIManager可用性
    if self.fusion then
        local ok, ui = pcall(function() return self.fusion.UIManager end)
        cap.has_uimanager = ok and ui ~= nil
    else
        cap.has_uimanager = false
    end

    -- bmd.UIDispatcher可用性
    local ok, _ = pcall(function() return bmd.UIDispatcher end)
    cap.has_uidispatcher = ok

    -- GetItemListInTrack（v18+）
    cap.has_item_list_api = true  -- 默认true，运行时fallback

    -- customData 支持（v19+）
    cap.has_custom_data = (self.major >= 19)

    -- AskUser总是可用
    cap.has_ask_user = true

    self.capabilities = cap
end

-- ============================================================
-- 判断版本是否受支持
-- ============================================================
function VersionCompat:is_supported()
    return self.major >= 17
end

-- ============================================================
-- 获取当前项目和时间线（带错误处理）
-- ============================================================
function VersionCompat:get_current_project_and_timeline()
    local pm = self.resolve:GetProjectManager()
    if not pm then
        return nil, nil, "无法获取 ProjectManager"
    end

    local project = pm:GetCurrentProject()
    if not project then
        return nil, nil, "请先打开一个项目"
    end

    local timeline = project:GetCurrentTimeline()
    if not timeline then
        return nil, nil, "请先打开一个时间线"
    end

    return project, timeline, nil
end

-- ============================================================
-- 获取项目中所有时间线列表
-- 返回: {{name="xx", timeline=obj, fps=25, index=1}, ...}, error
-- ============================================================
function VersionCompat:get_all_timelines()
    local pm = self.resolve:GetProjectManager()
    if not pm then
        return nil, "无法获取 ProjectManager"
    end

    local project = pm:GetCurrentProject()
    if not project then
        return nil, "请先打开一个项目"
    end

    local count = project:GetTimelineCount()
    if count == 0 then
        return nil, "当前项目没有时间线"
    end

    local timelines = {}
    for i = 1, count do
        local tl = project:GetTimelineByIndex(i)
        if tl then
            local name = "未命名"
            pcall(function() name = tl:GetName() end)

            -- 自动检测帧率
            local fps = nil
            pcall(function()
                local v = tonumber(tl:GetSetting("timelineFrameRate"))
                if v then fps = v end
            end)
            if not fps then
                pcall(function()
                    local v = tonumber(project:GetSetting("timelineFrameRate"))
                    if v then fps = v end
                end)
            end
            fps = fps or 25

            table.insert(timelines, {
                name = name,
                timeline = tl,
                fps = fps,
                index = i,
            })
        end
    end

    return timelines, nil
end

-- ============================================================
-- 获取时间线上的视频片段列表（兼容不同版本API）
-- ============================================================
function VersionCompat:get_video_items(timeline)
    local items = {}
    local item_to_track = {}  -- userdata做key映射轨道号，避免_userdata.__newindex静默失败
    local track_count = timeline:GetTrackCount("video")

    for track_idx = 1, track_count do
        local track_items = nil
        local ok = pcall(function()
            track_items = timeline:GetItemListInTrack("video", track_idx)
        end)

        if not ok or not track_items then
            -- Fallback: 使用旧版 GetItemsInTrack (v17)
            ok = pcall(function()
                track_items = timeline:GetItemsInTrack("video", track_idx)
            end)
        end

        if track_items and #track_items > 0 then
            for _, item in ipairs(track_items) do
                item_to_track[item] = track_idx  -- 用item自身做key映射
                item._track_index = track_idx     -- 保留旧方式兼容其他引用
                table.insert(items, item)
            end
        end
    end

    return items, item_to_track
end

-- ============================================================
-- 安全获取片段属性
-- ============================================================
function VersionCompat:get_clip_property(clip, prop_name)
    -- 策略1: Resolve 19+ 需通过 MediaPoolItem 获取属性
    local media_item = nil
    pcall(function() media_item = clip:GetMediaPoolItem() end)
    if media_item then
        local ok, val = pcall(function() return media_item:GetClipProperty(prop_name) end)
        if ok and val then return val end
    end
    -- 策略2: 旧版 API 直接在 TimelineItem 上调用 GetClipProperty
    local ok, val = pcall(function() return clip:GetClipProperty(prop_name) end)
    if ok and val then return val end
    return nil
end

-- ============================================================
-- 安全添加标记（兼容不同版本API签名）
-- ============================================================
function VersionCompat:safe_add_marker(target, frame, color, name, note, duration)
    local pcall_ok, result = pcall(function()
        if self.capabilities.has_custom_data then
            -- v19+: 6参数版本(frame, color, name, note, duration, customData)
            -- customData 必须是 table，传空字符串导致 API 调用失败 → 标记没打上
            return target:AddMarker(frame, color, name, note, duration or 1, {})
        else
            -- v17/v18: 5参数版本(frame, color, name, note, duration)
            return target:AddMarker(frame, color, name, note, duration or 1)
        end
    end)

    -- pcall只捕获Lua异常，不检查AddMarker的布尔返回值
    -- 颜色名无效时AddMarker返回false但pcall仍报成功 → 需双重检查
    if not pcall_ok or not result then
        config._trace(string.format("AddMarker failed: frame=%d color=%s name=%s pcall=%s result=%s",
            frame, tostring(color), tostring(name), tostring(pcall_ok), tostring(result)))
        return false
    end
    return true
end

-- ============================================================
-- 获取目标标记列表
-- ============================================================
function VersionCompat:get_markers(target)
    local ok, markers = pcall(function() return target:GetMarkers() end)
    if ok and markers then
        return markers
    end
    return {}
end

-- ============================================================
-- 按颜色删除标记
-- ============================================================
function VersionCompat:delete_markers_by_color(target, color)
    local ok = pcall(function() target:DeleteMarkersByColor(color) end)
    return ok
end

-- ============================================================
-- 获取时间线入出点范围（帧数）
-- 返回: in_point, out_point，未设置时均为nil
-- v1.9.21: 全面枚举timeline方法+多模式API探测+直接number类型支持
-- ============================================================
function VersionCompat:get_in_out_range(timeline)
    if not timeline then return nil, nil end

    local function dlog(msg)
        local f = io.open(config.get_debug_log_path(), "a")
        if f then f:write(os.date("%Y-%m-%d %H:%M:%S") .. " [IO] " .. tostring(msg) .. "\n"); f:close() end
    end

    local in_point, out_point = nil, nil

    -- ====== 阶段A: 枚举timeline对象的所有方法 ======
    dlog("--- 枚举timeline方法 ---")
    pcall(function()
        local methods = {}
        for k, v in pairs(timeline) do
            table.insert(methods, tostring(k) .. "(" .. type(v) .. ")")
        end
        table.sort(methods)
        dlog("timeline pairs: " .. table.concat(methods, ", "))
        -- 查找IO相关方法
        for _, m in ipairs(methods) do
            local lower = m:lower()
            if lower:find("in") or lower:find("out") or lower:find("point") or lower:find("io") or lower:find("mark") or lower:find("range") or lower:find("render") then
                dlog("  >>> IO相关: " .. m)
            end
        end
    end)

    -- ====== 阶段B: 尝试所有已知API变体 ======
    local function try_get_number(obj, method_name)
        local ok, val = pcall(function() return obj[method_name](obj) end)
        if not ok then
            dlog(string.format("  %s() → ERROR: %s", method_name, tostring(val)))
            return nil
        end
        dlog(string.format("  %s() → raw=%s type=%s", method_name, tostring(val), type(val)))
        if val ~= nil then
            if type(val) == "number" then
                return val
            elseif type(val) == "string" and val ~= "" then
                return tonumber(val)
            end
        end
        return nil
    end

    -- 直接方法调用（按优先级排列）
    local method_names = {
        "GetInPoint", "GetOutPoint",
        "GetIn", "GetOut",
        "GetInPointFrame", "GetOutPointFrame",
        "GetRenderIn", "GetRenderOut",
        "GetMarkIn", "GetMarkOut",
        "GetTimelineIn", "GetTimelineOut",
        "GetIOIn", "GetIOOut",
        "GetRangeIn", "GetRangeOut",
    }

    for i = 1, #method_names, 2 do
        local in_name = method_names[i]
        local out_name = method_names[i + 1]
        if in_point == nil then
            local v = try_get_number(timeline, in_name)
            if v and v >= 0 then in_point = v end
        end
        if out_point == nil then
            local v = try_get_number(timeline, out_name)
            if v and v >= 0 then out_point = v end
        end
    end

    -- ====== 阶段C: GetSetting 所有可能键名 ======
    if in_point == nil or out_point == nil then
        dlog("--- GetSetting 多键名探测 ---")
        local setting_keys = {
            "timelineIn", "timelineOut",
            "TimelineIn", "TimelineOut",
            "InPoint", "OutPoint",
            "inPoint", "outPoint",
            "timelineInPoint", "timelineOutPoint",
            "TimelineInPoint", "TimelineOutPoint",
            "renderIn", "renderOut",
            "RenderIn", "RenderOut",
            "markIn", "markOut",
            "ioIn", "ioOut",
            "in", "out",
            "timelineInFrame", "timelineOutFrame",
        }

        for i = 1, #setting_keys, 2 do
            local in_key = setting_keys[i]
            local out_key = setting_keys[i + 1]
            if in_point == nil then
                pcall(function()
                    local v = timeline:GetSetting(in_key)
                    if v ~= nil then
                        dlog(string.format("  GetSetting(%s) → raw=%s type=%s", in_key, tostring(v), type(v)))
                        if type(v) == "number" and v >= 0 then
                            in_point = v
                        elseif type(v) == "string" and v ~= "" then
                            local n = tonumber(v)
                            if n and n >= 0 then in_point = n end
                        end
                    end
                end)
            end
            if out_point == nil then
                pcall(function()
                    local v = timeline:GetSetting(out_key)
                    if v ~= nil then
                        dlog(string.format("  GetSetting(%s) → raw=%s type=%s", out_key, tostring(v), type(v)))
                        if type(v) == "number" and v >= 0 then
                            out_point = v
                        elseif type(v) == "string" and v ~= "" then
                            local n = tonumber(v)
                            if n and n >= 0 then out_point = n end
                        end
                    end
                end)
            end
        end
    end

    -- ====== 阶段D: 通过RenderSettings探测 ======
    if in_point == nil or out_point == nil then
        dlog("--- RenderSettings探测 ---")
        pcall(function()
            local rs = timeline:GetRenderSettings()
            if rs then
                dlog("GetRenderSettings type: " .. type(rs))
                -- 枚举渲染设置
                for k, v in pairs(rs) do
                    local key_lower = tostring(k):lower()
                    if key_lower:find("in") or key_lower:find("out") or key_lower:find("range") then
                        dlog(string.format("  rs[%s] = %s (%s)", tostring(k), tostring(v), type(v)))
                    end
                end
                -- 尝试常见属性
                for _, key in ipairs({"InPoint", "OutPoint", "RenderIn", "RenderOut", "TimelineIn", "TimelineOut", "MarkIn", "MarkOut"}) do
                    if in_point == nil then
                        local v = rs[key]
                        if v ~= nil then dlog(string.format("  rs.%s = %s (%s)", key, tostring(v), type(v))) end
                    end
                end
            else
                dlog("GetRenderSettings返回nil")
            end
        end)
    end

    -- ====== 阶段E: 通过Project设置探测 ======
    if in_point == nil or out_point == nil then
        dlog("--- Project设置探测 ---")
        pcall(function()
            local pm = self.resolve:GetProjectManager()
            if pm then
                local proj = pm:GetCurrentProject()
                if proj then
                    -- 尝试GetSetting
                    for _, key in ipairs({"timelineIn", "timelineOut", "InPoint", "OutPoint", "renderIn", "renderOut"}) do
                        pcall(function()
                            local v = proj:GetSetting(key)
                            if v ~= nil then
                                dlog(string.format("  project.GetSetting(%s) = %s (%s)", key, tostring(v), type(v)))
                                if in_point == nil then
                                    local n = type(v) == "number" and v or tonumber(v)
                                    if n and n >= 0 then in_point = n end
                                end
                            end
                        end)
                    end
                end
            end
        end)
    end

    dlog(string.format("最终结果: in_point=%s out_point=%s", tostring(in_point), tostring(out_point)))
    return in_point, out_point
end

-- ============================================================
-- 获取时间线起始时间码偏移（帧数）
-- 达芬奇默认起始为 01:00:00:00，标记和跳转需加上此偏移
-- ============================================================
function VersionCompat:get_timeline_start_offset(timeline, fps)
    if not timeline then return 0 end
    fps = fps or 25
    local tc_str = nil
    pcall(function()
        tc_str = timeline:GetStartTimecode()
    end)
    if not tc_str or tc_str == "" then
        pcall(function()
            tc_str = timeline:GetSetting("timelineStartTimecode")
        end)
    end
    if tc_str and tc_str ~= "" then
        local h, m, s = tc_str:match("(%d+):(%d+):(%d+)")
        if h and m and s then
            return (tonumber(h) * 3600 + tonumber(m) * 60 + tonumber(s)) * fps
        end
    end
    return 0
end

-- ============================================================
-- 安全获取轨道启用状态，失败返回true（兼容旧版本无此API）
-- ============================================================
function VersionCompat:get_track_enabled(timeline, track_type, track_index)
    if not timeline then return true end
    local val = true
    pcall(function()
        -- Resolve 19使用GetIsTrackEnabled，18以下用GetTrackEnabled
        local v = nil
        if timeline.GetIsTrackEnabled then
            v = timeline:GetIsTrackEnabled(track_type, track_index)
        elseif timeline.GetTrackEnabled then
            v = timeline:GetTrackEnabled(track_type, track_index)
        end
        if v ~= nil then val = v end
    end)
    return val
end

-- ============================================================
-- 安全获取片段不透明度 (0.0-100.0)，失败返回100
-- ============================================================
function VersionCompat:get_clip_opacity(item)
    if not item then return 100 end
    local val = 100
    pcall(function()
        local v = tonumber(item:GetProperty("Opacity"))
        if v then val = v end
    end)
    return val
end

-- ============================================================
-- 安全获取片段合成模式 (0=Normal)，失败返回0
-- ============================================================
function VersionCompat:get_clip_composite_mode(item)
    if not item then return 0 end
    local val = 0
    pcall(function()
        local v = tonumber(item:GetProperty("CompositeMode"))
        if v then val = v end
    end)
    return val
end

-- ============================================================
-- 安全获取片段启用状态 (18.5+)，失败返回true
-- ============================================================
function VersionCompat:get_clip_enabled(item)
    if not item then return true end
    local val = true
    pcall(function()
        local v = item:GetClipEnabled()
        if v ~= nil then val = v end
    end)
    return val
end

-- ============================================================
-- 转换为绝对路径（处理达芬奇URI格式）
-- ============================================================
function VersionCompat:normalize_path(davinci_path)
    if not davinci_path then
        return nil
    end

    local path = davinci_path

    -- 去除 file:// 前缀
    path = path:gsub("^file://", "")

    if self.os == "windows" then
        -- 处理 /C:/... 格式 → C:\...
        path = path:gsub("^/(%a):/", "%1:\\")
        -- 统一分隔符
        path = path:gsub("/", "\\")
    end

    -- 检查文件是否存在
    local f = io.open(path, "r")
    if f then
        f:close()
        return path
    end

    return path  -- 返回标准化后的路径，即使文件不可读
end

-- ============================================================
-- 检查UI能力
-- ============================================================
function VersionCompat:can_use_uimanager()
    return self.capabilities.has_uimanager
        and self.capabilities.has_uidispatcher
        and self.is_studio
end

-- ============================================================
-- 获取版本信息字符串
-- ============================================================
function VersionCompat:get_info_string()
    local edition = self.is_studio and "Studio" or "Free"
    return string.format(
        "DaVinci Resolve %s (%s) on %s | 清何黑帧夹帧 v" .. config.PLUGIN_VERSION,
        self.version_string, edition, self.os:upper()
    )
end

-- ============================================================
-- 获取脚本安装路径建议
-- ============================================================
function VersionCompat:get_install_path()
    local home = os.getenv("HOME") or os.getenv("USERPROFILE") or ""

    if self.os == "macos" then
        return home .. "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/black_frame_detector/"
    elseif self.os == "windows" then
        local appdata = os.getenv("APPDATA") or ""
        return appdata .. "\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts\\Edit\\black_frame_detector\\"
    else
        return home .. "/.local/share/DaVinciResolve/Fusion/Scripts/Edit/black_frame_detector/"
    end
end

return VersionCompat
