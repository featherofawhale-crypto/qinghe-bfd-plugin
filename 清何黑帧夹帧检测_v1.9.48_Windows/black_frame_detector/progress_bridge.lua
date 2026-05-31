-- progress_bridge.lua
-- Writes coarse detection progress for the external PySide6 UI.

local ProgressBridge = {}

local function escape_json(value)
    value = tostring(value or "")
    value = value:gsub("\\", "\\\\")
    value = value:gsub('"', '\\"')
    value = value:gsub("\n", "\\n")
    value = value:gsub("\r", "\\r")
    return value
end

local function write_progress(path, percent, stage, state)
    if not path or path == "" then return end
    local f = io.open(path, "w")
    if not f then return end
    f:write(string.format(
        '{"percent":%d,"stage":"%s","state":"%s","updated_at":%d}\n',
        math.floor(percent or 0),
        escape_json(stage),
        escape_json(state or "running"),
        os.time()
    ))
    f:close()
end

function ProgressBridge.update(params, percent, stage)
    if not params then return end
    write_progress(params.progress_file, percent, stage, "running")
end

function ProgressBridge.complete(params, stage)
    if not params then return end
    write_progress(params.progress_file, 100, stage or "检测完成", "complete")
end

function ProgressBridge.failed(params, stage)
    if not params then return end
    write_progress(params.progress_file, 100, stage or "检测失败", "failed")
end

return ProgressBridge
