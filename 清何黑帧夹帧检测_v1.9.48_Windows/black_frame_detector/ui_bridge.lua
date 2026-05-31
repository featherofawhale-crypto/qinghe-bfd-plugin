-- ui_bridge.lua - UI抽象层，三层降级策略
-- Level 1: UIManager (Studio版本，完整UI)
-- Level 2: AskUser (所有版本，简单对话框)
-- Level 3: 纯脚本模式 (无UI，默认参数)
-- v1.9.27-step15: dlog提升至模块级作用域

local config = require("config")

local UIBridge = {}
UIBridge._param_win = nil  -- 参数窗口引用，tab模式

-- 模块级调试日志（与主脚本dlog独立）
local function dlog(msg)
    local f = io.open(config.get_debug_log_path(), "a")
    if f then f:write(os.date("%Y-%m-%d %H:%M:%S") .. " [UB] " .. tostring(msg) .. "\n"); f:close() end
end

-- ============================================================
-- IO出入点缓存（Lua格式，独立于达芬奇缓存目录）
-- ============================================================
local IO_CACHE_FILE = config.get_io_cache_path()

function UIBridge.load_io_cache()
    local ok, data = pcall(function()
        local chunk = loadfile(IO_CACHE_FILE)
        if not chunk then return {} end
        return chunk() or {}
    end)
    if ok and type(data) == "table" then return data end
    -- 兼容旧JSON缓存
    local old_file = config.get_home() .. (config.get_platform() == "windows" and "\\.bfd_io_cache.json" or "/.bfd_io_cache.json")
    local f = io.open(old_file, "r")
    if f then f:close(); os.remove(old_file) end
    return {}
end

function UIBridge.save_io_cache(tl_name, io_in_str, io_out_str)
    local cache = UIBridge.load_io_cache()
    cache[tl_name] = {tin = io_in_str or "", tout = io_out_str or ""}
    -- 写入Lua格式（可靠，不依赖JSON解析）
    local lines = {"return {"}
    for name, data in pairs(cache) do
        table.insert(lines, string.format('  ["%s"] = {tin = "%s", tout = "%s"},',
            name:gsub('"', '\\"'), data.tin, data.tout))
    end
    table.insert(lines, "}")
    local f = io.open(IO_CACHE_FILE, "w")
    if f then f:write(table.concat(lines, "\n")); f:close() end
end

-- ============================================================
-- 检测可用的UI层级
-- ============================================================
function UIBridge.detect_ui_level(version_compat)
    if version_compat:can_use_uimanager() then
        return 1
    end
    local ok = pcall(function()
        if version_compat.fusion then
            version_compat.fusion:AskUser("Test", {{"test", "Checkbox", {Default = 0}}})
        end
    end)
    if ok then return 2 end
    return 3
end

-- ============================================================
-- Level 1: UIManager 完整UI
-- 分两阶段：参数配置 → 结果浏览
-- ============================================================

-- --------------- 参数配置窗口 ---------------
function UIBridge.get_params_uimanager(version_compat, timeline_list)
    local ui = version_compat.fusion.UIManager
    local disp = bmd.UIDispatcher(ui)

    -- DEBUG: 枚举 UIDispatcher 方法（诊断 Resolve 19 兼容性）
    dlog("--- UIDispatcher 方法枚举 ---")
    dlog("disp type: " .. type(disp))
    pcall(function()
        local methods = {}
        for k, v in pairs(disp) do
            table.insert(methods, tostring(k) .. "(" .. type(v) .. ")")
        end
        table.sort(methods)
        dlog("disp pairs: " .. table.concat(methods, ", "))
    end)
    local mt = getmetatable(disp)
    if mt then
        dlog("disp metatable: " .. type(mt))
        pcall(function()
            local mt_methods = {}
            for k, v in pairs(mt) do
                table.insert(mt_methods, tostring(k) .. "(" .. type(v) .. ")")
            end
            table.sort(mt_methods)
            dlog("mt pairs: " .. table.concat(mt_methods, ", "))
        end)
        if mt.__index then
            dlog("mt.__index type: " .. type(mt.__index))
            if type(mt.__index) == "table" then
                pcall(function()
                    local idx = {}
                    for k, v in pairs(mt.__index) do
                        table.insert(idx, tostring(k) .. "(" .. type(v) .. ")")
                    end
                    table.sort(idx)
                    dlog("__index pairs: " .. table.concat(idx, ", "))
                end)
            end
        end
    end
    dlog("disp.RunLoop: " .. type(disp.RunLoop))
    dlog("disp.GetEvent: " .. type(disp.GetEvent))
    dlog("--- UIDispatcher 枚举结束 ---")

    local params_result = nil
    local user_confirmed = false

    -- ====== 所有控件值通过局部变量追踪 ======
    -- Resolve 19: AddWindow 返回的 win 对象没有 FindGUI 方法
    -- 必须通过事件回调（ValueChanged/Clicked/CurrentIndexChanged）更新局部变量
    local stuck_frames_val = config.CLASSIFICATION.STUCK_FRAMES
    local suspect_frames_val = config.CLASSIFICATION.SUSPECT_FRAMES
    local pix_threshold_val = 10        -- Slider 1-50, 实际值*0.001
    local min_frames_val = 1            -- SpinBox
    local chk_error = config.DEFAULT_MARKER_TYPES.error
    local chk_suspect = config.DEFAULT_MARKER_TYPES.suspect
    local chk_scene = config.DEFAULT_MARKER_TYPES.scene
    local chk_gap = config.DEFAULT_MARKER_TYPES.gap
    local chk_opacity = config.OPACITY_DETECTION.ENABLED
    local chk_partial_opacity = true  -- 是否标记半透明素材（部分透明）
    local chk_mark_hidden = false    -- 是否标记隐藏/禁用素材（默认不勾选）
    local chk_png_opaque = false     -- PNG/PSD是否视为不透明遮挡层（默认不勾选）
    local chk_complex_mode = false   -- 复杂工程模式：跳过夹帧+叠加检测，仅FFmpeg合并分析
    local chk_corrupt_detect = false -- 渲染坏帧检测：默认关闭（可能误报）
    local chk_clear_old = true
    local chk_duplicate = true
    local chk_merge = config.MERGE_MODE.ENABLED  -- 成片模式
    local chk_html_report = false  -- HTML报告默认关闭
    local content_sample_val = config.DUPLICATE.CONTENT_SAMPLE_INTERVAL
    local io_in_tc_str = ""   -- 手动入点时间码 HH:MM:SS:FF（留空=自动检测）
    local io_out_tc_str = ""  -- 手动出点时间码

    -- 准备时间线数据 + 自动检测当前时间线
    local timeline_map = {}
    local timeline_count = 0
    if timeline_list and #timeline_list > 0 then
        for _, tl in ipairs(timeline_list) do
            table.insert(timeline_map, tl)
        end
        timeline_count = #timeline_list
    else
        table.insert(timeline_map, { name = "当前时间线", fps = 24, timeline = nil })
        timeline_count = 1
    end

    -- 自动检测当前打开的时间线，设为默认值
    local default_tl_index = 1
    local current_tl_name = nil
    pcall(function()
        local _, cur_tl = version_compat:get_current_project_and_timeline()
        if cur_tl then
            current_tl_name = cur_tl:GetName()
        end
    end)
    if current_tl_name then
        for i, tl in ipairs(timeline_map) do
            if tl.name == current_tl_name then
                default_tl_index = i
                break
            end
        end
    end
    local selected_tl_index = default_tl_index
    local selected_tl = timeline_map[default_tl_index]
    print(string.format("[BFD] 默认时间线: [%d/%d] %s (%.0ffps)",
        default_tl_index, timeline_count, selected_tl.name, selected_tl.fps))

    -- 构建时间线摘要文本（全部时间线，供TextEdit滚动查看）
    local tl_summary_lines = {}
    for i = 1, timeline_count do
        local tl = timeline_map[i]
        local marker = (i == default_tl_index) and " ←当前" or ""
        table.insert(tl_summary_lines, string.format("[%d] %s (%.0ffps)%s", i, tl.name, tl.fps, marker))
    end
    local tl_summary = table.concat(tl_summary_lines, "\n")

    -- 从缓存加载IO出入点（按时间线名称匹配）
    local io_cache = UIBridge.load_io_cache()
    local cached_io = io_cache[selected_tl.name] or {}
    io_in_tc_str = cached_io.tin or ""
    io_out_tc_str = cached_io.tout or ""
    if io_in_tc_str ~= "" or io_out_tc_str ~= "" then
        dlog("IO缓存加载: " .. selected_tl.name .. " 入点=" .. io_in_tc_str .. " 出点=" .. io_out_tc_str)
    end

    -- ====== 构建窗口（所有控件固定，不使用unpack） ======
    local win = disp:AddWindow({
        ID = "BFDMainWin",
        WindowTitle = "清何黑帧夹帧检测 v" .. config.PLUGIN_VERSION,
        Geometry = { 80, 60, 520, 820 },
        Spacing = 2,
        Margin = 10,
        ui:VGroup{
            ID = "Root",
            Spacing = 2,

            -- 标题
            ui:Label{ ID = "Title", Text = "清何黑帧夹帧检测 v" .. config.PLUGIN_VERSION,
                      Font = ui:Font{ PixelSize = 14, Bold = true },
                      Alignment = { AlignHCenter = true } },
            ui:VGap{ 2 },

            -- ====== 时间线选择 ======
            ui:HGroup{ Spacing = 4,
                ui:Label{ ID = "LblTL", Text = "时间线:", MinimumSize = { 48, 0 } },
                ui:SpinBox{ ID = "SpinTL", Value = default_tl_index, Minimum = 1, Maximum = timeline_count, MinimumSize = { 45, 0 } },
                ui:Label{ ID = "LblTLCount", Text = "/ " .. timeline_count .. "  默认=当前" },
            },
            ui:TextEdit{ ID = "TLSummary", Text = tl_summary, ReadOnly = true,
                         MinimumSize = { 200, 80 }, Font = ui:Font{ PixelSize = 9 } },
            ui:VGap{ 2 },

            -- ====== 判定阈值 ======
            ui:Label{ ID = "ClassGroupLabel", Text = "判定阈值（帧数）",
                      Font = ui:Font{ PixelSize = 11, Bold = true } },
            ui:HGroup{ Spacing = 4,
                ui:Label{ ID = "LblStuck", Text = "夹帧 ≤", MinimumSize = { 48, 0 } },
                ui:SpinBox{ ID = "StuckFrames", Value = config.CLASSIFICATION.STUCK_FRAMES, Minimum = 1, Maximum = 999, MinimumSize = { 60, 0 } },
                ui:Label{ ID = "ValStuck", Text = "→ 红色标记（需修复）" },
            },
            ui:HGroup{ Spacing = 4,
                ui:Label{ ID = "LblSus", Text = "可疑 ≤", MinimumSize = { 48, 0 } },
                ui:SpinBox{ ID = "SuspectFrames", Value = config.CLASSIFICATION.SUSPECT_FRAMES, Minimum = 1, Maximum = 9999, MinimumSize = { 60, 0 } },
                ui:Label{ ID = "ValSus", Text = "→ 黄色标记（需确认）" },
            },
            ui:Label{ ID = "ValScene", Text = "超过 → 蓝色标记（转场过渡，镜头切换的正常黑屏）",
                      Font = ui:Font{ PixelSize = 9 }, WordWrap = true, MinimumSize = { 200, 16 } },
            ui:VGap{ 2 },

            -- ====== IO入出点范围（带缓存） ======
            ui:Label{ ID = "IOGroupLabel", Text = "入出点范围（格式 HH:MM:SS:FF · 缓存按时间线名称）",
                      Font = ui:Font{ PixelSize = 11, Bold = true } },
            ui:Label{ ID = "IOHintLabel", Text = "⚠ 复杂模式必须填写出入点，否则无法开始检测",
                      Font = ui:Font{ PixelSize = 9 }, MinimumSize = { 380, 14 } },
            ui:HGroup{ Spacing = 4,
                ui:Label{ ID = "LblIOIn", Text = "入点:", MinimumSize = { 35, 0 } },
                ui:LineEdit{ ID = "IOInTC", Text = io_in_tc_str, MinimumSize = { 80, 0 } },
                ui:Label{ ID = "LblIOOut", Text = "出点:", MinimumSize = { 35, 0 } },
                ui:LineEdit{ ID = "IOOutTC", Text = io_out_tc_str, MinimumSize = { 80, 0 } },
                ui:Button{ ID = "BtnFullTimeline", Text = "全时间线", MinimumSize = { 70, 24 } },
            },
            ui:Label{ ID = "LblEstimate", Text = "⏱ 预估: 短素材(<5min) ~30s | 中等(15min) ~1min | 长素材(30min) ~2min | 超长(1h+) ~5min",
                      Font = ui:Font{ PixelSize = 9 }, MinimumSize = { 200, 14 } },
            ui:VGap{ 2 },

            -- ====== 检测参数 ======
            ui:Label{ ID = "DetectGroupLabel", Text = "检测参数",
                      Font = ui:Font{ PixelSize = 11, Bold = true } },
            ui:HGroup{ Spacing = 4,
                ui:Label{ ID = "LblPixTh", Text = "黑场阈值", MinimumSize = { 55, 0 } },
                ui:SpinBox{ ID = "PixThreshold", Value = 10, Minimum = 1, Maximum = 1000, MinimumSize = { 60, 0 } },
                ui:Label{ ID = "LblPixThUnit", Text = "x0.001（10=标准，越低越严，1000=1.0）" },
            },
            ui:HGroup{ Spacing = 4,
                ui:Label{ ID = "LblMinDr", Text = "最短持续", MinimumSize = { 55, 0 } },
                ui:SpinBox{ ID = "MinFrames", Value = 1, Minimum = 1, Maximum = 9999, MinimumSize = { 60, 0 } },
                ui:Label{ ID = "ValMinFrames", Text = "帧（短于此值忽略）" },
            },
            ui:VGap{ 2 },

            -- ====== 时间线颜色标记 ======
            ui:Label{ ID = "MarkerGroupLabel", Text = "时间线颜色标记（勾选即打在时间线上，按 ; 跳转）",
                      Font = ui:Font{ PixelSize = 11, Bold = true } },
            ui:HGroup{ Spacing = 6,
                ui:CheckBox{ ID = "ChkError",   Text = "🔴 夹帧",  Checked = config.DEFAULT_MARKER_TYPES.error },
                ui:CheckBox{ ID = "ChkSuspect", Text = "🟡 可疑",  Checked = config.DEFAULT_MARKER_TYPES.suspect },
                ui:CheckBox{ ID = "ChkScene",   Text = "🔵 转场",  Checked = config.DEFAULT_MARKER_TYPES.scene },
                ui:CheckBox{ ID = "ChkGap",     Text = "🟣 间隙",  Checked = config.DEFAULT_MARKER_TYPES.gap },
            },
            ui:Label{ ID = "MarkerHint", Text = "勾选的类型会在时间线上打对应颜色的标记点",
                      Font = ui:Font{ PixelSize = 9 }, WordWrap = true },
            ui:VGap{ 2 },

            -- ====== 附加功能 ======
            ui:Label{ ID = "OptionsLabel", Text = "附加功能",
                      Font = ui:Font{ PixelSize = 11, Bold = true } },
            ui:CheckBox{ ID = "ChkClearOld", Text = "清除旧标记", Checked = true },
            ui:CheckBox{ ID = "ChkDuplicate", Text = "重复片段检测（帧指纹比对）", Checked = true },
            ui:CheckBox{ ID = "ChkOpacity", Text = "透明度/禁用检测", Checked = config.OPACITY_DETECTION.ENABLED },
            ui:CheckBox{ ID = "ChkMarkHidden", Text = "  标记隐藏/禁用素材（默认跳过）", Checked = false },
            ui:CheckBox{ ID = "ChkPngOpaque", Text = "  PNG/PSD视为不透明遮挡层（多轨叠加时）", Checked = false },
            ui:CheckBox{ ID = "ChkComplexMode", Text = "  复杂工程模式（需填出入点 · 渲染后分析）", Checked = false },
            ui:CheckBox{ ID = "ChkCorruptDetect", Text = "    渲染坏帧检测 ⚠ 不推荐 · 可能误报 · 需开启复杂模式", Checked = false },
            ui:CheckBox{ ID = "ChkPartialOpacity", Text = "  标记半透明素材（取消则跳过半透明效果）", Checked = true },
            ui:CheckBox{ ID = "ChkMerge", Text = "成片模式（推荐，合并分析更快）", Checked = config.MERGE_MODE.ENABLED },
            ui:CheckBox{ ID = "ChkGenReport", Text = "生成HTML报告（检测完成后自动打开）", Checked = false },
            ui:HGroup{ Spacing = 4,
                ui:Label{ ID = "LblContentDup", Text = "指纹采样间隔", MinimumSize = { 80, 0 } },
                ui:SpinBox{ ID = "ContentSampleInterval", Value = config.DUPLICATE.CONTENT_SAMPLE_INTERVAL, Minimum = 1, Maximum = 9999, MinimumSize = { 60, 0 } },
                ui:Label{ ID = "ValContentInt", Text = "帧/次" },
            },
            ui:VGap{ 4 },

            -- ====== 状态栏 ======
            ui:Label{ ID = "StatusBar", Text = [[就绪 — 请配置参数后点击「开始检测」]],
                      Font = ui:Font{ PixelSize = 9 }, WordWrap = true,
                      Alignment = { AlignHCenter = true },
                      MinimumSize = { 200, 20 } },

            -- ====== 按钮 ======
            ui:Button{ ID = "StartBtn", Text = "开始检测", MinimumSize = { 200, 36 } },
            ui:VGap{ 2 },
            ui:HGroup{ Spacing = 6,
                ui:Button{ ID = "BtnClearMarkers", Text = "清除所有标记", MinimumSize = { 100, 28 } },
                ui:Button{ ID = "BtnFeedback", Text = "反馈", MinimumSize = { 80, 28 } },
                ui:Button{ ID = "BtnCancel", Text = "取消", MinimumSize = { 80, 28 } },
            },
        },
    })

    if not win then
        dlog("AddWindow 返回 nil")
        return nil, "UIManager AddWindow 返回 nil"
    end
    dlog("AddWindow 成功")

    -- ====== 事件回调：更新局部变量（不依赖FindGUI）======

    -- 时间线选择：SpinBox值变化
    win.On.SpinTL.ValueChanged = function(ev)
        local idx = ev.Value
        if idx >= 1 and idx <= timeline_count then
            selected_tl_index = idx
            selected_tl = timeline_map[idx]
            print(string.format("[BFD] 已选择时间线: [%d/%d] %s (%.0ffps)",
                idx, timeline_count, selected_tl.name or "?", selected_tl.fps or 24))
            dlog("时间线SpinBox: " .. idx)
        end
    end

    -- SpinBox: 值变化
    win.On.StuckFrames.ValueChanged = function(ev) stuck_frames_val = ev.Value end
    win.On.SuspectFrames.ValueChanged = function(ev) suspect_frames_val = ev.Value end
    win.On.MinFrames.ValueChanged = function(ev) min_frames_val = ev.Value end
    win.On.ContentSampleInterval.ValueChanged = function(ev) content_sample_val = ev.Value end
    -- Slider: 像素阈值
    win.On.PixThreshold.ValueChanged = function(ev) pix_threshold_val = ev.Value end

    -- CheckBox: 勾选状态变化（Clicked事件，ev.Checked = 新状态）
    win.On.ChkError.Clicked = function(ev) chk_error = ev.Checked ~= nil and ev.Checked or not chk_error end
    win.On.ChkSuspect.Clicked = function(ev) chk_suspect = ev.Checked ~= nil and ev.Checked or not chk_suspect end
    win.On.ChkScene.Clicked = function(ev) chk_scene = ev.Checked ~= nil and ev.Checked or not chk_scene end
    win.On.ChkGap.Clicked = function(ev) chk_gap = ev.Checked ~= nil and ev.Checked or not chk_gap end
    win.On.ChkOpacity.Clicked = function(ev) chk_opacity = ev.Checked ~= nil and ev.Checked or not chk_opacity end
    win.On.ChkMarkHidden.Clicked = function(ev) chk_mark_hidden = ev.Checked ~= nil and ev.Checked or not chk_mark_hidden end
    win.On.ChkPngOpaque.Clicked = function(ev) chk_png_opaque = ev.Checked ~= nil and ev.Checked or not chk_png_opaque end
    win.On.ChkComplexMode.Clicked = function(ev) chk_complex_mode = ev.Checked ~= nil and ev.Checked or not chk_complex_mode end
    win.On.ChkPartialOpacity.Clicked = function(ev) chk_partial_opacity = ev.Checked ~= nil and ev.Checked or not chk_partial_opacity end
    win.On.ChkClearOld.Clicked = function(ev) chk_clear_old = ev.Checked ~= nil and ev.Checked or not chk_clear_old end
    win.On.ChkDuplicate.Clicked = function(ev) chk_duplicate = ev.Checked ~= nil and ev.Checked or not chk_duplicate end
    win.On.ChkMerge.Clicked = function(ev) chk_merge = ev.Checked ~= nil and ev.Checked or not chk_merge end
    win.On.ChkCorruptDetect.Clicked = function(ev) chk_corrupt_detect = ev.Checked ~= nil and ev.Checked or not chk_corrupt_detect end
    win.On.ChkGenReport.Clicked = function(ev) chk_html_report = ev.Checked ~= nil and ev.Checked or not chk_html_report; dlog("ChkGenReport.Clicked: raw=" .. tostring(ev.Checked) .. " val=" .. tostring(chk_html_report)) end
    win.On.IOInTC.TextChanged = function(ev) io_in_tc_str = ev.Text or "" end
    win.On.IOOutTC.TextChanged = function(ev) io_out_tc_str = ev.Text or "" end
    win.On.BtnFullTimeline.Clicked = function(ev)
        io_in_tc_str = ""
        io_out_tc_str = ""
        local tl = selected_tl or timeline_map[1]
        if tl then UIBridge.save_io_cache(tl.name, "", "") end
        print("[BFD] IO出入点已清除，缓存已更新")
    end

    -- 开始检测（使用按钮选中的时间线）
    win.On.StartBtn.Clicked = function(ev)
        local tl = selected_tl or timeline_map[1]
        local tl_idx = selected_tl_index
        local tl_fps = tl.fps or 24
        dlog("StartBtn: idx=" .. tl_idx .. " timeline=" .. (tl.name or "?") .. " fps=" .. tl_fps .. " html_report=" .. tostring(chk_html_report))

        -- 复杂模式校验：必须填写IO出入点
        if chk_complex_mode and (io_in_tc_str == "" or io_out_tc_str == "") then
            dlog("复杂模式：IO为空，拒绝开始")
            print("[BFD] ⚠ 复杂工程模式需要填写出入点范围（上方IO区域），请填写后重新点击开始检测")
            return  -- 不退出RunLoop，不设置params_result
        end

        params_result = {
            use_frames       = true,
            stuck_frames     = stuck_frames_val,
            suspect_frames   = suspect_frames_val,
            pix_th           = pix_threshold_val * 0.001,
            min_duration     = min_frames_val / tl_fps,
            marker_types = {
                error   = chk_error,
                suspect = chk_suspect,
                scene   = chk_scene,
                gap     = chk_gap,
                opacity = chk_opacity,
            },
            clear_old        = chk_clear_old,
            detect_duplicate = chk_duplicate,
            merge_mode = chk_merge,
            mark_hidden_clips = chk_mark_hidden,
            png_as_opaque = chk_png_opaque,
            complex_mode = chk_complex_mode,
            detect_corrupt = chk_corrupt_detect,
            mark_partial_opacity = chk_partial_opacity,
            content_sample_interval = content_sample_val,
            manual_io_in     = io_in_tc_str,
            manual_io_out    = io_out_tc_str,
            html_report      = chk_html_report,
            verbose          = true,
            timeline_index   = tl_idx - 1,
            timeline_name    = tl.name,
            timeline_fps     = tl.fps,
            timeline_obj     = tl.timeline,
        }
        -- 保存IO出入点到缓存
        UIBridge.save_io_cache(tl.name, io_in_tc_str, io_out_tc_str)
        user_confirmed = true
        dlog("用户确认，退出事件循环")
        disp:ExitLoop()
    end

    -- 清除所有标记（直接清除，UIManager事件处理器内不能用AskUser）
    win.On.BtnClearMarkers.Clicked = function(ev)
        dlog("用户点击清除所有标记")
        local tl = selected_tl or timeline_map[1]
        local tl_obj = tl and tl.timeline
        if not tl_obj then
            pcall(function()
                local _, ct = version_compat:get_current_project_and_timeline()
                if ct then tl_obj = ct end
            end)
        end
        if tl_obj then
            -- 只清除本插件标记（按 [BFD] 前缀匹配），不误删用户手动标记
            local markers = version_compat:get_markers(tl_obj)
            local cleared = 0
            for frame, marker in pairs(markers) do
                if type(marker) == "table" and marker.name then
                    if marker.name:find("^%[BFD") then
                        local ok = pcall(function() tl_obj:DeleteMarkerAtFrame(frame) end)
                        if ok then cleared = cleared + 1 end
                    end
                end
            end
            print(string.format("[BFD] ✅ 已清除时间线 \"%s\" 上的 %d 个检测标记",
                tl.name or "?", cleared))
        else
            print("[BFD] ❌ 清除失败：未获取到时间线对象，请确认已打开项目和时间线")
        end
    end

    -- 取消
    win.On.BtnCancel.Clicked = function(ev)
        dlog("用户点击取消")
        params_result = nil
        user_confirmed = false
        disp:ExitLoop()
    end

    -- 反馈按钮（两步操作，避免阻塞UI）
    local fb_pending = false  -- 是否有待发送的反馈文件
    local fb_file_path = config.get_home() .. "/bfd_feedback.txt"

    local function do_send_feedback()
        -- 读取用户输入（跳过模板头部，取"────"分隔线之前的内容）
        local fb_text = ""
        local rf = io.open(fb_file_path, "r")
        if rf then
            local raw = rf:read("*a") or ""
            rf:close()
            -- 找到分隔线，取上方用户输入的内容
            local sep = raw:find("────────────")
            if sep then
                fb_text = raw:sub(1, sep - 1)
            end
            -- 清理模板头（╔═...╗ 块）
            fb_text = fb_text:gsub("%s*╔[═╗║╚╝★]+.-╝%s*", "")
            fb_text = fb_text:gsub("★ .-\n", "")
            fb_text = fb_text:gsub("版本: v[%d.]+ %| .-\n", "")
            fb_text = fb_text:gsub("^%s+", ""):gsub("%s+$", "")
        end
        pcall(function() os.remove(fb_file_path) end)

        if fb_text == "" then
            print("[BFD] ❌ 反馈内容为空，已取消发送")
            dlog("反馈取消：内容为空")
            return
        end

        -- 读取调试日志
        local log_lines = {}
        local log_path = config.get_debug_log_path()
        local lf = io.open(log_path, "r")
        if lf then
            for line in lf:lines() do table.insert(log_lines, line) end
            lf:close()
        end
        local log_tail = ""
        local start_line = math.max(1, #log_lines - 199)
        for i = start_line, #log_lines do
            log_tail = log_tail .. log_lines[i] .. "\n"
        end
        if #log_tail > 12000 then log_tail = log_tail:sub(-12000) end

        local msg = "【BFD 用户反馈】\n"
        msg = msg .. "版本: v" .. (config.PLUGIN_VERSION or "?") .. "\n"
        msg = msg .. "时间: " .. os.date("%Y-%m-%d %H:%M:%S") .. "\n"
        msg = msg .. "反馈内容:\n" .. fb_text .. "\n\n"
        msg = msg .. "--- 最近调试日志 ---\n" .. log_tail

        local function json_escape(s)
            return s:gsub("\\", "\\\\"):gsub('"', '\\"'):gsub("\n", "\\n"):gsub("\r", "\\r"):gsub("\t", "\\t"):gsub("%c", "")
        end
        local payload = string.format('{"msg_type":"text","content":{"text":"%s"}}', json_escape(msg))

        local home = config.get_home()
        local tmp_path = home .. "/bfd_feedback_payload.json"
        local tf2 = io.open(tmp_path, "w")
        if not tf2 then print("[BFD] ❌ 无法创建临时文件"); return end
        tf2:write(payload)
        tf2:close()

        local url = config.FEISHU_WEBHOOK_URL or ""
        local cmd = string.format(
            'curl -s -X POST --connect-timeout 10 --max-time 15 -H "Content-Type: application/json" -d @%s "%s"',
            tmp_path, url
        )
        local pf = io.popen(cmd, "r")
        local result = ""
        if pf then result = pf:read("*a") or ""; pf:close() end
        pcall(function() os.remove(tmp_path) end)

        if result:find('"code":0') or result:find('"ok":true') or result == "" then
            dlog("反馈发送成功: " .. result)
            print("[BFD] ✅ 反馈已发送，感谢！")
        else
            dlog("反馈发送失败: " .. result)
            print("[BFD] ❌ 反馈发送失败，请检查网络后重试")
        end
    end

    win.On.BtnFeedback.Clicked = function(ev)
        if fb_pending then
            -- 第二次点击：发送已编辑的反馈
            dlog("用户点击发送反馈")
            fb_pending = false
            do_send_feedback()
        else
            -- 第一次点击：打开文本编辑器
            dlog("用户点击反馈按钮，打开编辑器")
            fb_pending = true
            local tf = io.open(fb_file_path, "w")
            if tf then
                tf:write("╔══════════════════════════════════════════════════════════╗\n")
                tf:write("║  ★ 请在下方输入反馈内容，保存并关闭本窗口              ║\n")
                tf:write("║  ★ 关闭后必须再次点击达芬奇插件界面的「反馈」按钮发送  ║\n")
                tf:write("╚══════════════════════════════════════════════════════════╝\n")
                tf:write("\n")
                tf:write("版本: v" .. (config.PLUGIN_VERSION or "?") .. " | ")
                tf:write(os.date("%Y-%m-%d %H:%M:%S") .. "\n")
                tf:write("──────────────────────────────────────────────────────────\n\n")
                tf:close()
            end
            local plat = config.get_platform()
            if plat == "windows" then
                os.execute('start "" "' .. fb_file_path .. '" 2>nul')
            else
                os.execute('open "' .. fb_file_path .. '" 2>/dev/null')
            end
            print("[BFD] 📝 请在文本编辑器中输入反馈，保存关闭后再次点击「反馈」按钮发送")
        end
    end

    win.On.BFDMainWin.Close = function(ev)
        dlog("用户关闭窗口")
        params_result = nil
        user_confirmed = false
        disp:ExitLoop()
    end

    -- 显示窗口（AddWindow 需要显式 Show）
    win:Show()
    UIBridge._param_win = win  -- 保存引用，tab模式使用
    dlog("窗口已创建并显示，进入事件循环 (RunLoop)...")

    -- 事件循环：优先 RunLoop，失败则尝试 StepLoop
    local loop_ok, loop_err = pcall(function() disp:RunLoop() end)
    if not loop_ok then
        dlog("RunLoop 错误: " .. tostring(loop_err))
        -- RunLoop 失败，尝试 StepLoop
        if type(disp.StepLoop) == "function" then
            dlog("降级使用 StepLoop...")
            local step_count = 0
            pcall(function()
                while disp:StepLoop() do
                    step_count = step_count + 1
                end
            end)
            dlog("StepLoop 退出，共处理 " .. step_count .. " 个事件")
        end
    else
        dlog("RunLoop 正常退出")
    end

    if not user_confirmed then
        win:Hide()
        UIBridge._param_win = nil
        return nil, "用户取消"
    end

    -- Tab模式: 用户确认后不隐藏窗口，保持显示（检测期间冻结）
    -- 待结果窗口打开时再隐藏
    print("[BFD] 正在检测中... 参数窗口将保持显示")
    return params_result
end

-- --------------- 结果浏览窗口 ---------------
function UIBridge.show_results_console(analyzed_results, params)
    print("[BFD] 结果窗口无法创建（UIManager不可用），请使用标记导航：")
    print("[BFD]   按 ; 跳转到下一个标记")
    print("[BFD]   按 Shift+; 跳转到上一个标记")
    print("[BFD]   按 Shift+F 手动输入时间码跳转")
end

-- v1.9.21: Tab模式 + 时间码列表 + SpinBox选择 + 一键跳转
function UIBridge.show_results_uimanager(version_compat, analyzed_results, params)
    -- 保留参数窗口不隐藏，结果窗口打开查看，关闭后参数窗口仍可用
    dlog("results_win: 参数窗口保留，同时打开结果窗口")

    -- nil guard: 长时间检测后UIManager可能变stale
    if not version_compat or not version_compat.fusion then
        error("version_compat.fusion 为nil")
    end
    local ui = version_compat.fusion.UIManager
    if not ui then
        error("UIManager 为nil")
    end
    dlog("results_win: UIManager可用，创建UIDispatcher...")
    local disp = bmd.UIDispatcher(ui)
    if not disp then
        error("UIDispatcher创建失败")
    end
    dlog("results_win: UIDispatcher创建成功")
    local timeline = params and params.timeline_obj

    -- 构建有序问题列表（按时间线位置排序）
    local problem_list = {}
    for _, r in ipairs(analyzed_results.errors) do table.insert(problem_list, r) end
    for _, r in ipairs(analyzed_results.suspects) do table.insert(problem_list, r) end
    for _, r in ipairs(analyzed_results.gaps) do table.insert(problem_list, r) end
    for _, r in ipairs(analyzed_results.scenes) do table.insert(problem_list, r) end
    table.sort(problem_list, function(a, b) return a.timeline_start_frame < b.timeline_start_frame end)

    local total_problems = #problem_list
    -- 传统检测可能为空，但包含重复检测/透明度等结果（通过selected_records传入）
    local total_all = analyzed_results.total_all or total_problems
    if total_all == 0 then return end

    -- 统计文本
    local stats_text = string.format(
        "夹帧:%d  可疑:%d  转场:%d  空位:%d",
        analyzed_results.summary.error_count,
        analyzed_results.summary.suspect_count,
        analyzed_results.summary.scene_count,
        analyzed_results.summary.gap_count
    )

    -- 合并selected_records（重复检测/透明度等非FFmpeg结果）到显示列表
    if analyzed_results.selected_records then
        local sr = analyzed_results.selected_records
        -- 哈希表去重：O(n+m) 替代 O(n*m)
        local seen = {}
        for _, existing in ipairs(problem_list) do
            local key = tostring(existing.timeline_start_frame or 0) .. "|" .. tostring(existing.marker_name or "")
            seen[key] = true
        end
        local merged_count = 0
        for _, r in ipairs(sr) do
            local key = tostring(r.timeline_start_frame or 0) .. "|" .. tostring(r.marker_name or "")
            if not seen[key] then
                seen[key] = true
                table.insert(problem_list, r)
                merged_count = merged_count + 1
            end
        end
        if merged_count > 0 then
            table.sort(problem_list, function(a, b) return (a.timeline_start_frame or 0) < (b.timeline_start_frame or 0) end)
            total_problems = #problem_list
            dlog(string.format("results_win: 合并selected_records, 新增%d条, 总计%d条", merged_count, total_problems))
        end
    end

    -- 标记类型全称
    local type_names = {
        error = "夹帧异常", suspect = "可疑黑帧", scene = "转场过渡", gap = "片段间隙",
        opacity = "透明度", duplicate = "重复片段", content_dup = "内容重复",
        opacity_hidden = "隐藏素材", opacity_low = "低透明度", opacity_partial = "部分透明",
        clip_disabled = "已禁用", opacity_hidden_covered = "隐藏素材(下层有内容)",
        composite_nonormal = "非标准合成",
    }

    -- 构建问题列表文本（完整列表，用于TextEdit只读展示）
    local list_text_lines = {}
    for i, r in ipairs(problem_list) do
        local label = type_names[r.classification] or r.classification or r.marker_name or "?"
        local fname = ""
        if r.classification == "gap" then
            fname = "[片段间隙]"
        elseif r.source_file then
            fname = r.source_file:match("([^\\/]+)$") or ""
        end
        local dur = r.duration_frames or 0
        local tc = r.timeline_start_tc or ""
        local frame = r.timeline_start_frame or 0
        table.insert(list_text_lines, string.format("#%-4d [%s] %s  帧%-6d  %.1f帧  %s",
            i, label, tc, frame, dur, fname))
    end
    local list_text = table.concat(list_text_lines, "\n")
    dlog(string.format("results_win: list_text_lines=%d chars=%d", #list_text_lines, #list_text))

    -- 第一个问题的详情
    local r1 = problem_list[1]
    local detail1 = ""
    if r1 then
        local fname = r1.classification == "gap" and "[片段间隙]" or (r1.source_file and r1.source_file:match("([^\\/]+)$") or "?")
        local r1t = r1.timeline_start_tc or ""
        local r1f = r1.timeline_start_frame or 0
        local r1d = r1.duration_frames or 0
        detail1 = string.format("#1 [%s] %s | 帧%d | %.1f帧 | %s",
            type_names[r1.classification] or r1.classification or r1.marker_name or "?",
            r1t, r1f, r1d, fname)
    end

    local current_idx = 1

    -- 跳转到指定编号的问题帧
    local function do_jump(idx)
        if idx < 1 or idx > total_problems then return end
        current_idx = idx
        local r = problem_list[idx]
        local tname = type_names[r.classification] or r.classification or r.marker_name or "?"
        local fname = r.classification == "gap" and "[片段间隙]" or (r.source_file and r.source_file:match("([^\\/]+)$") or "?")
        local tc = r.timeline_start_tc or ""
        local sf = r.timeline_start_frame or 0
        local df = r.duration_frames or 0
        if r and timeline and tc ~= "" then
            local tc_ok, tc_err = pcall(function() timeline:SetCurrentTimecode(tc) end)
            if not tc_ok then
                dlog(string.format("results_win: SetCurrentTimecode(%s) failed: %s", tc, tostring(tc_err)))
            end
        end
        -- SpinBox无法程序化更新（Resolve 19无FindGUI），通过Console输出当前位置
        print(string.format("[BFD] >>> 第%d/%d个 [%s] %s | 帧%d | %.1f帧 | %s <<<",
            idx, total_problems, tname, tc, sf, df, fname))
    end

    dlog("results_win: 开始创建结果窗口...")
    local win
    local add_ok, add_err = pcall(function()
        win = disp:AddWindow({
            ID = "BFDResultWin",
            WindowTitle = "检测结果 - 清何黑帧夹帧检测",
            Geometry = { 60, 40, 600, 530 },
            Spacing = 3,
            Margin = 12,

            ui:VGroup{
                ID = "Root",

                ui:Label{ ID = "Title", Text = "检测完成 - 共 " .. total_problems .. " 个问题",
                          Font = ui:Font{ PixelSize = 14, Bold = true } },
                ui:Label{ ID = "StatsLabel", Text = stats_text,
                          Font = ui:Font{ PixelSize = 11 } },
                ui:VGap{ 2 },

                ui:TextEdit{ ID = "ProblemList", Text = list_text,
                             ReadOnly = true, MinimumSize = { 200, 340 } },
                ui:VGap{ 2 },

                ui:Label{ ID = "DetailLabel", Text = "选中: " .. detail1,
                          Font = ui:Font{ PixelSize = 10, Bold = true }, WordWrap = true,
                          MinimumSize = { 200, 20 } },

                ui:HGroup{ Spacing = 4,
                    ui:Button{ ID = "BtnPrev", Text = "◀ 上一个", MinimumSize = { 100, 28 } },
                    ui:Button{ ID = "BtnNext", Text = "下一个 ▶", MinimumSize = { 100, 28 } },
                },
                ui:VGap{ 2 },

                ui:Label{ ID = "HintLabel", Text = "◀▶ 按钮切换问题 | 当前序号看Console（工作区>Console）| 按 ; 键浏览标记",
                          Font = ui:Font{ PixelSize = 9 }, WordWrap = true,
                          MinimumSize = { 200, 28 } },
                ui:VGap{ 2 },

                ui:Button{ ID = "BtnClose", Text = "关闭", MinimumSize = { 80, 28 } },
            },
        })
    end)

    if not add_ok then
        local err_msg = "AddWindow异常: " .. tostring(add_err)
        dlog("results_win: " .. err_msg)
        print("[BFD] " .. err_msg)
        error(err_msg)  -- 向上抛给 show_results 的 pcall，触发 AskUser 降级
    end
    if not win then
        error("AddWindow返回nil")
    end
    dlog("results_win: AddWindow成功，注册事件回调...")

    -- 上一个
    win.On.BtnPrev.Clicked = function(ev)
        if current_idx > 1 then do_jump(current_idx - 1) end
    end
    -- 下一个
    win.On.BtnNext.Clicked = function(ev)
        if current_idx < total_problems then do_jump(current_idx + 1) end
    end
    win.On.BtnClose.Clicked = function(ev) disp:ExitLoop() end
    win.On.BFDResultWin.Close = function(ev) disp:ExitLoop() end

    -- 默认跳转到第一个问题
    do_jump(1)

    win:Show()
    local loop_ok, _ = pcall(function() disp:RunLoop() end)
    if not loop_ok then
        if type(disp.StepLoop) == "function" then
            pcall(function() while disp:StepLoop() do end end)
        end
    end
    win:Hide()
end

-- ============================================================
-- Level 2: AskUser 简单对话框获取参数
-- ============================================================
function UIBridge.get_params_askuser(version_compat, timeline_list)
    local comp = nil
    if version_compat.fusion then comp = version_compat.fusion end
    local selected_tl = nil

    -- 如果有多条时间线，让用户选择
    if timeline_list and #timeline_list > 1 then
        local tl_names = {}
        for _, tl in ipairs(timeline_list) do
            table.insert(tl_names, string.format("%s (%.0ffps)", tl.name, tl.fps))
        end
        local tl_ret = {}
        if comp then
            tl_ret = comp:AskUser("选择要检测的时间线", {
                {"timeline", "Dropdown", { Options = tl_names, Default = 0 }},
            })
        end
        selected_tl = timeline_list[(tl_ret.timeline or 0) + 1] or timeline_list[1]
    else
        selected_tl = timeline_list and timeline_list[1]
    end

    -- 步骤1: 灵敏度预设
    local preset_ret = {}
    if comp then
        preset_ret = comp:AskUser("选择检测模式", {
            {"preset", "Dropdown", {
                Options = {
                    config.PRESETS.high.name,
                    config.PRESETS.normal.name,
                    config.PRESETS.low.name,
                },
                Default = 1,
            }},
        })
    end

    local preset_map = {
        [0] = config.PRESETS.high,
        [1] = config.PRESETS.normal,
        [2] = config.PRESETS.low,
    }
    local selected = preset_ret and preset_map[preset_ret.preset] or config.PRESETS.normal

    -- 步骤2: 标记类型选择 + 重复检测 + 采样间隔
    local marker_ret = {}
    if comp then
        marker_ret = comp:AskUser("要标记的类型", {
            {"error",   "Checkbox", { Default = 1 }},
            {"suspect", "Checkbox", { Default = 1 }},
            {"scene",   "Checkbox", { Default = 0 }},
            {"gap",     "Checkbox", { Default = 1 }},
            {"duplicate", "Checkbox", { Default = 1 }},
            {"opacity", "Checkbox", { Default = 1 }},
        })
    end

    -- 步骤2b: 采样间隔
    local sample_ret = {}
    if comp then
        sample_ret = comp:AskUser("帧指纹采样间隔", {
            {"interval", "Dropdown", { Options = {"1帧 (最精确/最慢)", "2帧", "3帧 (推荐)", "5帧", "10帧 (快速)"}, Default = 2 }},
        })
    end
    local sample_interval_map = { [0]=1, 2, 3, 5, 10 }

    -- 步骤3: 确认开始
    if comp then
        local confirm = comp:AskUser("确认开始检测？", {
            {"confirm", "Checkbox", { Default = 1 }},
        })
        if not confirm then return nil, "用户取消" end
    end

    local params = {
        use_frames       = true,
        stuck_frames     = selected.stuck_frames,
        suspect_frames   = selected.suspect_frames,
        pix_th           = selected.pix_th,
        min_duration     = selected.min_duration,
        marker_types = {
            error   = marker_ret and marker_ret.error == 1,
            suspect = marker_ret and marker_ret.suspect == 1,
            scene   = marker_ret and marker_ret.scene == 1,
            gap     = marker_ret and marker_ret.gap == 1,
            opacity = marker_ret and marker_ret.opacity == 1,
        },
        clear_old        = true,
        detect_duplicate = true,
        mark_hidden_clips = false,
        png_as_opaque = false,
        complex_mode = false,
        detect_corrupt = false,  -- 渲染坏帧检测：默认关闭
        content_sample_interval = sample_interval_map[sample_ret.interval] or 3,
        html_report      = false,
        verbose          = true,
        -- 时间线选择
        timeline_name    = selected_tl and selected_tl.name or "当前时间线",
        timeline_fps     = selected_tl and selected_tl.fps or 24,
        timeline_obj     = selected_tl and selected_tl.timeline,
    }

    return params
end

-- ============================================================
-- Level 3: 纯脚本模式
-- ============================================================
function UIBridge.get_params_script()
    return {
        use_frames       = true,
        stuck_frames     = config.CLASSIFICATION.STUCK_FRAMES,
        suspect_frames   = config.CLASSIFICATION.SUSPECT_FRAMES,
        pix_th           = config.FFMPEG.PIXEL_THRESHOLD,
        pic_th           = config.FFMPEG.PICTURE_RATIO,
        min_duration     = config.FFMPEG.MIN_BLACK_DURATION,
        marker_types = {
            error     = config.DEFAULT_MARKER_TYPES.error,
            suspect   = config.DEFAULT_MARKER_TYPES.suspect,
            scene     = config.DEFAULT_MARKER_TYPES.scene,
            gap       = config.DEFAULT_MARKER_TYPES.gap,
            duplicate = config.DEFAULT_MARKER_TYPES.duplicate,
            opacity   = config.DEFAULT_MARKER_TYPES.opacity,
        },
        clear_old        = true,
        detect_duplicate = true,
        mark_hidden_clips = false,
        png_as_opaque = false,
        complex_mode = false,
        detect_corrupt = false,  -- 渲染坏帧检测：默认关闭
        content_sample_interval = config.DUPLICATE.CONTENT_SAMPLE_INTERVAL,
        html_report      = false,
        verbose          = true,
    }
end

-- ============================================================
-- 统一入口：获取检测参数
-- v1.9.1: Level 1 失败时自动降级到 Level 2
-- ============================================================
function UIBridge.get_detection_params(version_compat, timeline_list)
    local bridge_ok, PyParamsBridge = pcall(require, "py_params_bridge")
    if bridge_ok and PyParamsBridge and PyParamsBridge.has_pending_params then
        local has_external = false
        pcall(function()
            has_external = PyParamsBridge.has_pending_params()
        end)
        if has_external then
            local ok, params_or_err = pcall(PyParamsBridge.load_pending_params, timeline_list)
            if ok and params_or_err then
                print("[BFD] UI Level 0: PySide6 外部参数模式")
                return params_or_err
            end
            print("[BFD] PySide6 参数读取失败，回退到内置 UI: " .. tostring(params_or_err))
        end
    end

    local level = UIBridge.detect_ui_level(version_compat)

    if level == 1 then
        print("[BFD] UI Level 1: UIManager 完整模式")
        local ok, result = pcall(UIBridge.get_params_uimanager, version_compat, timeline_list)
        if ok and result then
            return result
        end
        print("[BFD] UIManager 失败 (" .. tostring(result) .. ")，返回错误")
        return nil, result or "UIManager 参数获取失败"
    end

    if level <= 2 then
        print("[BFD] UI Level 2: AskUser 简化模式")
        return UIBridge.get_params_askuser(version_compat, timeline_list)
    else
        print("[BFD] UI Level 3: 纯脚本模式（使用默认参数）")
        return UIBridge.get_params_script()
    end
end

-- ============================================================
-- 显示结果（自动选择UI方式）
-- ============================================================
function UIBridge.show_results(version_compat, analyzed_results, params)
    print("[BFD] show_results: 进入")
    local level = UIBridge.detect_ui_level(version_compat)
    print("[BFD] show_results: ui_level=" .. level)

    -- Console 始终打印摘要
    local Analyzer = require("black_frame_analyzer")
    local summary_text = Analyzer.generate_summary_text(analyzed_results)
    print("\n" .. summary_text)

    local uimgr_ok = false
    if level == 1 then
        print("[BFD] 正在打开结果浏览窗口...")
        local ok, err = pcall(UIBridge.show_results_uimanager, version_compat, analyzed_results, params)
        uimgr_ok = ok
        print("[BFD] show_results: pcall uimgr=" .. tostring(ok))
        if not ok then
            dlog("show_results: UIManager窗口失败: " .. tostring(err))
            print("[BFD] 结果窗口打开失败: " .. tostring(err))
        end
    end

    -- 如果UIManager窗口未显示（level>1 或 创建失败），降级到AskUser
    print("[BFD] show_results: 检查降级 level=" .. level .. " uimgr_ok=" .. tostring(uimgr_ok))
    if level > 1 or (level == 1 and not uimgr_ok) then
        print("[BFD] show_results: 进入降级分支，尝试Fusion()...")
        local fusion = nil
        pcall(function() fusion = Fusion() end)
        print("[BFD] show_results: Fusion()=" .. tostring(fusion ~= nil))
        if fusion then
            print("[BFD] show_results: 弹出AskUser...")
            local full = summary_text .. "\n\n提示: 按 ; 跳转到下一个标记 | Shift+; 上一个标记"
            fusion:AskUser("检测完成 - 清何黑帧夹帧", {
                {"msg", "Text", { Wrap = true, Lines = 22, Default = full }},
            })
            print("[BFD] show_results: AskUser返回")
        else
            print("")
            print(string.rep("█", 55))
            print("  [BFD] 无法弹出结果窗口，以下是检测结果(Console)")
            print(string.rep("█", 55))
            print(summary_text)
            print("")
            print("  导航: 按 ; 跳下一个标记 | Shift+; 上一个标记")
            print(string.rep("█", 55))
        end
    end
    print("[BFD] show_results: 退出")
end

-- ============================================================
-- 错误提示
-- ============================================================
function UIBridge.show_error(version_compat, message)
    print("[BFD ERROR] " .. message)
    if version_compat and version_compat.fusion then
        pcall(function()
            version_compat.fusion:AskUser("错误", {
                {"msg", "Text", { Wrap = true, Lines = 8, Default = message }},
            })
        end)
    end
end

-- ============================================================
-- 获取用户桌面路径
-- ============================================================
function UIBridge.get_desktop_path()
    local home = os.getenv("HOME") or os.getenv("USERPROFILE") or ""
    local sep = package.config:sub(1, 1)
    if sep == "\\" then
        return home .. "\\Desktop"
    else
        return home .. "/Desktop"
    end
end

-- ============================================================
-- 检测进度面板（检测超过3秒时弹出，检测完成自动关闭）
-- ============================================================
function UIBridge.show_progress_panel(version_compat, message)
    if not version_compat or not version_compat.fusion then
        dlog("progress_panel: version_compat.fusion 为nil")
        return nil
    end
    local ui = version_compat.fusion.UIManager
    if not ui then
        dlog("progress_panel: UIManager 为nil")
        return nil
    end
    dlog("progress_panel: UIManager可用，创建UIDispatcher...")
    local disp = bmd.UIDispatcher(ui)
    if not disp then
        dlog("progress_panel: UIDispatcher创建失败，返回nil")
        return nil
    end
    dlog("progress_panel: UIDispatcher创建成功，隐藏参数窗口...")

    -- 隐藏参数窗口（DaVinci不允许同时显示两个窗口）
    if UIBridge._param_win then
        pcall(function() UIBridge._param_win:Hide() end)
        dlog("progress_panel: 参数窗口已隐藏")
    end

    local elapsed = message or "检测中..."

    dlog("progress_panel: 开始创建进度窗口...")
    local win = disp:AddWindow({
        ID = "BFDProgressWin",
        WindowTitle = "检测进度",
        Geometry = { 200, 300, 300, 100 },
        Spacing = 4,
        Margin = 12,
        ui:VGroup{
            ui:VGap{ 8 },
            ui:Label{ ID = "ProgressLabel", Text = elapsed,
                      Font = ui:Font{ PixelSize = 14, Bold = true },
                      Alignment = { AlignHCenter = true } },
            ui:Label{ ID = "SubLabel", Text = "请稍候，正在分析中...",
                      Font = ui:Font{ PixelSize = 10 },
                      Alignment = { AlignHCenter = true } },
            ui:VGap{ 8 },
        },
    })

    if not win then
        dlog("progress_panel: AddWindow返回nil")
        -- 进度面板创建失败，恢复参数窗口
        if UIBridge._param_win then
            pcall(function() UIBridge._param_win:Show() end)
        end
        return nil
    end

    dlog("progress_panel: AddWindow成功，尝试Show...")
    pcall(function() win:Show() end)
    dlog("progress_panel: 返回handle")
    return { disp = disp, win = win }
end

function UIBridge.close_progress_panel(handle)
    if handle and handle.win then
        pcall(function() handle.win:Hide() end)
    end
end

return UIBridge
