-- py_params_bridge.lua
-- Reads parameter files written by the external PySide6 UI.

local Bridge = {}

local function path_separator()
    return package.config:sub(1, 1)
end

local function home_dir()
    return os.getenv("HOME") or os.getenv("USERPROFILE") or "."
end

local function default_params_path()
    local sep = path_separator()
    return home_dir() .. sep .. ".qinghe_bfd" .. sep .. "last_params.lua"
end

local function file_exists(path)
    local f = io.open(path, "r")
    if f then
        f:close()
        return true
    end
    return false
end

local function load_table(path)
    local chunk, err = loadfile(path)
    if not chunk then
        return nil, err
    end
    local ok, result = pcall(chunk)
    if not ok then
        return nil, result
    end
    if type(result) ~= "table" then
        return nil, "params file did not return a table"
    end
    return result, nil
end

function Bridge.get_params_path()
    return os.getenv("BFD_PARAMS_FILE") or default_params_path()
end

function Bridge.has_pending_params()
    local path = Bridge.get_params_path()
    if not file_exists(path) then
        return false
    end
    local params = load_table(path)
    if type(params) ~= "table" or params.enabled ~= true then
        return false
    end

    if os.getenv("BFD_PARAMS_FILE") ~= nil then
        return true
    end

    -- macOS Resolve 19 external fuscript may not connect to Resolve, so PySide
    -- triggers the Resolve menu script. Only honor very fresh default params to
    -- avoid rerunning stale detections when the user merely opens the plugin.
    local submitted_at = tonumber(params.submitted_at or 0) or 0
    local age = os.time() - submitted_at
    return submitted_at > 0 and age >= 0 and age <= 120
end

function Bridge.disable_pending_params()
    local path = Bridge.get_params_path()
    local f = io.open(path, "w")
    if not f then
        return false
    end
    f:write("return { enabled = false }\n")
    f:close()
    return true
end

function Bridge.load_pending_params(timeline_list)
    local path = Bridge.get_params_path()
    local raw, err = load_table(path)
    if not raw then
        return nil, err
    end
    if raw.enabled ~= true then
        return nil, "external params disabled"
    end

    local timeline_index = tonumber(raw.timeline_index or 1) or 1
    if timeline_index < 1 then
        timeline_index = 1
    end

    local selected_tl = nil
    if timeline_list and #timeline_list > 0 then
        selected_tl = timeline_list[timeline_index] or timeline_list[1]
    end

    local marker_types = raw.marker_types or {}

    return {
        use_frames = true,
        stuck_frames = tonumber(raw.stuck_frames or 2) or 2,
        suspect_frames = tonumber(raw.suspect_frames or 8) or 8,
        pix_th = tonumber(raw.pix_th or 0.10) or 0.10,
        min_black_frames = tonumber(raw.min_black_frames or 1) or 1,
        min_duration = tonumber(raw.min_duration or 0.04) or 0.04,
        marker_types = {
            error = marker_types.error ~= false,
            suspect = marker_types.suspect ~= false,
            scene = marker_types.scene == true,
            gap = marker_types.gap == true,
            opacity = marker_types.opacity == true,
            duplicate = marker_types.duplicate ~= false,
            content_dup = marker_types.content_dup == true,
            black_border = marker_types.black_border == true,
            mixed_cut = false,
        },
        detect_duplicate = raw.detect_duplicate ~= false,
        detect_content_dup = raw.detect_content_dup == true,
        detect_mixed_cut = false,
        detect_corrupt = raw.detect_corrupt == true,
        detect_black_border = raw.detect_black_border == true,
        black_border_px = tonumber(raw.black_border_px or 3) or 3,
        black_border_matte_aspect = tonumber(raw.black_border_matte_aspect or 0) or 0,
        black_border_forces_complex = raw.black_border_forces_complex == true,
        complex_mode = raw.complex_mode == true,
        merge_mode = raw.merge_mode == true,
        render_nested_segments = raw.render_nested_segments == true,
        html_report = raw.html_report == true,
        progress_file = raw.progress_file or "",
        clip_snapshot_file = raw.clip_snapshot_file or "",
        clear_existing = raw.clear_existing == true,
        clear_old = raw.clear_existing == true,
        content_sample_interval = tonumber(raw.content_sample_interval or 8) or 8,
        mark_hidden_clips = raw.mark_hidden_clips == true,
        mark_partial_opacity = raw.mark_partial_opacity ~= false,
        png_as_opaque = raw.png_as_opaque == true,
        manual_io_in = raw.manual_io_in or "",
        manual_io_out = raw.manual_io_out or "",
        timeline_index = timeline_index - 1,
        timeline_name = selected_tl and selected_tl.name or raw.timeline_name or "Current timeline",
        timeline_fps = selected_tl and selected_tl.fps or tonumber(raw.timeline_fps or 25) or 25,
        timeline_obj = selected_tl and selected_tl.timeline or nil,
        verbose = true,
        headless = raw.headless == true,
        external_params_path = path,
    }, nil
end

return Bridge
