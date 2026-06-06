-- test_e2e.lua - 端到端无UI测试
-- 模拟完整检测流程，跳过UI交互

local home = os.getenv("HOME") or os.getenv("USERPROFILE")
local mod_dir = home .. "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Modules/black_frame_detector"
package.path = package.path .. ";" .. mod_dir .. "/?.lua"

local log_path = home .. "/bfd_e2e_test.log"
local function tlog(msg)
    local f = io.open(log_path, "a")
    if f then f:write(os.date("%H:%M:%S") .. " " .. tostring(msg) .. "\n"); f:close() end
end

local f = io.open(log_path, "w")
if f then f:write("=== BFD E2E测试 " .. os.date("%Y-%m-%d %H:%M:%S") .. " ===\n"); f:close() end

-- 加载模块
local config = require("config")
tlog("v" .. config.PLUGIN_VERSION)

local VersionCompat = require("version_compat")
local Analyzer = require("black_frame_analyzer")
local DuplicateDetector = require("duplicate_detector")
local MarkerManager = require("marker_manager")
local FFmpegRunner = require("ffmpeg_runner")

-- 连接达芬奇
local resolve = bmd.scriptapp("Resolve")
local project = resolve:GetProjectManager():GetCurrentProject()
local timeline = project:GetCurrentTimeline()
tlog("时间线: " .. (timeline:GetName() or "?"))
tlog("FPS: " .. tostring(timeline:GetSetting("timelineFrameRate")))

-- 模拟参数（跳过UI）
local params = {
    marker_types = {
        error = true,
        suspect = true,
        scene = false,
        gap = true,
        duplicate = true,
        opacity = true,
    },
    stuck_frames = config.CLASSIFICATION.STUCK_FRAMES,
    suspect_frames = config.CLASSIFICATION.SUSPECT_FRAMES,
    pix_threshold = config.FFMPEG.PIXEL_THRESHOLD,
    picture_ratio = config.FFMPEG.PICTURE_RATIO,
    min_black_duration = config.FFMPEG.MIN_BLACK_DURATION,
    merge_mode = true,
    clear_old_markers = true,
    mark_partial_opacity = true,
    dup_enabled = true,
    dup_near_threshold = config.DUPLICATE.NEAR_THRESHOLD_SEC,
    dup_far_threshold = config.DUPLICATE.FAR_THRESHOLD_SEC,
    dup_content_enabled = config.DUPLICATE.CONTENT_DETECT_ENABLED,
    gen_html_report = false,
    full_timeline = false,
    io_in_tc = "",
    io_out_tc = "",
}

local compat = VersionCompat:new()
compat:init()

local timeline_fps = tonumber(timeline:GetSetting("timelineFrameRate")) or 24
local start_offset = compat:get_timeline_start_offset(timeline)

tlog("fps=" .. timeline_fps .. " offset=" .. tostring(start_offset))

-- 阶段4: 收集视频片段
tlog("阶段4: 收集视频片段...")
local all_items, item_to_track = compat:get_video_items(timeline)
tlog("all_items count=" .. #all_items)

local clips = {}
local track_enabled_cache = {}
for _, item in ipairs(all_items) do
    local file_path = compat:get_clip_property(item, "File Path")
    if file_path and file_path ~= "" then
        local track_idx = item_to_track[item] or item._track_index or 1
        if track_enabled_cache[track_idx] == nil then
            track_enabled_cache[track_idx] = compat:get_track_enabled(timeline, "video", track_idx)
        end
        if track_enabled_cache[track_idx] then
            local start_frame = 0; pcall(function() start_frame = item:GetStart() end)
            local duration = 0; pcall(function() duration = item:GetDuration() end)
            local left_offset = 0; pcall(function() left_offset = item:GetLeftOffset() end)
            local opacity = 100
            local is_enabled = true
            local composite_mode = 0
            local name = ""; pcall(function() name = item:GetName() end)
            -- 尝试获取opacity/enabled/composite（Resolve 19可能不支持）
            pcall(function() opacity = item:GetClipProperty("Opacity") or 100 end)
            pcall(function() is_enabled = item:GetClipProperty("Enabled") ~= false end)
            pcall(function() composite_mode = item:GetClipProperty("Composite Mode") or 0 end)

            table.insert(clips, {
                file_path = file_path,
                name = name,
                track_index = track_idx,
                timeline_start_frame = start_frame,
                source_duration_frames = duration,
                left_offset = left_offset,
                opacity = opacity,
                is_enabled = is_enabled,
                composite_mode = composite_mode,
                is_timeline_clip = (file_path:find("^Timeline ") ~= nil),
                clip = item,
                index = #clips + 1,
            })
        end
    end
end
tlog("收集到 " .. #clips .. " 个素材")

-- 阶段4.5: 透明度扫描
tlog("阶段4.5: 透明度扫描...")
local opacity_count = 0
for _, clip in ipairs(clips) do
    if clip.is_enabled ~= false and clip.opacity > 0 then
        if clip.opacity < config.OPACITY_DETECTION.LOW_OPACITY_THRESHOLD then
            opacity_count = opacity_count + 1
        elseif clip.opacity < config.OPACITY_DETECTION.PARTIAL_OPACITY_THRESHOLD then
            opacity_count = opacity_count + 1
        elseif clip.composite_mode ~= 0 then
            opacity_count = opacity_count + 1
        end
    end
end
tlog("透明度问题: " .. opacity_count .. " 个")

-- 阶段4.6: 真正夹帧检测
tlog("阶段4.6: 异常短片段检测...")
local stuck_count = 0
for _, clip in ipairs(clips) do
    if clip.source_duration_frames and clip.source_duration_frames <= params.stuck_frames then
        stuck_count = stuck_count + 1
    end
end
tlog("异常短片段(≤" .. params.stuck_frames .. "帧): " .. stuck_count)

-- 阶段4.7: 多轨道叠加检测
tlog("阶段4.7: 多轨道叠加检测...")
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
for _, clip in ipairs(clips) do
    local tl_dur = clip.source_duration_frames or 0
    if tl_dur > params.stuck_frames and tl_dur > 0 then
        if clip.is_enabled ~= false and Analyzer.is_fully_opaque(clip, config.OVERLAY_STUCK_DETECTION) then
            local result = Analyzer.compute_visible_intervals(clip, clips_by_track, max_track, config.OVERLAY_STUCK_DETECTION, 95)
            local visible_frames = result.total_visible_frames
            if visible_frames > 0 and visible_frames <= params.stuck_frames then
                local soft_result = Analyzer.compute_visible_intervals(clip, clips_by_track, max_track, config.OVERLAY_STUCK_DETECTION, 50)
                local soft_visible = soft_result.total_visible_frames
                if soft_visible <= 0 or soft_visible > params.stuck_frames then
                    overlay_soft_count = overlay_soft_count + 1
                else
                    overlay_count = overlay_count + 1
                end
            end
        end
    end
end
tlog("叠加夹帧: " .. overlay_count .. " (Red) + " .. overlay_soft_count .. " (Yellow)")

-- 阶段8: 重复检测
tlog("阶段8: 重复检测...")
local dup_params = {
    dup_enabled = true,
    dup_near_threshold = config.DUPLICATE.NEAR_THRESHOLD_SEC,
    dup_far_threshold = config.DUPLICATE.FAR_THRESHOLD_SEC,
    dup_content_enabled = true,
}
local dup_results = DuplicateDetector.detect(clips, timeline_fps, dup_params)
local near_count = #(dup_results.near_duplicates or {})
local far_count = #(dup_results.far_duplicates or {})
local distant_count = #(dup_results.distant_reuse or {})
tlog(string.format("重复检测: near=%d far=%d distant=%d", near_count, far_count, distant_count))

-- 转换为标记记录
local dup_records = DuplicateDetector.to_marker_records(dup_results)
tlog("重复标记记录: " .. #dup_records)

-- 验证重复标记duration (功能2)
for i, r in ipairs(dup_records) do
    local dur = (r.timeline_end_frame or 0) - (r.timeline_start_frame or 0)
    if dur > 1 then
        tlog(string.format("  [%d] %s dur=%d (区间标记 ✅)", i, r.marker_name, dur))
    else
        tlog(string.format("  [%d] %s dur=%d (单帧 ❌)", i, r.marker_name, dur))
    end
end

-- 清除旧标记 (功能: 标记删除安全)
if params.clear_old_markers then
    local removed = MarkerManager.clear_detection_markers(timeline, compat)
    tlog("清除旧标记: " .. removed .. " 个")
end

-- 添加新标记
if #dup_records > 0 then
    local added, failed = MarkerManager.apply_markers(timeline, dup_records, compat, nil, start_offset)
    tlog(string.format("添加标记: %d 成功, %d 失败", added, failed))
end

tlog("")
tlog("=== E2E测试完成 ===")
tlog("时间线: " .. (timeline:GetName() or "?"))
tlog("素材数: " .. #clips)
tlog("透明度问题: " .. opacity_count)
tlog("异常短片段: " .. stuck_count)
tlog("叠加夹帧: " .. overlay_count .. " Red + " .. overlay_soft_count .. " Yellow")
tlog("重复检测: near=" .. near_count .. " far=" .. far_count .. " distant=" .. distant_count)
tlog("重复标记区间: " .. #dup_records .. " 个")
tlog("")
tlog("✅ 完整检测流程未闪退！")

print("\n[BFD E2E] 端到端测试完成，结果见: " .. log_path)
