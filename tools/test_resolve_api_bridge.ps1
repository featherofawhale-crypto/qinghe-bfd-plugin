param(
    [switch]$Full,
    [switch]$MutateTempMarker
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$PySideDir = Join-Path $Root "pyside_ui"

function Resolve-PythonCommand {
    $bundledPython = Join-Path $PySideDir "python_runtime\python.exe"
    if (Test-Path $bundledPython) {
        return @{
            Exe = $bundledPython
            Args = @("-I", "-S")
            Label = $bundledPython
        }
    }

    if ($env:QINGHE_PYTHON) {
        if (!(Test-Path $env:QINGHE_PYTHON)) {
            throw "QINGHE_PYTHON points to a missing file: $env:QINGHE_PYTHON"
        }
        return @{
            Exe = $env:QINGHE_PYTHON
            Args = @()
            Label = $env:QINGHE_PYTHON
        }
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{
            Exe = $py.Source
            Args = @("-3")
            Label = "py -3"
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{
            Exe = $python.Source
            Args = @()
            Label = $python.Source
        }
    }

    throw "Python was not found. Install Python or set QINGHE_PYTHON to python.exe."
}

$python = Resolve-PythonCommand
if (!(Test-Path (Join-Path $PySideDir "resolve_bridge.py"))) {
    throw "Missing resolve_bridge.py in test root: $PySideDir"
}
$mode = if ($MutateTempMarker) { "mutate-temp-marker" } else { "readonly" }
$code = @'
import json
import os
import sys
from pathlib import Path

root = Path(os.environ["QINGHE_BFD_ROOT"])
sys.path.insert(0, str(root / "pyside_ui"))

from resolve_bridge import ResolveBridge

bridge = ResolveBridge()
result = {
    "ok": True,
    "mode": os.environ.get("QINGHE_BFD_SMOKE_MODE", "readonly"),
    "full": os.environ.get("QINGHE_BFD_SMOKE_FULL") == "1",
    "checks": {},
}

mode = result["mode"]
full = bool(result["full"])

timelines = bridge.list_timelines()
result["checks"]["timeline_count"] = len(timelines)
result["checks"]["timelines"] = [timeline.__dict__ for timeline in timelines[:10]]
if not timelines:
    result["ok"] = False
    result["error"] = "Resolve API returned no timelines."
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1)

current = next((timeline for timeline in timelines if "(当前)" in timeline.name or "(current)" in timeline.name.lower()), timelines[0])
result["checks"]["selected_timeline"] = current.__dict__

marks = bridge.current_timeline_marks(current.index)
result["checks"]["io_marks"] = marks
if not marks.get("ok"):
    result["ok"] = False
    result["error"] = "Resolve API did not return timeline IO marks. Set an In/Out range in Resolve and rerun."
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(2)

records = bridge.bfd_marker_records(current.index)
result["checks"]["bfd_marker_records"] = {
    "ok": records.get("ok"),
    "record_count": len(records.get("records") or []),
    "message": records.get("message", ""),
}
if not records.get("ok"):
    result["ok"] = False
    result["error"] = "BFD marker refresh bridge failed."
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(3)

if full:
    result["checks"]["resolve_version"] = bridge.resolve_version_string()

    clip_snapshot = bridge.current_timeline_clip_snapshot(current.index)
    result["checks"]["clip_snapshot"] = {
        "ok": clip_snapshot.get("ok"),
        "count": clip_snapshot.get("count", len(clip_snapshot.get("clips") or [])),
        "message": clip_snapshot.get("message", ""),
    }
    if not clip_snapshot.get("ok"):
        result["ok"] = False
        result["error"] = "Timeline clip snapshot failed."
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(4)

    risk = bridge.detect_complex_timeline_risk(current.index)
    result["checks"]["complex_timeline_risk"] = {
        "ok": risk.get("ok"),
        "count": risk.get("count", 0),
        "message": risk.get("message", ""),
    }
    if not risk.get("ok"):
        result["ok"] = False
        result["error"] = "Complex timeline risk scan failed."
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(5)

    audio = bridge.scan_mono_audio(current.index)
    result["checks"]["audio_scan"] = {
        "ok": audio.get("ok"),
        "count": audio.get("count", 0),
        "message": audio.get("message", ""),
    }
    if not audio.get("ok"):
        result["ok"] = False
        result["error"] = "Audio scan failed."
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(6)

    media_pool = bridge.probe_media_pool_api(current.index)
    result["checks"]["media_pool_probe"] = {
        "ok": media_pool.get("ok"),
        "message": media_pool.get("message", ""),
    }
    if not media_pool.get("ok"):
        result["ok"] = False
        result["error"] = "Media pool probe failed."
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(7)

    templates = bridge.list_caption_templates(current.index)
    result["checks"]["caption_templates"] = {
        "ok": templates.get("ok"),
        "count": len(templates.get("templates") or []),
        "message": templates.get("message", ""),
    }
    if not templates.get("ok"):
        result["ok"] = False
        result["error"] = "Caption template listing failed."
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(8)

    font_scan = bridge.scan_font_items(current.index)
    result["checks"]["font_scan"] = {
        "ok": font_scan.get("ok"),
        "count": len(font_scan.get("items") or []),
        "message": font_scan.get("message", ""),
    }
    if not font_scan.get("ok"):
        result["ok"] = False
        result["error"] = "Font panel scan failed."
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(11)

    font_check = bridge.check_font_available(current.index, "Arial", ["Arial", "Arial Regular"])
    result["checks"]["font_fusion_check"] = {
        "ok": font_check.get("ok"),
        "message": font_check.get("message", ""),
        "accepted_font": font_check.get("accepted_font", ""),
    }
    if not font_check.get("ok"):
        result["ok"] = False
        result["error"] = "Fusion font availability check failed for Arial."
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(12)

    data_dir = root / "pyside_ui" / "data"
    style_library = data_dir / "font_style_library.json"
    probe_rules = data_dir / "font_probe_rules.json"
    try:
        style_payload = json.loads(style_library.read_text(encoding="utf-8"))
        probe_payload = json.loads(probe_rules.read_text(encoding="utf-8"))
    except Exception as exc:
        result["ok"] = False
        result["checks"]["font_style_library_files"] = {"ok": False, "message": str(exc)}
        result["error"] = "Font style library JSON files failed to load."
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(13)
    result["checks"]["font_style_library_files"] = {
        "ok": isinstance(style_payload, list) and isinstance(probe_payload, dict),
        "style_count": len(style_payload) if isinstance(style_payload, list) else -1,
        "probe_rule_keys": sorted(list(probe_payload.keys()))[:12] if isinstance(probe_payload, dict) else [],
    }
    if not result["checks"]["font_style_library_files"]["ok"]:
        result["ok"] = False
        result["error"] = "Font style library JSON shape is invalid."
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(14)

    ffmpeg_path = bridge._find_ffmpeg_binary()
    ffprobe_path = bridge._find_ffprobe_binary()
    result["checks"]["bundled_media_tools"] = {
        "ok": bool(ffmpeg_path) and bool(ffprobe_path),
        "ffmpeg": ffmpeg_path,
        "ffprobe": ffprobe_path,
    }
    if not result["checks"]["bundled_media_tools"]["ok"]:
        result["ok"] = False
        result["error"] = "Bundled ffmpeg/ffprobe lookup failed."
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(15)

    bpm = bridge.estimate_selected_audio_bpm(current.index)
    result["checks"]["audio_bpm_probe"] = {
        "ok": bpm.get("ok"),
        "needs_selection": bpm.get("needs_selection", False),
        "method": bpm.get("method", ""),
        "bpm": bpm.get("bpm", ""),
        "message": bpm.get("message", ""),
        "clip": {
            "name": (bpm.get("clip") or {}).get("name", "") if isinstance(bpm.get("clip"), dict) else "",
            "path": (bpm.get("clip") or {}).get("path", "") if isinstance(bpm.get("clip"), dict) else "",
            "source": (bpm.get("clip") or {}).get("source", "") if isinstance(bpm.get("clip"), dict) else "",
        },
    }
    if not bpm.get("ok") and not bpm.get("needs_selection"):
        result["ok"] = False
        result["error"] = "Audio BPM probe failed without an actionable selection request."
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(16)

if mode == "mutate-temp-marker":
    add_result = bridge._run_resolve_python(
        r'''
import json
resolve = dvr_script.scriptapp("Resolve")
pm = resolve.GetProjectManager() if resolve else None
project = pm.GetCurrentProject() if pm else None
timeline = project.GetCurrentTimeline() if project else None
if not timeline:
    print(json.dumps({"ok": False, "message": "No current timeline."}, ensure_ascii=False))
    raise SystemExit(0)
try:
    start = int(float(timeline.GetStartFrame() or 0))
except Exception:
    start = 0
frame = start + 7
custom_data = "BFD_SMOKE_TEST_ONLY_DELETE_ME"
ok = bool(timeline.AddMarker(frame, "Blue", "[BFD-TEST] API smoke temporary", "BFD smoke test marker; safe to delete", 1, custom_data))
print(json.dumps({"ok": ok, "frame": frame}, ensure_ascii=False))
''',
        timeout=10,
    ) or {}
    result["checks"]["add_test_marker"] = add_result
    if not add_result.get("ok"):
        result["ok"] = False
        result["error"] = "Could not add temporary marker for clear-marker test."
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(9)
    delete_result = bridge._run_resolve_python(
        r'''
import json
resolve = dvr_script.scriptapp("Resolve")
pm = resolve.GetProjectManager() if resolve else None
project = pm.GetCurrentProject() if pm else None
timeline = project.GetCurrentTimeline() if project else None
if not timeline:
    print(json.dumps({"ok": False, "message": "No current timeline."}, ensure_ascii=False))
    raise SystemExit(0)
target_custom_data = "BFD_SMOKE_TEST_ONLY_DELETE_ME"
markers = timeline.GetMarkers() or {}
matched = 0
removed = 0
for frame, marker in list(markers.items()):
    custom_data = str(marker.get("customData", "")) if isinstance(marker, dict) else ""
    name = str(marker.get("name", "")) if isinstance(marker, dict) else ""
    if custom_data == target_custom_data or name == "[BFD-TEST] API smoke temporary":
        matched += 1
        if timeline.DeleteMarkerAtFrame(frame):
            removed += 1
print(json.dumps({"ok": matched > 0 and removed == matched, "matched": matched, "removed": removed}, ensure_ascii=False))
''',
        timeout=10,
    ) or {}
    result["checks"]["temp_marker_delete"] = delete_result
    if not delete_result.get("ok"):
        result["ok"] = False
        result["error"] = "Temporary marker delete API test failed."
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(10)

print(json.dumps(result, ensure_ascii=False, indent=2))
'@

$env:QINGHE_BFD_ROOT = $Root
$env:QINGHE_BFD_SMOKE_MODE = $mode
$env:QINGHE_BFD_SMOKE_FULL = if ($Full) { "1" } else { "0" }
$tempScript = [System.IO.Path]::ChangeExtension([System.IO.Path]::GetTempFileName(), ".py")
try {
    [System.IO.File]::WriteAllText($tempScript, $code, (New-Object System.Text.UTF8Encoding $false))
    & $python.Exe @($python.Args) $tempScript
    if ($LASTEXITCODE -ne 0) {
        throw "Resolve API bridge smoke test failed with exit code $LASTEXITCODE"
    }
} finally {
    if (Test-Path $tempScript) {
        Remove-Item -LiteralPath $tempScript -Force
    }
}
