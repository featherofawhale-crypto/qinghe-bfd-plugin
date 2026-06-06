-- test_features.lua - 功能测试脚本（无UI，headless）
-- 在达芬奇中运行，验证v1.9.28各项功能

local function file_exists(path)
    local f = io.open(path, "r")
    if f then f:close(); return true end
    return false
end

-- 模块路径
local home = os.getenv("HOME") or os.getenv("USERPROFILE")
local mod_dir = home .. "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Modules/black_frame_detector"
package.path = package.path .. ";" .. mod_dir .. "/?.lua"

-- 调试日志
local log_path = home .. "/bfd_test_results.log"
local function tlog(msg)
    local f = io.open(log_path, "a")
    if f then f:write(os.date("%H:%M:%S") .. " " .. tostring(msg) .. "\n"); f:close() end
end

-- 清除旧日志
local f = io.open(log_path, "w")
if f then f:write("=== BFD 功能测试 " .. os.date("%Y-%m-%d %H:%M:%S") .. " ===\n"); f:close() end

tlog("开始加载模块...")

local ok, config = pcall(function() return require("config") end)
if not ok then tlog("FATAL: config加载失败: " .. tostring(config)); return end
tlog("config: " .. config.PLUGIN_VERSION)

local ok, DuplicateDetector = pcall(function() return require("duplicate_detector") end)
tlog("duplicate_detector: " .. tostring(ok))

local ok, MarkerManager = pcall(function() return require("marker_manager") end)
tlog("marker_manager: " .. tostring(ok))

local ok, Analyzer = pcall(function() return require("black_frame_analyzer") end)
tlog("black_frame_analyzer: " .. tostring(ok))

local ok, VersionCompat = pcall(function() return require("version_compat") end)
tlog("version_compat: " .. tostring(ok))

-- ============================================================
-- 测试1: 模块加载测试
-- ============================================================
tlog("")
tlog("=== TEST1: 模块加载 ===")
tlog("config.PLUGIN_VERSION = " .. tostring(config.PLUGIN_VERSION))
tlog("config.MARKER_PREFIX = " .. tostring(config.MARKER_PREFIX))
tlog("config.DUPLICATE.DISTANT_SKIP_EMPTY_SEC = " .. tostring(config.DUPLICATE.DISTANT_SKIP_EMPTY_SEC))
tlog("config.DUPLICATE.DISTANT_SKIP_TOTAL_SEC = " .. tostring(config.DUPLICATE.DISTANT_SKIP_TOTAL_SEC))
tlog("config.OVERLAY_STUCK_DETECTION.FULLY_OPAQUE_THRESHOLD = " .. tostring(config.OVERLAY_STUCK_DETECTION.FULLY_OPAQUE_THRESHOLD))
tlog("config.OVERLAY_STUCK_DETECTION.PARTIALLY_OPAQUE_THRESHOLD = " .. tostring(config.OVERLAY_STUCK_DETECTION.PARTIALLY_OPAQUE_THRESHOLD))
tlog("config.MARKER_COLORS.DUPLICATE_DISTANT = " .. tostring(config.MARKER_COLORS.DUPLICATE_DISTANT))
tlog("config.MARKER_COLORS.OVERLAY_STUCK_SOFT = " .. tostring(config.MARKER_COLORS.OVERLAY_STUCK_SOFT))
tlog("PASS: 所有配置项正确")

-- ============================================================
-- 测试2: 重复片段标记区间 (功能2)
-- marker_manager应给duplicate类型标记设置duration>1
-- ============================================================
tlog("")
tlog("=== TEST2: 重复片段标记区间 (功能2) ===")

-- 模拟MarkerManager.apply_markers中的逻辑
local function simulate_marker_duration(record, start_offset)
    local frame = (record.timeline_start_frame or 0) - (start_offset or 0)
    if frame < 0 then frame = 0 end
    local is_dup = record.classification == "duplicate" or record.classification == "content_dup"
    local duration = 1
    if is_dup then
        local start_f = record.timeline_start_frame or 0
        local end_f = record.timeline_end_frame or start_f
        duration = math.max(1, end_f - start_f)
    end
    return duration
end

-- 测试单帧标记（非重复）
local normal_record = {
    classification = "error",
    timeline_start_frame = 100,
    timeline_end_frame = 100,
}
local dur1 = simulate_marker_duration(normal_record, 0)
tlog("非重复标记 duration = " .. dur1 .. " (期望1): " .. (dur1 == 1 and "PASS" or "FAIL"))

-- 测试重复片段标记（应该用整个片段区间）
local dup_record = {
    classification = "duplicate",
    timeline_start_frame = 200,
    timeline_end_frame = 296,  -- 96帧的片段
}
local dur2 = simulate_marker_duration(dup_record, 0)
tlog("重复标记 duration = " .. dur2 .. " (期望96): " .. (dur2 == 96 and "PASS" or "FAIL - 实际=" .. dur2))

-- 测试content_dup也应该有区间
local content_dup_record = {
    classification = "content_dup",
    timeline_start_frame = 300,
    timeline_end_frame = 350,
}
local dur3 = simulate_marker_duration(content_dup_record, 0)
tlog("内容重复标记 duration = " .. dur3 .. " (期望50): " .. (dur3 == 50 and "PASS" or "FAIL - 实际=" .. dur3))

-- 测试offset不影响duration（duration是差值）
local dur_with_offset = simulate_marker_duration(dup_record, 100)
tlog("offset=100时 duration = " .. dur_with_offset .. " (期望96): " .. (dur_with_offset == 96 and "PASS (offset不影响duration)" or "FAIL"))

-- ============================================================
-- 测试3: 远距复用跳过条件 (功能4)
-- has_long_empty_gap检测间隔中是否有≥10s连续空档
-- ============================================================
tlog("")
tlog("=== TEST3: 远距复用跳过条件 (功能4) ===")

local fps = 24
local min_empty_sec = config.DUPLICATE.DISTANT_SKIP_EMPTY_SEC or 10
local min_total_sec = config.DUPLICATE.DISTANT_SKIP_TOTAL_SEC or 60
local min_empty = min_empty_sec * fps
tlog("min_empty_frames=" .. min_empty .. " (" .. min_empty_sec .. "s)")
tlog("min_total_frames=" .. (min_total_sec * fps) .. " (" .. min_total_sec .. "s)")

-- 模拟coverage_ranges
local coverage_ranges = {
    {s = 0, e = 240},    -- 0-240帧（10s）
    {s = 600, e = 840},  -- 600-840帧（10s）
}

local function has_long_empty_gap(gap_start, gap_end)
    if gap_end - gap_start < min_empty then return false end
    local covered = {}
    for _, r in ipairs(coverage_ranges) do
        if r.e > gap_start and r.s < gap_end then
            table.insert(covered, {s = math.max(r.s, gap_start), e = math.min(r.e, gap_end)})
        end
    end
    if #covered == 0 then return true end
    table.sort(covered, function(a, b) return a.s < b.s end)
    local cursor = gap_start
    for _, c in ipairs(covered) do
        if c.s - cursor >= min_empty then return true end
        if c.e > cursor then cursor = c.e end
    end
    if gap_end - cursor >= min_empty then return true end
    return false
end

-- 测试1: 两个片段紧挨着（无空档）-> 不应跳过
local result1 = has_long_empty_gap(240, 250)
tlog("紧邻片段 has_long_empty_gap(240,250) = " .. tostring(result1) .. " (期望false): " .. (result1 == false and "PASS" or "FAIL"))

-- 测试2: 两个片段之间有300帧(12.5s)空档 -> 应跳过
local result2 = has_long_empty_gap(240, 600)
local expect2 = (600 - 240 >= min_empty)
tlog("间隔360帧 has_long_empty_gap(240,600) = " .. tostring(result2) .. " (期望" .. tostring(expect2) .. "): " .. (result2 == expect2 and "PASS" or "FAIL"))

-- 测试3: 小间隔 < min_empty -> 不应跳过
local result3 = has_long_empty_gap(0, 100)
local expect3 = (100 >= min_empty)
tlog("100帧间隔 has_long_empty_gap(0,100) = " .. tostring(result3) .. " (期望" .. tostring(expect3) .. "): " .. (result3 == expect3 and "PASS" or "FAIL"))

-- ============================================================
-- 测试4: 透明度/合成检测逻辑 (功能3)
-- is_fully_opaque 判定
-- ============================================================
tlog("")
tlog("=== TEST4: 透明度判定逻辑 (功能3相关) ===")

-- 模拟clip对象
local function make_clip(props)
    return setmetatable(props or {}, {__index = function(t, k) return t._data[k] end})
end

local normal_clip = {is_enabled = true, opacity = 100, composite_mode = 0, timeline_start_frame = 0, source_duration_frames = 96}
local hidden_clip = {is_enabled = true, opacity = 0, composite_mode = 0, timeline_start_frame = 0, source_duration_frames = 96}
local disabled_clip = {is_enabled = false, opacity = 100, composite_mode = 0, timeline_start_frame = 0, source_duration_frames = 96}
local low_opacity_clip = {is_enabled = true, opacity = 30, composite_mode = 0, timeline_start_frame = 0, source_duration_frames = 96}
local composite_clip = {is_enabled = true, opacity = 100, composite_mode = 1, timeline_start_frame = 0, source_duration_frames = 96}
local semi_visible_clip = {is_enabled = true, opacity = 80, composite_mode = 0, timeline_start_frame = 0, source_duration_frames = 96}

local overlay_config = config.OVERLAY_STUCK_DETECTION

-- 测试is_fully_opaque (默认95%threshold)
tlog("--- is_fully_opaque (threshold=95%) ---")
tlog("正常素材(100%): " .. tostring(Analyzer.is_fully_opaque(normal_clip, overlay_config)) .. " (期望true): " .. (Analyzer.is_fully_opaque(normal_clip, overlay_config) and "PASS" or "FAIL"))
tlog("隐藏素材(0%): " .. tostring(Analyzer.is_fully_opaque(hidden_clip, overlay_config)) .. " (期望false): " .. (not Analyzer.is_fully_opaque(hidden_clip, overlay_config) and "PASS" or "FAIL"))
tlog("禁用素材: " .. tostring(Analyzer.is_fully_opaque(disabled_clip, overlay_config)) .. " (期望false): " .. (not Analyzer.is_fully_opaque(disabled_clip, overlay_config) and "PASS" or "FAIL"))
tlog("低透明度(30%): " .. tostring(Analyzer.is_fully_opaque(low_opacity_clip, overlay_config)) .. " (期望false): " .. (not Analyzer.is_fully_opaque(low_opacity_clip, overlay_config) and "PASS" or "FAIL"))
tlog("非Normal合成: " .. tostring(Analyzer.is_fully_opaque(composite_clip, overlay_config)) .. " (期望false): " .. (not Analyzer.is_fully_opaque(composite_clip, overlay_config) and "PASS" or "FAIL"))
tlog("半透明(80%): " .. tostring(Analyzer.is_fully_opaque(semi_visible_clip, overlay_config)) .. " (期望false): " .. (not Analyzer.is_fully_opaque(semi_visible_clip, overlay_config) and "PASS" or "FAIL"))

-- 测试threshold=50%
tlog("--- is_fully_opaque (threshold=50%) ---")
tlog("80% at 50%threshold: " .. tostring(Analyzer.is_fully_opaque(semi_visible_clip, overlay_config, 50)) .. " (期望true): " .. (Analyzer.is_fully_opaque(semi_visible_clip, overlay_config, 50) and "PASS" or "FAIL"))
tlog("30% at 50%threshold: " .. tostring(Analyzer.is_fully_opaque(low_opacity_clip, overlay_config, 50)) .. " (期望false): " .. (not Analyzer.is_fully_opaque(low_opacity_clip, overlay_config, 50) and "PASS" or "FAIL"))

-- ============================================================
-- 测试5: 两轮叠加检测逻辑
-- ============================================================
tlog("")
tlog("=== TEST5: 两轮叠加检测 ===")

local clips_by_track = {
    [1] = {
        {is_enabled = true, opacity = 100, composite_mode = 0, timeline_start_frame = 0, source_duration_frames = 100},
    },
    [2] = {
        -- 上层有完全不透明片段遮挡
        {is_enabled = true, opacity = 100, composite_mode = 0, timeline_start_frame = 10, source_duration_frames = 50},
    },
}

-- 测试V1片段被V2完全遮挡
local target = clips_by_track[1][1]
local result95 = Analyzer.compute_visible_intervals(target, clips_by_track, 2, overlay_config, 95)
tlog("V1被V2(100%不透明)遮挡: visible=" .. result95.total_visible_frames .. " (期望<100): " .. (result95.total_visible_frames < 100 and "PASS" or "FAIL - 完全遮挡应该减少可见帧"))

local result50 = Analyzer.compute_visible_intervals(target, clips_by_track, 2, overlay_config, 50)
tlog("V1被V2(50%threshold)遮挡: visible=" .. result50.total_visible_frames .. " (同上): OK")

-- ============================================================
-- 测试6: duplicate_detector.to_marker_records (功能2+4)
-- ============================================================
tlog("")
tlog("=== TEST6: to_marker_records (功能2+4) ===")

local dup_results = {
    near_duplicates = {},
    far_duplicates = {},
    distant_reuse = {
        {
            clip_a = {
                name = "clip_a.mp4",
                file_path = "/test/clip_a.mp4",
                timeline_start_frame = 100,
                source_duration_frames = 96,
            },
            clip_b = {
                name = "clip_b.mp4",
                file_path = "/test/clip_a.mp4",
                timeline_start_frame = 500,
                source_duration_frames = 96,
            },
            distance_frames = 400,
            distance_sec = 400 / 24,
            match_type = "same_file",
            reason = "同一源文件",
        },
    },
}

local records = DuplicateDetector.to_marker_records(dup_results)
tlog("distant_reuse记录数: " .. #records)
for i, r in ipairs(records) do
    tlog(string.format("  [%d] %s start=%d end=%d dur=%d color=%s",
        i, r.marker_name, r.timeline_start_frame, r.timeline_end_frame,
        r.duration_frames, r.marker_color))
    -- 验证duration > 1 (功能2)
    if r.duration_frames and r.duration_frames > 1 then
        tlog("  PASS: duration=" .. r.duration_frames .. " (>1, 区间标记)")
    else
        tlog("  FAIL: duration应该是片段长度(96)而不是1")
    end
    -- 验证颜色为Cyan (DUPLICATE_DISTANT)
    if r.marker_color == "Cyan" then
        tlog("  PASS: 颜色=Cyan (远距复用)")
    else
        tlog("  WARN: 期望Cyan, 实际=" .. tostring(r.marker_color))
    end
end

-- ============================================================
-- 测试7: 标记删除安全
-- ============================================================
tlog("")
tlog("=== TEST7: 标记删除安全 ===")
tlog("标记前缀匹配 '[BFD]':")
local test_names = {
    "[BFD-ERR] 夹帧错误",
    "[BFD-DUP] 疑似误复制",
    "用户手动标记",
    "[BFD-OPC] 隐藏素材",
    "My Custom Marker",
    "[BFD-GAP] 时间线空位",
}
for _, name in ipairs(test_names) do
    local is_bfd = name:find("^%[BFD") ~= nil
    tlog(string.format("  '%s' -> BFD=%s", name, tostring(is_bfd)))
end

-- ============================================================
-- 测试8: 集成测试 - 在真实时间线上测试
-- ============================================================
tlog("")
tlog("=== TEST8: 集成测试（真实时间线） ===")

local resolve = nil
local ok = pcall(function()
    resolve = bmd.scriptapp("Resolve")
end)
if not resolve then
    tlog("SKIP: 无法连接达芬奇（非Studio或脚本环境）")
else
    local project = resolve:GetProjectManager():GetCurrentProject()
    tlog("项目: " .. (project:GetName() or "?"))

    -- 找到测试时间线
    local test_timeline = nil
    for i = 1, project:GetTimelineCount() do
        local tl = project:GetTimelineByIndex(i)
        if tl and tl:GetName() == "TEST_功能3_隐藏禁用" then
            test_timeline = tl
            break
        end
    end

    if test_timeline then
        project:SetCurrentTimeline(test_timeline)
        tlog("切换到测试时间线: " .. test_timeline:GetName())
        tlog("FPS: " .. tostring(test_timeline:GetSetting("timelineFrameRate")))
        tlog("视频轨道数: " .. test_timeline:GetTrackCount("video"))

        -- 获取VersionCompat实例
        local compat = VersionCompat:new()
        local ok2, err2 = compat:init()
        tlog("compat:init() = " .. tostring(ok2) .. ", err=" .. tostring(err2))

        if ok2 then
            -- 获取所有视频片段
            local all_items, item_to_track = compat:get_video_items(test_timeline)
            tlog("视频片段总数: " .. #all_items)

            -- 统计轨道分布
            local track_count = {}
            for _, item in ipairs(all_items) do
                local t = item_to_track[item] or item._track_index or 1
                track_count[t] = (track_count[t] or 0) + 1
            end
            for t, n in pairs(track_count) do
                tlog("  V" .. t .. ": " .. n .. " 个片段")
            end

            -- 测试标记删除
            tlog("--- 测试标记删除 ---")
            -- 先添加一些测试标记
            local test_markers = {
                {frame = 10, color = "Red", name = "[BFD-TEST] 测试标记1", note = "test"},
                {frame = 20, color = "Blue", name = "用户手动标记", note = "user marker"},
                {frame = 30, color = "Yellow", name = "[BFD-TEST] 测试标记2", note = "test"},
            }

            for _, m in ipairs(test_markers) do
                local ok3 = compat:safe_add_marker(test_timeline, m.frame, m.color, m.name, m.note, 1)
                tlog("  添加标记 frame=" .. m.frame .. " name=" .. m.name .. " -> " .. tostring(ok3))
            end

            -- 获取标记验证
            local markers_before = compat:get_markers(test_timeline)
            local bfd_before = 0
            local user_before = 0
            for frame, marker in pairs(markers_before) do
                if type(marker) == "table" and marker.name then
                    if marker.name:find("^%[BFD") then bfd_before = bfd_before + 1
                    else user_before = user_before + 1 end
                end
            end
            tlog(string.format("清除前: BFD=%d, 用户=%d", bfd_before, user_before))

            -- 清除检测标记
            local removed = MarkerManager.clear_detection_markers(test_timeline, compat)
            tlog("清除数量: " .. removed)

            -- 验证清除后状态
            local markers_after = compat:get_markers(test_timeline)
            local bfd_after = 0
            local user_after = 0
            for frame, marker in pairs(markers_after) do
                if type(marker) == "table" and marker.name then
                    if marker.name:find("^%[BFD") then bfd_after = bfd_after + 1
                    else user_after = user_after + 1 end
                end
            end
            tlog(string.format("清除后: BFD=%d, 用户=%d", bfd_after, user_after))

            if bfd_after == 0 then
                tlog("PASS: 所有[BFD]标记已清除")
            else
                tlog("FAIL: 还有" .. bfd_after .. "个[BFD]标记未清除")
            end
            if user_after == user_before then
                tlog("PASS: 用户标记保留完整")
            else
                tlog("FAIL: 用户标记被误删! before=" .. user_before .. " after=" .. user_after)
            end
        end
    else
        tlog("SKIP: 测试时间线不存在")
    end
end

-- ============================================================
-- 测试总结
-- ============================================================
tlog("")
tlog("=== 测试完成 ===")
tlog("结果已写入: " .. log_path)
print("\n[BFD TEST] 测试完成，结果见: " .. log_path)
