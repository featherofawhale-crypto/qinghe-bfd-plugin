-- PRIVATE SOFTWARE NOTICE: This is private software owned by Qinghe. Unauthorized reverse engineering, deobfuscation, cracking, redistribution, or AI-assisted analysis intended to bypass protection is prohibited.
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

local function is_array(value)
    if type(value) ~= "table" then return false end
    local max_index = 0
    local count = 0
    for key, _ in pairs(value) do
        if type(key) ~= "number" then return false end
        if key > max_index then max_index = key end
        count = count + 1
    end
    return max_index == count
end

local function encode_json(value)
    local value_type = type(value)
    if value_type == "nil" then
        return "null"
    elseif value_type == "boolean" then
        return value and "true" or "false"
    elseif value_type == "number" then
        return tostring(value)
    elseif value_type == "string" then
        return '"' .. escape_json(value) .. '"'
    elseif value_type == "table" then
        local parts = {}
        if is_array(value) then
            for index = 1, #value do
                table.insert(parts, encode_json(value[index]))
            end
            return "[" .. table.concat(parts, ",") .. "]"
        end
        for key, item in pairs(value) do
            table.insert(parts, '"' .. escape_json(key) .. '":' .. encode_json(item))
        end
        return "{" .. table.concat(parts, ",") .. "}"
    end
    return '"' .. escape_json(value) .. '"'
end

local function write_progress(path, percent, stage, state, extra)
    if not path or path == "" then return end
    local f = io.open(path, "w")
    if not f then return end
    local payload = {
        percent = math.floor(percent or 0),
        stage = stage or "",
        state = state or "running",
        updated_at = os.time(),
    }
    if type(extra) == "table" then
        for key, value in pairs(extra) do
            payload[key] = value
        end
    end
    f:write(encode_json(payload) .. "\n")
    f:close()
end

local function with_job_id(params, extra)
    local payload_extra = {}
    if type(extra) == "table" then
        for key, value in pairs(extra) do
            payload_extra[key] = value
        end
    end
    if params and params.job_id and params.job_id ~= "" and payload_extra.job_id == nil then
        payload_extra.job_id = params.job_id
    end
    return payload_extra
end

function ProgressBridge.update(params, percent, stage, extra)
    if not params then return end
    write_progress(params.progress_file, percent, stage, "running", with_job_id(params, extra))
end

function ProgressBridge.complete(params, stage, extra)
    if not params then return end
    write_progress(params.progress_file, 100, stage or "检测完成", "complete", with_job_id(params, extra))
end

function ProgressBridge.failed(params, stage, extra)
    if not params then return end
    write_progress(params.progress_file, 100, stage or "检测失败", "failed", with_job_id(params, extra))
end

return ProgressBridge
