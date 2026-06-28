-- PRIVATE SOFTWARE NOTICE: This is private software owned by Qinghe. Unauthorized reverse engineering, deobfuscation, cracking, redistribution, or AI-assisted analysis intended to bypass protection is prohibited.
-- report_generator.lua - 检测报告生成器（TXT/HTML）

local config = require("config")

local ReportGenerator = {}

-- ============================================================
-- 生成 TXT 报告
-- ============================================================
function ReportGenerator.generate_txt(analyzed_results, timeline_name, params, extra_info)
    local lines = {}

    -- 报告头
    table.insert(lines, string.rep("=", 60))
    table.insert(lines, "   黑帧夹帧检测报告")
    table.insert(lines, string.rep("=", 60))
    table.insert(lines, "时间线: " .. (timeline_name or "未知"))
    table.insert(lines, "检测时间: " .. os.date("%Y-%m-%d %H:%M:%S"))
    table.insert(lines, "插件版本: v" .. config.PLUGIN_VERSION)
    table.insert(lines, "watermark: " .. config.get_watermark_label())

    -- 版本信息
    if extra_info and extra_info.resolve_info then
        table.insert(lines, "Resolve版本: " .. extra_info.resolve_info)
    end

    -- 检测参数
    table.insert(lines, string.rep("-", 60))
    table.insert(lines, "检测参数:")
    if params then
        table.insert(lines, string.format("  最小黑帧时长: d=%.4fs", params.min_duration or config.FFMPEG.MIN_BLACK_DURATION))
        table.insert(lines, string.format("  像素阈值:     pix_th=%.4f", params.pix_th or config.FFMPEG.PIXEL_THRESHOLD))
        if params.use_frames then
            table.insert(lines, string.format("  夹帧判定:     ≤%d帧 (红色标记)",
                params.stuck_frames or config.CLASSIFICATION.STUCK_FRAMES))
            table.insert(lines, string.format("  可疑判定:     ≤%d帧 (黄色标记)",
                params.suspect_frames or config.CLASSIFICATION.SUSPECT_FRAMES))
            table.insert(lines, "  大于以上:     蓝色标记（场景转场）")
        else
            table.insert(lines, string.format("  夹帧判定:     ≤%.3fs", params.stuck_threshold or config.CLASSIFICATION.STUCK_FRAME_THRESHOLD))
            table.insert(lines, string.format("  可疑判定:     ≤%.3fs", params.suspect_threshold or config.CLASSIFICATION.SUSPECT_THRESHOLD))
        end
    end

    -- 摘要
    table.insert(lines, string.rep("-", 60))
    table.insert(lines, "检测摘要:")
    local s = analyzed_results.summary
    table.insert(lines, string.format("  总检测点:     %d", s.total_segments))
    table.insert(lines, string.format("  夹帧错误:     %d 处 (红色标记)", s.error_count))
    table.insert(lines, string.format("  可疑黑帧:     %d 处 (黄色标记)", s.suspect_count))
    table.insert(lines, string.format("  场景转场:     %d 处 (蓝色标记)", s.scene_count))
    if (s.gap_count or 0) > 0 then
        table.insert(lines, string.format("  时间线空位:   %d 处 (紫色标记 - 片段间隙)", s.gap_count))
    end
    if s.ignored_count > 0 then
        table.insert(lines, string.format("  已忽略:       %d 处 (纯黑素材)", s.ignored_count))
    end
    table.insert(lines, string.format("  扫描片段数:   %d", s.total_clips))

    -- 详细结果 - 夹帧错误
    if #analyzed_results.errors > 0 then
        table.insert(lines, string.rep("=", 60))
        table.insert(lines, "🔴 夹帧错误 (" .. #analyzed_results.errors .. " 处)")
        table.insert(lines, string.rep("=", 60))
        local idx = 1
        for _, r in ipairs(analyzed_results.errors) do
            table.insert(lines, string.format(
                "\n[错误 #%d] 位置: %s (帧 %d)",
                idx, r.timeline_start_tc, r.timeline_start_frame
            ))
            table.insert(lines, string.format("  黑帧持续: %.3fs", r.source_duration_sec))
            table.insert(lines, string.format("  来源: %s", r.source_file or "未知"))
            table.insert(lines, string.format("  片段内: %.3fs - %.3fs", r.source_start_sec, r.source_start_sec + r.source_duration_sec))
            idx = idx + 1
        end
    end

    -- 详细结果 - 可疑黑帧
    if #analyzed_results.suspects > 0 then
        table.insert(lines, string.rep("=", 60))
        table.insert(lines, "🟡 可疑黑帧 (" .. #analyzed_results.suspects .. " 处)")
        table.insert(lines, string.rep("=", 60))
        local idx = 1
        for _, r in ipairs(analyzed_results.suspects) do
            table.insert(lines, string.format(
                "\n[可疑 #%d] 位置: %s (帧 %d)",
                idx, r.timeline_start_tc, r.timeline_start_frame
            ))
            table.insert(lines, string.format("  黑帧持续: %.3fs", r.source_duration_sec))
            table.insert(lines, string.format("  来源: %s", r.source_file or "未知"))
            idx = idx + 1
        end
    end

    -- 详细结果 - 场景转场（仅报告数量，不列出每一个）
    if #analyzed_results.scenes > 0 then
        table.insert(lines, string.rep("=", 60))
        table.insert(lines, string.format("🔵 正常场景转场: %d 处（蓝色标记）", #analyzed_results.scenes))
        table.insert(lines, string.rep("=", 60))
    end

    -- 详细结果 - 时间线空位
    if analyzed_results.gaps and #analyzed_results.gaps > 0 then
        table.insert(lines, string.rep("=", 60))
        table.insert(lines, "🟣 时间线空位 (" .. #analyzed_results.gaps .. " 处)")
        table.insert(lines, "说明: 这些黑帧位于片段间隙，不是素材内的夹帧")
        table.insert(lines, string.rep("=", 60))
        local idx = 1
        for _, r in ipairs(analyzed_results.gaps) do
            table.insert(lines, string.format(
                "\n[空位 #%d] 位置: %s (帧 %d)",
                idx, r.timeline_start_tc, r.timeline_start_frame
            ))
            table.insert(lines, string.format("  黑帧持续: %.1f帧", r.duration_frames or 0))
            idx = idx + 1
        end
    end

    -- 页脚
    table.insert(lines, "")
    table.insert(lines, string.rep("=", 60))
    table.insert(lines, "报告生成完毕。时间线上的标记颜色说明：")
    table.insert(lines, "  🔴 红色 = 夹帧错误（素材内异常黑帧）")
    table.insert(lines, "  🟡 黄色 = 可疑黑帧（建议人工确认）")
    table.insert(lines, "  🔵 蓝色 = 场景转场（正常）")
    table.insert(lines, "  🟣 紫色 = 时间线空位（片段间隙，非素材问题）")
    table.insert(lines, string.rep("=", 60))

    return table.concat(lines, "\n")
end

-- ============================================================
-- 生成 HTML 报告
-- ============================================================
function ReportGenerator.generate_html(analyzed_results, timeline_name, params, extra_info)
    local s = analyzed_results.summary
    local html = {}

    table.insert(html, [[<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>黑帧夹帧检测报告 - ]] .. (timeline_name or "未命名") .. [[</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         max-width: 900px; margin: 40px auto; padding: 20px; color: #333; background: #fafafa; }
  h1 { color: #1a1a1a; border-bottom: 3px solid #e0e0e0; padding-bottom: 10px; }
  h2 { color: #444; margin-top: 30px; }
  .summary { display: flex; gap: 20px; flex-wrap: wrap; margin: 20px 0; }
  .stat-card { background: white; border-radius: 8px; padding: 16px 24px;
               box-shadow: 0 1px 3px rgba(0,0,0,0.1); min-width: 120px; text-align: center; }
  .stat-card .count { font-size: 32px; font-weight: bold; }
  .stat-card .label { color: #666; font-size: 14px; margin-top: 4px; }
  .stat-card.error .count { color: #d32f2f; }
  .stat-card.suspect .count { color: #f57c00; }
  .stat-card.scene .count { color: #1976d2; }
  table { width: 100%; border-collapse: collapse; margin: 16px 0;
          background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden; }
  th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; }
  th { background: #f5f5f5; font-weight: 600; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; color: white; }
  .badge-error { background: #d32f2f; }
  .badge-suspect { background: #f57c00; }
  .badge-scene { background: #1976d2; }
  .params { background: white; padding: 16px; border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1); font-family: monospace; font-size: 14px; }
  .footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #e0e0e0; color: #999; font-size: 13px; }
</style>
</head>
<body>
]])

    -- 标题
    table.insert(html, "<h1>黑帧夹帧检测报告</h1>")
    table.insert(html, "<p>时间线: <strong>" .. (timeline_name or "未知") .. "</strong></p>")
    table.insert(html, "<p>检测时间: " .. os.date("%Y-%m-%d %H:%M:%S") .. "</p>")
    table.insert(html, "<p style='color:#999;font-size:12px;'>watermark: " .. config.get_watermark_label() .. "</p>")

    -- 参数
    if params then
        table.insert(html, "<h2>检测参数</h2>")
        table.insert(html, "<div class='params'>")
        table.insert(html, string.format("min_duration=%.4f | pix_th=%.4f",
            params.min_duration or config.FFMPEG.MIN_BLACK_DURATION,
            params.pix_th or config.FFMPEG.PIXEL_THRESHOLD))
        if params.use_frames then
            table.insert(html, string.format("<br>夹帧≤%d帧 | 可疑≤%d帧 | 空位检测: 已启用",
                params.stuck_frames or config.CLASSIFICATION.STUCK_FRAMES,
                params.suspect_frames or config.CLASSIFICATION.SUSPECT_FRAMES))
        end
        table.insert(html, "</div>")
    end

    -- 摘要统计卡片
    table.insert(html, "<h2>检测摘要</h2>")
    table.insert(html, "<div class='summary'>")
    table.insert(html, string.format("<div class='stat-card error'><div class='count'>%d</div><div class='label'>🔴 夹帧错误</div></div>", s.error_count))
    table.insert(html, string.format("<div class='stat-card suspect'><div class='count'>%d</div><div class='label'>🟡 可疑黑帧</div></div>", s.suspect_count))
    table.insert(html, string.format("<div class='stat-card scene'><div class='count'>%d</div><div class='label'>🔵 场景转场</div></div>", s.scene_count))
    if (s.gap_count or 0) > 0 then
        table.insert(html, string.format("<div class='stat-card' style='border-left: 3px solid #9c27b0;'><div class='count' style='color:#9c27b0;'>%d</div><div class='label'>🟣 时间线空位</div></div>", s.gap_count))
    end
    table.insert(html, string.format("<div class='stat-card'><div class='count'>%d</div><div class='label'>总检测点</div></div>", s.total_segments))
    table.insert(html, "</div>")

    -- 夹帧错误表格
    if #analyzed_results.errors > 0 then
        table.insert(html, "<h2>🔴 夹帧错误 (" .. #analyzed_results.errors .. " 处)</h2>")
        table.insert(html, "<table><tr><th>#</th><th>时间线位置</th><th>帧号</th><th>持续时长</th><th>来源</th></tr>")
        for idx, r in ipairs(analyzed_results.errors) do
            local filename = r.source_file and r.source_file:match("([^\\/]+)$") or "未知"
            table.insert(html, string.format(
                "<tr><td>%d</td><td><span class='badge badge-error'>错误</span> %s</td><td>%d</td><td>%.3fs</td><td>%s</td></tr>",
                idx, r.timeline_start_tc, r.timeline_start_frame, r.source_duration_sec, filename
            ))
        end
        table.insert(html, "</table>")
    end

    -- 可疑黑帧表格
    if #analyzed_results.suspects > 0 then
        table.insert(html, "<h2>🟡 可疑黑帧 (" .. #analyzed_results.suspects .. " 处)</h2>")
        table.insert(html, "<table><tr><th>#</th><th>时间线位置</th><th>帧号</th><th>持续时长</th><th>来源</th></tr>")
        for idx, r in ipairs(analyzed_results.suspects) do
            local filename = r.source_file and r.source_file:match("([^\\/]+)$") or "未知"
            table.insert(html, string.format(
                "<tr><td>%d</td><td><span class='badge badge-suspect'>可疑</span> %s</td><td>%d</td><td>%.3fs</td><td>%s</td></tr>",
                idx, r.timeline_start_tc, r.timeline_start_frame, r.source_duration_sec, filename
            ))
        end
        table.insert(html, "</table>")
    end

    -- 场景转场
    if #analyzed_results.scenes > 0 then
        table.insert(html, string.format("<h2>🔵 场景转场 (%d 处)</h2>", #analyzed_results.scenes))
        table.insert(html, "<p>正常场景转场已在时间线上用蓝色标记标注。</p>")
    end

    -- 时间线空位表格
    if analyzed_results.gaps and #analyzed_results.gaps > 0 then
        table.insert(html, "<h2>🟣 时间线空位 (" .. #analyzed_results.gaps .. " 处)</h2>")
        table.insert(html, "<p style='color:#9c27b0;'>以下黑帧位于片段间隙，不是素材内的夹帧错误。</p>")
        table.insert(html, "<table><tr><th>#</th><th>时间线位置</th><th>帧号</th><th>持续</th></tr>")
        for idx, r in ipairs(analyzed_results.gaps) do
            table.insert(html, string.format(
                "<tr><td>%d</td><td><span class='badge' style='background:#9c27b0;'>空位</span> %s</td><td>%d</td><td>%.1f帧</td></tr>",
                idx, r.timeline_start_tc, r.timeline_start_frame, r.duration_frames or 0
            ))
        end
        table.insert(html, "</table>")
    end

    -- 页脚
    table.insert(html, "<div class='footer'>")
    table.insert(html, "黑帧夹帧检测插件 v" .. config.PLUGIN_VERSION .. " | watermark: " .. config.get_watermark_label())
    table.insert(html, "</div>")
    table.insert(html, "</body></html>")

    return table.concat(html, "\n")
end

-- ============================================================
-- 保存报告到文件
-- ============================================================
function ReportGenerator.save_report(content, file_path)
    local f, err = io.open(file_path, "w")
    if not f then
        return false, err
    end
    f:write(content)
    f:close()
    return true, nil
end

-- ============================================================
-- 生成并保存完整报告
-- ============================================================
function ReportGenerator.generate_and_save(analyzed_results, timeline_name, params, extra_info)
    local desktop = config.get_desktop_path()
    local safe_name = (timeline_name or "未命名"):gsub("[\\/:*?\"<>|]", "_")
    local date_str = os.date("%Y%m%d_%H%M%S")
    local base_name = "黑帧检测报告_" .. safe_name .. "_" .. date_str

    local results = {}

    -- TXT报告
    local txt_content = ReportGenerator.generate_txt(analyzed_results, timeline_name, params, extra_info)
    local txt_path = desktop .. "/" .. base_name .. ".txt"
    local ok, err = ReportGenerator.save_report(txt_content, txt_path)
    if ok then
        results.txt = txt_path
    else
        results.txt_error = err
    end

    -- HTML报告（可选）
    if params and params.html_report then
        local html_content = ReportGenerator.generate_html(analyzed_results, timeline_name, params, extra_info)
        local html_path = desktop .. "/" .. base_name .. ".html"
        ok, err = ReportGenerator.save_report(html_content, html_path)
        if ok then
            results.html = html_path
        else
            results.html_error = err
        end
    end

    return results
end

return ReportGenerator
