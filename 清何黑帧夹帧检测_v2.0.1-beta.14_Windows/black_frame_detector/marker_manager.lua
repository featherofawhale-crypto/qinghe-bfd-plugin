-- marker_manager.lua - 达芬奇时间线标记管理
-- 负责在时间线上添加/删除/查询黑帧检测标记
-- v1.9.21: AddMarker使用显示帧号基准，需减去start_offset转换
-- 绝对帧号(GetStart) - 时间线起始偏移 = 显示帧号(AddMarker)

local config = require("config")

local MarkerManager = {}

-- ============================================================
-- 清除所有黑帧检测标记（按名称前缀匹配）
-- 支持 Timeline 和 TimelineItem 两种目标
-- ============================================================
function MarkerManager.clear_detection_markers(target, version_compat)
    -- 只删除本插件生成的标记（按名称前缀 [BFD] 匹配）
    -- 不使用 DeleteMarkersByColor，避免误删用户手动添加的同色标记
    local markers = version_compat:get_markers(target)
    local removed = 0
    for frame, marker in pairs(markers) do
        if type(marker) == "table" and marker.name then
            if marker.name:find("^%[BFD") then
                local ok = pcall(function() target:DeleteMarkerAtFrame(frame) end)
                if ok then removed = removed + 1 end
            end
        end
    end
    return removed
end

-- ============================================================
-- 在时间线上批量添加标记
-- records: {marker_color, marker_name, timeline_start_frame, timeline_end_frame, note, duration}
-- ============================================================
function MarkerManager.apply_markers(timeline, records, version_compat, progress_callback, start_offset)
    local added = 0
    local failed = 0
    local skipped = 0
    local total = #records

    local function marker_priority(record)
        if record and (record.is_mixed_cut or (record.segment and record.segment.is_mixed_cut)) then
            return 100
        end
        if record and (record.nested_short_scene or (record.segment and record.segment.nested_short_scene)) then
            return 100
        end
        local name = record and tostring(record.marker_name or "") or ""
        if name:find("%[BFD%-MIX%]") then return 100 end
        if name:find("%[BFD%-OVL%]") then return 80 end
        if record and record.classification == "error" then return 70 end
        if record and record.classification == "opacity" then return 60 end
        if record and record.classification == "gap" then return 50 end
        if record and record.classification == "duplicate" then return 30 end
        return 10
    end

    -- 按帧去重：达芬奇同一帧只能有一个标记；同帧时保留更具体的错误类型
    local seen_frames = {}
    local deduped_records = {}
    for _, record in ipairs(records) do
        local frame = (record.timeline_start_frame or 0) - (start_offset or 0)
        if frame < 0 then
            skipped = skipped + 1
            goto continue_dedup
        end
        local existing_index = seen_frames[frame]
        if not existing_index then
            deduped_records[#deduped_records + 1] = {record = record, frame = frame}
            seen_frames[frame] = #deduped_records
        elseif marker_priority(record) > marker_priority(deduped_records[existing_index].record) then
            deduped_records[existing_index] = {record = record, frame = frame}
            skipped = skipped + 1
        else
            skipped = skipped + 1
        end
        ::continue_dedup::
    end
    if skipped > 0 then
        print(string.format("[BFD] 标记去重: 跳过 %d 个同帧冲突标记", skipped))
    end

    for i, entry in ipairs(deduped_records) do
        local record = entry.record
        local frame = entry.frame
        local color = record.marker_color or config.MARKER_COLORS.ERROR
        local name = record.marker_name or "[BFD]"
        local note = record.note or ""
        -- 只有重复片段标记使用区间，其余保持单帧
        local is_dup = record.classification == "duplicate" or record.classification == "content_dup"
        local duration = 1
        if is_dup then
            local start_f = record.timeline_start_frame or 0
            local end_f = record.timeline_end_frame or start_f
            duration = math.max(1, end_f - start_f)
        end

        if i <= 5 then
            local dlog = function(msg)
                local f = io.open(config.get_debug_log_path(), "a")
                if f then f:write(os.date("%Y-%m-%d %H:%M:%S") .. " [MM] " .. msg .. "\n"); f:close() end
            end
            dlog(string.format("apply_marker[%d/%d]: frame=%d color=%s name=%s dur=%d",
                i, #deduped_records, frame, color, name, duration))
        end
        local custom_data = config.build_watermark_payload(record, frame, name)
        local ok = version_compat:safe_add_marker(
            timeline, frame, color, name, note, duration, custom_data
        )

        if ok then
            added = added + 1
        else
            failed = failed + 1
        end

        if progress_callback then
            progress_callback(i, #deduped_records, added, failed)
        end
    end

    return added, failed
end

-- ============================================================
-- 仅添加错误标记（红色，用于快速定位问题）
-- ============================================================
function MarkerManager.apply_error_markers(timeline, error_records, version_compat)
    return MarkerManager.apply_markers(timeline, error_records, version_compat)
end

-- ============================================================
-- 按类型选择性添加标记
-- ============================================================
function MarkerManager.apply_markers_by_type(timeline, analyzed_results, types, version_compat)
    local records = {}
    if types.error then
        for _, r in ipairs(analyzed_results.errors) do table.insert(records, r) end
    end
    if types.suspect then
        for _, r in ipairs(analyzed_results.suspects) do table.insert(records, r) end
    end
    if types.scene then
        for _, r in ipairs(analyzed_results.scenes) do table.insert(records, r) end
    end
    return MarkerManager.apply_markers(timeline, records, version_compat)
end

-- ============================================================
-- 导出标记列表为CSV字符串
-- ============================================================
function MarkerManager.export_to_csv(analyzed_results)
    local lines = {}
    table.insert(lines, "Frame,Timecode,Color,Type,Duration(s),Source")

    local all_records = {}
    for _, r in ipairs(analyzed_results.errors) do table.insert(all_records, r) end
    for _, r in ipairs(analyzed_results.suspects) do table.insert(all_records, r) end
    for _, r in ipairs(analyzed_results.scenes) do table.insert(all_records, r) end

    -- 按帧号排序
    table.sort(all_records, function(a, b)
        return (a.timeline_start_frame or 0) < (b.timeline_start_frame or 0)
    end)

    for _, r in ipairs(all_records) do
        local line = string.format(
            "%d,%s,%s,%s,%.4f,%s",
            r.timeline_start_frame,
            r.timeline_start_tc,
            r.marker_color,
            r.classification,
            r.source_duration_sec or 0,
            r.source_file or ""
        )
        table.insert(lines, line)
    end

    return table.concat(lines, "\n")
end

-- ============================================================
-- 获取检测标记统计
-- ============================================================
function MarkerManager.get_marker_stats(analyzed_results)
    return {
        total = #analyzed_results.errors + #analyzed_results.suspects + #analyzed_results.scenes,
        errors = #analyzed_results.errors,
        suspects = #analyzed_results.suspects,
        scenes = #analyzed_results.scenes,
    }
end

return MarkerManager
