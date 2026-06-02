-- black_frame_analyzer.lua - 黑帧分类核心算法
-- 区分夹帧错误 / 可疑黑帧 / 正常场景转场 / 时间线空位
-- v1.9.0: 支持帧数阈值 + 时间线空位检测（按时长分级）

local config = require("config")

local function dlog(msg)
    local f = io.open(config.get_debug_log_path(), "a")
    if f then f:write(os.date("%Y-%m-%d %H:%M:%S") .. " [BA] " .. tostring(msg) .. "\n"); f:close() end
end

local Analyzer = {}

-- ============================================================
-- 帧数 → 秒数 换算
-- ============================================================
function Analyzer.frames_to_seconds(frames, fps)
    fps = fps or 25
    return frames / fps
end

-- ============================================================
-- 秒数 → 帧数 换算
-- ============================================================
function Analyzer.seconds_to_frames(seconds, fps)
    fps = fps or 25
    return seconds * fps
end

-- ============================================================
-- 分类一个黑帧段
-- params.use_frames: true = 用帧数分类, false = 用秒数分类
-- params.stuck_threshold / stuck_frames: 夹帧判定上限
-- params.suspect_threshold / suspect_frames: 可疑帧判定上限
-- 返回: "error" | "suspect" | "scene" | "ignore"
-- ============================================================
function Analyzer.classify_segment(duration_sec, params, fps)
    params = params or {}
    fps = fps or 25

    local ignore_above = params.ignore_above or config.CLASSIFICATION.IGNORE_ABOVE

    -- 极长黑帧→纯黑素材，忽略
    if duration_sec > ignore_above then
        return "ignore"
    end

    local use_frames = false
    if params.use_frames ~= nil then
        use_frames = params.use_frames
    else
        use_frames = config.CLASSIFICATION.USE_FRAMES
    end

    local stuck_limit, suspect_limit

    if use_frames then
        -- 帧数模式：把帧数阈值换算成秒数
        local stuck_frames = params.stuck_frames or config.CLASSIFICATION.STUCK_FRAMES
        local suspect_frames = params.suspect_frames or config.CLASSIFICATION.SUSPECT_FRAMES
        stuck_limit = Analyzer.frames_to_seconds(stuck_frames, fps)
        suspect_limit = Analyzer.frames_to_seconds(suspect_frames, fps)
    else
        -- 秒数模式
        stuck_limit = params.stuck_threshold or config.CLASSIFICATION.STUCK_FRAME_THRESHOLD
        suspect_limit = params.suspect_threshold or config.CLASSIFICATION.SUSPECT_THRESHOLD
    end

    if duration_sec <= stuck_limit then
        return "error"
    end

    if duration_sec <= suspect_limit then
        return "suspect"
    end

    return "scene"
end

-- ============================================================
-- 获取分类的可读标签
-- ============================================================
function Analyzer.get_classification_label(classification)
    local map = {
        error   = "夹帧错误",
        suspect = "可疑黑帧",
        scene   = "场景转场",
        gap     = "时间线空位",
        ignore  = "已忽略",
    }
    return map[classification] or "未知"
end

-- ============================================================
-- 根据分类获取标记颜色
-- ============================================================
function Analyzer.get_marker_color(classification)
    local map = {
        error   = config.MARKER_COLORS.ERROR,
        suspect = config.MARKER_COLORS.SUSPECT,
        scene   = config.MARKER_COLORS.SCENE,
        gap     = config.MARKER_COLORS.GAP,
    }
    return map[classification] or config.MARKER_COLORS.INFO
end

-- ============================================================
-- 根据分类获取标记名称
-- ============================================================
function Analyzer.get_marker_name(classification)
    local map = {
        error   = config.MARKER_NAMES.ERROR,
        suspect = config.MARKER_NAMES.SUSPECT,
        scene   = config.MARKER_NAMES.SCENE,
        gap     = config.MARKER_NAMES.GAP,
    }
    return map[classification] or "[BFD] 未知"
end

-- ============================================================
-- 将片段内的秒数映射到时间线帧号
-- ============================================================
function Analyzer.map_to_timeline_frames(clip_start_frame, segment_start_sec, segment_end_sec, fps, left_offset)
    left_offset = left_offset or 0
    local start_frame = clip_start_frame + math.floor(segment_start_sec * fps) - left_offset
    local end_frame = clip_start_frame + math.floor(segment_end_sec * fps) - left_offset
    return { start_frame = start_frame, end_frame = end_frame }
end

-- ============================================================
-- 时间码格式化（帧号 → HH:MM:SS:FF）
-- ============================================================
function Analyzer.frame_to_timecode(frame, fps)
    fps = fps or 25
    local total_seconds = math.floor(frame / fps)
    local hours = math.floor(total_seconds / 3600)
    local minutes = math.floor((total_seconds % 3600) / 60)
    local seconds = total_seconds % 60
    local frames = frame % fps
    return string.format("%02d:%02d:%02d:%02d", hours, minutes, seconds, frames)
end

-- ============================================================
-- 帧数文本（用于标记备注）
-- ============================================================
function Analyzer.frames_text(duration_sec, fps)
    fps = fps or 25
    local exact_frames = duration_sec * fps
    return string.format("%.1f帧 @%dfps", exact_frames, fps)
end

-- ============================================================
-- 构建时间线片段覆盖表（用于检测空位）
-- 输入: clips列表（每个有timeline_start_frame和file_path）
-- 返回: coverage_ranges = {{start=n, end=n}, ...} 按start排序
-- ============================================================
function Analyzer.build_coverage_table(clips, timeline_fps)
    local ranges = {}
    for _, clip in ipairs(clips) do
        -- 估算片段在时间线上的结束帧
        -- GetDuration()返回的是片段时长(帧数)
        local duration_frames = 0
        if clip.item then
            pcall(function()
                duration_frames = clip.item:GetDuration()
            end)
        end

        local start_f = clip.timeline_start_frame
        local end_f = start_f + duration_frames

        table.insert(ranges, {
            start_frame = start_f,
            end_frame = end_f,
        })
    end

    -- 按起始帧排序
    table.sort(ranges, function(a, b) return a.start_frame < b.start_frame end)

    -- 合并没有间隙的重叠区间
    local merged = {}
    for _, r in ipairs(ranges) do
        if #merged == 0 then
            table.insert(merged, r)
        else
            local last = merged[#merged]
            if r.start_frame <= last.end_frame then
                -- 重叠或相邻，合并
                last.end_frame = math.max(last.end_frame, r.end_frame)
            else
                table.insert(merged, r)
            end
        end
    end

    return merged
end

-- ============================================================
-- 检测黑帧段是否落在时间线空位（片段间隙）
-- 输入: timeline_frame - 黑帧在时间线上的起始帧号
--        coverage_table - build_coverage_table的输出
--        tolerance_frames - 容差帧数
-- 返回: true = 是空位, false = 在片段内
-- ============================================================
function Analyzer.is_in_gap(timeline_frame, coverage_table, tolerance_frames)
    tolerance_frames = tolerance_frames or config.GAP_DETECTION.TOLERANCE_FRAMES

    for _, range in ipairs(coverage_table) do
        -- 检查帧是否在某个片段覆盖范围内（允许容差）
        if timeline_frame >= (range.start_frame - tolerance_frames)
           and timeline_frame <= (range.end_frame + tolerance_frames) then
            return false  -- 在片段内
        end
    end

    return true  -- 不在任何片段内 → 是空位
end

-- ============================================================
-- 从覆盖表反向计算所有空白区间（按时长做区间分级判断）
-- 返回: {{start_frame, end_frame, duration_sec}, ...}
-- ============================================================
function Analyzer.compute_gap_ranges(coverage_table, timeline_fps)
    local gaps = {}
    if not coverage_table or #coverage_table == 0 then return gaps end

    -- 检查开头是否有空白（第一个片段之前的空位）
    if coverage_table[1].start_frame > 0 then
        table.insert(gaps, {
            start_frame = 0,
            end_frame = coverage_table[1].start_frame,
            duration_sec = coverage_table[1].start_frame / timeline_fps,
        })
    end

    -- 检查片段之间的空白
    for i = 1, #coverage_table - 1 do
        local gap_start = coverage_table[i].end_frame
        local gap_end = coverage_table[i + 1].start_frame
        if gap_end > gap_start then
            table.insert(gaps, {
                start_frame = gap_start,
                end_frame = gap_end,
                duration_sec = (gap_end - gap_start) / timeline_fps,
            })
        end
    end

    return gaps
end

-- ============================================================
-- 生成标记备注文本
-- ============================================================
function Analyzer.generate_note(segment, clip_info, timeline_fps, params, duration_frames)
    local parts = {}

    if segment.is_mixed_cut then
        table.insert(parts, string.format("混剪源内短镜头: %d帧", duration_frames or math.floor(segment.duration * timeline_fps)))
        table.insert(parts, string.format("持续: %.3fs (%d帧)", segment.duration,
            duration_frames or math.floor(segment.duration * timeline_fps)))
        if clip_info.source_file then
            local filename = clip_info.source_file:match("([^\\/]+)$") or clip_info.source_file
            table.insert(parts, string.format("来源: %s", filename))
        end
        if segment.scene_score then
            table.insert(parts, string.format("scene score: %.3f", segment.scene_score))
        end
        if segment.edge_visible then
            table.insert(parts, "位置: 源内切点靠近时间线实际可见窗口边界")
        elseif segment.single_scene_candidate then
            table.insert(parts, "位置: 源内高强度场景切点，未依赖时间线切刀")
        end
        table.insert(parts, "判定: 时间线上可见镜头内部存在极短源内切点，疑似混剪漏帧/夹帧")
        return table.concat(parts, "\n")
    end

    local frame_text = Analyzer.frames_text(segment.duration, timeline_fps)
    table.insert(parts, string.format("黑帧: %s", frame_text))
    table.insert(parts, string.format("持续: %.3fs (%d帧)", segment.duration,
        duration_frames or math.floor(segment.duration * timeline_fps)))

    if clip_info.source_file then
        local filename = clip_info.source_file:match("([^\\/]+)$") or clip_info.source_file
        table.insert(parts, string.format("来源: %s", filename))
    end

    if timeline_fps then
        local src_tc_start = Analyzer.frame_to_timecode(
            math.floor(segment.start * timeline_fps), timeline_fps
        )
        local src_tc_end = Analyzer.frame_to_timecode(
            math.floor(segment.end_ * timeline_fps), timeline_fps
        )
        table.insert(parts, string.format("片段内: %s - %s", src_tc_start, src_tc_end))
    end

    -- 判定参数（显示帧数）
    if params.use_frames then
        local sf = params.stuck_frames or config.CLASSIFICATION.STUCK_FRAMES
        local spf = params.suspect_frames or config.CLASSIFICATION.SUSPECT_FRAMES
        table.insert(parts, string.format("判定: ≤%d帧夹帧 ≤%d帧可疑", sf, spf))
    else
        table.insert(parts, string.format("判定: ≤%.3fs夹帧 ≤%.3fs可疑",
            params.stuck_threshold or config.CLASSIFICATION.STUCK_FRAME_THRESHOLD,
            params.suspect_threshold or config.CLASSIFICATION.SUSPECT_THRESHOLD))
    end

    return table.concat(parts, "\n")
end

-- ============================================================
-- 核心方法：对检测结果进行分类、时间映射、空位检测
-- 输入: ffmpeg_results, timeline_fps, params, clips (用于空位检测)
-- 输出: 完整的分类结果
-- ============================================================
function Analyzer.analyze_results(ffmpeg_results, timeline_fps, params, clips)
    params = params or {}
    timeline_fps = timeline_fps or 25

    -- 构建片段覆盖表用于空位检测
    local coverage_table = nil
    if config.GAP_DETECTION.ENABLED and clips then
        coverage_table = Analyzer.build_coverage_table(clips, timeline_fps)
    end

    local results = {
        errors = {},
        suspects = {},
        scenes = {},
        gaps = {},       -- 时间线空位（新增）
        ignored = {},
        summary = {
            total_segments = 0,
            error_count = 0,
            suspect_count = 0,
            scene_count = 0,
            gap_count = 0,
            ignored_count = 0,
            total_clips = #ffmpeg_results,
        },
    }

    for _, result in ipairs(ffmpeg_results) do
        local clip = result.clip

        for _, segment in ipairs(result.segments) do
            results.summary.total_segments = results.summary.total_segments + 1

            -- 先按时长分类
            local classification = Analyzer.classify_segment(segment.duration, params, timeline_fps)

            -- 时间码映射到时间线（考虑场景探测的裁剪偏移）
            local frames = Analyzer.map_to_timeline_frames(
                clip.timeline_start_frame,
                segment.start,
                segment.end_,
                timeline_fps,
                clip.left_offset or 0
            )
            if segment.timeline_frame then
                frames.start_frame = segment.timeline_frame
                frames.end_frame = segment.timeline_frame + math.max(1, math.floor(segment.duration * timeline_fps + 0.5))
            end
            if results.summary.total_segments <= 3 then
                dlog(string.format(
                    "  seg#%d: clip_start=%d seg.start=%.3f seg.end=%.3f fps=%.0f lo=%d -> tl_frame=%d..%d tc=%s",
                    results.summary.total_segments,
                    clip.timeline_start_frame, segment.start, segment.end_,
                    timeline_fps, clip.left_offset or 0,
                    frames.start_frame, frames.end_frame,
                    Analyzer.frame_to_timecode(frames.start_frame, timeline_fps)
                ))
            end

            -- 空位检测：如果分类是error/suspect/scene，但落在时间线空位，重新标记为gap
            if coverage_table and classification ~= "ignore" then
                if Analyzer.is_in_gap(frames.start_frame, coverage_table) then
                    classification = "gap"
                end
            end

            -- 计算精确帧数
            local duration_frames = math.floor(segment.duration * timeline_fps)

            local record = {
                classification = classification,
                marker_color = Analyzer.get_marker_color(classification),
                marker_name = segment.is_mixed_cut and "[BFD-MIX] 混剪源内夹帧" or Analyzer.get_marker_name(classification),

                timeline_start_frame = frames.start_frame,
                timeline_end_frame = frames.end_frame,
                timeline_start_tc = Analyzer.frame_to_timecode(frames.start_frame, timeline_fps),
                timeline_end_tc = Analyzer.frame_to_timecode(frames.end_frame, timeline_fps),

                segment = segment,
                source_file = clip.file_path,
                source_start_sec = segment.start,
                source_duration_sec = segment.duration,
                duration_frames = duration_frames,

                note = Analyzer.generate_note(segment, {
                    source_file = clip.file_path,
                    clip_name = clip.name,
                }, timeline_fps, params, duration_frames),
            }

            -- 分类存储
            if classification == "error" then
                table.insert(results.errors, record)
                results.summary.error_count = results.summary.error_count + 1
            elseif classification == "suspect" then
                table.insert(results.suspects, record)
                results.summary.suspect_count = results.summary.suspect_count + 1
            elseif classification == "scene" then
                table.insert(results.scenes, record)
                results.summary.scene_count = results.summary.scene_count + 1
            elseif classification == "gap" then
                table.insert(results.gaps, record)
                results.summary.gap_count = results.summary.gap_count + 1
            else
                table.insert(results.ignored, record)
                results.summary.ignored_count = results.summary.ignored_count + 1
            end
        end
    end

    -- ============================================================
    -- 扫描时间线空白区域（按区间时长分级标记）
    -- ============================================================
    if coverage_table and config.GAP_DETECTION.ENABLED then
        local gap_ranges = Analyzer.compute_gap_ranges(coverage_table, timeline_fps)
        local max_mark_sec = params.gap_max_mark_sec or config.GAP_DETECTION.MAX_GAP_MARK_SEC
        local ignore_above_sec = params.gap_ignore_above_sec or config.GAP_DETECTION.IGNORE_GAP_ABOVE_SEC

        for _, gr in ipairs(gap_ranges) do
            local dur_sec = gr.duration_sec

            -- 太大的空白不标记（纯空着，无关紧要）
            if dur_sec >= ignore_above_sec then
                goto continue_gap
            end

            -- 去重：检查是否已有FFmpeg黑帧检测到的空位记录覆盖此范围
            local already_covered = false
            for _, existing in ipairs(results.gaps) do
                if existing.timeline_start_frame and existing.timeline_end_frame then
                    -- 如果此空位和已有gap记录重叠超过50%，跳过
                    local overlap_start = math.max(gr.start_frame, existing.timeline_start_frame)
                    local overlap_end = math.min(gr.end_frame, existing.timeline_end_frame)
                    if overlap_end > overlap_start then
                        local overlap_ratio = (overlap_end - overlap_start) / (gr.end_frame - gr.start_frame)
                        if overlap_ratio > 0.5 then
                            already_covered = true
                            break
                        end
                    end
                end
            end
            if already_covered then goto continue_gap end

            -- 区分：小空白(可疑) vs 大空白(信息)
            local is_small_gap = (dur_sec <= max_mark_sec)

            local gap_record = {
                classification = is_small_gap and "gap" or "gap_large",
                marker_color = is_small_gap and config.MARKER_COLORS.GAP or config.MARKER_COLORS.INFO,
                marker_name = is_small_gap and "[BFD-GAP] 时间线空位" or "[BFD-GAP] 时间线空白区域",

                timeline_start_frame = gr.start_frame,
                timeline_end_frame = gr.end_frame,
                timeline_start_tc = Analyzer.frame_to_timecode(gr.start_frame, timeline_fps),
                timeline_end_tc = Analyzer.frame_to_timecode(gr.end_frame, timeline_fps),

                source_file = nil,
                source_start_sec = 0,
                source_duration_sec = dur_sec,
                duration_frames = gr.end_frame - gr.start_frame,

                note = is_small_gap
                    and string.format("时间线空位\n片段间隙: %.1f帧 (%.1fs)\n可能是剪辑留下的空白",
                        gr.end_frame - gr.start_frame, dur_sec)
                    or string.format("时间线空白区域\n片段间隙: %.1f帧 (%.1fs)\n较大空白，非夹帧问题",
                        gr.end_frame - gr.start_frame, dur_sec),
            }

            if is_small_gap then
                table.insert(results.gaps, gap_record)
                results.summary.gap_count = results.summary.gap_count + 1
            else
                -- 大空白放到gaps列表中（但仍可被用户选择是否标记）
                table.insert(results.gaps, gap_record)
                results.summary.gap_count = results.summary.gap_count + 1
            end

            ::continue_gap::
        end
    end

    return results
end

-- ============================================================
-- 根据用户选择的标记类型过滤记录
-- enabled_types = {error=true, suspect=true, scene=false, gap=true}
-- ============================================================
function Analyzer.get_filtered_marker_records(analyzed_results, enabled_types)
    local records = {}

    if enabled_types.error then
        for _, r in ipairs(analyzed_results.errors) do table.insert(records, r) end
    end
    if enabled_types.suspect then
        for _, r in ipairs(analyzed_results.suspects) do table.insert(records, r) end
    end
    if enabled_types.scene then
        for _, r in ipairs(analyzed_results.scenes) do table.insert(records, r) end
    end
    if enabled_types.gap then
        for _, r in ipairs(analyzed_results.gaps) do table.insert(records, r) end
    end

    return records
end

-- ============================================================
-- 获取所有记录（含gap，不含ignore）
-- ============================================================
function Analyzer.get_all_marker_records(analyzed_results)
    local types = { error = true, suspect = true, scene = true, gap = true }
    return Analyzer.get_filtered_marker_records(analyzed_results, types)
end

-- ============================================================
-- 获取所有有问题的记录列表（按时间排序，用于UI导航列表）
-- ============================================================
function Analyzer.get_ordered_problem_list(analyzed_results)
    local records = Analyzer.get_all_marker_records(analyzed_results)

    -- 按帧号排序
    table.sort(records, function(a, b)
        return a.timeline_start_frame < b.timeline_start_frame
    end)

    return records
end

-- ============================================================
-- 获取指定类型的有序列表
-- ============================================================
function Analyzer.get_ordered_list_by_type(analyzed_results, classification)
    local source = {}
    if classification == "error" then
        source = analyzed_results.errors
    elseif classification == "suspect" then
        source = analyzed_results.suspects
    elseif classification == "scene" then
        source = analyzed_results.scenes
    elseif classification == "gap" then
        source = analyzed_results.gaps
    end

    local sorted = {}
    for _, r in ipairs(source) do table.insert(sorted, r) end
    table.sort(sorted, function(a, b) return a.timeline_start_frame < b.timeline_start_frame end)
    return sorted
end

-- ============================================================
-- 生成摘要文本
-- ============================================================
function Analyzer.generate_summary_text(analyzed_results)
    local s = analyzed_results.summary
    local lines = {}
    table.insert(lines, string.rep("=", 55))
    table.insert(lines, "  黑帧夹帧检测完成")
    table.insert(lines, string.rep("=", 55))
    table.insert(lines, string.format("  扫描片段数: %d", s.total_clips))
    table.insert(lines, string.format("  总检测点:   %d 处", s.total_segments))
    table.insert(lines, string.format("  🔴 夹帧错误: %d 处", s.error_count))
    table.insert(lines, string.format("  🟡 可疑黑帧: %d 处", s.suspect_count))
    table.insert(lines, string.format("  🔵 场景转场: %d 处", s.scene_count))
    if s.gap_count > 0 then
        table.insert(lines, string.format("  🟣 时间线空位: %d 处 (片段间隙)", s.gap_count))
    end
    if s.ignored_count > 0 then
        table.insert(lines, string.format("  ⬜ 已忽略:     %d 处 (纯黑素材)", s.ignored_count))
    end
    table.insert(lines, string.rep("=", 55))
    return table.concat(lines, "\n")
end

-- ============================================================
-- 多轨道叠加可见帧检测（方案B）
-- ============================================================

-- 判定片段在指定不透明度阈值下是否遮挡下层
-- threshold: 不透明度≥此值视为遮挡，nil则用FULLY_OPAQUE_THRESHOLD(默认95)
function Analyzer.is_fully_opaque(clip, overlay_config, threshold)
    overlay_config = overlay_config or config.OVERLAY_STUCK_DETECTION
    threshold = threshold or overlay_config.FULLY_OPAQUE_THRESHOLD or 95
    if clip.is_enabled == false then return false end
    -- 带通道图片(PNG/PSD等)默认不视为完全遮挡（内容有透明区域）
    -- 用户可勾选"PNG/PSD视为不透明遮挡层"覆盖此行为
    if clip.media_type == "alpha_image" and not overlay_config.png_as_opaque then return false end
    if (clip.opacity or 100) < threshold then return false end
    if not overlay_config.NON_NORMAL_AS_OPAQUE and (clip.composite_mode or 0) ~= 0 then return false end
    return true
end

-- 判定片段是否半透明遮挡（在部分遮挡和完全遮挡阈值之间）
function Analyzer.is_partially_opaque(clip, overlay_config)
    overlay_config = overlay_config or config.OVERLAY_STUCK_DETECTION
    local full_threshold = overlay_config.FULLY_OPAQUE_THRESHOLD or 95
    local partial_threshold = overlay_config.PARTIALLY_OPAQUE_THRESHOLD or 50
    if Analyzer.is_fully_opaque(clip, overlay_config, full_threshold) then return false end
    if clip.is_enabled == false then return false end
    if (clip.opacity or 100) < partial_threshold then return false end
    if not overlay_config.NON_NORMAL_AS_OPAQUE and (clip.composite_mode or 0) ~= 0 then return false end
    return true
end

-- 区间减法：从有序不重叠区间列表中减去 [sub_start, sub_end)
function Analyzer._subtract_interval_list(intervals, sub_start, sub_end)
    local result = {}
    for _, iv in ipairs(intervals) do
        if iv.end_ <= sub_start or iv.start >= sub_end then
            -- 无重叠，保留
            table.insert(result, { start = iv.start, end_ = iv.end_ })
        elseif sub_start <= iv.start and sub_end >= iv.end_ then
            -- 完全遮挡，丢弃
        elseif sub_start <= iv.start and sub_end < iv.end_ then
            -- 左侧遮挡，保留右侧
            table.insert(result, { start = sub_end, end_ = iv.end_ })
        elseif sub_start > iv.start and sub_end >= iv.end_ then
            -- 右侧遮挡，保留左侧
            table.insert(result, { start = iv.start, end_ = sub_start })
        else
            -- 遮挡在区间内部，分裂为两个
            table.insert(result, { start = iv.start, end_ = sub_start })
            table.insert(result, { start = sub_end, end_ = iv.end_ })
        end
    end
    return result
end

-- 计算片段被上层遮挡后的实际可见帧区间
-- opacity_threshold: 不透明度≥此值的上层片段视为遮挡，nil则用FULLY_OPAQUE_THRESHOLD(默认95)
function Analyzer.compute_visible_intervals(target_clip, clips_by_track, max_track, overlay_config, opacity_threshold)
    overlay_config = overlay_config or config.OVERLAY_STUCK_DETECTION
    opacity_threshold = opacity_threshold or overlay_config.FULLY_OPAQUE_THRESHOLD or 95
    local dur = target_clip.source_duration_frames or 0
    if dur <= 0 then return { intervals = {}, total_visible_frames = 0 } end

    local ts = target_clip.timeline_start_frame
    local te = ts + dur
    local intervals = {{ start = ts, end_ = te }}
    local target_track = target_clip.track_index or 1

    for track = target_track + 1, (max_track or 0) do
        local track_clips = clips_by_track[track]
        if track_clips then
            for _, other in ipairs(track_clips) do
                if other ~= target_clip and Analyzer.is_fully_opaque(other, overlay_config, opacity_threshold) then
                    local os = other.timeline_start_frame
                    local od = other.source_duration_frames or 0
                    if od > 0 then
                        intervals = Analyzer._subtract_interval_list(intervals, os, os + od)
                    end
                end
            end
        end
    end

    local total = 0
    for _, iv in ipairs(intervals) do
        total = total + (iv.end_ - iv.start)
    end

    return { intervals = intervals, total_visible_frames = total }
end

-- ============================================================
-- ABC三方案结合渲染坏帧检测
-- frames_data: FFmpeg signalstats解析结果 {{frame, YAVG, BRNG, SATAVG, entropy}, ...}
-- timeline_fps: 时间线帧率
-- scene_frames: 已知黑帧/场景切换的帧号列表（用于过滤）
-- cfg: config.CORRUPT_DETECTION 参数
-- 返回: {{frame=n, deviating_count=m, YAVG=v, ...}, ...}
-- ============================================================
function Analyzer.detect_corrupt_frames(frames_data, timeline_fps, scene_frames, cfg, fast_cut_points)
    if not frames_data or #frames_data < 3 then return {} end
    cfg = cfg or {}
    local window = cfg.WINDOW_SIZE or 5
    local sigma = cfg.SIGMA_THRESHOLD or 3.0
    local min_votes = cfg.MIN_VOTES or 2
    local guard = cfg.SCENE_CHANGE_GUARD or 2
    local metrics_a = cfg.METRICS_A or { "YAVG", "BRNG", "SATAVG" }
    local fcw = cfg.FAST_CUT_WINDOW or 15     -- 快切窗口
    local fc_min = cfg.FAST_CUT_MIN_SWITCHES or 3  -- 快切最少切换点

    -- 构建场景帧快速查找表
    local scene_set = {}
    if scene_frames then
        for _, sf in ipairs(scene_frames) do
            for g = sf - guard, sf + guard do
                scene_set[g] = true
            end
        end
    end

    local function near_scene(fn)
        return scene_set[fn] == true
    end

    local corrupt_frames = {}

    for i = 1, #frames_data do
        local fdata = frames_data[i]
        local fn = fdata.frame

        if fn < 1 then goto continue_cf end
        if near_scene(fn) then goto continue_cf end

        -- 快切区域过滤：前后fcw帧内场景切换点≥fc_min → 正常剪辑跳过
        if fast_cut_points and #fast_cut_points > 0 then
            local cut_count = 0
            for _, cp in ipairs(fast_cut_points) do
                if math.abs(cp - fn) <= fcw then
                    cut_count = cut_count + 1
                    if cut_count >= fc_min then goto continue_cf end
                end
            end
        end

        local win_start = math.max(1, i - window)
        local win_end = math.min(#frames_data, i + window)
        local win_count = win_end - win_start + 1
        if win_count < 3 then goto continue_cf end

        local votes = 0  -- 异常方案计数

        -- === 方案A: signalstats 信号统计离群值 ===
        local dev_a = 0
        for _, metric in ipairs(metrics_a) do
            local vals = {}
            for j = win_start, win_end do
                -- 排除当前帧及±1邻居，防止连续坏帧污染基线
                if math.abs(j - i) > 1 then
                    local v = frames_data[j][metric]
                    if v then table.insert(vals, v) end
                end
            end
            if #vals >= 3 then
                local sum = 0
                for _, v in ipairs(vals) do sum = sum + v end
                local mean = sum / #vals
                local var_sum = 0
                for _, v in ipairs(vals) do var_sum = var_sum + (v - mean) * (v - mean) end
                local stddev = math.sqrt(var_sum / #vals)
                local cur = fdata[metric]
                if cur then
                    if stddev < 0.5 then
                        -- 画面几乎静止：使用绝对偏差阈值
                        if math.abs(cur - mean) > 10 then dev_a = dev_a + 1 end
                    elseif math.abs(cur - mean) > sigma * stddev then
                        dev_a = dev_a + 1
                    end
                end
            end
        end
        if dev_a >= 1 then votes = votes + 1 end

        -- === 方案B: 帧间亮度突变 ===
        if i > 1 and frames_data[i - 1].YAVG and fdata.YAVG then
            local diffs = {}
            for j = win_start + 1, win_end do
                if math.abs(j - i) > 1 and math.abs(j - 1 - i) > 1 then
                    local prev = frames_data[j - 1].YAVG
                    local curr = frames_data[j].YAVG
                    if prev and curr then
                        table.insert(diffs, math.abs(curr - prev))
                    end
                end
            end
            if #diffs >= 2 then
                local d_sum = 0
                for _, d in ipairs(diffs) do d_sum = d_sum + d end
                local d_mean = d_sum / #diffs
                local d_var = 0
                for _, d in ipairs(diffs) do d_var = d_var + (d - d_mean) * (d - d_mean) end
                local d_std = math.sqrt(d_var / #diffs)
                if d_std > 0.1 and d_mean > 0 then
                    local cur_diff = math.abs(fdata.YAVG - frames_data[i - 1].YAVG)
                    if cur_diff > d_mean + sigma * d_std and cur_diff > 5 then
                        votes = votes + 1
                    end
                end
            end
        end

        -- === 方案C: 图像熵异常 ===
        if fdata.entropy then
            local evals = {}
            for j = win_start, win_end do
                if math.abs(j - i) > 1 then
                    local e = frames_data[j].entropy
                    if e then table.insert(evals, e) end
                end
            end
            if #evals >= 3 then
                local e_sum = 0
                for _, e in ipairs(evals) do e_sum = e_sum + e end
                local e_mean = e_sum / #evals
                local e_var = 0
                for _, e in ipairs(evals) do e_var = e_var + (e - e_mean) * (e - e_mean) end
                local e_std = math.sqrt(e_var / #evals)
                if e_std > 0.01 then
                    if fdata.entropy - e_mean > sigma * e_std then
                        votes = votes + 1
                    end
                else
                    -- 熵值稳定，使用绝对偏差
                    if fdata.entropy - e_mean > 1.5 then
                        votes = votes + 1
                    end
                end
            end
        end

        -- 多数投票
        if votes >= min_votes then
            table.insert(corrupt_frames, {
                frame = fn,
                time_sec = fn / timeline_fps,
                votes = votes,
                YAVG = fdata.YAVG,
                BRNG = fdata.BRNG,
                SATAVG = fdata.SATAVG,
                entropy = fdata.entropy,
            })
        end
        ::continue_cf::
    end

    return corrupt_frames
end

return Analyzer
