#!/usr/bin/env python3
"""Read-only Resolve timeline probe for retimed clips.

This script does not mutate the project. It inspects the current timeline and
records which timeline-item properties Resolve exposes for speed changes, so we
can verify whether normal black/stuck-frame detection may mis-map source time.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SCRIPT_API = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
DEFAULT_SCRIPT_LIB = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"


def setup_resolve_env() -> None:
    script_api = os.environ.setdefault("RESOLVE_SCRIPT_API", DEFAULT_SCRIPT_API)
    os.environ.setdefault("RESOLVE_SCRIPT_LIB", DEFAULT_SCRIPT_LIB)
    modules = os.path.join(script_api, "Modules")
    if modules not in sys.path:
        sys.path.insert(0, modules)


def safe(call, default: Any = None) -> Any:
    try:
        return call()
    except Exception:
        return default


def resolve_app() -> Any:
    setup_resolve_env()
    import DaVinciResolveScript as dvr  # type: ignore

    return dvr.scriptapp("Resolve")


def scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [scalar(item) for item in value]
    if isinstance(value, dict):
        return {str(k): scalar(v) for k, v in value.items()}
    return str(value)


def interesting_properties(props: dict[str, Any]) -> dict[str, Any]:
    needles = (
        "speed",
        "retime",
        "motion",
        "frame",
        "duration",
        "start",
        "end",
        "offset",
        "source",
        "clip",
    )
    found: dict[str, Any] = {}
    for key, value in sorted(props.items(), key=lambda item: str(item[0]).lower()):
        text = str(key).lower()
        if any(needle in text for needle in needles):
            found[str(key)] = scalar(value)
    return found


def retime_risk_checks(row: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    duration = row.get("duration")
    left_offset = row.get("left_offset")
    right_offset = row.get("right_offset")
    source_start = row.get("source_start_frame")
    source_end = row.get("source_end_frame")
    props = row.get("interesting_properties") or {}

    def number(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except Exception:
            return None

    duration_n = number(duration)
    left_n = number(left_offset)
    right_n = number(right_offset)
    if duration_n is not None and left_n is not None and right_n is not None:
        offset_span = right_n - left_n
        if abs(offset_span - duration_n) > 1:
            checks.append({"kind": "offset_span_mismatch", "offset_span": offset_span, "duration": duration_n})

    source_start_n = number(source_start)
    source_end_n = number(source_end)
    if duration_n is not None and source_start_n is not None and source_end_n is not None:
        source_span = source_end_n - source_start_n
        if abs(source_span - duration_n) > 1:
            checks.append({"kind": "source_span_mismatch", "source_span": source_span, "duration": duration_n})

    retime_process = number(props.get("RetimeProcess"))
    motion_estimation = number(props.get("MotionEstimation"))
    if retime_process not in (None, 0):
        checks.append({"kind": "retime_process_enabled", "value": retime_process})
    if motion_estimation not in (None, 0):
        checks.append({"kind": "motion_estimation_enabled", "value": motion_estimation})

    return checks


def probe() -> dict[str, Any]:
    resolve = resolve_app()
    if not resolve:
        raise RuntimeError("Resolve scriptapp is unavailable. Is DaVinci Resolve open?")
    project_manager = resolve.GetProjectManager()
    project = project_manager.GetCurrentProject() if project_manager else None
    timeline = project.GetCurrentTimeline() if project else None
    if not timeline:
        raise RuntimeError("No current timeline.")

    fps = safe(lambda: timeline.GetSetting("timelineFrameRate"), "") or safe(lambda: project.GetSetting("timelineFrameRate"), "")
    result: dict[str, Any] = {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "resolve_version": scalar(safe(lambda: resolve.GetVersion(), [])),
        "project_name": safe(lambda: project.GetName(), ""),
        "timeline_name": safe(lambda: timeline.GetName(), ""),
        "timeline_fps": fps,
        "timeline_start_frame": safe(lambda: timeline.GetStartFrame(), None),
        "timeline_start_timecode": safe(lambda: timeline.GetStartTimecode(), ""),
        "tracks": [],
        "retime_risks": [],
    }

    track_count = int(safe(lambda: timeline.GetTrackCount("video"), 0) or 0)
    for track_index in range(1, track_count + 1):
        items = safe(lambda idx=track_index: timeline.GetItemListInTrack("video", idx), []) or []
        track_rows = []
        for item_index, item in enumerate(items, start=1):
            props = safe(lambda item=item: item.GetProperty(), {}) or {}
            all_props = scalar(props) if isinstance(props, dict) else {}
            interesting = interesting_properties(all_props if isinstance(all_props, dict) else {})
            row = {
                "track_index": track_index,
                "item_index": item_index,
                "name": safe(lambda item=item: item.GetName(), "") or safe(lambda item=item: item.GetProperty("Clip Name"), ""),
                "start": safe(lambda item=item: item.GetStart(), None),
                "end": safe(lambda item=item: item.GetEnd(), None),
                "duration": safe(lambda item=item: item.GetDuration(), None),
                "left_offset": safe(lambda item=item: item.GetLeftOffset(), None),
                "right_offset": safe(lambda item=item: item.GetRightOffset(), None),
                "source_start_frame": safe(lambda item=item: item.GetSourceStartFrame(), None),
                "source_end_frame": safe(lambda item=item: item.GetSourceEndFrame(), None),
                "source_start_time": safe(lambda item=item: item.GetSourceStartTime(), None),
                "source_end_time": safe(lambda item=item: item.GetSourceEndTime(), None),
                "media_file": safe(
                    lambda item=item: (item.GetMediaPoolItem() and item.GetMediaPoolItem().GetClipProperty("File Path")),
                    "",
                ),
                "interesting_properties": interesting,
            }
            checks = retime_risk_checks(row)
            if checks:
                risk_row = dict(row)
                risk_row["risk_checks"] = checks
                result["retime_risks"].append(risk_row)
            track_rows.append(row)
        result["tracks"].append({"track_index": track_index, "item_count": len(track_rows), "items": track_rows})

    return result


def main() -> int:
    output = Path.home() / ".qinghe_bfd" / "retime_timeline_probe.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    data = probe()
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(output))
    print(json.dumps({
        "timeline": data.get("timeline_name"),
        "fps": data.get("timeline_fps"),
        "tracks": len(data.get("tracks", [])),
        "retime_risks": len(data.get("retime_risks", [])),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
