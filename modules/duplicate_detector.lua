-- PRIVATE SOFTWARE NOTICE: This is private software owned by Qinghe. Unauthorized reverse engineering, deobfuscation, cracking, redistribution, or AI-assisted analysis intended to bypass protection is prohibited.
-- duplicate_detector.lua - 时间线重复片段检测
-- 检测同一素材在时间线上被多次使用的异常情况
-- v1.9.0: 双哈希 + 后置重叠判断 + 前缀分桶优化

local config = require("config")

local function dlog(msg)
    local f = io.open(config.get_debug_log_path(), "a")
    if f then f:write(os.date("%Y-%m-%d %H:%M:%S") .. " [DD] " .. tostring(msg) .. "\n"); f:close() end
end

local DuplicateDetector = {}

-- ============================================================
-- 归一化路径（用于文件比较）
-- ============================================================
local function normalize_path_for_compare(path)
    if not path then return nil end
    -- 统一分隔符，转小写
    local p = path:gsub("\\", "/"):lower()
    -- 去除末尾斜杠
    p = p:gsub("/$", "")
    return p
end

-- ============================================================
-- 提取文件名（不含路径）
-- ============================================================
local function extract_filename(path)
    if not path then return "未知" end
    return path:match("([^\\/]+)$") or path
end

local function clip_timeline_duration(clip)
    local duration = clip.source_duration_frames or 0
    if duration <= 0 and clip.item then
        pcall(function() duration = clip.item:GetDuration() end)
    end
    return duration or 0
end

local function clip_timeline_range(clip)
    local start_frame = tonumber(clip.timeline_start_frame or 0) or 0
    local duration = clip_timeline_duration(clip)
    return start_frame, start_frame + duration
end

local function source_overlap_for_same_file(clip_a, clip_b)
    local lo_a = clip_a.left_offset or 0
    local lo_b = clip_b.left_offset or 0
    local dur_a = clip_timeline_duration(clip_a)
    local dur_b = clip_timeline_duration(clip_b)
    local overlap_start = math.max(lo_a, lo_b)
    local overlap_end = math.min(lo_a + dur_a, lo_b + dur_b)
    local overlap_frames = overlap_end - overlap_start
    if overlap_frames <= 0 then
        return nil
    end
    return {
        source_start = overlap_start,
        source_end = overlap_end,
        frames = overlap_frames,
        a_timeline_start = (clip_a.timeline_start_frame or 0) + (overlap_start - lo_a),
        b_timeline_start = (clip_b.timeline_start_frame or 0) + (overlap_start - lo_b),
    }
end

-- ============================================================
-- 核心方法：检测重复片段
-- 输入: clips列表（包含file_path, timeline_start_frame, name, item等）
-- 输出: duplicates列表，每个元素为 {type, clips, distance_frames, distance_sec, reason}
-- ============================================================
function DuplicateDetector.detect(clips, timeline_fps, params)
    params = params or {}
    timeline_fps = timeline_fps or 25
    local io_in = tonumber(params.in_point)
    local io_out = tonumber(params.out_point)
    local has_io_range = io_in ~= nil and io_out ~= nil and io_out > io_in
    local function clip_overlaps_io(clip)
        if not has_io_range then return true end
        local s, e = clip_timeline_range(clip)
        return e > io_in and s < io_out
    end

    local near_threshold_sec = params.dup_near_threshold or config.DUPLICATE.NEAR_THRESHOLD_SEC
    local far_threshold_sec = params.dup_far_threshold or config.DUPLICATE.FAR_THRESHOLD_SEC
    local near_threshold_frames = math.floor(near_threshold_sec * timeline_fps)
    local far_threshold_frames = math.floor(far_threshold_sec * timeline_fps)
    -- 构建全片段覆盖表，用于判断间隔是否为空档
    local function build_gap_coverage(all_clips)
        local ranges = {}
        for _, c in ipairs(all_clips) do
            local s = c.timeline_start_frame
            local d = c.source_duration_frames or 0
            if d > 0 then table.insert(ranges, {s = s, e = s + d}) end
        end
        table.sort(ranges, function(a, b) return a.s < b.s end)
        return ranges
    end
    local coverage_ranges = build_gap_coverage(clips)

    local min_empty_sec = config.DUPLICATE.DISTANT_SKIP_EMPTY_SEC or 10
    local min_total_sec = config.DUPLICATE.DISTANT_SKIP_TOTAL_SEC or 60
    local short_overlap_force_sec = config.DUPLICATE.DISTANT_SHORT_OVERLAP_FORCE_SEC or 5

    -- 判断两个帧号之间是否有≥min_empty_sec秒的连续空档(无镜头覆盖)
    local function has_long_empty_gap(gap_start, gap_end)
        if gap_end - gap_start < min_empty_sec * timeline_fps then return false end
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
            if c.s - cursor >= min_empty_sec * timeline_fps then return true end
            if c.e > cursor then cursor = c.e end
        end
        if gap_end - cursor >= min_empty_sec * timeline_fps then return true end
        return false
    end

    local results = {
        near_duplicates = {},   -- 近距重复（高嫌疑，< near_threshold）
        far_duplicates = {},    -- 远距重复（可能有意，< far_threshold）
        distant_reuse = {},     -- 远距复用（> far_threshold，信息标记）
        summary = {
            near_count = 0,
            far_count = 0,
            distant_count = 0,
            total_groups = 0,
        },
    }

    -- ----------------------------------------------------------
    -- 方法1: 按源文件路径分组（精确匹配）
    -- ----------------------------------------------------------
    local path_groups = {}
    for idx, clip in ipairs(clips) do
        if not clip_overlaps_io(clip) then goto skip_path_group end
        local key = normalize_path_for_compare(clip.file_path)
        if key then
            if not path_groups[key] then
                path_groups[key] = {}
            end
            table.insert(path_groups[key], {
                index = idx,
                clip = clip,
                match_type = "same_file",
            })
        end
        ::skip_path_group::
    end

    -- ----------------------------------------------------------
    -- 方法2: 按文件名+时长分组（不同路径但相同内容）
    -- ----------------------------------------------------------
    local name_dur_groups = {}
    for idx, clip in ipairs(clips) do
        if not clip_overlaps_io(clip) then goto skip_name_duration_group end
        local filename = extract_filename(clip.file_path)
        local duration = 0
        if clip.item then
            pcall(function() duration = clip.item:GetDuration() end)
        end
        if duration <= 0 then
            goto skip_name_duration_group
        end
        -- 用文件名+时长作为近似指纹（允许1帧误差）
        local key = string.format("%s|%d", filename:lower(), math.floor(duration))
        if not name_dur_groups[key] then
            name_dur_groups[key] = {}
        end
        table.insert(name_dur_groups[key], {
            index = idx,
            clip = clip,
            match_type = "same_name_duration",
        })
        ::skip_name_duration_group::
    end

    -- ----------------------------------------------------------
    -- 分析同一文件组内的重复
    -- ----------------------------------------------------------
    local function analyze_group(group, match_type, threshold_frames, result_list, count_field)
        if #group < 2 then return end

        -- 按时间线位置排序
        table.sort(group, function(a, b)
            return a.clip.timeline_start_frame < b.clip.timeline_start_frame
        end)

        -- 相邻片段对分析
        for i = 1, #group - 1 do
            for j = i + 1, #group do
                local clip_a = group[i].clip
                local clip_b = group[j].clip

                -- 计算时间线位置
                local a_start = clip_a.timeline_start_frame
                local a_end = a_start
                if clip_a.item then
                    pcall(function() a_end = a_start + clip_a.item:GetDuration() end)
                end

                local b_start = clip_b.timeline_start_frame
                local b_end = b_start
                if clip_b.item then
                    pcall(function() b_end = b_start + clip_b.item:GetDuration() end)
                end

                -- 距离：片段A结束 到 片段B开始
                local distance_frames = b_start - a_end
                if distance_frames < 0 then
                    -- 重叠（更严重的问题）
                    distance_frames = 0
                end

                local distance_sec = distance_frames / timeline_fps
                local short_duplicate_side = nil
                local source_overlap = nil

                -- 同源文件检测：只有源时间码范围有重叠才算重复
                -- 使用同一文件的不同片段范围是正常场景切割，不应标记
                if match_type == "same_file" then
                    source_overlap = source_overlap_for_same_file(clip_a, clip_b)
                    if not source_overlap then
                        goto skip_entry
                    end

                    local dur_a = clip_timeline_duration(clip_a)
                    local dur_b = clip_timeline_duration(clip_b)
                    local min_dur = math.min(dur_a, dur_b)
                    local max_dur = math.max(dur_a, dur_b)
                    if min_dur > 0 and max_dur >= min_dur * 4 then
                        local overlap_of_long = source_overlap.frames / max_dur
                        if overlap_of_long <= 0.35 then
                            short_duplicate_side = dur_a <= dur_b and "a" or "b"
                        end
                    end
                end

                -- 检查是否超过阈值
                if distance_frames > threshold_frames then
                    -- 超过此级阈值，放到下一级
                    -- 不在这里处理
                else
                    local entry = {
                        clip_a = clip_a,
                        clip_b = clip_b,
                        clip_a_index = group[i].index,
                        clip_b_index = group[j].index,
                        distance_frames = distance_frames,
                        distance_sec = distance_sec,
                        match_type = match_type,
                        short_duplicate_side = short_duplicate_side,
                        source_overlap = source_overlap,
                        reason = DuplicateDetector._build_reason(
                            clip_a, clip_b, distance_sec, distance_frames, match_type, timeline_fps
                        ),
                    }
                    table.insert(result_list, entry)
                end

                ::skip_entry::
            end
        end
    end

    -- 按路径分组 → 近距/远距检测
    for _, group in pairs(path_groups) do
        if #group >= 2 then
            results.summary.total_groups = results.summary.total_groups + 1
            -- 近距检测
            analyze_group(group, "same_file", near_threshold_frames, results.near_duplicates, "near_count")
            -- 远距检测（独立于近距，处理所有对，不限于2元素组）
            analyze_group(group, "same_file", far_threshold_frames, results.far_duplicates, "far_count")
        end
    end

    -- 去重：从far_duplicates中移除已在near_duplicates中的对
    do
        local near_keys = {}
        for _, dup in ipairs(results.near_duplicates) do
            local a, b = dup.clip_a_index, dup.clip_b_index
            if a and b then
                near_keys[tostring(math.min(a, b)) .. "_" .. tostring(math.max(a, b))] = true
            end
        end
        local deduped = {}
        for _, dup in ipairs(results.far_duplicates) do
            local a, b = dup.clip_a_index, dup.clip_b_index
            if a and b then
                local k = tostring(math.min(a, b)) .. "_" .. tostring(math.max(a, b))
                if not near_keys[k] then
                    table.insert(deduped, dup)
                end
            else
                table.insert(deduped, dup)
            end
        end
        results.far_duplicates = deduped
    end

    -- 远距复用：对所有组中超出far_threshold的未匹配对
    for _, group in pairs(path_groups) do
        if #group >= 2 then
            table.sort(group, function(a, b)
                return a.clip.timeline_start_frame < b.clip.timeline_start_frame
            end)
            for i = 1, #group - 1 do
                for j = i + 1, #group do
                    local clip_a = group[i].clip
                    local clip_b = group[j].clip

                    -- 检查源范围是否重叠（不重叠=不同场景切割，跳过）
                    local lo_a = clip_a.left_offset or 0
                    local lo_b = clip_b.left_offset or 0
                    local dur_a = clip_a.source_duration_frames or 0
                    local dur_b = clip_b.source_duration_frames or 0
                    local src_a_start = lo_a
                    local src_a_end = lo_a + dur_a
                    local src_b_start = lo_b
                    local src_b_end = lo_b + dur_b
                    local overlap_start = math.max(src_a_start, src_b_start)
                    local overlap_end = math.min(src_a_end, src_b_end)
                    if overlap_end - overlap_start <= 0 then
                        goto distant_skip
                    end

                    -- 计算距离
                    local a_end = clip_a.timeline_start_frame
                    if clip_a.item then
                        pcall(function() a_end = a_end + clip_a.item:GetDuration() end)
                    end
                    local b_start = clip_b.timeline_start_frame
                    local dist = b_start - a_end
                    if dist < 0 then dist = 0 end
                    local dist_sec = dist / timeline_fps

                    -- 已在far阈值内（已由analyze_group处理）→ 跳过
                    if dist_sec <= far_threshold_sec then
                        goto distant_skip
                    end

                    local overlap_frames = overlap_end - overlap_start
                    local is_short_overlap = (overlap_frames / timeline_fps) <= short_overlap_force_sec

                    -- 有长空档且总距离大 → 故意复用，跳过。
                    -- 但短源区间重复更像误复制，不能因为隔得远就完全不报。
                    if (not is_short_overlap) and has_long_empty_gap(a_end, b_start) and dist_sec > min_total_sec then
                        dlog(string.format("skip distant: gap has empty>%ds, total>%ds, %s <-> %s",
                            min_empty_sec, min_total_sec,
                            clip_a.name or "?", clip_b.name or "?"))
                    else
                        table.insert(results.distant_reuse, {
                            clip_a = clip_a, clip_b = clip_b,
                            clip_a_index = group[i].index, clip_b_index = group[j].index,
                            distance_frames = dist, distance_sec = dist_sec,
                            match_type = "same_file",
                            source_overlap = {
                                source_start = overlap_start,
                                source_end = overlap_end,
                                frames = overlap_frames,
                                a_timeline_start = (clip_a.timeline_start_frame or 0) + (overlap_start - lo_a),
                                b_timeline_start = (clip_b.timeline_start_frame or 0) + (overlap_start - lo_b),
                            },
                            reason = DuplicateDetector._build_reason(
                                clip_a, clip_b, dist_sec, dist, "same_file", timeline_fps
                            ),
                        })
                    end
                    ::distant_skip::
                end
            end
        end
    end

    -- 按文件名+时长分组 → 仅检测近距（更不可靠的匹配）
    for key, group in pairs(name_dur_groups) do
        -- 跳过已经被same_file覆盖的（避免重复报告）
        local all_same_file = true
        for _, entry in ipairs(group) do
            if entry.match_type ~= "same_file" then
                all_same_file = false
                break
            end
        end
        if not all_same_file and #group >= 2 then
            results.summary.total_groups = results.summary.total_groups + 1
            analyze_group(group, "same_name_duration", near_threshold_frames,
                results.near_duplicates, "near_count")
        end
    end

    -- 更新计数
    results.summary.near_count = #results.near_duplicates
    results.summary.far_count = #results.far_duplicates
    results.summary.distant_count = #results.distant_reuse

    return results
end

-- ============================================================
-- 构建重复原因描述文本
-- ============================================================
function DuplicateDetector._build_reason(clip_a, clip_b, distance_sec, distance_frames, match_type, fps)
    local parts = {}

    local name_a = extract_filename(clip_a.file_path)
    local name_b = extract_filename(clip_b.file_path)

    if match_type == "same_file" then
        table.insert(parts, string.format("同一文件被使用2次: %s", name_a))
    else
        table.insert(parts, string.format("疑似相同内容: %s ≈ %s", name_a, name_b))
    end

    if distance_frames <= 0 then
        table.insert(parts, "⚠️ 两个片段重叠，可能是剪辑错误")
    elseif distance_sec <= 1.0 then
        table.insert(parts, string.format("间距 %.1f帧 (%.2fs) - 很近，极可能是误复制", distance_frames, distance_sec))
    else
        table.insert(parts, string.format("间距 %.0f帧 (%.1fs)", distance_frames, distance_sec))
    end

    table.insert(parts, string.format("片段A起始: 帧%d", clip_a.timeline_start_frame))
    table.insert(parts, string.format("片段B起始: 帧%d", clip_b.timeline_start_frame))

    return table.concat(parts, "\n")
end

-- ============================================================
-- 将重复检测结果转为时间线标记记录
-- ============================================================
function DuplicateDetector.to_marker_records(dup_results, timeline_fps, params)
    local Analyzer = require("black_frame_analyzer")
    local fps = timeline_fps or 25
    local records = {}
    params = params or {}
    local io_in = tonumber(params.in_point)
    local io_out = tonumber(params.out_point)
    local has_io_range = io_in ~= nil and io_out ~= nil and io_out > io_in

    local function add_marker_record(record)
        local s = tonumber(record.timeline_start_frame or 0) or 0
        local e = tonumber(record.timeline_end_frame or s + (record.duration_frames or 1)) or (s + 1)
        if has_io_range then
            local clipped_s = math.max(s, io_in)
            local clipped_e = math.min(e, io_out)
            if clipped_e <= clipped_s then return end
            if clipped_s ~= s or clipped_e ~= e then
                record.timeline_start_frame = clipped_s
                record.timeline_end_frame = clipped_e
                record.timeline_start_tc = Analyzer.frame_to_timecode(clipped_s, fps)
                record.timeline_end_tc = Analyzer.frame_to_timecode(clipped_e, fps)
                record.duration_frames = math.max(1, clipped_e - clipped_s)
                record.source_duration_sec = record.duration_frames / fps
                record.note = tostring(record.note or "") .. "\n已按当前 I/O 范围裁剪重复标记。"
            end
        end
        table.insert(records, record)
    end

    local function add_dup_records(dup, color, name_a, name_b)
        local dur_a = clip_timeline_duration(dup.clip_a)
        local dur_b = clip_timeline_duration(dup.clip_b)
        local end_a = dup.clip_a.timeline_start_frame + dur_a
        local end_b = dup.clip_b.timeline_start_frame + dur_b
        local overlap = dup.source_overlap

        local function add_single_duplicate_record(clip, dur)
            local end_frame = clip.timeline_start_frame + dur
            add_marker_record({
                classification = "duplicate",
                marker_color = color,
                marker_name = name_b,
                timeline_start_frame = clip.timeline_start_frame,
                timeline_end_frame = end_frame,
                timeline_start_tc = Analyzer.frame_to_timecode(clip.timeline_start_frame, fps),
                timeline_end_tc = Analyzer.frame_to_timecode(end_frame, fps),
                note = string.format("重复短切片: %s\n片段区间: %d-%d帧 (%d帧)\n长主片段不标记为副本，避免误报整段素材。",
                    extract_filename(clip.file_path), clip.timeline_start_frame, end_frame, dur),
                source_file = clip.file_path,
                source_duration_sec = dur / fps,
                duration_frames = dur,
            })
        end

        if dup.match_type == "same_file" and overlap and overlap.frames and overlap.frames > 0 then
            local start_a = overlap.a_timeline_start or dup.clip_a.timeline_start_frame
            local start_b = overlap.b_timeline_start or dup.clip_b.timeline_start_frame
            local end_overlap_a = start_a + overlap.frames
            local end_overlap_b = start_b + overlap.frames
            local note = (dup.reason or "重复片段") .. string.format(
                "\n实际重复源区间: %d-%d帧 (%d帧)\n仅标记长成片内部真正重复的镜头范围。",
                overlap.source_start or 0,
                overlap.source_end or 0,
                overlap.frames
            )
            add_marker_record({
                classification = "duplicate",
                marker_color = color,
                marker_name = name_a,
                timeline_start_frame = start_a,
                timeline_end_frame = end_overlap_a,
                timeline_start_tc = Analyzer.frame_to_timecode(start_a, fps),
                timeline_end_tc = Analyzer.frame_to_timecode(end_overlap_a, fps),
                note = note .. string.format("\n片段A重复区间: %d-%d帧 (%d帧)", start_a, end_overlap_a, overlap.frames),
                source_file = dup.clip_a.file_path,
                source_duration_sec = overlap.frames / fps,
                duration_frames = overlap.frames,
            })
            add_marker_record({
                classification = "duplicate",
                marker_color = color,
                marker_name = name_b,
                timeline_start_frame = start_b,
                timeline_end_frame = end_overlap_b,
                timeline_start_tc = Analyzer.frame_to_timecode(start_b, fps),
                timeline_end_tc = Analyzer.frame_to_timecode(end_overlap_b, fps),
                note = string.format(
                    "重复副本: %s\n实际重复源区间: %d-%d帧 (%d帧)\n片段B重复区间: %d-%d帧 (%d帧)",
                    extract_filename(dup.clip_a.file_path),
                    overlap.source_start or 0,
                    overlap.source_end or 0,
                    overlap.frames,
                    start_b,
                    end_overlap_b,
                    overlap.frames
                ),
                source_file = dup.clip_b.file_path,
                source_duration_sec = overlap.frames / fps,
                duration_frames = overlap.frames,
            })
            return
        end

        if dup.short_duplicate_side == "a" then
            add_single_duplicate_record(dup.clip_a, dur_a)
            return
        elseif dup.short_duplicate_side == "b" then
            add_single_duplicate_record(dup.clip_b, dur_b)
            return
        end

        add_marker_record({
            classification = "duplicate",
            marker_color = color,
            marker_name = name_a,
            timeline_start_frame = dup.clip_a.timeline_start_frame,
            timeline_end_frame = end_a,
            timeline_start_tc = Analyzer.frame_to_timecode(dup.clip_a.timeline_start_frame, fps),
            timeline_end_tc = Analyzer.frame_to_timecode(end_a, fps),
            note = (dup.reason or "重复片段") .. string.format("\n片段区间: %d-%d帧 (%d帧)",
                dup.clip_a.timeline_start_frame, end_a, dur_a),
            source_file = dup.clip_a.file_path,
            source_duration_sec = dur_a / fps,
            duration_frames = dur_a,
        })
        add_marker_record({
            classification = "duplicate",
            marker_color = color,
            marker_name = name_b,
            timeline_start_frame = dup.clip_b.timeline_start_frame,
            timeline_end_frame = end_b,
            timeline_start_tc = Analyzer.frame_to_timecode(dup.clip_b.timeline_start_frame, fps),
            timeline_end_tc = Analyzer.frame_to_timecode(end_b, fps),
            note = string.format("重复副本: %s\n片段区间: %d-%d帧 (%d帧)",
                extract_filename(dup.clip_a.file_path), dup.clip_b.timeline_start_frame, end_b, dur_b),
            source_file = dup.clip_b.file_path,
            source_duration_sec = dur_b / fps,
            duration_frames = dur_b,
        })
    end

    -- 近距重复 → Rose（高嫌疑）
    for _, dup in ipairs(dup_results.near_duplicates) do
        add_dup_records(dup,
            config.MARKER_COLORS.DUPLICATE_NEAR or "Rose",
            "[BFD-DUP] 疑似误复制（近距）",
            "[BFD-DUP] 重复副本")
    end

    -- 远距重复 → Sand（需确认）
    for _, dup in ipairs(dup_results.far_duplicates) do
        add_dup_records(dup,
            config.MARKER_COLORS.DUPLICATE_FAR or "Sand",
            "[BFD-DUP] 远距重复（请确认）",
            "[BFD-DUP] 远距重复副本")
    end

    -- 远距复用(跨轨道) → Cyan（信息提示）
    for _, dup in ipairs(dup_results.distant_reuse or {}) do
        add_dup_records(dup,
            config.MARKER_COLORS.DUPLICATE_DISTANT or "Cyan",
            "[BFD-DUP] 远距复用(跨轨道)",
            "[BFD-DUP] 远距复用副本")
    end

    return records
end

-- ============================================================
-- 生成重复检测摘要文本
-- ============================================================
function DuplicateDetector.generate_summary(dup_results)
    local s = dup_results.summary
    local lines = {}
    table.insert(lines, string.rep("-", 55))
    table.insert(lines, "  重复片段检测")
    table.insert(lines, string.rep("-", 55))
    table.insert(lines, string.format("  检测到 %d 组重复素材", s.total_groups))
    table.insert(lines, string.format("  🟠 近距重复: %d 对 (高嫌疑，可能是误复制)", s.near_count))
    table.insert(lines, string.format("  🟤 远距重复: %d 对 (需确认，可能是有意复用)", s.far_count))
    table.insert(lines, string.format("  ⬜ 远距复用: %d 对 (信息标记)", s.distant_count))
    return table.concat(lines, "\n")
end

-- ============================================================
-- 帧指纹内容重复检测 (v1.9.0)
-- 双哈希策略：
--   块均值哈希(Block-Mean): 快速精确匹配，4x4块→32位
--   边缘哈希(Edge Hash/dHash): 调色免疫，梯度方向→480位
-- ============================================================

local FINGERPRINT_THUMB = 16   -- 缩略图尺寸（像素）
local FINGERPRINT_BLOCK = 4    -- 块均值哈希分块数（4x4=16块）
local DARK_THRESHOLD = 10      -- 黑帧判定：平均亮度低于此值跳过
local MAX_HAMMING = 20         -- 边缘哈希汉明距离阈值（≤此值视为重复，480位中约4%容差）
local MAX_GRAY_HAMMING = 48    -- 灰度结构哈希阈值（256位中约19%容差，适合调色变体）

-- 预计算4位XOR的popcount查找表 (Lua 5.1无位运算)
local XOR_POPCOUNT = {}
for a = 0, 15 do
    for b = 0, 15 do
        local bits = 0
        -- 手动计算a XOR b的1的个数（每位比较）
        for bit = 0, 3 do
            local ba = math.floor(a / (2 ^ bit)) % 2
            local bb = math.floor(b / (2 ^ bit)) % 2
            if ba ~= bb then bits = bits + 1 end
        end
        XOR_POPCOUNT[a * 16 + b + 1] = bits
    end
end

-- 计算两个hex字符串的汉明距离（使用预计算的XOR popcount表）
local function hamming_distance_hex(h1, h2)
    if #h1 ~= #h2 then return 999 end
    local dist = 0
    for i = 1, #h1 do
        local b1 = tonumber(h1:sub(i, i), 16)
        local b2 = tonumber(h2:sub(i, i), 16)
        if b1 and b2 then
            dist = dist + XOR_POPCOUNT[b1 * 16 + b2 + 1]
        end
    end
    return dist
end

local function bits_to_hex(bits)
    local hex_parts = {}
    for b = 1, #bits, 4 do
        local nibble = (bits[b] or 0) * 8 + (bits[b+1] or 0) * 4
                     + (bits[b+2] or 0) * 2 + (bits[b+3] or 0)
        table.insert(hex_parts, string.format("%x", nibble))
    end
    return table.concat(hex_parts)
end

local function build_gray_structure_hash_from_values(values)
    if not values or #values <= 0 then return nil end
    local min_g, max_g, sum = 255, 0, 0
    for i = 1, #values do
        local g = values[i] or 0
        if g < min_g then min_g = g end
        if g > max_g then max_g = g end
        sum = sum + g
    end
    local range = max_g - min_g
    local avg = 0
    local normalized = {}
    for i = 1, #values do
        local v = values[i] or 0
        if range > 8 then
            v = math.floor(((v - min_g) * 255) / range)
        end
        normalized[i] = v
        avg = avg + v
    end
    avg = avg / #values
    local bits = {}
    for i = 1, #values do
        bits[i] = (normalized[i] >= avg) and 1 or 0
    end
    return bits_to_hex(bits)
end

local function build_gray_structure_hash(gray, px_count)
    if not gray or px_count <= 0 then return nil end
    local values = {}
    for i = 1, px_count do values[i] = gray[i] or 0 end
    return build_gray_structure_hash_from_values(values)
end

local function build_gray_structure_hash_scaled(gray, ts, margin)
    if not gray or not ts or ts <= 1 then return nil end
    margin = margin or 0
    local span = (ts - 1) - margin * 2
    if span <= 1 then return nil end
    local values = {}
    local out_size = 16
    for oy = 0, out_size - 1 do
        local sy = margin + (oy / (out_size - 1)) * span
        local y = math.floor(sy + 0.5)
        if y < 0 then y = 0 elseif y > ts - 1 then y = ts - 1 end
        for ox = 0, out_size - 1 do
            local sx = margin + (ox / (out_size - 1)) * span
            local x = math.floor(sx + 0.5)
            if x < 0 then x = 0 elseif x > ts - 1 then x = ts - 1 end
            table.insert(values, gray[y * ts + x + 1] or 0)
        end
    end
    return build_gray_structure_hash_from_values(values)
end

local function gray_hash_distance(fp_a, fp_b)
    local hashes_a = fp_a and fp_a.gray_hashes or nil
    local hashes_b = fp_b and fp_b.gray_hashes or nil
    if (not hashes_a or #hashes_a == 0) and fp_a and fp_a.gray_hash then hashes_a = { fp_a.gray_hash } end
    if (not hashes_b or #hashes_b == 0) and fp_b and fp_b.gray_hash then hashes_b = { fp_b.gray_hash } end
    if not hashes_a or not hashes_b then return 999 end
    local best = 999
    for _, ha in ipairs(hashes_a) do
        for _, hb in ipairs(hashes_b) do
            if ha and hb and #ha == #hb then
                local d = hamming_distance_hex(ha, hb)
                if d < best then best = d end
            end
        end
    end
    return best
end

-- 提取单个视频文件的双哈希指纹序列
-- 返回: {{sec, frame, hash, edge_hash}, ...}
--   hash = 块均值哈希(8 hex) 用于精确匹配
--   edge_hash = 边缘哈希(120 hex) 用于调色后汉明距离匹配
function DuplicateDetector._extract_fingerprints(file_path, interval_frames, thumb_size, fps, clip_start_sec, clip_duration_sec)
    fps = fps or 25
    if not file_path then return {} end

    local f = io.open(file_path, "r")
    if not f then return {} end
    f:close()

    -- 自适应采样率：短片段至少采到3帧，否则指纹匹配无意义
    local eff_dur = clip_duration_sec or 5
    local interval_sec = interval_frames / fps
    local sample_fps = 1.0 / interval_sec
    if eff_dur > 0 and eff_dur * sample_fps < 3 then
        -- 太短的片段提高采样率，确保至少3帧
        sample_fps = 3.0 / eff_dur
        interval_sec = 1.0 / sample_fps
    end
    local eff_dur_for_log = eff_dur  -- 保存用于日志
    local ts = thumb_size or FINGERPRINT_THUMB
    local block_cnt = FINGERPRINT_BLOCK
    local px_per_block = ts / block_cnt
    local block_px_total = px_per_block * px_per_block

    -- 范围限制参数（快速seek）
    local range_args = ""
    local time_offset = 0
    if clip_start_sec and clip_start_sec > 0 then
        range_args = range_args .. string.format(" -ss %.3f", clip_start_sec)
        time_offset = clip_start_sec
    end
    if clip_duration_sec and clip_duration_sec > 0 then
        range_args = range_args .. string.format(" -t %.3f", clip_duration_sec)
    end

    -- 查找ffmpeg路径（优先FFmpegRunner找到的路径，否则回退裸命令）
    local ffmpeg_bin = "ffmpeg"
    if config._cached_ffmpeg_path then
        ffmpeg_bin = config._cached_ffmpeg_path
    end
    local cmd = string.format(
        '%s%s -i "%s" -vf "fps=%.4f,scale=%d:%d" -f rawvideo -pix_fmt rgb24 - 2>/dev/null',
        ffmpeg_bin, range_args, file_path, sample_fps, ts, ts
    )

    local pipe = io.popen(cmd, "r")
    if not pipe then return {} end

    local fingerprints = {}
    local frame_size = ts * ts * 3
    local idx = 0
    local gray = {}

    while true do
        local data = pipe:read(frame_size)
        if not data or #data < frame_size then break end

        -- 转灰度
        for i = 1, #gray do gray[i] = nil end
        local gi = 1
        local total_bright = 0
        for i = 1, #data, 3 do
            local g = math.floor((data:byte(i) + data:byte(i+1) + data:byte(i+2)) / 3)
            gray[gi] = g
            total_bright = total_bright + g
            gi = gi + 1
        end
        local px_count = gi - 1
        local avg_bright = total_bright / px_count

        if avg_bright < DARK_THRESHOLD then
            idx = idx + 1
            goto continue_frame
        end

        -- ====== 块均值哈希（快速精确匹配）======
        local bm_hash_val = 0
        for by = 0, block_cnt - 1 do
            for bx = 0, block_cnt - 1 do
                local block_sum = 0
                for py = 0, px_per_block - 1 do
                    for px = 0, px_per_block - 1 do
                        local gi2 = by * px_per_block * ts + bx * px_per_block + py * ts + px + 1
                        block_sum = block_sum + (gray[gi2] or 0)
                    end
                end
                local block_mean = math.floor(block_sum / block_px_total)
                local q
                if block_mean < 64 then q = 0
                elseif block_mean < 128 then q = 1
                elseif block_mean < 192 then q = 2
                else q = 3 end
                bm_hash_val = bm_hash_val * 4 + q
            end
        end
        local bm_hash = string.format("%08x", bm_hash_val)

        -- ====== 边缘哈希（调色免疫）======
        local edge_bits = {}
        local bit_count = 0
        -- 水平梯度: pixel(x,y) < pixel(x+1,y)
        for y = 0, ts - 1 do
            for x = 0, ts - 2 do
                local g1 = gray[y * ts + x + 1] or 0
                local g2 = gray[y * ts + x + 2] or 0
                bit_count = bit_count + 1
                edge_bits[bit_count] = (g1 < g2) and 1 or 0
            end
        end
        -- 垂直梯度: pixel(x,y) < pixel(x,y+1)
        for y = 0, ts - 2 do
            for x = 0, ts - 1 do
                local g1 = gray[y * ts + x + 1] or 0
                local g2 = gray[(y + 1) * ts + x + 1] or 0
                bit_count = bit_count + 1
                edge_bits[bit_count] = (g1 < g2) and 1 or 0
            end
        end

        local hex_parts = {}
        for b = 1, bit_count, 4 do
            local nibble = (edge_bits[b] or 0) * 8 + (edge_bits[b+1] or 0) * 4
                         + (edge_bits[b+2] or 0) * 2 + (edge_bits[b+3] or 0)
            table.insert(hex_parts, string.format("%x", nibble))
        end
        local edge_hash = table.concat(hex_parts)

        local sec = idx * interval_sec + time_offset
        local frame = math.floor(sec * fps)
        table.insert(fingerprints, {
            sec = sec, frame = frame,
            hash = bm_hash,        -- 块均值哈希(8 hex) 精确匹配
            edge_hash = edge_hash,  -- 边缘哈希(120 hex) 调色后汉明距离匹配
            gray_hash = build_gray_structure_hash(gray, px_count), -- 灰度结构哈希，容忍调色/亮度变化
            gray_hashes = {
                build_gray_structure_hash(gray, px_count),
                build_gray_structure_hash_scaled(gray, ts, 1),
                build_gray_structure_hash_scaled(gray, ts, 2),
            },
        })
        idx = idx + 1

        ::continue_frame::
    end

    pipe:close()
    local fname = file_path:match("([^\\/]+)$") or file_path
    dlog(string.format("fingerprint: %s dur=%.2fs fps=%.1f → %d fingerprints",
        fname, eff_dur_for_log, sample_fps, #fingerprints))
    return fingerprints
end

-- 在指纹序列中找重复区间
-- 返回: {{start1, end1, start2, end2, frame1_start, frame1_end, frame2_start, frame2_end, count}, ...}
function DuplicateDetector._find_dup_ranges(fingerprints, min_gap_sec, fps)
    local results = {}
    if #fingerprints < 2 then return results end

    -- 按hash分组
    local hash_map = {}
    for i, fp in ipairs(fingerprints) do
        local h = fp.hash
        if not hash_map[h] then hash_map[h] = {} end
        table.insert(hash_map[h], i)
    end

    -- 计算采样间隔（用于后置重叠判断）
    local sample_interval_frames = config.DUPLICATE.CONTENT_SAMPLE_INTERVAL or 5
    if #fingerprints >= 2 then
        sample_interval_frames = fingerprints[2].frame - fingerprints[1].frame
    end

    -- 收集匹配对：仅跳过极近帧（<0.1s），真正的过滤在合并后做重叠判断
    local pairs_found = {}
    for h, indices in pairs(hash_map) do
        if #indices >= 2 then
            for a = 1, #indices do
                for b = a + 1, #indices do
                    local i1, i2 = indices[a], indices[b]
                    local gap = math.abs(fingerprints[i2].sec - fingerprints[i1].sec)
                    -- 仅跳过0.1s以内的配对，避免self-match和相邻帧
                    if gap >= 0.1 then
                        table.insert(pairs_found, {
                            idx1 = i1, idx2 = i2,
                            sec1 = fingerprints[i1].sec,
                            sec2 = fingerprints[i2].sec,
                            frame1 = fingerprints[i1].frame,
                            frame2 = fingerprints[i2].frame,
                        })
                    end
                end
            end
        end
    end

    if #pairs_found == 0 then return results end

    -- 按idx1排序后合并连续区间
    table.sort(pairs_found, function(a, b) return a.idx1 < b.idx1 end)

    local merged = {}
    local used = {}
    for i, pair in ipairs(pairs_found) do
        if not used[i] then
            local seg = {
                start1 = pair.sec1, end1 = pair.sec1,
                start2 = pair.sec2, end2 = pair.sec2,
                frame1_start = pair.frame1, frame1_end = pair.frame1,
                frame2_start = pair.frame2, frame2_end = pair.frame2,
                count = 1,
                end1_idx_fp = pair.idx1,
                end2_idx_fp = pair.idx2,
            }
            used[i] = true

            for j = i + 1, #pairs_found do
                if not used[j] then
                    local np = pairs_found[j]
                    if np.idx1 > seg.end1_idx_fp and np.idx1 - seg.end1_idx_fp <= 2
                        and np.idx2 > seg.end2_idx_fp and np.idx2 - seg.end2_idx_fp <= 2 then
                        seg.end1 = np.sec1
                        seg.end1_idx_fp = np.idx1
                        seg.end2 = np.sec2
                        seg.end2_idx_fp = np.idx2
                        seg.frame1_end = np.frame1
                        seg.frame2_end = np.frame2
                        seg.count = seg.count + 1
                        used[j] = true
                    end
                end
            end

            if seg.count >= 3 then
                -- 后置重叠判断：seq1和seq2在时间上重叠则为静态场景，丢弃
                -- 重叠判定：start2_frame <= end1_frame + sample_interval
                if seg.frame2_start > seg.frame1_end + sample_interval_frames then
                    table.insert(merged, seg)
                end
            end
        end
    end

    return merged
end

-- 在指纹序列中用边缘哈希 + 汉明距离找重复区间（调色免疫）
-- v1.8.0: 前缀分桶优化 + 后置重叠判断，避免静态场景误报
function DuplicateDetector._find_dup_ranges_edge(fingerprints, min_gap_sec, fps)
    local results = {}
    local n = #fingerprints
    if n < 2 then return results end

    -- 采样间隔（帧）
    local sample_interval_frames = config.DUPLICATE.CONTENT_SAMPLE_INTERVAL or 5
    if n >= 2 then
        sample_interval_frames = fingerprints[2].frame - fingerprints[1].frame
    end

    -- 前缀分桶：用边缘哈希前4个字符（16 bit）做快速分组
    local prefix_buckets = {}
    for i, fp in ipairs(fingerprints) do
        local prefix = fp.edge_hash:sub(1, 4)
        if not prefix_buckets[prefix] then prefix_buckets[prefix] = {} end
        table.insert(prefix_buckets[prefix], i)
    end

    -- 收集汉明距离≤阈值的匹配对
    local pairs_found = {}
    local min_gap_idx = math.max(1, math.ceil(0.1 / (fingerprints[2].sec - fingerprints[1].sec)))

    for _, group in pairs(prefix_buckets) do
        local gn = #group
        if gn >= 2 then
            for a = 1, gn do
                for b = a + 1, gn do
                    local i, j = group[a], group[b]
                    -- 跳过太近的帧对（<0.1s等价）
                    if j - i >= min_gap_idx then
                        local dist = hamming_distance_hex(fingerprints[i].edge_hash, fingerprints[j].edge_hash)
                        if dist <= MAX_HAMMING then
                            table.insert(pairs_found, {
                                idx1 = i, idx2 = j,
                                sec1 = fingerprints[i].sec,
                                sec2 = fingerprints[j].sec,
                                frame1 = fingerprints[i].frame,
                                frame2 = fingerprints[j].frame,
                                dist = dist,
                            })
                        end
                    end
                end
            end
        end
    end

    -- 跨前缀桶搜索：不同前缀但汉明距离≤阈值的配对
    local prefix_list = {}
    for p, _ in pairs(prefix_buckets) do table.insert(prefix_list, p) end
    for pi = 1, #prefix_list do
        for pj = pi + 1, #prefix_list do
            local g1 = prefix_buckets[prefix_list[pi]]
            local g2 = prefix_buckets[prefix_list[pj]]
            -- 限制每对桶的检查数量，避免巨大桶导致O(n²)爆炸
            local max_check = math.min(#g1, 200)
            for a = 1, max_check do
                local i = g1[a]
                local max_b = math.min(#g2, 200)
                for b = 1, max_b do
                    local j = g2[b]
                    if math.abs(j - i) >= min_gap_idx then
                        local dist = hamming_distance_hex(fingerprints[i].edge_hash, fingerprints[j].edge_hash)
                        if dist <= MAX_HAMMING then
                            table.insert(pairs_found, {
                                idx1 = i, idx2 = j,
                                sec1 = fingerprints[i].sec,
                                sec2 = fingerprints[j].sec,
                                frame1 = fingerprints[i].frame,
                                frame2 = fingerprints[j].frame,
                                dist = dist,
                            })
                        end
                    end
                end
            end
        end
    end

    if #pairs_found == 0 then return results end

    -- 按idx1排序后合并连续区间
    table.sort(pairs_found, function(a, b) return a.idx1 < b.idx1 end)

    local merged = {}
    local used = {}
    for i, pair in ipairs(pairs_found) do
        if not used[i] then
            local seg = {
                start1 = pair.sec1, end1 = pair.sec1,
                start2 = pair.sec2, end2 = pair.sec2,
                frame1_start = pair.frame1, frame1_end = pair.frame1,
                frame2_start = pair.frame2, frame2_end = pair.frame2,
                count = 1,
                end1_idx_fp = pair.idx1,
                end2_idx_fp = pair.idx2,
            }
            used[i] = true

            for j = i + 1, #pairs_found do
                if not used[j] then
                    local np = pairs_found[j]
                    if np.idx1 > seg.end1_idx_fp and np.idx1 - seg.end1_idx_fp <= 2
                        and np.idx2 > seg.end2_idx_fp and np.idx2 - seg.end2_idx_fp <= 2 then
                        seg.end1 = np.sec1
                        seg.end1_idx_fp = np.idx1
                        seg.end2 = np.sec2
                        seg.end2_idx_fp = np.idx2
                        seg.frame1_end = np.frame1
                        seg.frame2_end = np.frame2
                        seg.count = seg.count + 1
                        used[j] = true
                    end
                end
            end

            if seg.count >= 3 then
                -- 后置重叠判断：seq1和seq2在时间上重叠则为静态场景，丢弃
                if seg.frame2_start > seg.frame1_end + sample_interval_frames then
                    table.insert(merged, seg)
                end
            end
        end
    end

    return merged
end

-- 灰度结构哈希：先做亮度归一化，再用多尺度中心裁切容忍轻微缩放/画幅变化。
function DuplicateDetector._find_dup_ranges_gray(fingerprints, min_gap_sec, fps)
    local results = {}
    local n = #fingerprints
    if n < 2 then return results end

    local sample_interval_frames = config.DUPLICATE.CONTENT_SAMPLE_INTERVAL or 5
    if n >= 2 then
        sample_interval_frames = fingerprints[2].frame - fingerprints[1].frame
    end

    local min_gap_idx = math.max(1, math.ceil(0.1 / (fingerprints[2].sec - fingerprints[1].sec)))
    local prefix_buckets = {}
    for i, fp in ipairs(fingerprints) do
        local h = fp.gray_hash
        if h then
            local prefixes = { h:sub(1, 4), h:sub(17, 20), h:sub(33, 36), h:sub(49, 52) }
            local added = {}
            for _, prefix in ipairs(prefixes) do
                if prefix and prefix ~= "" and not added[prefix] then
                    if not prefix_buckets[prefix] then prefix_buckets[prefix] = {} end
                    table.insert(prefix_buckets[prefix], i)
                    added[prefix] = true
                end
            end
        end
    end

    local pairs_found = {}
    local seen_pairs = {}
    for _, group in pairs(prefix_buckets) do
        local gn = #group
        if gn >= 2 then
            for a = 1, gn do
                local i = group[a]
                for b = a + 1, gn do
                    local j = group[b]
                    if math.abs(j - i) >= min_gap_idx then
                        local k = tostring(math.min(i, j)) .. "_" .. tostring(math.max(i, j))
                        if not seen_pairs[k] then
                            seen_pairs[k] = true
                            local dist = gray_hash_distance(fingerprints[i], fingerprints[j])
                            if dist <= MAX_GRAY_HAMMING then
                                table.insert(pairs_found, {
                                    idx1 = i, idx2 = j,
                                    sec1 = fingerprints[i].sec,
                                    sec2 = fingerprints[j].sec,
                                    frame1 = fingerprints[i].frame,
                                    frame2 = fingerprints[j].frame,
                                    dist = dist,
                                })
                            end
                        end
                    end
                end
            end
        end
    end

    if #pairs_found == 0 then return results end
    table.sort(pairs_found, function(a, b) return a.idx1 < b.idx1 end)

    local merged = {}
    local used = {}
    for i, pair in ipairs(pairs_found) do
        if not used[i] then
            local seg = {
                start1 = pair.sec1, end1 = pair.sec1,
                start2 = pair.sec2, end2 = pair.sec2,
                frame1_start = pair.frame1, frame1_end = pair.frame1,
                frame2_start = pair.frame2, frame2_end = pair.frame2,
                count = 1,
                end1_idx_fp = pair.idx1,
                end2_idx_fp = pair.idx2,
            }
            used[i] = true

            for j = i + 1, #pairs_found do
                if not used[j] then
                    local np = pairs_found[j]
                    if np.idx1 > seg.end1_idx_fp and np.idx1 - seg.end1_idx_fp <= 2
                        and np.idx2 > seg.end2_idx_fp and np.idx2 - seg.end2_idx_fp <= 2 then
                        seg.end1 = np.sec1
                        seg.end1_idx_fp = np.idx1
                        seg.end2 = np.sec2
                        seg.end2_idx_fp = np.idx2
                        seg.frame1_end = np.frame1
                        seg.frame2_end = np.frame2
                        seg.count = seg.count + 1
                        used[j] = true
                    end
                end
            end

            if seg.count >= 3 and seg.frame2_start > seg.frame1_end + sample_interval_frames then
                table.insert(merged, seg)
            end
        end
    end

    return merged
end

-- 主入口：检测所有片段的内容重复（双哈希策略）
function DuplicateDetector.detect_content(clips, timeline_fps, params)
    params = params or {}
    timeline_fps = timeline_fps or 25

    local interval_frames = params.content_sample_interval or config.DUPLICATE.CONTENT_SAMPLE_INTERVAL
    local thumb_size = params.content_thumb_size or config.DUPLICATE.CONTENT_THUMB_SIZE
    local min_gap_sec = params.content_min_gap or config.DUPLICATE.CONTENT_MIN_GAP_SEC

    local function get_clip_fps(clip)
        local fps = timeline_fps
        if clip and clip.item then
            pcall(function()
                local v = tonumber(clip.item:GetClipProperty("FPS"))
                if v and v > 0 then fps = v end
            end)
        end
        return fps
    end

    local all_dup_ranges = {}
    local total_fps = 0
    local files_scanned = 0
    local bm_hits = 0    -- 块均值哈希命中数
    local edge_hits = 0  -- 边缘哈希命中数
    local gray_hits = 0  -- 灰度结构哈希命中数（调色/亮度/轻微缩放容忍）

    for _, clip in ipairs(clips) do
        local file_path = clip.file_path
        if not file_path then goto continue_clip end

        local fps = get_clip_fps(clip)

        -- 计算剪辑范围用于ffmpeg -ss/-to加速
        local clip_start = nil
        local clip_dur = nil
        if clip.left_offset and clip.source_duration_frames and clip.source_duration_frames > 0 then
            clip_start = (clip.left_offset or 0) / fps
            clip_dur = (clip.source_duration_frames or 0) / fps
        end

        local fingerprints = DuplicateDetector._extract_fingerprints(
            file_path, interval_frames, thumb_size, fps, clip_start, clip_dur
        )

        if #fingerprints > 0 then
            files_scanned = files_scanned + 1
            total_fps = total_fps + #fingerprints

            -- Pass 1: 块均值哈希精确匹配（快速）
            local ranges_bm = DuplicateDetector._find_dup_ranges(fingerprints, min_gap_sec, fps)
            -- Pass 2: 边缘哈希汉明距离匹配（调色免疫）
            local ranges_edge = DuplicateDetector._find_dup_ranges_edge(fingerprints, min_gap_sec, fps)
            -- Pass 3: 灰度结构哈希匹配（调色、亮度和轻微缩放容忍）
            local ranges_gray = DuplicateDetector._find_dup_ranges_gray(fingerprints, min_gap_sec, fps)

            -- 合并两次结果，去重
            local all_ranges = {}
            for _, r in ipairs(ranges_bm) do table.insert(all_ranges, r) end
            bm_hits = bm_hits + #ranges_bm

            -- 边缘哈希结果：检查是否与块均值结果重叠，去重
            for _, re in ipairs(ranges_edge) do
                local is_new = true
                for _, rb in ipairs(ranges_bm) do
                    if math.abs(re.start1 - rb.start1) < 0.5 and math.abs(re.start2 - rb.start2) < 0.5 then
                        is_new = false
                        break
                    end
                end
                if is_new then
                    table.insert(all_ranges, re)
                    edge_hits = edge_hits + 1
                end
            end
            for _, rg in ipairs(ranges_gray) do
                local is_new = true
                for _, existing in ipairs(all_ranges) do
                    if math.abs(rg.start1 - existing.start1) < 0.5 and math.abs(rg.start2 - existing.start2) < 0.5 then
                        is_new = false
                        break
                    end
                end
                if is_new then
                    table.insert(all_ranges, rg)
                    gray_hits = gray_hits + 1
                end
            end

            if #all_ranges > 0 then
                table.insert(all_dup_ranges, {
                    clip = clip,
                    file_path = file_path,
                    ranges = all_ranges,
                    fp_count = #fingerprints,
                })
            end
        end

        ::continue_clip::
    end

    -- 跨文件内容比对：收集所有文件的指纹，用边缘哈希做跨文件匹配
    local cross_file_pairs = {}
    do
        -- 收集所有指纹到全局池（按文件+clip分组）
        local global_fps = {}  -- {file_path, clip, sec, frame, edge_hash}[]
        for _, clip in ipairs(clips) do
            local file_path = clip.file_path
            if file_path then
                local clip_fps = get_clip_fps(clip)
                local fingerprints = DuplicateDetector._extract_fingerprints(
                    file_path, interval_frames, thumb_size, clip_fps,
                    clip.left_offset and clip.left_offset > 0 and (clip.left_offset / clip_fps) or nil,
                    clip.source_duration_frames and clip.source_duration_frames > 0 and (clip.source_duration_frames / clip_fps) or nil
                )
                if #fingerprints > 0 then
                    for _, fp in ipairs(fingerprints) do
                        table.insert(global_fps, {
                            file_path = file_path,
                            clip = clip,
                            sec = fp.sec,
                            frame = fp.frame,
                            edge_hash = fp.edge_hash,
                            gray_hash = fp.gray_hash,
                            gray_hashes = fp.gray_hashes,
                            bm_hash = fp.hash,
                        })
                    end
                end
            end
        end

        -- 用边缘哈希/灰度结构哈希前缀分桶做跨文件匹配
        local prefix_map = {}
        for i, fp in ipairs(global_fps) do
            local prefix = fp.edge_hash:sub(1, 4)
            if not prefix_map[prefix] then prefix_map[prefix] = {} end
            table.insert(prefix_map[prefix], i)
            if fp.gray_hash then
                local added = {}
                for _, gp in ipairs({ fp.gray_hash:sub(1, 4), fp.gray_hash:sub(17, 20), fp.gray_hash:sub(33, 36), fp.gray_hash:sub(49, 52) }) do
                    local key = "g:" .. gp
                    if gp ~= "" and not added[key] then
                        if not prefix_map[key] then prefix_map[key] = {} end
                        table.insert(prefix_map[key], i)
                        added[key] = true
                    end
                end
            end
        end

        local matched_pairs = {}  -- {idx1, idx2, dist}
        local seen_matched_pairs = {}
        for _, group in pairs(prefix_map) do
            if #group >= 2 then
                for a = 1, #group do
                    for b = a + 1, #group do
                        local i, j = group[a], group[b]
                        local fp_i, fp_j = global_fps[i], global_fps[j]
                        -- 跳过同一文件的指纹（已被per-file检测覆盖）
                        if fp_i.file_path ~= fp_j.file_path then
                            local key = tostring(math.min(i, j)) .. "_" .. tostring(math.max(i, j))
                            if not seen_matched_pairs[key] then
                                seen_matched_pairs[key] = true
                                local edge_dist = hamming_distance_hex(fp_i.edge_hash, fp_j.edge_hash)
                                local gray_dist = gray_hash_distance(fp_i, fp_j)
                                if edge_dist <= MAX_HAMMING or gray_dist <= MAX_GRAY_HAMMING then
                                    table.insert(matched_pairs, {i = i, j = j, dist = math.min(edge_dist, gray_dist)})
                                end
                            end
                        end
                    end
                end
            end
        end

        -- 将跨文件匹配按clip对分组。必须把 clip 与 sec 同步规范到同一方向，
        -- 否则同一组里 A/B 会交叉，后面的连续片段判断会失真。
        local pair_groups = {}  -- key = "clip1_idx|clip2_idx"
        for _, mp in ipairs(matched_pairs) do
            local fp_i = global_fps[mp.i]
            local fp_j = global_fps[mp.j]
            local ci = fp_i.clip
            local cj = fp_j.clip
            -- 用timeline_start_frame作clip标识
            local k1 = (ci.timeline_start_frame or 0) .. "|" .. (ci.file_path or "")
            local k2 = (cj.timeline_start_frame or 0) .. "|" .. (cj.file_path or "")
            local sec_a, sec_b = fp_i.sec, fp_j.sec
            if k1 > k2 then
                k1, k2 = k2, k1
                ci, cj = cj, ci
                sec_a, sec_b = sec_b, sec_a
            end
            local key = k1 .. "||" .. k2
            if not pair_groups[key] then
                pair_groups[key] = {clip_a = ci, clip_b = cj, matches = {}}
            end
            table.insert(pair_groups[key].matches, {
                sec_a = sec_a,
                sec_b = sec_b,
                dist = mp.dist,
            })
        end

        local function best_contiguous_cross_segment(matches)
            if #matches < 3 then return nil end
            table.sort(matches, function(a, b)
                if a.sec_a == b.sec_a then return a.sec_b < b.sec_b end
                return a.sec_a < b.sec_a
            end)

            local interval_sec = interval_frames / timeline_fps
            local max_step = interval_sec * 2.25 + 0.04
            local min_advance = interval_sec * 0.35
            local min_span = interval_sec * 1.5
            local best = nil
            local seg = nil

            local function finish_segment()
                if not seg or seg.count < 3 then return end
                local span_a = seg.end_a - seg.start_a
                local span_b = seg.end_b - seg.start_b
                local span = math.min(span_a, span_b)
                if span >= min_span and (not best or seg.count > best.count or (seg.count == best.count and span > best.span)) then
                    best = {
                        count = seg.count,
                        span = span,
                        start_a = seg.start_a,
                        end_a = seg.end_a,
                        start_b = seg.start_b,
                        end_b = seg.end_b,
                        best_dist = seg.best_dist,
                    }
                end
            end

            for _, m in ipairs(matches) do
                if not seg then
                    seg = {
                        start_a = m.sec_a, end_a = m.sec_a,
                        start_b = m.sec_b, end_b = m.sec_b,
                        count = 1,
                        best_dist = m.dist or 9999,
                    }
                else
                    local da = m.sec_a - seg.end_a
                    local db = m.sec_b - seg.end_b
                    local continuous = da >= min_advance and db >= min_advance and da <= max_step and db <= max_step and math.abs(da - db) <= max_step
                    if continuous then
                        seg.end_a = m.sec_a
                        seg.end_b = m.sec_b
                        seg.count = seg.count + 1
                        if (m.dist or 9999) < seg.best_dist then seg.best_dist = m.dist or 9999 end
                    else
                        finish_segment()
                        seg = {
                            start_a = m.sec_a, end_a = m.sec_a,
                            start_b = m.sec_b, end_b = m.sec_b,
                            count = 1,
                            best_dist = m.dist or 9999,
                        }
                    end
                end
            end
            finish_segment()
            return best
        end

        -- 跨文件内容重复必须是连续片段级命中，不能靠零散相似帧报错。
        for _, pg in pairs(pair_groups) do
            local dur_a = pg.clip_a.source_duration_frames or 0
            local dur_b = pg.clip_b.source_duration_frames or 0
            local min_clip_frames = math.min(dur_a, dur_b)
            local seg = best_contiguous_cross_segment(pg.matches)
            if seg and min_clip_frames >= interval_frames * 2 then
                table.insert(cross_file_pairs, {
                    clip_a = pg.clip_a,
                    clip_b = pg.clip_b,
                    match_count = seg.count,
                    match_span_sec = seg.span,
                    match_start_a = seg.start_a,
                    match_start_b = seg.start_b,
                    match_best_dist = seg.best_dist,
                    match_type = "content_cross",
                    reason = string.format("跨文件内容重复!\n%s\n≈\n%s\n连续命中 %.2fs / %d 个指纹点",
                        pg.clip_a.file_path and pg.clip_a.file_path:match("([^\\/]+)$") or "?",
                        pg.clip_b.file_path and pg.clip_b.file_path:match("([^\\/]+)$") or "?",
                        seg.span,
                        seg.count
                    ),
                })
            end
        end

        if #cross_file_pairs > 0 then
            dlog(string.format("detect_content: 跨文件匹配 %d 对", #cross_file_pairs))
        end
    end

    return {
        results = all_dup_ranges,
        cross_file_pairs = cross_file_pairs,
        summary = {
            files_scanned = files_scanned,
            total_fingerprints = total_fps,
            files_with_duplicates = #all_dup_ranges + #cross_file_pairs,
            cross_file_count = #cross_file_pairs,
            total_dup_ranges = 0,
            bm_hits = bm_hits,
            edge_hits = edge_hits,
            gray_hits = gray_hits,
        },
    }
end

-- 复杂模式：对渲染文件做帧指纹内容重复检测
-- render_path: 渲染的临时视频文件
-- io_in_frame: IO入点的绝对帧号（渲染帧0 = 时间线io_in_frame）
-- 返回格式与detect_content一致
function DuplicateDetector.detect_content_render(render_path, io_in_frame, timeline_fps, params)
    timeline_fps = timeline_fps or 25
    local interval = params.content_sample_interval or config.DUPLICATE.CONTENT_SAMPLE_INTERVAL
    local thumb_size = config.DUPLICATE.CONTENT_THUMB_SIZE
    local min_gap_sec = config.DUPLICATE.CONTENT_MIN_GAP_SEC

    local results = {
        summary = {
            files_scanned = 0,
            total_fingerprints = 0,
            files_with_duplicates = 0,
            total_dup_ranges = 0,
            bm_hits = 0,
            edge_hits = 0,
            gray_hits = 0,
        },
        results = {},
    }

    if not render_path then
        dlog("detect_content_render: 渲染路径为空")
        return results
    end
    local test_f = io.open(render_path, "r")
    if not test_f then
        dlog("detect_content_render: 渲染文件不存在: " .. tostring(render_path))
        return results
    end
    test_f:close()

    dlog(string.format("detect_content_render: path=%s io_in=%d fps=%.0f interval=%d",
        render_path, io_in_frame or 0, timeline_fps, interval))

    -- 提取整个渲染文件的指纹（无-ss/-to限制）
    local fingerprints = DuplicateDetector._extract_fingerprints(
        render_path, interval, thumb_size, timeline_fps, nil, nil
    )

    results.summary.total_fingerprints = #fingerprints
    dlog(string.format("detect_content_render: 提取到 %d 个指纹", #fingerprints))

    if #fingerprints < 2 then return results end

    -- 查找重复帧范围
    local ranges_bm = DuplicateDetector._find_dup_ranges(fingerprints, min_gap_sec, timeline_fps)
    local ranges_edge = DuplicateDetector._find_dup_ranges_edge(fingerprints, min_gap_sec, timeline_fps)
    local ranges_gray = DuplicateDetector._find_dup_ranges_gray(fingerprints, min_gap_sec, timeline_fps)
    results.summary.bm_hits = #ranges_bm
    results.summary.edge_hits = #ranges_edge
    results.summary.gray_hits = #ranges_gray

    -- 合并去重
    local all_ranges = {}
    local seen = {}
    for _, r in ipairs(ranges_bm) do
        local k = string.format("%d_%d", r.frame1_start, r.frame2_start)
        if not seen[k] then seen[k] = true; table.insert(all_ranges, r) end
    end
    for _, r in ipairs(ranges_edge) do
        local k = string.format("%d_%d", r.frame1_start, r.frame2_start)
        if not seen[k] then seen[k] = true; table.insert(all_ranges, r) end
    end
    for _, r in ipairs(ranges_gray) do
        local k = string.format("%d_%d", r.frame1_start, r.frame2_start)
        if not seen[k] then seen[k] = true; table.insert(all_ranges, r) end
    end

    if #all_ranges == 0 then return results end

    -- 映射回时间线帧号（渲染帧0 = io_in_frame）
    local io_offset = io_in_frame or 0
    local mapped_ranges = {}
    for _, r in ipairs(all_ranges) do
        -- fingerprints[r.frame1_start].sec 是渲染文件中的时间（秒）
        local fp1 = fingerprints[r.frame1_start]
        local fp2 = fingerprints[r.frame2_start]
        if fp1 and fp2 then
            local tl_frame1 = io_offset + math.floor(fp1.sec * timeline_fps + 0.5)
            local tl_frame2 = io_offset + math.floor(fp2.sec * timeline_fps + 0.5)
            table.insert(mapped_ranges, {
                frame1_start = tl_frame1,
                frame1_end = tl_frame1 + math.floor((r.end1 - r.start1) * timeline_fps + 0.5),
                frame2_start = tl_frame2,
                frame2_end = tl_frame2 + math.floor((r.end2 - r.start2) * timeline_fps + 0.5),
                start1 = fp1.sec,
                end1 = fp1.sec + (r.end1 - r.start1),
                start2 = fp2.sec,
                end2 = fp2.sec + (r.end2 - r.start2),
                count = tonumber(r.count or 0) or 0,
            })
        end
    end

    results.summary.files_scanned = 1
    results.summary.files_with_duplicates = #mapped_ranges
    results.summary.total_dup_ranges = #mapped_ranges
    -- 用虚拟clip承载渲染文件结果
    local dummy_clip = {
        timeline_start_frame = 0,
        file_path = render_path,
        name = "[复杂模式渲染]",
    }
    table.insert(results.results, {
        clip = dummy_clip,
        file_path = render_path,
        ranges = mapped_ranges,
        timeline_frames_absolute = true,
    })

    return results
end

-- 将内容重复结果转为标记记录
function DuplicateDetector.content_to_marker_records(content_results, timeline_fps)
    local Analyzer = require("black_frame_analyzer")
    local records = {}
    timeline_fps = timeline_fps or 25

    for _, file_result in ipairs(content_results.results) do
        local clip = file_result.clip
        local clip_start = tonumber(clip and clip.timeline_start_frame or 0) or 0
        if file_result.timeline_frames_absolute == true then
            clip_start = 0
        end

        for _, range in ipairs(file_result.ranges) do
            local frame1_start = tonumber(range.frame1_start)
            local frame1_end = tonumber(range.frame1_end)
            local frame2_start = tonumber(range.frame2_start)
            local frame2_end = tonumber(range.frame2_end)
            local count = tonumber(range.count or 0) or 0
            local min_same_file_frames = math.max(18, math.floor((timeline_fps or 25) * 0.5 + 0.5))
            if not frame1_start or not frame1_end or not frame2_start or not frame2_end then
                goto continue_range
            end
            if frame1_end <= frame1_start or frame2_end <= frame2_start then
                goto continue_range
            end
            if count < 3 then
                goto continue_range
            end
            if math.min(frame1_end - frame1_start, frame2_end - frame2_start) < min_same_file_frames then
                goto continue_range
            end

            -- 映射到时间线帧
            local tl_frame1_start = clip_start + frame1_start
            local tl_frame1_end = clip_start + frame1_end
            local tl_frame2_start = clip_start + frame2_start
            local tl_frame2_end = clip_start + frame2_end

            local dur_sec1 = range.end1 - range.start1
            local dur_sec2 = range.end2 - range.start2
            local gap_sec = range.start2 - range.start1
            if dur_sec1 <= 0 or dur_sec2 <= 0 then
                goto continue_range
            end

            local note = string.format(
                "内容重复!\n段1: 帧%d-%d (%.1fs)\n段2: 帧%d-%d (%.1fs)\n间距: %.1fs\n来源: %s",
                frame1_start, frame1_end, dur_sec1,
                frame2_start, frame2_end, dur_sec2,
                gap_sec,
                file_result.file_path and file_result.file_path:match("([^\\/]+)$") or "未知"
            )

            -- 段1标记
            table.insert(records, {
                classification = "content_dup",
                marker_color = config.MARKER_COLORS.CONTENT_DUP or "Fuchsia",
                marker_name = "[BFD-FP] 内容重复A",
                timeline_start_frame = tl_frame1_start,
                timeline_end_frame = tl_frame1_end,
                timeline_start_tc = Analyzer.frame_to_timecode(tl_frame1_start, timeline_fps),
                timeline_end_tc = Analyzer.frame_to_timecode(tl_frame1_end, timeline_fps),
                note = note,
                source_file = file_result.file_path,
                source_duration_sec = dur_sec1,
                duration_frames = frame1_end - frame1_start,
            })

            -- 段2标记
            table.insert(records, {
                classification = "content_dup",
                marker_color = config.MARKER_COLORS.CONTENT_DUP or "Fuchsia",
                marker_name = "[BFD-FP] 内容重复B",
                timeline_start_frame = tl_frame2_start,
                timeline_end_frame = tl_frame2_end,
                timeline_start_tc = Analyzer.frame_to_timecode(tl_frame2_start, timeline_fps),
                timeline_end_tc = Analyzer.frame_to_timecode(tl_frame2_end, timeline_fps),
                note = "此段与上方内容重复",
                source_file = file_result.file_path,
                source_duration_sec = dur_sec2,
                duration_frames = frame2_end - frame2_start,
            })
            ::continue_range::
        end
    end

    -- 计算总重复区间数
    content_results.summary.total_dup_ranges = #records / 2

    return records
end

-- 生成内容重复摘要
function DuplicateDetector.generate_content_summary(content_results)
    local s = content_results.summary or {}
    local lines = {}
    table.insert(lines, string.rep("-", 55))
    table.insert(lines, "  帧指纹内容重复检测（双哈希）")
    table.insert(lines, string.rep("-", 55))
    table.insert(lines, string.format("  扫描文件: %d 个 | 总指纹: %d 个", s.files_scanned, s.total_fingerprints))
    table.insert(lines, string.format("  块均值哈希命中: %d 处 | 边缘哈希补充命中: %d 处",
        s.bm_hits or 0, s.edge_hits or 0))
    table.insert(lines, string.format("  🟣 发现内容重复: %d 个文件, %d 处重复区间",
        tonumber(s.files_with_duplicates or 0) or 0,
        tonumber(s.total_dup_ranges or 0) or 0))
    return table.concat(lines, "\n")
end

return DuplicateDetector
