#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYSIDE_DIR = ROOT / "QingheBFD_v1.9.104_macOS" / "QingheBFD_Plugin_macOS" / "pyside_ui"
sys.path.insert(0, str(PYSIDE_DIR))

from resolve_bridge import ResolveBridge, progress_path, read_progress_file, runtime_dir, write_lua_params  # noqa: E402


def tail_new_log(log_path: Path, start_size: int, max_lines: int = 80) -> list[str]:
    if not log_path.exists():
        return []
    data = log_path.read_bytes()
    if start_size < len(data):
        data = data[start_size:]
    text = data.decode("utf-8", errors="replace")
    return text.splitlines()[-max_lines:]


def params_disabled(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return "enabled = false" in text or "enabled=false" in text


def marker_summary(progress: dict) -> dict:
    counts = progress.get("counts") or {}
    records = progress.get("records") or []
    return {
        "ok": True,
        "counts": counts,
        "records": len(records),
        "first_records": records[:5],
    }


def run_case(
    bridge: ResolveBridge,
    case: dict,
    timeline_index: int,
    timeline_name: str,
    fps: float,
    io_in: str,
    io_out: str,
    timeout: int,
) -> dict:
    log_path = Path.home() / "bfd_debug.log"
    log_start = log_path.stat().st_size if log_path.exists() else 0
    params_path = runtime_dir() / f"regression_{case['name']}.lua"
    prog_path = runtime_dir() / f"progress_{case['name']}.json"
    if prog_path.exists():
        prog_path.unlink()

    params = {
        "enabled": True,
        "submitted_at": int(time.time()),
        "headless": True,
        "timeline_index": timeline_index,
        "timeline_name": timeline_name,
        "timeline_fps": fps,
        "manual_io_in": io_in,
        "manual_io_out": io_out,
        "stuck_frames": 3,
        "suspect_frames": 12,
        "pix_th": 0.10,
        "min_duration": 1 / max(1.0, fps),
        "min_black_frames": 1,
        "clear_existing": True,
        "complex_mode": case.get("complex_mode", False),
        "merge_mode": case.get("merge_mode", True),
        "render_nested_segments": case.get("render_nested_segments", False),
        "detect_duplicate": case.get("detect_duplicate", True),
        "detect_content_dup": case.get("detect_content_dup", False),
        "detect_corrupt": case.get("detect_corrupt", False),
        "marker_types": {
            "error": case.get("error", True),
            "suspect": case.get("suspect", True),
            "scene": case.get("scene", False),
            "gap": case.get("gap", True),
            "opacity": case.get("opacity", True),
            "duplicate": case.get("duplicate", True),
            "content_dup": case.get("content_dup", False),
        },
        "mark_hidden_clips": False,
        "mark_partial_opacity": True,
        "png_as_opaque": True,
        "html_report": False,
        "progress_file": str(prog_path),
        "clip_snapshot_file": str(runtime_dir() / f"clip_snapshot_{case['name']}.lua"),
    }
    write_lua_params(params, params_path)

    bridge.clear_bfd_markers(timeline_index)
    started_at = time.time()
    ok, message = bridge.run_lua_entry_with_fuscript(params_path)
    if not ok:
        return {
            "case": case["name"],
            "ok": False,
            "message": message,
            "elapsed_sec": round(time.time() - started_at, 2),
            "log_tail": tail_new_log(log_path, log_start),
        }

    last_progress = {}
    while time.time() - started_at < timeout:
        last_progress = read_progress_file(prog_path) or {}
        if params_disabled(params_path):
            break
        if int(last_progress.get("percent") or 0) >= 100:
            break
        time.sleep(0.7)

    elapsed = round(time.time() - started_at, 2)
    log_tail = tail_new_log(log_path, log_start)
    markers = marker_summary(last_progress)
    counts = markers.get("counts") if markers.get("ok") else {}
    total = int((counts or {}).get("total") or markers.get("records") or 0)

    return {
        "case": case["name"],
        "ok": bool(params_disabled(params_path) and total >= case.get("min_total_markers", 1)),
        "message": message,
        "elapsed_sec": elapsed,
        "progress": last_progress,
        "markers": markers,
        "log_tail": log_tail,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Qinghe BFD detection regression matrix against the current Resolve project.")
    parser.add_argument("--timeline-index", type=int, default=0, help="Resolve timeline index, default=current timeline if discoverable.")
    parser.add_argument("--io-in", default="00:04:39:10", help="Manual IO in timecode.")
    parser.add_argument("--io-out", default="00:06:02:05", help="Manual IO out timecode.")
    parser.add_argument("--timeout", type=int, default=420, help="Timeout per case in seconds.")
    parser.add_argument("--json-out", type=Path, default=runtime_dir() / "detection_regression_report.json")
    args = parser.parse_args()

    bridge = ResolveBridge()
    timelines = bridge.list_timelines()
    if not timelines:
        print("未读取到 Resolve 时间线，请确认 DaVinci Resolve 已打开并加载项目。", file=sys.stderr)
        return 2

    timeline = None
    if args.timeline_index > 0:
        timeline = next((item for item in timelines if item.index == args.timeline_index), None)
    if timeline is None:
        timeline = next((item for item in timelines if "当前" in item.name), None) or timelines[0]

    cases = [
        {"name": "ordinary_merge", "merge_mode": True, "render_nested_segments": False, "complex_mode": False},
        {"name": "nested_render", "merge_mode": True, "render_nested_segments": True, "complex_mode": False},
        {"name": "complex_render", "merge_mode": True, "render_nested_segments": False, "complex_mode": True},
    ]

    print(f"目标时间线: {timeline.index}. {timeline.name} / {timeline.fps:g}fps", flush=True)
    print(f"IO范围: {args.io_in} - {args.io_out}", flush=True)
    results = []
    for case in cases:
        print(f"\n=== {case['name']} ===", flush=True)
        result = run_case(
            bridge,
            case,
            timeline.index,
            timeline.name.replace("  (当前)", ""),
            timeline.fps,
            args.io_in,
            args.io_out,
            args.timeout,
        )
        results.append(result)
        counts = ((result.get("markers") or {}).get("counts") or {})
        print(f"ok={result['ok']} elapsed={result['elapsed_sec']}s markers={counts}", flush=True)
        for line in result.get("log_tail", [])[-12:]:
            if "阶段6" in line or "阶段7" in line or "阶段10" in line or "复合" in line or "复杂模式" in line:
                print(line, flush=True)

    report = {
        "timeline": {"index": timeline.index, "name": timeline.name, "fps": timeline.fps},
        "io": {"in": args.io_in, "out": args.io_out},
        "results": results,
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告: {args.json_out}", flush=True)
    return 0 if all(item.get("ok") for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
