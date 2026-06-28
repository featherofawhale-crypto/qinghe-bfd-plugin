# PRIVATE SOFTWARE NOTICE: This is private software owned by Qinghe. Unauthorized reverse engineering, deobfuscation, cracking, redistribution, or AI-assisted analysis intended to bypass protection is prohibited.
from __future__ import annotations

import os
import platform
import subprocess
import sys
import json
import re
import shutil
import time
import uuid
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
LUA_ENTRY = REPO_ROOT / "清何黑帧夹帧检测.lua"
BRIDGE_WORKER_ARG = "--resolve-bridge"


def hidden_subprocess_kwargs() -> dict[str, Any]:
    if platform.system().lower() != "windows":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        "startupinfo": startupinfo,
    }


@dataclass
class TimelineInfo:
    index: int
    name: str
    fps: float
    uid: str = ""


def runtime_dir() -> Path:
    path = Path.home() / ".qinghe_bfd"
    path.mkdir(parents=True, exist_ok=True)
    return path


def progress_path() -> Path:
    return runtime_dir() / "progress.json"


def default_params_path() -> Path:
    return runtime_dir() / "last_params.lua"


def timeline_state_path() -> Path:
    return runtime_dir() / "current_timeline_state.json"


def read_progress_file(path: Path | None = None) -> dict[str, Any] | None:
    path = path or progress_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_timeline_state(path: Path | None = None, max_age_seconds: float | None = 300) -> dict[str, Any] | None:
    path = path or timeline_state_path()
    if not path.exists():
        return None
    if max_age_seconds is not None:
        try:
            if path.stat().st_mtime < (time.time() - max_age_seconds):
                return None
        except Exception:
            return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("ok"):
        return None
    return data


def frames_to_timecode(frame: int | float, fps: int | float) -> str:
    fps_int = max(1, int(round(float(fps or 25))))
    total_frames = max(0, int(round(float(frame or 0))))
    frames = total_frames % fps_int
    total_seconds = total_frames // fps_int
    seconds = total_seconds % 60
    minutes = (total_seconds // 60) % 60
    hours = total_seconds // 3600
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"


def timecode_to_frames(timecode: str, fps: int | float) -> int:
    fps_int = max(1, int(round(float(fps or 25))))
    parts = str(timecode or "00:00:00:00").split(":")
    if len(parts) != 4:
        return 0
    try:
        hh, mm, ss, ff = [int(float(part)) for part in parts]
    except Exception:
        return 0
    return (((hh * 60) + mm) * 60 + ss) * fps_int + ff


def timeline_frame_to_timecode(
    frame: int | float,
    fps: int | float,
    start_frame: int | float = 0,
    start_timecode: str = "00:00:00:00",
) -> str:
    relative_frame = int(round(float(frame or 0))) - int(round(float(start_frame or 0)))
    display_frame = timecode_to_frames(start_timecode, fps) + max(0, relative_frame)
    return frames_to_timecode(display_frame, fps)


def is_mono_audio_mapping(mapping: Any) -> bool:
    if not isinstance(mapping, dict):
        return False
    channels = mapping.get("embedded_audio_channels")
    try:
        if channels is not None and int(channels) == 1:
            return True
    except Exception:
        pass
    track_mapping = mapping.get("track_mapping")
    if isinstance(track_mapping, dict):
        for entry in track_mapping.values():
            if not isinstance(entry, dict):
                continue
            entry_type = str(entry.get("type", "")).lower()
            if entry_type == "mono":
                return True
            channel_idx = entry.get("channel_idx")
            if not entry_type and isinstance(channel_idx, list) and len(channel_idx) == 1:
                return True
    return False


def beat_quality(beat_times: list[float]) -> dict[str, float]:
    intervals = [
        float(beat_times[idx + 1]) - float(beat_times[idx])
        for idx in range(len(beat_times) - 1)
        if float(beat_times[idx + 1]) > float(beat_times[idx])
    ]
    if not intervals:
        return {
            "median_beat_interval_seconds": 0.0,
            "beat_interval_jitter": 1.0,
        }
    intervals_sorted = sorted(intervals)
    median = intervals_sorted[len(intervals_sorted) // 2]
    if median <= 0:
        jitter = 1.0
    else:
        deviations = sorted(abs(value - median) for value in intervals)
        jitter = deviations[len(deviations) // 2] / median
    return {
        "median_beat_interval_seconds": round(float(median), 4),
        "beat_interval_jitter": round(float(jitter), 4),
    }


def lua_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


def lua_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return lua_string(value)
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            parts.append(f"{key} = {lua_value(item)}")
        return "{ " + ", ".join(parts) + " }"
    if isinstance(value, (list, tuple)):
        return "{ " + ", ".join(lua_value(item) for item in value) + " }"
    if value is None:
        return "nil"
    return lua_string(str(value))


def resolve_python_script(body: str) -> str:
    bootstrap = r'''
import importlib.util
import json
import os
import platform
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

def add_default_module_path():
    system = platform.system().lower()
    if system == "windows":
        base = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        script_api = os.environ.get(
            "RESOLVE_SCRIPT_API",
            os.path.join(base, "Blackmagic Design", "DaVinci Resolve", "Support", "Developer", "Scripting"),
        )
        path = os.path.join(script_api, "Modules")
    elif system == "darwin":
        script_api = os.environ.get(
            "RESOLVE_SCRIPT_API",
            "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting",
        )
        script_lib = os.environ.get(
            "RESOLVE_SCRIPT_LIB",
            "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so",
        )
        if os.path.exists(script_lib):
            os.environ.setdefault("RESOLVE_SCRIPT_LIB", script_lib)
        path = os.path.join(script_api, "Modules")
    else:
        script_api = os.environ.get("RESOLVE_SCRIPT_API", "/opt/resolve/Developer/Scripting")
        path = os.path.join(script_api, "Modules")
    if os.path.isdir(path):
        sys.path.insert(0, path)

add_default_module_path()
import DaVinciResolveScript as dvr_script
'''
    return bootstrap + "\n" + body


def build_resolve_python_process(body: str) -> tuple[list[str], str | None]:
    script = resolve_python_script(body)
    if getattr(sys, "frozen", False):
        return [sys.executable, BRIDGE_WORKER_ARG], script
    return [sys.executable, "-c", "import sys; exec(sys.stdin.read())"], script


def run_resolve_bridge_worker() -> int:
    script = sys.stdin.read()
    if not script:
        return 2
    namespace: dict[str, Any] = {"__name__": "__resolve_bridge_worker__"}
    try:
        exec(compile(script, "<resolve-bridge-worker>", "exec"), namespace, namespace)
    except SystemExit as exc:
        if exc.code is None:
            return 0
        if isinstance(exc.code, int):
            return exc.code
        print(exc.code, file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Resolve bridge worker failed: {exc}", file=sys.stderr)
        return 1
    return 0


def find_lua_entry() -> Path | None:
    candidates: list[Path] = []

    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        for root in [exe.parent, *exe.parents]:
            candidates.extend(root.glob("QingheBFD_Plugin_Windows/*.lua"))
    else:
        candidates.append(LUA_ENTRY)

    if platform.system().lower() == "windows":
        appdata = Path(os.environ.get("APPDATA", ""))
        if appdata:
            edit_dir = (
                appdata
                / "Blackmagic Design"
                / "DaVinci Resolve"
                / "Support"
                / "Fusion"
                / "Scripts"
                / "Edit"
            )
            candidates.extend(edit_dir.glob("*.lua"))
    elif platform.system().lower() == "darwin":
        edit_dir = (
            Path.home()
            / "Library"
            / "Application Support"
            / "Blackmagic Design"
            / "DaVinci Resolve"
            / "Fusion"
            / "Scripts"
            / "Edit"
        )
        candidates.extend(edit_dir.glob("*.lua"))

    for candidate in candidates:
        if candidate.exists() and "黑帧" in candidate.name:
            return candidate
    for candidate in candidates:
        if candidate.exists():
            return candidate
    if LUA_ENTRY.exists():
        return LUA_ENTRY
    return None


def write_lua_params(params: dict[str, Any], target: Path | None = None) -> Path:
    target = target or default_params_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = ["return {"]
    for key, value in params.items():
        lines.append(f"  {key} = {lua_value(value)},")
    lines.append("}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def clean_resolve_text(value: Any) -> str:
    text = str(value or "")
    replacements = {
        "��ǰ": "当前",
        "褰撳墠": "当前",
        "锛": "：",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text


def configure_resolve_python_path() -> None:
    system = platform.system().lower()
    candidates: list[Path] = []
    if system == "windows":
        program_data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        candidates.append(
            program_data
            / "Blackmagic Design"
            / "DaVinci Resolve"
            / "Support"
            / "Developer"
            / "Scripting"
            / "Modules"
        )
    elif system == "darwin":
        candidates.append(
            Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
        )
    else:
        candidates.append(Path("/opt/resolve/Developer/Scripting/Modules"))

    for candidate in candidates:
        if candidate.exists():
            sys.path.insert(0, str(candidate))
            return


class ResolveBridge:
    def __init__(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def _subtitle_operation_timeout(self, timeline_index: int = 1, minimum: float = 120, per_item: float = 0.15) -> float:
        """Allow long subtitle timelines on macOS without cutting Resolve API reads short."""
        timeout = float(minimum)
        state = read_timeline_state(max_age_seconds=1800) or {}
        timelines = state.get("timelines") if isinstance(state, dict) else []
        info = {}
        if isinstance(timelines, list):
            for item in timelines:
                if isinstance(item, dict) and int(item.get("index", 0) or 0) == int(timeline_index):
                    info = item
                    break
        fps = 25.0
        try:
            fps = float(info.get("fps") or state.get("fps") or 25.0)
        except Exception:
            fps = 25.0
        frame_span = 0.0
        for start_key, end_key in (
            ("start_frame", "end_frame"),
            ("timeline_start_frame", "timeline_end_frame"),
            ("start", "end"),
        ):
            try:
                start = float(info.get(start_key, state.get(start_key, 0)) or 0)
                end = float(info.get(end_key, state.get(end_key, 0)) or 0)
            except Exception:
                continue
            if end > start:
                frame_span = max(frame_span, end - start)
        duration_sec = frame_span / max(1.0, fps)
        if duration_sec:
            timeout = max(timeout, 90 + duration_sec / 18)
        item_count = 0
        for key in ("subtitle_count", "text_item_count", "clip_count"):
            try:
                item_count = max(item_count, int(info.get(key, state.get(key, 0)) or 0))
            except Exception:
                pass
        if item_count:
            timeout = max(timeout, minimum + item_count * per_item)
        return min(900.0, timeout)

    @staticmethod
    def _timelines_from_state(state: dict[str, Any]) -> list[TimelineInfo]:
        timelines = state.get("timelines")
        if not isinstance(timelines, list):
            return []
        return [
            TimelineInfo(
                int(item.get("index", index + 1)),
                clean_resolve_text(item.get("name")),
                float(item.get("fps", 25.0)),
                clean_resolve_text(item.get("uid")),
            )
            for index, item in enumerate(timelines)
            if isinstance(item, dict)
        ]

    def list_timelines(self) -> list[TimelineInfo]:
        # Try live query first for accurate data
        data = self._run_resolve_python(
            r'''
import json
import os
import re
import shutil
import subprocess
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
if not project:
    print(json.dumps({"connected": bool(resolve), "timelines": []}, ensure_ascii=False))
    raise SystemExit(0)
current = project.GetCurrentTimeline()
current_name = current.GetName() if current else ""
current_uid = ""
try:
    current_uid = current.GetUniqueId() if current else ""
except Exception:
    current_uid = ""
items = []
count = int(project.GetTimelineCount() or 0)
seen = set()
for index in range(1, count + 1):
    timeline = project.GetTimelineByIndex(index)
    if not timeline:
        continue
    name = timeline.GetName() or f"Timeline {index}"
    try:
        uid = timeline.GetUniqueId() or name
    except Exception:
        uid = name
    if uid in seen:
        continue
    seen.add(uid)
    fps_raw = timeline.GetSetting("timelineFrameRate") or 25
    try:
        fps = float(fps_raw)
    except Exception:
        fps = 25.0
    if (uid and uid == current_uid) or name == current_name:
        name = name + "  (当前)"
    items.append({"index": index, "name": name, "fps": fps, "uid": uid})
print(json.dumps({"connected": True, "timelines": items}, ensure_ascii=False))
''',
            timeout=8,
        )
        if data and data.get("timelines"):
            self._connected = bool(data.get("connected", True))
            return [
                TimelineInfo(
                    int(item["index"]),
                    clean_resolve_text(item.get("name")),
                    float(item["fps"]),
                    clean_resolve_text(item.get("uid")),
                )
                for item in data.get("timelines", [])
            ]

        # Fallback: cached state from last Lua run
        cached = read_timeline_state()
        if cached:
            timelines = self._timelines_from_state(cached)
            if timelines:
                self._connected = False
                return timelines

        # Last resort: stale cache
        stale_cached = read_timeline_state(max_age_seconds=None)
        if stale_cached:
            timelines = self._timelines_from_state(stale_cached)
            if timelines:
                self._connected = False
                return timelines

        self._connected = False
        return [TimelineInfo(1, "当前时间线", 25.0)]

    def submit_params(self, params: dict[str, Any]) -> Path:
        params = dict(params)
        job_id = str(params.get("job_id") or uuid.uuid4().hex)
        safe_job_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", job_id).strip("._") or "job"
        params["job_id"] = job_id
        params["enabled"] = True
        params["submitted_at"] = int(time.time())
        params["progress_file"] = str(progress_path())
        progress_path().write_text(
            json.dumps(
                {
                    "percent": 1,
                    "stage": "参数已提交，等待 Resolve 执行",
                    "state": "pending",
                    "job_id": job_id,
                    "timeline_index": params.get("timeline_index"),
                    "timeline_name": params.get("timeline_name"),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        params_path = write_lua_params(params, runtime_dir() / f"params_{safe_job_id}.lua")
        try:
            write_lua_params(params, default_params_path())
        except Exception:
            pass
        return params_path

    def current_timeline_clip_snapshot(self, timeline_index: int = 1) -> dict[str, Any]:
        data = self._run_resolve_python(
            rf'''
import json
import os
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
timeline = project.GetTimelineByIndex({int(timeline_index)}) if project else None
if not timeline:
    print(json.dumps({{"ok": False, "message": "未找到目标时间线。", "clips": []}}, ensure_ascii=False))
    raise SystemExit(0)

def safe(callable_obj, default=None):
    try:
        return callable_obj()
    except Exception:
        return default

def media_type_for(path):
    ext = os.path.splitext(str(path or ""))[1].lower().lstrip(".")
    if ext in {{"mov", "mp4", "mxf", "avi", "mkv", "mts", "m2ts", "r3d", "braw", "ari", "arx", "dng", "cin", "rmf", "wmv", "flv", "m4v", "mpg", "mpeg", "ts", "webm", "vob", "m2v", "dv", "h264", "hevc", "prores", "3gp", "ogv"}}:
        return "video"
    if ext in {{"png", "psd", "tiff", "tif", "exr"}}:
        return "alpha_image"
    if ext in {{"jpg", "jpeg", "bmp", "gif", "webp"}}:
        return "still_image"
    return ""

def clip_prop(media_pool_item, keys):
    if not media_pool_item:
        return ""
    props = safe(lambda: media_pool_item.GetClipProperty(), {{}}) or {{}}
    for key in keys:
        value = safe(lambda key=key: media_pool_item.GetClipProperty(key), None)
        if value:
            return str(value)
        if isinstance(props, dict) and props.get(key):
            return str(props.get(key))
    if isinstance(props, dict):
        lowered = {{str(key).lower(): value for key, value in props.items()}}
        for key in keys:
            value = lowered.get(str(key).lower())
            if value:
                return str(value)
    return ""

def item_property(item, keys, default=None):
    props = safe(lambda: item.GetProperty(), {{}}) or {{}}
    for key in keys:
        value = safe(lambda key=key: item.GetProperty(key), None)
        if value is not None and value != "":
            return value
        if isinstance(props, dict) and props.get(key) is not None:
            return props.get(key)
    return default

clips = []
track_count = int(safe(lambda: timeline.GetTrackCount("video"), 0) or 0)
for track_index in range(1, track_count + 1):
    enabled = safe(lambda track_index=track_index: timeline.GetIsTrackEnabled("video", track_index), True)
    if enabled is False:
        continue
    items = safe(lambda track_index=track_index: timeline.GetItemListInTrack("video", track_index), []) or []
    for item in items:
        media_pool_item = safe(lambda item=item: item.GetMediaPoolItem())
        file_path = clip_prop(media_pool_item, ("File Path", "FilePath", "Clip File Path"))
        media_type = media_type_for(file_path)
        if not file_path or not media_type:
            continue
        start_frame = int(safe(lambda item=item: item.GetStart(), 0) or 0)
        end_frame = int(safe(lambda item=item: item.GetEnd(), start_frame) or start_frame)
        duration = int(safe(lambda item=item: item.GetDuration(), max(0, end_frame - start_frame)) or 0)
        if end_frame <= start_frame and duration > 0:
            end_frame = start_frame + duration
        if duration <= 0 and end_frame > start_frame:
            duration = end_frame - start_frame
        left_value = safe(lambda item=item: item.GetLeftOffset(), None)
        left_offset_ok = left_value is not None
        left_offset = int(left_value or 0)
        name = clip_prop(media_pool_item, ("File Name", "Clip Name")) or str(safe(lambda item=item: item.GetName(), "未知") or "未知")
        opacity_raw = item_property(item, ("Opacity", "opacity", "CompositeOpacity"), 100)
        try:
            opacity = float(opacity_raw)
        except Exception:
            opacity = 100.0
        source_fps_raw = clip_prop(media_pool_item, ("FPS", "Shot Frame Rate", "Video Frame Rate"))
        try:
            source_fps = float(source_fps_raw) if source_fps_raw else None
        except Exception:
            source_fps = None
        clips.append({{
            "file_path": file_path,
            "name": name,
            "timeline_start_frame": start_frame,
            "timeline_end_frame": end_frame,
            "left_offset": left_offset,
            "left_offset_ok": left_offset_ok,
            "source_range_reliable": left_offset_ok and duration > 0,
            "source_duration_frames": duration,
            "source_fps": source_fps,
            "track_index": track_index,
            "opacity": opacity,
            "composite_mode": str(item_property(item, ("Composite Mode", "CompositeMode", "compositeMode"), "Normal") or "Normal"),
            "is_enabled": bool(item_property(item, ("Enabled", "enabled"), True)),
            "media_type": media_type,
            "skip_ffmpeg": media_type in ("still_image", "alpha_image", "nested"),
            "skip_stuck": media_type == "alpha_image",
        }})
print(json.dumps({{"ok": True, "clips": clips, "count": len(clips)}}, ensure_ascii=False))
''',
            timeout=12,
        )
        return data or {"ok": False, "clips": [], "message": "片段快照读取失败。"}

    def open_resolve_page(self) -> bool:
        data = self._run_resolve_python(
            r'''
import json
resolve = dvr_script.scriptapp("Resolve")
ok = bool(resolve and resolve.OpenPage("edit"))
print(json.dumps({"ok": ok}))
'''
        )
        return bool(data and data.get("ok"))

    def current_timeline_identity(self) -> dict[str, Any]:
        data = self._run_resolve_python(
            r'''
import json
resolve = dvr_script.scriptapp("Resolve")
pm = resolve.GetProjectManager() if resolve else None
project = pm.GetCurrentProject() if pm else None
timeline = project.GetCurrentTimeline() if project else None
if not timeline:
    print(json.dumps({"ok": False}, ensure_ascii=False))
    raise SystemExit(0)
uid = ""
try:
    uid = timeline.GetUniqueId() or ""
except Exception:
    uid = ""
print(json.dumps({"ok": True, "name": timeline.GetName() or "", "uid": uid}, ensure_ascii=False))
''',
            timeout=3,
        )
        return data or {"ok": False}

    def activate_timeline(self, timeline_index: int = 1) -> tuple[bool, str]:
        data = self._run_resolve_python(
            rf'''
import json
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
timeline = project.GetTimelineByIndex({max(1, int(timeline_index))}) if project else None
ok = False
name = ""
if project and timeline:
    name = timeline.GetName() or ""
    ok = bool(project.SetCurrentTimeline(timeline))
    if resolve:
        resolve.OpenPage("edit")
message = f"已打开时间线：{{name}}" if ok else "未找到或无法打开目标时间线。"
print(json.dumps({{"ok": ok, "message": message, "name": name}}, ensure_ascii=False))
'''
        )
        if not data:
            return False, "Resolve API 未返回时间线切换结果。"
        return bool(data.get("ok")), str(data.get("message", "时间线已打开。"))

    def clear_bfd_markers(self, timeline_index: int = 1) -> tuple[bool, str]:
        data = self._run_resolve_python(
            rf'''
import json
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
current_timeline = project.GetCurrentTimeline() if project else None
indexed_timeline = project.GetTimelineByIndex({int(timeline_index)}) if project else None
timeline = current_timeline or indexed_timeline
if not timeline:
    print(json.dumps({{"ok": False, "message": "未找到当前时间线。"}}, ensure_ascii=False))
    raise SystemExit(0)
markers = timeline.GetMarkers() or {{}}
removed = 0
for frame, marker in list(markers.items()):
    name = str(marker.get("name", ""))
    note = str(marker.get("note", ""))
    if name.startswith("[BFD") or "[BFD" in note:
        try:
            if timeline.DeleteMarkerAtFrame(frame):
                removed += 1
        except Exception:
            pass
print(json.dumps({{"ok": True, "message": f"已清除 {{removed}} 个 BFD 标记。"}}, ensure_ascii=False))
''',
            timeout=120,
        )
        if not data:
            return False, "清除失败：Resolve API 未返回结果。"
        return bool(data.get("ok")), str(data.get("message", "清除完成。"))

    def clear_current_bfd_markers(self) -> tuple[bool, str]:
        data = self._run_resolve_python(
            r'''
import json
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
timeline = project.GetCurrentTimeline() if project else None
if not timeline:
    print(json.dumps({"ok": False, "message": "未找到 Resolve 当前时间线。"}, ensure_ascii=False))
    raise SystemExit(0)
timeline_name = timeline.GetName() or ""
markers = timeline.GetMarkers() or {}
removed = 0
failed = 0
matched = 0
for frame, marker in list(markers.items()):
    name = str(marker.get("name", "")) if isinstance(marker, dict) else ""
    note = str(marker.get("note", "")) if isinstance(marker, dict) else ""
    custom_data = str(marker.get("customData", "")) if isinstance(marker, dict) else ""
    if name.startswith("[BFD") or "[BFD" in note or custom_data.startswith("BFD"):
        matched += 1
        deleted = False
        for candidate_frame in (frame, int(float(frame)) if str(frame).replace(".", "", 1).isdigit() else frame):
            try:
                if timeline.DeleteMarkerAtFrame(candidate_frame):
                    deleted = True
                    break
            except Exception:
                pass
        if deleted:
            removed += 1
        else:
            failed += 1
print(json.dumps({
    "ok": failed == 0,
    "message": "当前时间线“%s”：匹配 %d 个 BFD 标记，已清除 %d 个%s。" % (
        timeline_name,
        matched,
        removed,
        ("，失败 %d 个" % failed) if failed else ""
    ),
    "timeline": timeline_name,
    "matched": matched,
    "removed": removed,
    "failed": failed,
}, ensure_ascii=False))
''',
            timeout=120,
        )
        if not data:
            return False, "清除失败：Resolve API 未返回结果。"
        return bool(data.get("ok")), str(data.get("message", "清除完成。"))

    def current_timeline_marks(self, timeline_index: int = 1) -> dict[str, Any]:
        data = self._run_resolve_python(
            rf'''
import json
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
timeline = project.GetTimelineByIndex({max(1, int(timeline_index))}) if project else None
if not timeline:
    print(json.dumps({{"ok": False, "message": "未找到目标时间线。"}}, ensure_ascii=False))
    raise SystemExit(0)
try:
    project.SetCurrentTimeline(timeline)
except Exception:
    pass
try:
    resolve_version = resolve.GetVersion() or []
except Exception:
    resolve_version = []
try:
    resolve_major = int(resolve_version[0]) if len(resolve_version) > 0 else 0
except Exception:
    resolve_major = 0
try:
    resolve_minor = int(resolve_version[1]) if len(resolve_version) > 1 else 0
except Exception:
    resolve_minor = 0
supports_direct_mark_query = resolve_major > 19 or (resolve_major == 19 and resolve_minor >= 1)
fps_raw = timeline.GetSetting("timelineFrameRate") or 25
try:
    fps = float(fps_raw)
except Exception:
    fps = 25.0
try:
    start_frame = int(float(timeline.GetStartFrame() or 0))
except Exception:
    start_frame = 0
try:
    start_timecode = str(timeline.GetStartTimecode() or timeline.GetSetting("timelineStartTimecode") or "00:00:00:00")
except Exception:
    start_timecode = "00:00:00:00"

def as_number(value):
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except Exception:
        return None

def normalize_mark_frame(value):
    frame = as_number(value)
    if frame is None:
        return None
    if start_frame > 0 and frame < start_frame:
        return start_frame + frame
    return frame

def try_method(name):
    try:
        fn = getattr(timeline, name, None)
        if fn:
            return as_number(fn())
    except Exception:
        return None
    return None

def pair_from_values(in_value, out_value):
    i = normalize_mark_frame(in_value)
    o = normalize_mark_frame(out_value)
    if i is not None and o is not None and o > i:
        return i, o
    return None, None

def first_pair_from_methods(pairs):
    for in_name, out_name in pairs:
        i, o = pair_from_values(try_method(in_name), try_method(out_name))
        if i is not None and o is not None:
            return i, o, in_name + "/" + out_name
    return None, None, ""

def first_partial_from_methods(pairs):
    for in_name, out_name in pairs:
        i = normalize_mark_frame(try_method(in_name))
        o = normalize_mark_frame(try_method(out_name))
        if i is not None or o is not None:
            return i, o, in_name + "/" + out_name
    return None, None, ""

def first_pair_from_settings(pairs):
    for in_key, out_key in pairs:
        try:
            i, o = pair_from_values(timeline.GetSetting(in_key), timeline.GetSetting(out_key))
            if i is not None and o is not None:
                return i, o, "GetSetting(" + in_key + "/" + out_key + ")"
        except Exception:
            pass
    return None, None, ""

def first_partial_from_settings(pairs):
    for in_key, out_key in pairs:
        try:
            i = normalize_mark_frame(timeline.GetSetting(in_key))
            o = normalize_mark_frame(timeline.GetSetting(out_key))
            if i is not None or o is not None:
                return i, o, "GetSetting(" + in_key + "/" + out_key + ")"
        except Exception:
            pass
    return None, None, ""

in_frame = None
out_frame = None
in_frame_fallback = False
source = ""
try:
    mark = timeline.GetMarkInOut() or {{}}
except Exception:
    mark = {{}}
if isinstance(mark, dict):
    for mark_type in ("video", "all", "audio"):
        entry = mark.get(mark_type)
        if not isinstance(entry, dict):
            continue
        in_frame, out_frame = pair_from_values(entry.get("in"), entry.get("out"))
        if in_frame is not None and out_frame is not None:
            source = "GetMarkInOut(" + mark_type + ")"
            break

if in_frame is None or out_frame is None:
    method_pairs = [
        ("GetInPoint", "GetOutPoint"),
        ("GetMarkIn", "GetMarkOut"),
        ("GetRenderIn", "GetRenderOut"),
        ("GetTimelineIn", "GetTimelineOut"),
    ]
    in_frame, out_frame, source = first_pair_from_methods(method_pairs)
    if in_frame is None or out_frame is None:
        partial_in, partial_out, partial_source = first_partial_from_methods(method_pairs)
        if partial_in is not None or partial_out is not None:
            in_frame = in_frame if in_frame is not None else partial_in
            out_frame = out_frame if out_frame is not None else partial_out
            source = source or partial_source

if in_frame is None or out_frame is None:
    setting_pairs = [
        ("timelineIn", "timelineOut"),
        ("InPoint", "OutPoint"),
        ("markIn", "markOut"),
        ("renderIn", "renderOut"),
    ]
    pair_in, pair_out, pair_source = first_pair_from_settings(setting_pairs)
    if pair_in is not None and pair_out is not None:
        in_frame, out_frame, source = pair_in, pair_out, pair_source
    else:
        partial_in, partial_out, partial_source = first_partial_from_settings(setting_pairs)
        if partial_in is not None or partial_out is not None:
            in_frame = in_frame if in_frame is not None else partial_in
            out_frame = out_frame if out_frame is not None else partial_out
            source = source or partial_source

if in_frame is None and out_frame is not None:
    in_frame = start_frame
    in_frame_fallback = True

if (in_frame is None or out_frame is None) and not supports_direct_mark_query:
    previous_page = "edit"
    job_id = None
    try:
        import tempfile

        previous_page = str(resolve.GetCurrentPage() or "edit") if resolve else "edit"
        before_jobs = project.GetRenderJobList() or []
        before_ids = {{str(job.get("JobId")) for job in before_jobs if isinstance(job, dict)}}
        project.SetRenderSettings({{
            "TargetDir": tempfile.gettempdir(),
            "CustomName": "bfd_io_probe_do_not_render",
            "ExportVideo": True,
            "ExportAudio": False,
        }})
        job_id = project.AddRenderJob()
        after_jobs = project.GetRenderJobList() or []
        probe_job = None
        if job_id:
            for job in after_jobs:
                if isinstance(job, dict) and str(job.get("JobId")) == str(job_id):
                    probe_job = job
                    break
        if probe_job is None:
            new_jobs = [job for job in after_jobs if isinstance(job, dict) and str(job.get("JobId")) not in before_ids]
            if new_jobs:
                probe_job = new_jobs[-1]
        if probe_job:
            i, o = pair_from_values(probe_job.get("MarkIn"), probe_job.get("MarkOut"))
            if i is not None and o is not None:
                in_frame, out_frame = i, o + 1
                source = "AddRenderJobProbe"
    except Exception:
        pass
    finally:
        try:
            if job_id:
                project.DeleteRenderJob(job_id)
        except Exception:
            pass
        try:
            if resolve:
                resolve.OpenPage(previous_page or "edit")
        except Exception:
            pass

ok = in_frame is not None and out_frame is not None and out_frame > in_frame
message = "已读取当前时间线入出点。" if ok else "当前时间线没有可读取的入出点。"
if ok and in_frame_fallback:
    message = "Resolve API 未返回 In 点，已按时间线起点作为 In 点。"
elif ok and source == "AddRenderJobProbe":
    message = "Resolve 19.0 旧版 API 已通过临时渲染队列探测读取入出点，并自动回到原页面。"
elif not ok and supports_direct_mark_query:
    message = "Resolve 19.1/20 直接 IO API 未返回入出点，请确认时间线已设置 In/Out。"
print(json.dumps({{
    "ok": ok,
    "in_frame": in_frame,
    "out_frame": out_frame,
    "fps": fps,
    "start_frame": start_frame,
    "start_timecode": start_timecode,
    "resolve_version": resolve_version,
    "supports_direct_mark_query": supports_direct_mark_query,
    "source": source,
    "in_frame_fallback": in_frame_fallback,
    "message": message
}}, ensure_ascii=False))
'''
        )
        if not data:
            return {"ok": False, "message": "读取失败：Resolve API 未返回结果。"}
        if data.get("ok"):
            fps = float(data.get("fps", 25.0))
            start_frame = data.get("start_frame", 0)
            start_timecode = str(data.get("start_timecode", "00:00:00:00"))
            data["in_tc"] = timeline_frame_to_timecode(data.get("in_frame", 0), fps, start_frame, start_timecode)
            data["out_tc"] = timeline_frame_to_timecode(data.get("out_frame", 0), fps, start_frame, start_timecode)
        return data

    def detect_complex_timeline_risk(self, timeline_index: int = 1) -> dict[str, Any]:
        data = self._run_resolve_python(
            rf'''
import json
import os
import re
import shutil
import subprocess
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
timeline = project.GetTimelineByIndex({int(timeline_index)}) if project else None
if not timeline:
    print(json.dumps({{"ok": False, "message": "未找到目标时间线。", "candidates": [], "count": 0}}, ensure_ascii=False))
    raise SystemExit(0)

def safe(callable_obj, default=None):
    try:
        return callable_obj()
    except Exception:
        return default

def clip_name(item, media_pool_item=None):
    media_pool_item = media_pool_item or safe(lambda: item.GetMediaPoolItem())
    if media_pool_item:
        for key in ("Clip Name", "File Name"):
            value = safe(lambda key=key: media_pool_item.GetClipProperty(key))
            if value:
                return str(value)
    return str(safe(lambda: item.GetName(), "未命名片段") or "未命名片段")

def clip_file_path(media_pool_item):
    if not media_pool_item:
        return ""
    for key in ("File Path", "FilePath", "Clip File Path"):
        value = safe(lambda key=key: media_pool_item.GetClipProperty(key))
        if value:
            return str(value)
    props = safe(lambda: media_pool_item.GetClipProperty(), {{}}) or {{}}
    if isinstance(props, dict):
        for key, value in props.items():
            if "path" in str(key).lower() and value:
                return str(value)
    return ""

def clip_type(media_pool_item):
    if not media_pool_item:
        return ""
    value = safe(lambda: media_pool_item.GetClipProperty("Type"), "")
    return str(value or "")

fps_raw = safe(lambda: timeline.GetSetting("timelineFrameRate"), 25) or 25
try:
    fps = float(fps_raw)
except Exception:
    fps = 25.0
long_clip_frames = max(1, int(round(fps * 30)))
track_count = int(safe(lambda: timeline.GetTrackCount("video"), 0) or 0)
candidates = []

def find_ffmpeg():
    for candidate in (
        shutil.which("ffmpeg"),
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
    ):
        if candidate and os.path.exists(candidate):
            return candidate
    return ""

ffmpeg_path = find_ffmpeg()
scene_probe_budget = 2

def source_scene_cut_count(path, start_sec, duration_sec):
    if not ffmpeg_path or not path or not os.path.exists(path):
        return 0
    if duration_sec < 15:
        return 0
    probe_duration = min(float(duration_sec), 90.0)
    cmd = [
        ffmpeg_path,
        "-hide_banner",
        "-ss", "%.3f" % max(0.0, float(start_sec or 0.0)),
        "-t", "%.3f" % probe_duration,
        "-i", path,
        "-vf", "select='gt(scene\\,0.18)',metadata=print",
        "-an",
        "-f", "null",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=7)
    except Exception:
        return 0
    text = (proc.stdout or "") + "\\n" + (proc.stderr or "")
    return len(re.findall(r"lavfi\\.scene_score\\s*=", text))

for track_index in range(1, track_count + 1):
    items = safe(lambda track_index=track_index: timeline.GetItemListInTrack("video", track_index), []) or []
    for item_index, item in enumerate(items):
        media_pool_item = safe(lambda item=item: item.GetMediaPoolItem())
        name = clip_name(item, media_pool_item)
        path = clip_file_path(media_pool_item)
        ctype = clip_type(media_pool_item)
        start = int(safe(lambda item=item: item.GetStart(), 0) or 0)
        end = int(safe(lambda item=item: item.GetEnd(), start) or start)
        duration = max(0, end - start)
        fusion_count = int(safe(lambda item=item: item.GetFusionCompCount(), 0) or 0)
        left_offset = int(safe(lambda item=item: item.GetLeftOffset(), 0) or 0)
        source_fps_raw = safe(lambda: media_pool_item.GetClipProperty("FPS") if media_pool_item else None, None)
        try:
            source_fps = float(source_fps_raw or fps or 25.0)
        except Exception:
            source_fps = fps or 25.0
        lower_name = name.lower()
        lower_type = ctype.lower()
        is_text_generator = any(token in lower_type or token in lower_name for token in (
            "text+", "text", "title", "subtitle", "caption", "generator",
            "文本", "字幕", "标题", "生成器"
        ))
        if fusion_count > 0 and not is_text_generator:
            candidates.append({{
                "name": name,
                "track_index": track_index,
                "kind": "nested",
                "reason": "片段含 Fusion 合成，普通模式不分析最终画面",
            }})
        elif (not is_text_generator) and any(token in lower_type for token in ("fusion", "复合", "compound")):
            candidates.append({{
                "name": name,
                "track_index": track_index,
                "kind": "nested",
                "reason": f"片段类型为 {{ctype or '无源文件片段'}}，建议复合/Fusion 片段精查",
            }})
        elif not path and duration > 0 and not is_text_generator:
            candidates.append({{
                "name": name,
                "track_index": track_index,
                "kind": "nested",
                "reason": "疑似复合/Fusion片段或无源文件路径，建议复合/Fusion 片段精查",
            }})
        elif path and duration >= long_clip_frames and scene_probe_budget > 0:
            scene_probe_budget -= 1
            source_start_sec = float(left_offset) / max(1.0, source_fps)
            duration_sec = float(duration) / max(1.0, fps)
            scene_cut_count = source_scene_cut_count(path, source_start_sec, duration_sec)
            scene_cut_density = scene_cut_count / max(0.25, min(duration_sec, 90.0) / 60.0)
            if scene_cut_count >= 5 and scene_cut_density >= 4.0:
                candidates.append({{
                    "name": name,
                    "track_index": track_index,
                    "kind": "complex",
                    "reason": "源文件内部检测到多处切点，疑似混剪/成片导出文件",
                    "scene_cut_count": scene_cut_count,
                }})

deduped = []
seen = set()
for item in candidates:
    key = (item.get("name"), item.get("reason"), item.get("source_file", ""))
    if key in seen:
        continue
    seen.add(key)
    deduped.append(item)

nested_count = sum(1 for item in deduped if item.get("kind") == "nested")
complex_count = sum(1 for item in deduped if item.get("kind") == "complex")
if complex_count:
    message = f"发现 {{complex_count}} 个疑似混剪/成片文件，建议启用复杂模式。"
elif nested_count:
    message = f"发现 {{nested_count}} 个复合/Fusion 片段，建议启用复合/Fusion 片段精查。"
else:
    message = "未发现明显复合/Fusion/成片风险。"
print(json.dumps({{
    "ok": True,
    "count": len(deduped),
    "nested_count": nested_count,
    "complex_count": complex_count,
    "message": message,
    "candidates": deduped[:8],
}}, ensure_ascii=False))
'''
        )
        if not data:
            return {"ok": False, "message": "时间线结构扫描失败：Resolve API 未返回结果。", "candidates": [], "count": 0}
        return data

    def scan_mono_audio(self, timeline_index: int = 1, io_in: str = "", io_out: str = "") -> dict[str, Any]:
        return self._audio_action(timeline_index, "scan", io_in, io_out)

    def mark_mono_audio(self, timeline_index: int = 1, io_in: str = "", io_out: str = "") -> dict[str, Any]:
        return self._audio_action(timeline_index, "mark", io_in, io_out)

    def clear_mono_audio_markers(self, timeline_index: int = 1) -> dict[str, Any]:
        data = self._run_resolve_python(
            rf'''
import json
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
timeline = project.GetCurrentTimeline() if project else None
if not timeline and project:
    timeline = project.GetTimelineByIndex({int(timeline_index)})
if not timeline:
    print(json.dumps({{"ok": False, "message": "未找到目标时间线。"}}, ensure_ascii=False))
    raise SystemExit(0)

def safe(callable_obj, default=None):
    try:
        return callable_obj()
    except Exception:
        return default

def as_items(value):
    if value is None:
        return []
    if isinstance(value, dict):
        return [item for item in value.values() if item]
    if isinstance(value, (list, tuple)):
        return [item for item in value if item]
    return [value]

def marker_custom(marker):
    if not isinstance(marker, dict):
        return ""
    return str(marker.get("customData", "") or marker.get("custom_data", "") or "")

def is_audio_marker(marker):
    if not isinstance(marker, dict):
        return False
    return str(marker.get("name", "")).startswith("[BFD-AUDIO]") or marker_custom(marker).startswith("qinghe-bfd-audio-mono")

removed = 0
failed = 0
for frame_id, marker in list((safe(lambda: timeline.GetMarkers(), {{}}) or {{}}).items()):
    if not is_audio_marker(marker):
        continue
    if safe(lambda frame_id=frame_id: timeline.DeleteMarkerAtFrame(frame_id), False):
        removed += 1
    else:
        failed += 1

track_count = int(safe(lambda: timeline.GetTrackCount("audio"), 0) or 0)
for track_index in range(1, track_count + 1):
    for item in as_items(safe(lambda idx=track_index: timeline.GetItemListInTrack("audio", idx), [])):
        markers = safe(lambda item=item: item.GetMarkers(), {{}}) or {{}}
        for frame_id, marker in list(markers.items()):
            if not is_audio_marker(marker):
                continue
            if safe(lambda item=item, frame_id=frame_id: item.DeleteMarkerAtFrame(frame_id), False):
                removed += 1
            else:
                failed += 1

print(json.dumps({{
    "ok": True,
    "removed": removed,
    "failed": failed,
    "message": "已清除单声道音频标记 %d 个%s。" % (removed, ("，失败 %d 个" % failed) if failed else ""),
}}, ensure_ascii=False))
''',
            timeout=30,
        )
        if not data:
            return {"ok": False, "message": "清除单声道音频标记失败：Resolve API 未返回结果。"}
        return data

    def fix_mono_audio_to_stereo(self, timeline_index: int = 1, io_in: str = "", io_out: str = "") -> dict[str, Any]:
        return self._audio_action(timeline_index, "fix", io_in, io_out)

    def resolve_version_string(self) -> str:
        data = self._run_resolve_python(
            '''
import json
resolve = dvr_script.scriptapp("Resolve")
version = ""
if resolve:
    try:
        version = str(resolve.GetVersionString() or "")
    except Exception:
        try:
            version = ".".join(str(part) for part in (resolve.GetVersion() or []))
        except Exception:
            version = ""
print(json.dumps({"ok": bool(version), "version": version}, ensure_ascii=False))
''',
            timeout=10,
        )
        if not data:
            return ""
        return str(data.get("version", "") or "")

    def probe_audio_fx_api(self, timeline_index: int = 1) -> dict[str, Any]:
        data = self._run_resolve_python(
            rf'''
import json
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
timeline = project.GetCurrentTimeline() if project else None
if not timeline and project:
    timeline = project.GetTimelineByIndex({int(timeline_index)})
if not timeline:
    print(json.dumps({{"ok": False, "message": "未找到目标时间线。", "probe": {{}}}}, ensure_ascii=False))
    raise SystemExit(0)

def safe(callable_obj, default=None):
    try:
        return callable_obj()
    except Exception:
        return default

KEYWORDS = (
    "audio", "fairlight", "fx", "ofx", "effect", "plugin", "filter",
    "eq", "equal", "compress", "dynamics", "limiter", "normalize", "loudness",
)
WRITE_PREFIXES = ("Add", "Apply", "Insert", "Set", "Enable", "Create")
WRITE_KEYWORDS = ("fx", "ofx", "effect", "plugin", "fairlight", "filter")

def interesting_methods(obj):
    if obj is None:
        return []
    names = []
    for name in dir(obj):
        if name.startswith("_"):
            continue
        lowered = name.lower()
        if any(token in lowered for token in KEYWORDS):
            attr = safe(lambda n=name: getattr(obj, n), None)
            if callable(attr):
                names.append(name)
    return sorted(set(names))

def possible_write_methods(methods):
    found = []
    for name in methods:
        if name in ("InsertOFXGeneratorIntoTimeline",):
            continue
        if not name.startswith(WRITE_PREFIXES):
            continue
        lowered = name.lower()
        if ("audio" in lowered or "fairlight" in lowered) and any(token in lowered for token in WRITE_KEYWORDS):
            found.append(name)
    return found

def sample_call(obj, name):
    fn = safe(lambda: getattr(obj, name), None)
    if not callable(fn):
        return {{"ok": False, "value": "not callable"}}
    try:
        value = fn()
        if isinstance(value, (str, int, float, bool)) or value is None:
            return {{"ok": True, "value": value}}
        if isinstance(value, dict):
            return {{"ok": True, "type": "dict", "keys": [str(key) for key in list(value.keys())[:20]]}}
        if isinstance(value, (list, tuple)):
            return {{"ok": True, "type": "list", "count": len(value), "sample": [str(item)[:80] for item in list(value)[:5]]}}
        return {{"ok": True, "type": type(value).__name__, "repr": str(value)[:120]}}
    except Exception as exc:
        return {{"ok": False, "error": str(exc)[:160]}}

track_count = int(safe(lambda: timeline.GetTrackCount("audio"), 0) or 0)
first_item = None
first_media = None
first_track_index = 0
for track_index in range(1, track_count + 1):
    items = safe(lambda idx=track_index: timeline.GetItemListInTrack("audio", idx), []) or []
    if items:
        first_item = items[0]
        first_media = safe(lambda item=first_item: item.GetMediaPoolItem())
        first_track_index = track_index
        break

objects = {{
    "resolve": resolve,
    "project": project,
    "timeline": timeline,
    "audio_item": first_item,
    "media_pool_item": first_media,
}}
method_report = {{}}
write_candidates = {{}}
for label, obj in objects.items():
    methods = interesting_methods(obj)
    method_report[label] = methods[:80]
    write_candidates[label] = possible_write_methods(methods)

timeline_settings = safe(lambda: timeline.GetSetting(), {{}}) or {{}}
project_settings = safe(lambda: project.GetSetting(), {{}}) or {{}}
item_properties = safe(lambda: first_item.GetProperty(), {{}}) if first_item else {{}}
clip_properties = safe(lambda: first_media.GetClipProperty(), {{}}) if first_media else {{}}
sample_calls = {{}}
for label, obj in objects.items():
    calls = {{}}
    for name in method_report.get(label, []):
        if name.startswith("Get") or name.startswith("List"):
            calls[name] = sample_call(obj, name)
    sample_calls[label] = calls

can_insert_or_modify_fx = any(bool(values) for values in write_candidates.values())
if can_insert_or_modify_fx:
    message = "探测到疑似可写音频/Fairlight FX 方法；需要下一步用临时测试片段做写入验证。"
else:
    message = "未探测到公开的音频/Fairlight FX 插入或参数写入方法；当前只能可靠读取音频片段/轨道属性。"

print(json.dumps({{
    "ok": True,
    "message": message,
    "probe": {{
        "resolve_version": safe(lambda: resolve.GetVersionString(), ""),
        "current_page": safe(lambda: resolve.GetCurrentPage(), ""),
        "audio_track_count": track_count,
        "sample_audio_track_index": first_track_index,
        "has_sample_audio_item": first_item is not None,
        "methods": method_report,
        "write_candidates": write_candidates,
        "timeline_audio_setting_keys": [str(key) for key in timeline_settings.keys() if "audio" in str(key).lower()][:40] if isinstance(timeline_settings, dict) else [],
        "project_audio_setting_keys": [str(key) for key in project_settings.keys() if "audio" in str(key).lower()][:40] if isinstance(project_settings, dict) else [],
        "audio_item_property_keys": [str(key) for key in item_properties.keys()][:80] if isinstance(item_properties, dict) else [],
        "media_clip_audio_property_keys": [str(key) for key in clip_properties.keys() if "audio" in str(key).lower() or "channel" in str(key).lower()][:80] if isinstance(clip_properties, dict) else [],
        "sample_calls": sample_calls,
    }},
}}, ensure_ascii=False))
''',
            timeout=45,
        )
        if not data:
            return {"ok": False, "message": "音频 FX API 探测失败：Resolve API 未返回结果。", "probe": {}}
        return data

    def estimate_selected_audio_bpm(
        self,
        timeline_index: int = 1,
        clip_selector: str = "",
        prefer_playhead_clip: bool = False,
        require_selected_audio: bool = False,
    ) -> dict[str, Any]:
        data = self._run_resolve_python(
            rf'''
import json
CLIP_SELECTOR = {json.dumps(clip_selector)}
PREFER_PLAYHEAD_CLIP = {bool(prefer_playhead_clip)!r}
REQUIRE_SELECTED_AUDIO = {bool(require_selected_audio)!r}
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
timeline = project.GetCurrentTimeline() if project else None
if not timeline and project:
    timeline = project.GetTimelineByIndex({int(timeline_index)})
if not timeline:
    print(json.dumps({{"ok": False, "message": "未找到目标时间线。", "clip": {{}}}}, ensure_ascii=False))
    raise SystemExit(0)

def safe(callable_obj, default=None):
    try:
        return callable_obj()
    except Exception:
        return default

def as_items(value):
    if value is None:
        return []
    if isinstance(value, dict):
        return [item for item in value.values() if item]
    if isinstance(value, (list, tuple)):
        return [item for item in value if item]
    return [value]

def read_properties(target):
    if not target:
        return {{}}
    for method_name in ("GetClipProperty", "GetProperty"):
        method = getattr(target, method_name, None)
        if not callable(method):
            continue
        props = safe(lambda method=method: method(), {{}})
        if isinstance(props, dict):
            return props
    return {{}}

def clip_name(item, media_pool_item=None):
    media_pool_item = media_pool_item or safe(lambda: item.GetMediaPoolItem())
    for target, keys in (
        (media_pool_item, ("Clip Name", "File Name", "Name")),
        (item, ("Name",)),
    ):
        props = read_properties(target)
        for key in keys:
            if isinstance(props, dict) and props.get(key):
                return str(props.get(key))
    return str(safe(lambda: item.GetName(), "") or "未命名音频")

def file_path_from_props(props):
    if not isinstance(props, dict):
        return ""
    keys = (
        "File Path", "FilePath", "Path", "Full Path", "FullPath", "Filename", "File Name",
        "Source File", "Source Path", "源文件", "文件路径",
    )
    for key in keys:
        value = props.get(key)
        if value:
            return str(value)
    for key, value in props.items():
        key_text = str(key).lower()
        if ("path" in key_text or "file" in key_text or "文件" in key_text) and value:
            return str(value)
    return ""

def item_track_type(item):
    value = safe(lambda: item.GetTrackTypeAndIndex(), None)
    if isinstance(value, (list, tuple)) and value:
        return str(value[0]).lower()
    if isinstance(value, dict):
        return str(value.get("trackType") or value.get("type") or "").lower()
    props = read_properties(item)
    return str(props.get("Track Type") or props.get("Type") or "").lower()

def item_frame(item, method_name, default=0):
    method = getattr(item, method_name, None)
    if not callable(method):
        return default
    try:
        return int(method() or default)
    except Exception:
        return default

def item_record(item, source, track_index=0, item_index=-1):
    media_pool_item = safe(lambda: item.GetMediaPoolItem())
    item_props = read_properties(item)
    media_props = read_properties(media_pool_item)
    path = file_path_from_props(media_props) or file_path_from_props(item_props)
    unique_id = str(safe(lambda: item.GetUniqueId(), "") or "")
    bpm_props = {{}}
    for props in (item_props, media_props):
        if not isinstance(props, dict):
            continue
        for key, value in props.items():
            lower = str(key).lower()
            if any(token in lower for token in ("bpm", "tempo", "beat", "节拍", "速度")) and value not in (None, ""):
                bpm_props[str(key)] = str(value)
    return {{
        "name": clip_name(item, media_pool_item),
        "path": path,
        "source": source,
        "selector": str(source) + "|" + str(track_index) + "|" + str(item_index) + "|" + unique_id,
        "track_index": int(track_index or 0),
        "item_index": int(item_index or -1),
        "unique_id": unique_id,
        "start_frame": item_frame(item, "GetStart", 0),
        "end_frame": item_frame(item, "GetEnd", 0),
        "source_start_frame": item_frame(item, "GetSourceStartFrame", 0),
        "source_end_frame": item_frame(item, "GetSourceEndFrame", 0),
        "fps": fps,
        "playhead_frame": current_playhead_frame,
        "playhead_timecode": current_tc,
        "bpm_properties": bpm_props,
        "track_type": item_track_type(item),
    }}

current_tc = str(safe(lambda: timeline.GetCurrentTimecode(), "") or "")
fps_raw = safe(lambda: timeline.GetSetting("timelineFrameRate"), None) or safe(lambda: project.GetSetting("timelineFrameRate"), None) or 25
try:
    fps = float(fps_raw)
except Exception:
    fps = 25.0
fps_int = max(1, int(round(fps)))
def tc_to_frames(tc):
    parts = str(tc or "").split(":")
    if len(parts) != 4:
        return None
    try:
        hh, mm, ss, ff = [int(float(part)) for part in parts]
    except Exception:
        return None
    return (((hh * 60) + mm) * 60 + ss) * fps_int + ff
playhead_display_frame = tc_to_frames(current_tc)
timeline_start_frame = int(safe(lambda: timeline.GetStartFrame(), 0) or 0)
start_tc = str(safe(lambda: timeline.GetStartTimecode(), "") or safe(lambda: timeline.GetSetting("timelineStartTimecode"), "") or "00:00:00:00")
start_display = tc_to_frames(start_tc) or 0
current_playhead_frame = None
if playhead_display_frame is not None:
    current_playhead_frame = timeline_start_frame + max(0, playhead_display_frame - start_display)

def selected_audio_items():
    selected = []
    for method_name in ("GetSelectedItems", "GetSelectedClips", "GetSelectedTimelineItems"):
        method = getattr(timeline, method_name, None)
        if not callable(method):
            continue
        for item in as_items(safe(lambda method=method: method(), [])):
            track_type = item_track_type(item)
            if "audio" in track_type or not track_type:
                selected.append((item, method_name, 0, -1))
    return selected

selected_items = selected_audio_items()
playhead_items = []
for track_index in range(1, int(safe(lambda: timeline.GetTrackCount("audio"), 0) or 0) + 1):
    for item_index, item in enumerate(as_items(safe(lambda idx=track_index: timeline.GetItemListInTrack("audio", idx), []))):
        start = item_frame(item, "GetStart", 0)
        end = item_frame(item, "GetEnd", start)
        if current_playhead_frame is not None and start <= current_playhead_frame < end:
            playhead_items.append((item, "playhead_audio_clip", track_index, item_index))

items = selected_items
source_label = "selected"
if REQUIRE_SELECTED_AUDIO:
    if selected_items:
        items = selected_items
        source_label = "selected"
    elif len(playhead_items) == 1:
        items = playhead_items
        source_label = "playhead"
    elif len(playhead_items) > 1:
        print(json.dumps({{
            "ok": False,
            "needs_selection": True,
            "message": "播放头下有多条音频，请先用鼠标选中要识别的音乐音频。",
            "clip": {{}},
            "source_mode": "playhead_multiple",
        }}, ensure_ascii=False))
        raise SystemExit(0)
    else:
        items = []
        source_label = "selected"
elif PREFER_PLAYHEAD_CLIP and playhead_items:
    selected_under_playhead = []
    for item, method_name, track_index, item_index in selected_items:
        start = item_frame(item, "GetStart", 0)
        end = item_frame(item, "GetEnd", start)
        if current_playhead_frame is not None and start <= current_playhead_frame < end:
            selected_under_playhead.append((item, method_name, track_index, item_index))
    items = selected_under_playhead or playhead_items
    source_label = "selected" if selected_under_playhead else "playhead"
elif not items:
    items = playhead_items
    source_label = "playhead"

if not items:
    print(json.dumps({{
        "ok": False,
        "needs_selection": True,
        "message": "请先用鼠标在时间线选中一段音乐音频；如果未选中，播放头需要停在唯一一条音乐音频上。",
        "clip": {{}},
    }}, ensure_ascii=False))
    raise SystemExit(0)

records = [item_record(item, source, track_index, item_index) for item, source, track_index, item_index in items]
def record_source_duration(record):
    try:
        duration = int(record.get("source_end_frame") or 0) - int(record.get("source_start_frame") or 0)
    except Exception:
        duration = 0
    if duration <= 0:
        try:
            duration = int(record.get("end_frame") or 0) - int(record.get("start_frame") or 0)
        except Exception:
            duration = 0
    return max(0, duration)

def record_timeline_duration(record):
    try:
        return max(0, int(record.get("end_frame") or 0) - int(record.get("start_frame") or 0))
    except Exception:
        return 0

records.sort(key=lambda record: (record_source_duration(record), record_timeline_duration(record)), reverse=True)
if CLIP_SELECTOR:
    filtered = [record for record in records if str(record.get("selector", "")) == CLIP_SELECTOR]
    if filtered:
        records = filtered
if not CLIP_SELECTOR and len(records) > 1 and not (REQUIRE_SELECTED_AUDIO or PREFER_PLAYHEAD_CLIP):
    print(json.dumps({{
        "ok": False,
        "needs_selection": True,
        "message": "播放头下有 " + str(len(records)) + " 条音频，请选择要识别 BPM 的音乐片段。",
        "candidates": records,
        "clip": {{}},
        "source_mode": source_label,
    }}, ensure_ascii=False))
    raise SystemExit(0)

record = records[0]
api_bpm = ""
for value in record.get("bpm_properties", {{}}).values():
    if value:
        api_bpm = str(value)
        break
message = "Resolve 属性里找到了 BPM/Tempo 字段。" if api_bpm else (
    "Resolve API 未公开 BPM 识别字段；将使用 Essentia 解码音频识别节拍，失败时回退 FFmpeg 轻量估算。"
)
if source_label == "playhead":
    message += " 当前版本未读取到选中音频，已改用播放头所在音频片段。"
print(json.dumps({{
    "ok": True,
    "message": message,
    "clip": record,
    "api_bpm": api_bpm,
    "source_mode": source_label,
}}, ensure_ascii=False))
''',
            timeout=30,
        )
        if not data:
            return {"ok": False, "message": "BPM 探测失败：Resolve API 未返回结果。", "clip": {}}
        if not data.get("ok"):
            return data
        api_bpm = str(data.get("api_bpm") or "").strip()
        if api_bpm:
            data["bpm"] = api_bpm
            data["method"] = "resolve_property"
            return data
        clip = data.get("clip") if isinstance(data.get("clip"), dict) else {}
        path = str(clip.get("path") or "").strip()
        if not path or not Path(path).exists():
            data["ok"] = False
            data["message"] = "已定位音频片段，但 Resolve 没有返回可访问的源文件路径，无法用 FFmpeg 估算 BPM。"
            return data
        try:
            fps = float(clip.get("fps") or 25.0)
        except Exception:
            fps = 25.0
        fps = fps if fps > 0 else 25.0
        try:
            source_start_frame = int(float(clip.get("source_start_frame") or 0))
            source_end_frame = int(float(clip.get("source_end_frame") or 0))
            timeline_start_frame = int(float(clip.get("start_frame") or 0))
            timeline_end_frame = int(float(clip.get("end_frame") or 0))
        except Exception:
            source_start_frame = source_end_frame = timeline_start_frame = timeline_end_frame = 0
        source_range_known = source_end_frame > source_start_frame
        if source_range_known:
            duration_frames = max(0, source_end_frame - source_start_frame)
            start_seconds = max(0.0, source_start_frame / fps)
            duration_seconds = max(0.0, duration_frames / fps)
        else:
            # Resolve often does not expose audio source in/out for cut timeline items.
            # In that case trimming from source file 0s gives the wrong BPM for later cuts.
            start_seconds = 0.0
            duration_seconds = 0.0
            clip["source_range_known"] = False
        estimate = self._estimate_bpm_with_essentia(Path(path), start_seconds, duration_seconds)
        if not estimate.get("ok"):
            fallback = self._estimate_bpm_with_ffmpeg(Path(path))
            if fallback.get("ok"):
                fallback["essentia_message"] = str(estimate.get("message", "Essentia 不可用。"))
                estimate = fallback
        data.update(estimate)
        if estimate.get("ok"):
            data["message"] = f"BPM 估算完成：约 {estimate.get('bpm')} BPM。"
            if estimate.get("method") == "essentia_rhythm_extractor":
                data["message"] = f"Essentia 节拍识别完成：约 {estimate.get('bpm')} BPM，检测到 {len(estimate.get('beat_times_seconds') or [])} 个 beat 点。"
            if data.get("source_mode") == "playhead":
                data["message"] += " 当前 Resolve 未返回选中音频，使用播放头所在音频片段。"
        else:
            data["message"] = str(estimate.get("message", "BPM 估算失败。"))
        return data

    def _estimate_bpm_with_essentia(self, path: Path, start_seconds: float = 0.0, duration_seconds: float = 0.0) -> dict[str, Any]:
        if getattr(sys, "frozen", False):
            worker = self._find_bpm_worker_binary()
            if not worker:
                system_python = self._find_fast_bpm_python()
                if system_python:
                    return self._run_bpm_worker_with_python(system_python, path, start_seconds, duration_seconds)
                return {"ok": False, "message": "未找到内置 Essentia BPM Worker，已回退轻量 BPM 算法。"}
            try:
                cmd = [
                    worker,
                    str(path),
                    "--start-seconds",
                    f"{max(0.0, float(start_seconds)):.6f}",
                    "--duration-seconds",
                    f"{max(0.0, float(duration_seconds)):.6f}",
                ]
                ffmpeg = self._find_ffmpeg_binary()
                if ffmpeg:
                    cmd.extend(["--ffmpeg", ffmpeg])
                proc = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=90,
                    **hidden_subprocess_kwargs(),
                )
            except Exception as exc:
                return {"ok": False, "message": f"Essentia BPM Worker 启动失败：{exc}"}
            output = proc.stdout.decode("utf-8", errors="ignore").strip()
            error = proc.stderr.decode("utf-8", errors="ignore").strip()
            if proc.returncode != 0:
                return {
                    "ok": False,
                    "message": "Essentia BPM Worker 运行失败。"
                    + (f" {error[:160]}" if error else ""),
                }
            try:
                data = json.loads(output)
            except Exception:
                return {
                    "ok": False,
                    "message": "Essentia BPM Worker 未返回有效结果。"
                    + (f" {error[:160]}" if error else ""),
                }
            if isinstance(data, dict):
                data.setdefault("worker", worker)
                data.setdefault("worker_mode", "bundled_python")
                return data
            return {"ok": False, "message": "Essentia BPM Worker 返回结果格式异常。"}
        try:
            import importlib

            es = importlib.import_module("essentia.standard")
        except Exception:
            return {"ok": False, "message": "未安装 Essentia，已回退轻量 BPM 算法。"}
        try:
            audio = es.MonoLoader(filename=str(path), sampleRate=44100)()
            rhythm_extractor = es.RhythmExtractor2013(method="multifeature")
            bpm, beats, beats_confidence, _estimates, _intervals = rhythm_extractor(audio)
        except Exception as exc:
            return {"ok": False, "message": f"Essentia 节拍识别失败：{exc}"}
        beat_times = [float(value) for value in list(beats) if float(value) >= 0]
        if not beat_times:
            return {"ok": False, "message": "Essentia 未检测到 beat 点。"}
        quality = beat_quality(beat_times)
        return {
            "ok": True,
            "bpm": round(float(bpm), 2),
            "confidence": round(float(beats_confidence or 0.0), 2),
            "method": "essentia_rhythm_extractor",
            "beat_times_seconds": beat_times[:4000],
            **quality,
            "alternatives": [],
        }

    def _run_bpm_worker_with_python(self, python_path: str, path: Path, start_seconds: float, duration_seconds: float) -> dict[str, Any]:
        worker_script = Path(__file__).resolve().with_name("bpm_worker.py")
        cmd = [
            python_path,
            str(worker_script),
            str(path),
            "--start-seconds",
            f"{max(0.0, float(start_seconds)):.6f}",
            "--duration-seconds",
            f"{max(0.0, float(duration_seconds)):.6f}",
        ]
        ffmpeg = self._find_ffmpeg_binary()
        if ffmpeg:
            cmd.extend(["--ffmpeg", ffmpeg])
        env = os.environ.copy()
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
                env=env,
                **hidden_subprocess_kwargs(),
            )
        except Exception as exc:
            return {"ok": False, "message": f"系统 Python BPM Worker 启动失败：{exc}"}
        output = proc.stdout.decode("utf-8", errors="ignore").strip()
        error = proc.stderr.decode("utf-8", errors="ignore").strip()
        try:
            data = json.loads(output) if output else {}
        except Exception:
            data = {}
        if proc.returncode == 0 and isinstance(data, dict) and data.get("ok"):
            data.setdefault("worker", python_path)
            data.setdefault("worker_mode", "system_python_fallback")
            return data
        return {"ok": False, "message": str(data.get("message") or error[:160] or "系统 Python BPM Worker 未返回有效结果。")}

    def _find_fast_bpm_python(self) -> str:
        if getattr(self, "_fast_bpm_python_checked", False):
            return str(getattr(self, "_fast_bpm_python", "") or "")
        candidates = [
            os.environ.get("QINGHE_BPM_PYTHON", ""),
            "/Library/Developer/CommandLineTools/usr/bin/python3",
            shutil.which("python3") or "",
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            "/usr/bin/python3",
        ]
        seen: set[str] = set()
        current_executable = str(Path(sys.executable).resolve()) if sys.executable else ""
        for candidate in candidates:
            if not candidate:
                continue
            path = str(Path(candidate).expanduser())
            if path in seen or not Path(path).exists():
                continue
            seen.add(path)
            try:
                if current_executable and str(Path(path).resolve()) == current_executable:
                    continue
            except Exception:
                pass
            env = os.environ.copy()
            env.pop("PYTHONHOME", None)
            env.pop("PYTHONPATH", None)
            try:
                proc = subprocess.run(
                    [path, "-c", "import essentia.standard"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=4,
                    env=env,
                    **hidden_subprocess_kwargs(),
                )
            except Exception:
                continue
            if proc.returncode == 0:
                self._fast_bpm_python = path
                self._fast_bpm_python_checked = True
                return path
        self._fast_bpm_python = ""
        self._fast_bpm_python_checked = True
        return ""

    def _find_bpm_worker_binary(self) -> str:
        names = ["QingheBPMWorker.exe", "QingheBPMWorker"] if platform.system().lower() == "windows" else ["QingheBPMWorker"]
        roots: list[Path] = []
        try:
            roots.append(Path(sys.executable).resolve().parent)
        except Exception:
            pass
        try:
            roots.append(Path(__file__).resolve().parent)
        except Exception:
            pass
        expanded: list[Path] = []
        for root in roots:
            expanded.extend([root, root.parent])
        for root in expanded:
            for name in names:
                candidate = root / "QingheBPMWorker" / name
                if candidate.exists() and os.access(candidate, os.X_OK):
                    return str(candidate)
        return ""

    def probe_media_pool_api(self, timeline_index: int = 1) -> dict[str, Any]:
        data = self._run_resolve_python(
            rf'''
import json
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
media_pool = project.GetMediaPool() if project else None
timeline = project.GetTimelineByIndex({int(timeline_index)}) if project else None

def safe(callable_obj, default=None):
    try:
        return callable_obj()
    except Exception as exc:
        return default

def trim(value, max_len=160):
    text = str(value)
    return text if len(text) <= max_len else text[:max_len] + "...<截断>"

def method_names(target, limit=120):
    if not target:
        return []
    names = []
    tokens = (
        "media", "pool", "folder", "clip", "item", "marker", "property", "metadata",
        "audio", "timeline", "append", "import", "export", "selected", "current",
        "track", "take", "color", "flag",
    )
    for name in dir(target):
        if name.startswith("_"):
            continue
        lower = name.lower()
        if any(token in lower for token in tokens):
            attr = safe(lambda name=name: getattr(target, name), None)
            if callable(attr):
                names.append(str(name))
    return sorted(set(names))[:limit]

def as_list(value):
    if value is None:
        return []
    if isinstance(value, dict):
        return [item for item in value.values() if item]
    if isinstance(value, (list, tuple)):
        return [item for item in value if item]
    return [value]

def read_props(target, limit_keys=80):
    props = {{}}
    if not target:
        return props
    for method_name in ("GetClipProperty", "GetProperty", "GetMetadata"):
        method = getattr(target, method_name, None)
        if not callable(method):
            continue
        value = safe(lambda method=method: method(), None)
        if isinstance(value, dict):
            props = value
            break
    result = {{}}
    for idx, (key, value) in enumerate(props.items() if isinstance(props, dict) else []):
        if idx >= limit_keys:
            break
        result[str(key)] = trim(value)
    return result

def folder_clips(folder, limit=8):
    clips = []
    if not folder:
        return clips
    for method_name in ("GetClipList", "GetClips"):
        method = getattr(folder, method_name, None)
        if callable(method):
            clips = as_list(safe(lambda method=method: method(), []))
            if clips:
                break
    return clips[:limit]

def folder_children(folder, limit=12):
    folders = []
    if not folder:
        return folders
    for method_name in ("GetSubFolderList", "GetSubFolders"):
        method = getattr(folder, method_name, None)
        if callable(method):
            folders = as_list(safe(lambda method=method: method(), []))
            if folders:
                break
    names = []
    for folder_item in folders[:limit]:
        names.append(trim(safe(lambda folder_item=folder_item: folder_item.GetName(), "未命名文件夹")))
    return names

def clip_record(clip):
    props = read_props(clip, 60)
    name = ""
    for key in ("Clip Name", "File Name", "Name"):
        if props.get(key):
            name = str(props.get(key))
            break
    if not name:
        name = trim(safe(lambda: clip.GetName(), "未命名素材"))
    useful = {{}}
    for key, value in props.items():
        lower = str(key).lower()
        if any(token in lower for token in ("name", "file", "path", "duration", "frames", "resolution", "fps", "audio", "channel", "type")):
            useful[key] = value
    return {{
        "name": name,
        "media_id": trim(safe(lambda: clip.GetMediaId(), "")),
        "clip_color": trim(safe(lambda: clip.GetClipColor(), "")),
        "property_keys": list(props.keys())[:80],
        "useful_properties": useful,
        "methods": method_names(clip, 90),
    }}

root_folder = safe(lambda: media_pool.GetRootFolder(), None) if media_pool else None
current_folder = safe(lambda: media_pool.GetCurrentFolder(), None) if media_pool else None
selected_clips = []
for method_name in ("GetSelectedClips", "GetSelectedItems", "GetSelectedMediaPoolItems"):
    method = getattr(media_pool, method_name, None) if media_pool else None
    if callable(method):
        selected_clips = as_list(safe(lambda method=method: method(), []))
        if selected_clips:
            break

root_clips = folder_clips(root_folder)
current_clips = folder_clips(current_folder)
sample_clips = selected_clips[:5] or current_clips[:5] or root_clips[:5]

timeline_audio_item = None
timeline_video_item = None
if timeline:
    for track_type, holder in (("audio", "audio"), ("video", "video")):
        count = int(safe(lambda track_type=track_type: timeline.GetTrackCount(track_type), 0) or 0)
        for track_index in range(1, count + 1):
            items = safe(lambda track_type=track_type, track_index=track_index: timeline.GetItemListInTrack(track_type, track_index), []) or []
            if items:
                if track_type == "audio":
                    timeline_audio_item = items[0]
                else:
                    timeline_video_item = items[0]
                break

timeline_samples = []
for item in (timeline_video_item, timeline_audio_item):
    if not item:
        continue
    mpi = safe(lambda item=item: item.GetMediaPoolItem(), None)
    timeline_samples.append({{
        "timeline_item_name": trim(safe(lambda item=item: item.GetName(), "未命名时间线片段")),
        "timeline_item_methods": method_names(item, 80),
        "timeline_item_property_keys": list(read_props(item, 50).keys()),
        "media_pool_item": clip_record(mpi) if mpi else {{}},
    }})

result = {{
    "ok": True,
    "message": "媒体池/API 探针完成。",
    "source": "MediaPool / Folder / MediaPoolItem / TimelineItem diagnostic probe",
    "resolve_version": trim(safe(lambda: resolve.GetVersionString(), "")) if resolve else "",
    "project_name": trim(safe(lambda: project.GetName(), "")) if project else "",
    "timeline": {{
        "name": trim(safe(lambda: timeline.GetName(), "")) if timeline else "",
        "fps": trim(safe(lambda: timeline.GetSetting("timelineFrameRate"), "")) if timeline else "",
        "start_frame": safe(lambda: timeline.GetStartFrame(), None) if timeline else None,
        "start_timecode": trim(safe(lambda: timeline.GetStartTimecode(), "")) if timeline else "",
    }},
    "media_pool_methods": method_names(media_pool, 140),
    "root_folder": {{
        "name": trim(safe(lambda: root_folder.GetName(), "")) if root_folder else "",
        "methods": method_names(root_folder, 100),
        "subfolders": folder_children(root_folder),
        "sample_clips": [clip_record(clip) for clip in root_clips[:5]],
    }},
    "current_folder": {{
        "name": trim(safe(lambda: current_folder.GetName(), "")) if current_folder else "",
        "methods": method_names(current_folder, 100),
        "subfolders": folder_children(current_folder),
        "sample_clips": [clip_record(clip) for clip in current_clips[:5]],
    }},
    "selected_media_pool_clips": [clip_record(clip) for clip in selected_clips[:5]],
    "sample_media_pool_clips": [clip_record(clip) for clip in sample_clips[:5]],
    "timeline_samples": timeline_samples,
    "capabilities": {{
        "has_media_pool": media_pool is not None,
        "has_root_folder": root_folder is not None,
        "selected_clip_count": len(selected_clips),
        "root_sample_count": len(root_clips),
        "current_sample_count": len(current_clips),
        "can_append_to_timeline": "AppendToTimeline" in method_names(media_pool, 200),
        "can_import_timeline_from_file": "ImportTimelineFromFile" in method_names(media_pool, 200),
        "can_read_selected_media_pool": len(selected_clips) > 0,
    }},
}}
print(json.dumps(result, ensure_ascii=False))
''',
            timeout=45,
        )
        if not data:
            return {"ok": False, "message": "媒体池/API 探针失败：Resolve API 未返回结果。"}
        return data

    def add_bpm_grid_markers(
        self,
        timeline_index: int,
        bpm: float,
        start_frame: int,
        end_frame: int,
        clip_name: str = "",
        start_bpm: float = 120.0,
        tightness: float = 100.0,
        hop_length: int = 512,
        marker_scope: str = "clip",
        clip_track_index: int = 0,
        clip_item_index: int = -1,
        clip_unique_id: str = "",
        beat_offset_seconds: float = 0.0,
        source_start_frame: int = 0,
        beat_times_seconds: list[float] | None = None,
        beat_marker_step: int = 4,
        beat_marker_phase: int = 1,
        first_beat_anchor_frame: int | None = None,
        force_grid_markers: bool = False,
    ) -> dict[str, Any]:
        data = self._run_resolve_python(
            rf'''
import json
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
timeline = project.GetCurrentTimeline() if project else None
if not timeline and project:
    timeline = project.GetTimelineByIndex({int(timeline_index)})
if not timeline:
    print(json.dumps({{"ok": False, "message": "未找到目标时间线。"}}, ensure_ascii=False))
    raise SystemExit(0)

def safe(callable_obj, default=None):
    try:
        return callable_obj()
    except Exception:
        return default

def as_items(value):
    if value is None:
        return []
    if isinstance(value, dict):
        return [item for item in value.values() if item]
    if isinstance(value, (list, tuple)):
        return [item for item in value if item]
    return [value]

bpm = float({float(bpm)})
start_frame = int({int(start_frame)})
end_frame = int({int(end_frame)})
clip_name = {json.dumps(clip_name)}
start_bpm = float({float(start_bpm)})
tightness = float({float(tightness)})
hop_length = int({int(hop_length)})
marker_scope = {json.dumps(marker_scope)}
clip_track_index = int({int(clip_track_index)})
clip_item_index = int({int(clip_item_index)})
clip_unique_id = {json.dumps(clip_unique_id)}
source_start_frame = int({int(source_start_frame)})
beat_times_seconds = json.loads({json.dumps(json.dumps(beat_times_seconds or [], ensure_ascii=False))})
beat_marker_step = max(1, int({int(beat_marker_step)}))
beat_marker_phase = max(1, int({int(beat_marker_phase)}))
first_beat_anchor_frame = {json.dumps(first_beat_anchor_frame)}
force_grid_markers = {bool(force_grid_markers)!r}
fps_raw = safe(lambda: timeline.GetSetting("timelineFrameRate"), None) or safe(lambda: project.GetSetting("timelineFrameRate"), None) or 25
try:
    fps = float(fps_raw)
except Exception:
    fps = 25.0
if bpm <= 0 or end_frame <= start_frame:
    print(json.dumps({{"ok": False, "message": "BPM 或音频区间无效，未写入节拍标记。"}}, ensure_ascii=False))
    raise SystemExit(0)

prefix = "[QH-BPM]"

def marker_custom(marker):
    if not isinstance(marker, dict):
        return ""
    return str(marker.get("customData", "") or marker.get("custom_data", "") or "")

def is_bpm_marker(marker):
    if not isinstance(marker, dict):
        return False
    return str(marker.get("name", "")).startswith(prefix) or marker_custom(marker).startswith("QH-BPM")

def delete_matching_markers(target):
    removed_count = 0
    failed_count = 0
    get_markers = getattr(target, "GetMarkers", None)
    delete_marker = getattr(target, "DeleteMarkerAtFrame", None)
    delete_custom = getattr(target, "DeleteMarkerByCustomData", None)
    if not callable(get_markers) or not callable(delete_marker):
        return removed_count, failed_count
    for frame_id, marker in list((safe(lambda: get_markers(), {{}}) or {{}}).items()):
        if not is_bpm_marker(marker):
            continue
        try:
            try:
                target_frame = int(float(frame_id))
            except Exception:
                target_frame = frame_id
            if delete_marker(target_frame):
                removed_count += 1
            elif callable(delete_custom) and marker_custom(marker) and delete_custom(marker_custom(marker)):
                removed_count += 1
            else:
                failed_count += 1
        except Exception:
            failed_count += 1
    return removed_count, failed_count

def collect_manual_restart_markers(target, frame_offset=0, source_offset=0):
    anchors = []
    get_markers = getattr(target, "GetMarkers", None)
    if not callable(get_markers):
        return anchors
    for frame_id, marker in list((safe(lambda: get_markers(), {{}}) or {{}}).items()):
        if is_bpm_marker(marker):
            continue
        try:
            frame = int(float(frame_id)) - int(source_offset) + int(frame_offset)
        except Exception:
            continue
        if int(start_frame) <= frame <= int(end_frame):
            anchors.append(frame)
    return sorted(set(anchors))

def item_frame(item, method_name, default=0):
    method = getattr(item, method_name, None)
    if not callable(method):
        return default
    try:
        return int(method() or default)
    except Exception:
        return default

def item_unique_id(item):
    return str(safe(lambda: item.GetUniqueId(), "") or "")

def find_target_audio_clip():
    track_count = int(safe(lambda: timeline.GetTrackCount("audio"), 0) or 0)
    for track_index in range(1, track_count + 1):
        items = as_items(safe(lambda idx=track_index: timeline.GetItemListInTrack("audio", idx), []))
        for item_index, item in enumerate(items):
            if not item:
                continue
            if clip_unique_id and item_unique_id(item) == clip_unique_id:
                return item
            if clip_track_index == track_index and clip_item_index == item_index:
                return item
            start = item_frame(item, "GetStart", 0)
            end = item_frame(item, "GetEnd", start)
            if start == start_frame and end == end_frame:
                return item
    return None

removed = 0
failed_clear = 0
target = timeline
target_clip = find_target_audio_clip()
target_clip_left_offset = item_frame(target_clip, "GetLeftOffset", 0) if target_clip else 0
if marker_scope == "clip":
    target = target_clip
    if not target_clip:
        print(json.dumps({{"ok": False, "message": "未找到要写入节拍标记的音频片段。请重新选择音乐片段或把播放头停在片段上。", "marker_scope": marker_scope}}, ensure_ascii=False))
        raise SystemExit(0)
manual_restart_frames = []
if target_clip:
    manual_restart_frames.extend(collect_manual_restart_markers(target_clip, start_frame, target_clip_left_offset))
manual_restart_frames.extend(collect_manual_restart_markers(timeline, 0))
manual_restart_frames = sorted(set(manual_restart_frames))
timeline_removed, timeline_failed_clear = delete_matching_markers(timeline)
clip_removed, clip_failed_clear = (0, 0)
if target_clip:
    clip_removed, clip_failed_clear = delete_matching_markers(target_clip)
removed = timeline_removed + clip_removed
failed_clear = timeline_failed_clear + clip_failed_clear

interval = max(1.0, fps * 60.0 / bpm)
marker_spacing_frames = interval * beat_marker_step
count = 0
max_markers = 2000
phase_offset = (beat_marker_phase - 1) % beat_marker_step
anchor_frame = float(start_frame)
anchor_valid = False
try:
    candidate_anchor = int(float(first_beat_anchor_frame))
except Exception:
    candidate_anchor = None
if candidate_anchor is not None and int(start_frame) <= candidate_anchor < int(end_frame):
    anchor_frame = float(candidate_anchor)
    anchor_valid = True

marker_frames = []
beat_anchor_index = None
beat_frame_shift = 0
beat_segment_count = 0
breath_gap_count = 0
anchor_snap_delta_frames = 0
beat_snap_points = []
if isinstance(beat_times_seconds, list) and beat_times_seconds:
    for beat_second in beat_times_seconds:
        try:
            beat_frame = int(round(float(start_frame) + (float(beat_second) * fps) - float(source_start_frame or 0)))
        except Exception:
            continue
        if int(start_frame) - int(interval) <= beat_frame <= int(end_frame) + int(interval):
            beat_snap_points.append(beat_frame)
    beat_snap_points = sorted(set(beat_snap_points))
if anchor_valid and beat_snap_points:
    anchor_int_for_snap = int(round(anchor_frame))
    nearest_anchor = min(beat_snap_points, key=lambda frame: abs(frame - anchor_int_for_snap))
    anchor_snap_tolerance = max(4.0, interval * 0.45)
    if abs(nearest_anchor - anchor_int_for_snap) <= anchor_snap_tolerance:
        anchor_snap_delta_frames = int(nearest_anchor - anchor_int_for_snap)
        anchor_frame = float(nearest_anchor)

if (not force_grid_markers) and isinstance(beat_times_seconds, list) and beat_times_seconds:
    detected_frames = []
    for beat_index, beat_second in enumerate(beat_times_seconds):
        try:
            detected_frame = int(round(float(start_frame) + (float(beat_second) * fps) - float(source_start_frame or 0)))
        except Exception:
            continue
        if int(start_frame) - int(interval) <= detected_frame <= int(end_frame) + int(interval):
            detected_frames.append((beat_index, detected_frame))
    if detected_frames:
        anchor_int = int(round(anchor_frame))
        detected_points = sorted(set(int(frame) for _idx, frame in detected_frames))
        min_spacing = max(1.0, interval * 0.55)
        def dedupe_beat_points(points):
            result = []
            for frame in sorted(set(int(point) for point in points)):
                if result and abs(frame - result[-1]) < min_spacing:
                    if anchor_valid and abs(frame - anchor_int) < abs(result[-1] - anchor_int):
                        result[-1] = frame
                    continue
                result.append(frame)
            return result

        normalized_points = dedupe_beat_points(detected_points)

        gaps = [normalized_points[idx + 1] - normalized_points[idx] for idx in range(len(normalized_points) - 1)]
        normal_gaps = sorted(
            gap for gap in gaps
            if max(1.0, interval * 0.45) <= gap <= max(interval * 1.65, interval + 6)
        )
        if normal_gaps:
            normal_interval = float(normal_gaps[len(normal_gaps) // 2])
        else:
            normal_interval = interval
        breath_gap_threshold = max(normal_interval * 1.85, interval * 1.85, normal_interval + 10)
        anchor_snap_tolerance = max(6.0, normal_interval * 0.45)

        if anchor_valid:
            closest_index, closest_frame = min(
                enumerate(normalized_points),
                key=lambda item: abs(item[1] - anchor_int),
            )
            beat_anchor_index = int(closest_index)
            beat_frame_shift = anchor_int - int(closest_frame)
            if abs(int(closest_frame) - anchor_int) <= anchor_snap_tolerance:
                shifted_points = []
                for frame in normalized_points:
                    shifted_frame = int(frame) + int(beat_frame_shift)
                    if int(start_frame) - int(interval) <= shifted_frame <= int(end_frame) + int(interval):
                        shifted_points.append(shifted_frame)
                if int(start_frame) <= anchor_int <= int(end_frame):
                    shifted_points.append(anchor_int)
                normalized_points = dedupe_beat_points(shifted_points)
                if anchor_int in normalized_points:
                    beat_anchor_index = normalized_points.index(anchor_int)
            elif int(start_frame) <= anchor_int <= int(end_frame):
                normalized_points.append(anchor_int)
                normalized_points = dedupe_beat_points(normalized_points)
                beat_anchor_index = normalized_points.index(anchor_int)
                beat_frame_shift = 0

        segments = []
        current_segment = []
        for frame in normalized_points:
            if not current_segment:
                current_segment = [frame]
                continue
            gap = frame - current_segment[-1]
            if gap > breath_gap_threshold:
                segments.append(current_segment)
                current_segment = [frame]
                breath_gap_count += 1
            else:
                current_segment.append(frame)
        if current_segment:
            segments.append(current_segment)
        beat_segment_count = len(segments)

        for segment in segments:
            if not segment:
                continue
            segment_anchor_index = None
            if anchor_valid and segment[0] <= anchor_int <= segment[-1]:
                try:
                    segment_anchor_index = segment.index(anchor_int)
                except ValueError:
                    segment_anchor_index, _nearest = min(
                        enumerate(segment),
                        key=lambda item: abs(item[1] - anchor_int),
                    )
            if segment_anchor_index is None:
                segment_anchor_index = 0
            for idx, marker_frame in enumerate(segment):
                if (idx - segment_anchor_index) % beat_marker_step != 0:
                    continue
                if marker_frame < int(start_frame) or marker_frame > int(end_frame):
                    continue
                if marker_frame not in marker_frames:
                    marker_frames.append(marker_frame)
                if len(marker_frames) >= max_markers:
                    break
            if len(marker_frames) >= max_markers:
                break
elif anchor_valid:
    marker_spacing = marker_spacing_frames
    grid_anchors = sorted(set(
        int(frame)
        for frame in [int(round(anchor_frame)), *manual_restart_frames]
        if int(start_frame) <= int(frame) <= int(end_frame)
    ))
    if not grid_anchors:
        grid_anchors = [int(round(anchor_frame))]
    for anchor_index, grid_anchor in enumerate(grid_anchors):
        left_bound = int(start_frame) if anchor_index == 0 else grid_anchors[anchor_index - 1] + 1
        right_bound = int(end_frame) if anchor_index == len(grid_anchors) - 1 else grid_anchors[anchor_index + 1] - 1
        frame = float(grid_anchor)
        while frame >= float(left_bound) and len(marker_frames) < max_markers:
            marker = int(round(frame))
            if marker not in marker_frames:
                marker_frames.append(marker)
            frame -= marker_spacing
        frame = float(grid_anchor) + marker_spacing
        while frame <= float(right_bound) and len(marker_frames) < max_markers:
            marker = int(round(frame))
            if marker not in marker_frames:
                marker_frames.append(marker)
            frame += marker_spacing
        if len(marker_frames) >= max_markers:
            break
    marker_frames.sort()
elif isinstance(beat_times_seconds, list) and beat_times_seconds:
    try:
        beat_origin_seconds = float(beat_times_seconds[0])
    except Exception:
        beat_origin_seconds = 0.0
    for beat_index, beat_second in enumerate(beat_times_seconds):
        if beat_index % beat_marker_step != phase_offset:
            continue
        try:
            source_frame = max(0.0, float(beat_second) - beat_origin_seconds) * fps
        except Exception:
            continue
        marker_frame = int(round(anchor_frame + source_frame))
        if marker_frame < int(start_frame) or marker_frame > int(end_frame):
            continue
        if marker_frame not in marker_frames:
            marker_frames.append(marker_frame)
        if len(marker_frames) >= max_markers:
            break
else:
    frame = anchor_frame + (interval * phase_offset)
    while frame <= float(end_frame) and len(marker_frames) < max_markers:
        marker_frames.append(int(round(frame)))
        frame += interval * beat_marker_step

if anchor_valid:
    anchor_int = int(round(anchor_frame))
    if int(start_frame) <= anchor_int <= int(end_frame) and anchor_int not in marker_frames:
        marker_frames.append(anchor_int)
        marker_frames.sort()

clip_color_changed = False

for marker_frame in marker_frames:
    marker_frame = int(marker_frame)
    note = "clip=%s | bpm=%.2f | start-bpm=%.1f | tightness=%.1f | hop=%d" % (
        clip_name, bpm, start_bpm, tightness, hop_length
    )
    custom = "QH-BPM|%s|%.4f|%s" % (marker_scope, bpm, clip_name)
    target_frame = marker_frame
    if marker_scope == "clip":
        target_frame = max(0, marker_frame - start_frame + target_clip_left_offset)
    ok = False
    for args in (
        (target_frame, "Yellow", prefix + " Beat", note, 1, custom),
        (target_frame, "Yellow", prefix + " Beat", note, 1),
    ):
        try:
            ok = bool(target.AddMarker(*args))
        except Exception:
            ok = False
        if ok:
            break
    if ok:
        count += 1
if marker_scope == "clip" and count == 0:
    print(json.dumps({{
        "ok": False,
        "message": "当前 Resolve 没有接受音频片段 AddMarker，未写入节拍标记。可切回“标到时间线”。",
        "marker_scope": marker_scope,
        "marker_count": 0,
        "removed_old_markers": removed,
        "failed_clear": failed_clear,
    }}, ensure_ascii=False))
    raise SystemExit(0)
target_label = "音频片段" if marker_scope == "clip" else "时间线"
if manual_restart_frames and anchor_valid:
    beat_source_label = "手动段落锚点+BPM分段网格"
elif force_grid_markers and isinstance(beat_times_seconds, list) and beat_times_seconds:
    beat_source_label = "播放头锚点吸附+BPM稳定网格"
elif isinstance(beat_times_seconds, list) and beat_times_seconds:
    if anchor_valid:
        beat_source_label = "真实 beat 点+播放头重拍校准+气口分段重启"
    else:
        beat_source_label = "真实 beat 点+气口分段重启"
elif anchor_valid:
    beat_source_label = "播放头锚点+BPM网格兜底"
else:
    beat_source_label = "BPM网格"
first_marker_delta = marker_frames[0] - int(start_frame) if marker_frames else 0
anchor_delta = int(round(anchor_frame)) - int(start_frame)
message = "已在%s生成 %d 个节拍标记；来源 %s，每 %d 拍约 %.2f 帧标一次，锚点本身会被标记，锚点距片段起点 %d 帧，识别段落 %d 段/气口 %d 处。已清理旧节拍标记 %d 个；不会修改片段颜色。" % (target_label, count, beat_source_label, beat_marker_step, marker_spacing_frames, anchor_delta, beat_segment_count, breath_gap_count, removed)
print(json.dumps({{
    "ok": True,
    "message": message,
    "marker_count": count,
    "removed_old_markers": removed,
    "failed_clear": failed_clear,
    "interval_frames": round(interval, 2),
    "marker_spacing_frames": round(marker_spacing_frames, 2),
    "bpm": bpm,
    "fps": fps,
    "marker_scope": marker_scope,
    "first_marker_delta_frames": round(first_marker_delta, 2),
    "first_beat_anchor_frame": int(round(anchor_frame)),
    "first_beat_anchor_delta_frames": anchor_delta,
    "beat_anchor_index": beat_anchor_index,
    "beat_frame_shift": beat_frame_shift,
    "anchor_snap_delta_frames": anchor_snap_delta_frames,
    "beat_source": beat_source_label,
    "manual_restart_count": len(manual_restart_frames),
    "manual_restart_frames": manual_restart_frames[:80],
    "beat_marker_step": beat_marker_step,
    "beat_marker_phase": beat_marker_phase,
    "beat_segment_count": beat_segment_count,
    "breath_gap_count": breath_gap_count,
    "anchor_valid": anchor_valid,
    "clip_color_changed": clip_color_changed,
}}, ensure_ascii=False))
''',
            timeout=120,
        )
        if not data:
            return {"ok": False, "message": "节拍标记失败：Resolve API 未返回结果。"}
        return data

    def clear_bpm_markers(self, timeline_index: int = 1, marker_scope: str = "clip") -> dict[str, Any]:
        data = self._run_resolve_python(
            rf'''
import json
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
timeline = project.GetCurrentTimeline() if project else None
if not timeline and project:
    timeline = project.GetTimelineByIndex({int(timeline_index)})
if not timeline:
    print(json.dumps({{"ok": False, "message": "未找到目标时间线。"}}, ensure_ascii=False))
    raise SystemExit(0)
marker_scope = {json.dumps(marker_scope)}

def safe(callable_obj, default=None):
    try:
        return callable_obj()
    except Exception:
        return default

def as_items(value):
    if value is None:
        return []
    if isinstance(value, dict):
        return [item for item in value.values() if item]
    if isinstance(value, (list, tuple)):
        return [item for item in value if item]
    return [value]

def marker_custom(marker):
    if not isinstance(marker, dict):
        return ""
    return str(marker.get("customData", "") or marker.get("custom_data", "") or "")

def is_bpm_marker(marker):
    if not isinstance(marker, dict):
        return False
    return str(marker.get("name", "")).startswith("[QH-BPM]") or marker_custom(marker).startswith("QH-BPM")

def delete_matching_markers(target):
    removed_count = 0
    failed_count = 0
    get_markers = getattr(target, "GetMarkers", None)
    delete_marker = getattr(target, "DeleteMarkerAtFrame", None)
    delete_custom = getattr(target, "DeleteMarkerByCustomData", None)
    if not callable(get_markers) or not callable(delete_marker):
        return removed_count, failed_count
    for frame_id, marker in list((safe(lambda: get_markers(), {{}}) or {{}}).items()):
        if not is_bpm_marker(marker):
            continue
        try:
            try:
                target_frame = int(float(frame_id))
            except Exception:
                target_frame = frame_id
            if delete_marker(target_frame):
                removed_count += 1
            elif callable(delete_custom) and marker_custom(marker) and delete_custom(marker_custom(marker)):
                removed_count += 1
            else:
                failed_count += 1
        except Exception:
            failed_count += 1
    return removed_count, failed_count

removed = 0
failed = 0
if marker_scope == "clip":
    for track_index in range(1, int(safe(lambda: timeline.GetTrackCount("audio"), 0) or 0) + 1):
        for item in as_items(safe(lambda idx=track_index: timeline.GetItemListInTrack("audio", idx), [])):
            item_removed, item_failed = delete_matching_markers(item)
            removed += item_removed
            failed += item_failed
else:
    removed, failed = delete_matching_markers(timeline)
target_label = "音频片段" if marker_scope == "clip" else "时间线"
print(json.dumps({{
    "ok": failed == 0,
    "message": "已从%s清除 %d 个节拍标记%s。" % (target_label, removed, ("，失败 %d 个" % failed) if failed else ""),
    "removed": removed,
    "failed": failed,
    "marker_scope": marker_scope,
}}, ensure_ascii=False))
''',
            timeout=120,
        )
        if not data:
            return {"ok": False, "message": "清除节拍标记失败：Resolve API 未返回结果。"}
        return data

    def clear_current_audio_bpm_markers(self, timeline_index: int = 1) -> dict[str, Any]:
        data = self._run_resolve_python(
            rf'''
import json
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
timeline = project.GetCurrentTimeline() if project else None
if not timeline and project:
    timeline = project.GetTimelineByIndex({int(timeline_index)})
if not timeline:
    print(json.dumps({{"ok": False, "message": "未找到目标时间线。"}}, ensure_ascii=False))
    raise SystemExit(0)

def safe(callable_obj, default=None):
    try:
        return callable_obj()
    except Exception:
        return default

def as_items(value):
    if value is None:
        return []
    if isinstance(value, dict):
        return [item for item in value.values() if item]
    if isinstance(value, (list, tuple)):
        return [item for item in value if item]
    return [value]

def read_properties(target):
    if not target:
        return {{}}
    for method_name in ("GetClipProperty", "GetProperty"):
        method = getattr(target, method_name, None)
        if not callable(method):
            continue
        props = safe(lambda method=method: method(), {{}})
        if isinstance(props, dict):
            return props
    return {{}}

def item_track_type(item):
    value = safe(lambda: item.GetTrackTypeAndIndex(), None)
    if isinstance(value, (list, tuple)) and value:
        return str(value[0]).lower()
    if isinstance(value, dict):
        return str(value.get("trackType") or value.get("type") or "").lower()
    props = read_properties(item)
    return str(props.get("Track Type") or props.get("Type") or "").lower()

def item_frame(item, method_name, default=0):
    method = getattr(item, method_name, None)
    if not callable(method):
        return default
    try:
        return int(method() or default)
    except Exception:
        return default

def clip_name(item):
    props = read_properties(item)
    for key in ("Clip Name", "File Name", "Name"):
        if props.get(key):
            return str(props.get(key))
    return str(safe(lambda: item.GetName(), "") or "未命名音频")

def marker_custom(marker):
    if not isinstance(marker, dict):
        return ""
    return str(marker.get("customData", "") or marker.get("custom_data", "") or "")

def is_bpm_marker(marker):
    if not isinstance(marker, dict):
        return False
    return str(marker.get("name", "")).startswith("[QH-BPM]") or marker_custom(marker).startswith("QH-BPM")

def delete_matching_markers(target):
    removed_count = 0
    failed_count = 0
    get_markers = getattr(target, "GetMarkers", None)
    delete_marker = getattr(target, "DeleteMarkerAtFrame", None)
    delete_custom = getattr(target, "DeleteMarkerByCustomData", None)
    if not callable(get_markers) or not callable(delete_marker):
        return removed_count, failed_count
    for frame_id, marker in list((safe(lambda: get_markers(), {{}}) or {{}}).items()):
        if not is_bpm_marker(marker):
            continue
        try:
            try:
                target_frame = int(float(frame_id))
            except Exception:
                target_frame = frame_id
            if delete_marker(target_frame):
                removed_count += 1
            elif callable(delete_custom) and marker_custom(marker) and delete_custom(marker_custom(marker)):
                removed_count += 1
            else:
                failed_count += 1
        except Exception:
            failed_count += 1
    return removed_count, failed_count

current_tc = str(safe(lambda: timeline.GetCurrentTimecode(), "") or "")
fps_raw = safe(lambda: timeline.GetSetting("timelineFrameRate"), None) or safe(lambda: project.GetSetting("timelineFrameRate"), None) or 25
try:
    fps = float(fps_raw)
except Exception:
    fps = 25.0
fps_int = max(1, int(round(fps)))
def tc_to_frames(tc):
    parts = str(tc or "").split(":")
    if len(parts) != 4:
        return None
    try:
        hh, mm, ss, ff = [int(float(part)) for part in parts]
    except Exception:
        return None
    return (((hh * 60) + mm) * 60 + ss) * fps_int + ff
playhead_display_frame = tc_to_frames(current_tc)
timeline_start_frame = int(safe(lambda: timeline.GetStartFrame(), 0) or 0)
start_tc = str(safe(lambda: timeline.GetStartTimecode(), "") or safe(lambda: timeline.GetSetting("timelineStartTimecode"), "") or "00:00:00:00")
start_display = tc_to_frames(start_tc) or 0
current_playhead_frame = None
if playhead_display_frame is not None:
    current_playhead_frame = timeline_start_frame + max(0, playhead_display_frame - start_display)

targets = []
for method_name in ("GetSelectedItems", "GetSelectedClips", "GetSelectedTimelineItems"):
    method = getattr(timeline, method_name, None)
    if not callable(method):
        continue
    for item in as_items(safe(lambda method=method: method(), [])):
        track_type = item_track_type(item)
        if "audio" in track_type or not track_type:
            targets.append((item, "selected"))

if not targets and current_playhead_frame is not None:
    for track_index in range(1, int(safe(lambda: timeline.GetTrackCount("audio"), 0) or 0) + 1):
        for item in as_items(safe(lambda idx=track_index: timeline.GetItemListInTrack("audio", idx), [])):
            start = item_frame(item, "GetStart", 0)
            end = item_frame(item, "GetEnd", start)
            if start <= current_playhead_frame < end:
                targets.append((item, "playhead"))

if not targets:
    print(json.dumps({{
        "ok": False,
        "message": "未找到当前音频片段。请选中音乐片段，或把播放头停在要清除的音频片段上。",
        "removed": 0,
        "failed": 0,
    }}, ensure_ascii=False))
    raise SystemExit(0)

seen = set()
removed = 0
failed = 0
clips = []
source_mode = "selected" if any(source == "selected" for _item, source in targets) else "playhead"
for item, source in targets:
    uid = str(safe(lambda item=item: item.GetUniqueId(), "") or "")
    key = uid or str(id(item))
    if key in seen:
        continue
    seen.add(key)
    item_removed, item_failed = delete_matching_markers(item)
    removed += item_removed
    failed += item_failed
    clips.append({{
        "name": clip_name(item),
        "start_frame": item_frame(item, "GetStart", 0),
        "end_frame": item_frame(item, "GetEnd", 0),
        "removed": item_removed,
        "failed": item_failed,
        "source": source,
    }})

print(json.dumps({{
    "ok": failed == 0,
    "message": "已从当前音频清除 %d 个节拍标记%s。" % (removed, ("，失败 %d 个" % failed) if failed else ""),
    "removed": removed,
    "failed": failed,
    "source_mode": source_mode,
    "clips": clips,
}}, ensure_ascii=False))
''',
            timeout=120,
        )
        if not data:
            return {"ok": False, "message": "清除当前音频节拍标记失败：Resolve API 未返回结果。"}
        return data

    def _find_ffmpeg_binary(self) -> str:
        if platform.system().lower() == "windows":
            appdata = Path(os.environ.get("APPDATA", ""))
            candidates = [
                str(REPO_ROOT / "QingheBFD_Plugin_Windows" / "ffmpeg" / "windows" / "ffmpeg.exe"),
                str(REPO_ROOT / "ffmpeg" / "bin" / "ffmpeg.exe"),
                str(REPO_ROOT / "ffmpeg" / "windows" / "ffmpeg.exe"),
                str(appdata / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Scripts" / "Modules" / "black_frame_detector" / "ffmpeg" / "windows" / "ffmpeg.exe") if appdata else "",
                shutil.which("ffmpeg") or "",
            ]
        else:
            bundled = REPO_ROOT / "ffmpeg" / "macos" / "ffmpeg"
            candidates = [
                str(bundled),
                shutil.which("ffmpeg") or "",
                "/opt/homebrew/bin/ffmpeg",
                "/usr/local/bin/ffmpeg",
                "/usr/bin/ffmpeg",
            ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate
        return ""

    def _find_ffprobe_binary(self) -> str:
        if platform.system().lower() == "windows":
            appdata = Path(os.environ.get("APPDATA", ""))
            candidates = [
                str(REPO_ROOT / "QingheBFD_Plugin_Windows" / "ffmpeg" / "windows" / "ffprobe.exe"),
                str(REPO_ROOT / "ffmpeg" / "bin" / "ffprobe.exe"),
                str(REPO_ROOT / "ffmpeg" / "windows" / "ffprobe.exe"),
                str(appdata / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Scripts" / "Modules" / "black_frame_detector" / "ffmpeg" / "windows" / "ffprobe.exe") if appdata else "",
                shutil.which("ffprobe") or "",
            ]
        else:
            bundled = REPO_ROOT / "ffmpeg" / "macos" / "ffprobe"
            candidates = [
                str(bundled),
                shutil.which("ffprobe") or "",
                "/opt/homebrew/bin/ffprobe",
                "/usr/local/bin/ffprobe",
                "/usr/bin/ffprobe",
            ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate
        return ""

    def _estimate_bpm_with_ffmpeg(self, path: Path) -> dict[str, Any]:
        ffmpeg = self._find_ffmpeg_binary()
        if not ffmpeg:
            return {"ok": False, "message": "未找到 FFmpeg，无法本地估算 BPM。"}
        sample_rate = 11025
        max_seconds = 90
        cmd = [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(path),
            "-t",
            str(max_seconds),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-f",
            "s16le",
            "pipe:1",
        ]
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=45,
                **hidden_subprocess_kwargs(),
            )
        except Exception as exc:
            return {"ok": False, "message": f"FFmpeg 解码失败：{exc}"}
        if proc.returncode != 0 or not proc.stdout:
            error = proc.stderr.decode("utf-8", errors="ignore").strip()
            return {"ok": False, "message": "FFmpeg 未能读取该音频。" + (f" {error[:120]}" if error else "")}
        samples = array("h")
        samples.frombytes(proc.stdout)
        if sys.byteorder != "little":
            samples.byteswap()
        bpm_result = self._estimate_bpm_from_samples(samples, sample_rate)
        bpm_result.update({"ffmpeg": ffmpeg, "analyzed_seconds": min(max_seconds, len(samples) / float(sample_rate))})
        return bpm_result

    def _estimate_bpm_from_samples(self, samples: array, sample_rate: int) -> dict[str, Any]:
        if len(samples) < sample_rate * 8:
            return {"ok": False, "message": "音频太短，至少需要约 8 秒才能估算 BPM。"}
        hop = 512
        frame = 1024
        energies: list[float] = []
        limit = len(samples) - frame
        for start in range(0, max(0, limit), hop):
            chunk = samples[start : start + frame]
            if not chunk:
                continue
            energies.append(sum(abs(value) for value in chunk) / float(len(chunk)))
        if len(energies) < 64:
            return {"ok": False, "message": "音频有效采样不足，无法估算 BPM。"}
        smooth: list[float] = []
        radius = 3
        for idx in range(len(energies)):
            left = max(0, idx - radius)
            right = min(len(energies), idx + radius + 1)
            smooth.append(sum(energies[left:right]) / float(right - left))
        novelty = [0.0]
        for idx in range(1, len(smooth)):
            novelty.append(max(0.0, smooth[idx] - smooth[idx - 1]))
        mean = sum(novelty) / float(len(novelty))
        novelty = [max(0.0, value - mean) for value in novelty]
        if max(novelty or [0.0]) <= 0:
            return {"ok": False, "message": "没有检测到足够稳定的节拍变化。"}
        min_bpm = 60
        max_bpm = 190
        scored: list[tuple[float, int, float]] = []
        for bpm in range(min_bpm, max_bpm + 1):
            lag = int(round((60.0 * sample_rate) / (float(bpm) * hop)))
            if lag <= 1 or lag >= len(novelty) // 2:
                continue
            score = 0.0
            count = 0
            for idx in range(lag, len(novelty)):
                score += novelty[idx] * novelty[idx - lag]
                count += 1
            if count:
                scored.append((score / count, bpm, float(lag)))
        if not scored:
            return {"ok": False, "message": "没有找到可信 BPM 候选。"}
        scored.sort(reverse=True)
        best_score, best_bpm, best_lag = scored[0]
        median_score = sorted(score for score, _bpm, _lag in scored)[len(scored) // 2] or 1.0
        confidence = max(0.0, min(1.0, (best_score / max(median_score, 1e-9) - 1.0) / 4.0))
        alternatives = [{"bpm": bpm, "score": round(score, 4)} for score, bpm, _lag in scored[:5]]
        return {
            "ok": True,
            "bpm": best_bpm,
            "confidence": round(confidence, 2),
            "method": "ffmpeg_pcm_autocorrelation",
            "alternatives": alternatives,
        }

    def jump_to_timecode(self, timeline_index: int, timecode: str) -> tuple[bool, str]:
        data = self._run_resolve_python(
            rf'''
import json
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
timeline = project.GetTimelineByIndex({int(timeline_index)}) if project else None
ok = False
message = "未找到目标时间线。"
if project and timeline:
    project.SetCurrentTimeline(timeline)
    try:
        ok = bool(timeline.SetCurrentTimecode({json.dumps(timecode)}))
    except Exception:
        ok = False
    if not ok:
        try:
            ok = bool(timeline.SetCurrentTimecode(str({json.dumps(timecode)})))
        except Exception:
            ok = False
    if resolve:
        resolve.OpenPage("edit")
    message = "已跳转到 " + {json.dumps(timecode)} if ok else "Resolve 未接受该时间码。"
print(json.dumps({{"ok": ok, "message": message}}, ensure_ascii=False))
'''
        )
        if not data:
            return False, "跳转失败：Resolve API 未返回结果。"
        return bool(data.get("ok")), str(data.get("message", "跳转完成。"))

    def bfd_marker_records(self, timeline_index: int = 1) -> dict[str, Any]:
        data = self._run_resolve_python(
            rf'''
import json
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
timeline = project.GetTimelineByIndex({int(timeline_index)}) if project else None
if not timeline:
    print(json.dumps({{"ok": False, "message": "未找到目标时间线。", "records": []}}, ensure_ascii=False))
    raise SystemExit(0)

def safe(callable_obj, default=None):
    try:
        return callable_obj()
    except Exception:
        return default

STYLE_SUFFIXES = [
    "Regular", "Bold", "Italic", "Medium", "Light", "Book", "Normal",
    "Demibold", "DemiBold", "Extrabold", "ExtraBold", "Heavy", "Black",
]

def parse_font_candidate(value):
    text = str(value or "").strip()
    if "|||" in text:
        parts = text.split("|||", 2)
        while len(parts) < 3:
            parts.append("")
        family, style, path = parts[:3]
        return family.strip(), style.strip(), path.strip()
    for style in STYLE_SUFFIXES:
        suffix = " " + style
        if text.endswith(suffix):
            return text[:-len(suffix)].strip(), style, ""
    return text, "", ""

def font_replace_result(ok, font, accepted_font, message, **extra):
    payload = {{
        "ok": bool(ok),
        "font": font,
        "accepted_font": accepted_font,
        "message": message,
    }}
    payload.update(extra)
    return payload

def tc_from_frame(frame, fps):
    fps_int = max(1, int(round(float(fps or 25))))
    total = max(0, int(round(float(frame or 0))))
    ff = total % fps_int
    total_seconds = total // fps_int
    ss = total_seconds % 60
    mm = (total_seconds // 60) % 60
    hh = total_seconds // 3600
    return "%02d:%02d:%02d:%02d" % (hh, mm, ss, ff)

fps_raw = safe(lambda: timeline.GetSetting("timelineFrameRate"), None) or safe(lambda: project.GetSetting("timelineFrameRate"), None) or 25
try:
    fps = float(fps_raw)
except Exception:
    fps = 25.0
start_frame = safe(lambda: timeline.GetStartFrame(), 0) or 0
start_timecode = str(safe(lambda: timeline.GetStartTimecode(), None) or safe(lambda: timeline.GetSetting("timelineStartTimecode"), None) or "00:00:00:00")
markers = timeline.GetMarkers() or {{}}
records = []
counts = {{"total": 0, "error": 0, "suspect": 0, "scene": 0, "gap": 0, "duplicate": 0, "content_dup": 0, "opacity": 0, "corrupt": 0, "black_border": 0}}

def timecode_to_frames(tc, fps):
    fps_int = max(1, int(round(float(fps or 25))))
    parts = str(tc or "00:00:00:00").split(":")
    if len(parts) != 4:
        return 0
    try:
        hh, mm, ss, ff = [int(float(part)) for part in parts]
    except Exception:
        return 0
    return (((hh * 60) + mm) * 60 + ss) * fps_int + ff

STYLE_SUFFIXES = [
    "Regular", "Bold", "Italic", "Medium", "Light", "Book", "Normal",
    "Demibold", "DemiBold", "Extrabold", "ExtraBold", "Heavy", "Black",
]

def parse_font_candidate(value):
    text = str(value or "").strip()
    if "|||" in text:
        family, style = text.split("|||", 1)
        return family.strip(), style.strip()
    for style in STYLE_SUFFIXES:
        suffix = " " + style
        if text.endswith(suffix):
            return text[:-len(suffix)].strip(), style
    return text, ""

def tc_from_timeline_frame(frame, fps, timeline_start_frame, timeline_start_tc):
    rel = int(round(float(frame or 0))) - int(round(float(timeline_start_frame or 0)))
    return tc_from_frame(timecode_to_frames(timeline_start_tc, fps) + max(0, rel), fps)

def classify(name, color):
    text = str(name or "").upper()
    if "BDR" in text or "BORDER" in text or "BLACK_BORDER" in text or "黑边" in str(name or ""):
        return "black_border"
    if "OPC" in text:
        return "opacity"
    if "GAP" in text:
        return "gap"
    if "DUP" in text:
        return "duplicate"
    if "COR" in text:
        return "corrupt"
    if "SUS" in text:
        return "suspect"
    if "SCN" in text or "SCENE" in text:
        return "scene"
    if "FP" in text or "FINGER" in text:
        return "content_dup"
    if "OVL" in text or "ERR" in text or "BFD" in text:
        return "error"
    return "info"

for frame, marker in markers.items():
    name = str(marker.get("name", "") or "")
    note = str(marker.get("note", "") or "")
    if "[BFD" not in name and "[BFD" not in note:
        continue
    try:
        relative_frame = int(float(frame))
    except Exception:
        relative_frame = 0
    abs_frame = int(start_frame) + relative_frame
    color = str(marker.get("color", "") or "")
    classification = classify(name, color)
    counts["total"] += 1
    if classification in counts:
        counts[classification] += 1
    records.append({{
        "timeline_index": {int(timeline_index)},
        "frame": abs_frame,
        "marker_frame": relative_frame,
        "timecode": tc_from_timeline_frame(abs_frame, fps, start_frame, start_timecode),
        "color": color,
        "classification": classification,
        "name": name,
        "note": note,
        "duration_frames": marker.get("duration", 1),
    }})

records.sort(key=lambda item: int(item.get("frame") or 0))
print(json.dumps({{
    "ok": True,
    "message": f"已从时间线读取 {{len(records)}} 条 BFD 标记。",
    "records": records,
    "counts": counts,
}}, ensure_ascii=False))
'''
        )
        if not data:
            return {"ok": False, "message": "读取时间线标记失败：Resolve API 未返回结果。", "records": [], "counts": {}}
        return data

    def scan_text_items(
        self,
        timeline_index: int = 1,
        query: str = "",
        scan_types: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._text_action(timeline_index, "scan", query=query, scan_types=scan_types)

    def jump_to_text_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return self._text_action(int(item.get("timeline_index", 1)), "jump", item=item)

    def replace_text_item(self, item: dict[str, Any], text: str) -> dict[str, Any]:
        return self._text_action(int(item.get("timeline_index", 1)), "replace", item=item, text=text)

    def delete_text_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return self._text_action(int(item.get("timeline_index", 1)), "delete", item=item)

    def restore_deleted_text_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return self._text_action(int(item.get("timeline_index", 1)), "restore_delete", item=item)

    def scan_font_items(self, timeline_index: int = 1) -> dict[str, Any]:
        return self._font_action(timeline_index, "scan")

    def jump_to_font_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return self._font_action(int(item.get("timeline_index", 1)), "jump", item=item)

    def replace_font_item(
        self,
        item: dict[str, Any],
        font_name: str,
        font_candidates: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._font_action(
            int(item.get("timeline_index", 1)),
            "replace",
            item=item,
            font_name=font_name,
            font_candidates=font_candidates,
        )

    def check_font_available(
        self,
        timeline_index: int,
        font_name: str,
        font_candidates: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._font_action(
            int(timeline_index),
            "check_font",
            font_name=font_name,
            font_candidates=font_candidates,
        )

    def copy_textplus_style(self, item: dict[str, Any]) -> dict[str, Any]:
        return self._font_action(int(item.get("timeline_index", 1)), "copy_style", item=item)

    def copy_textplus_position(self, item: dict[str, Any]) -> dict[str, Any]:
        return self._font_action(int(item.get("timeline_index", 1)), "copy_position", item=item)

    def apply_textplus_style(self, item: dict[str, Any], style: dict[str, Any]) -> dict[str, Any]:
        return self._font_action(int(item.get("timeline_index", 1)), "apply_style", item=item, style_payload=style)

    def list_caption_templates(self, timeline_index: int = 1) -> dict[str, Any]:
        return self._font_action(int(timeline_index), "list_caption_templates")

    def caption_conversion_info(self, timeline_index: int = 1, template_uid: str = "") -> dict[str, Any]:
        return self._font_action(int(timeline_index), "caption_conversion_info", item={"caption_template_uid": template_uid})

    def convert_srt_to_textplus(
        self,
        timeline_index: int = 1,
        template_uid: str = "",
        write_markers: bool = False,
    ) -> dict[str, Any]:
        return self._font_action(
            int(timeline_index),
            "convert_srt_textplus",
            item={"caption_template_uid": template_uid, "write_markers": bool(write_markers)},
        )

    def _font_action(
        self,
        timeline_index: int,
        action: str,
        item: dict[str, Any] | None = None,
        font_name: str = "",
        font_candidates: list[str] | None = None,
        style_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        action = action if action in {"scan", "jump", "replace", "check_font", "copy_style", "copy_position", "apply_style", "convert_srt_textplus", "list_caption_templates", "caption_conversion_info"} else "scan"
        candidates: list[str] = []
        ordered_candidates = [*(font_candidates or []), font_name]
        for candidate in ordered_candidates:
            text = str(candidate or "").strip()
            if text and text not in candidates:
                candidates.append(text)
        template_path = Path(__file__).resolve().with_name("templates") / "caption-bin.drb"
        timeout = 45.0
        if action == "convert_srt_textplus":
            timeout = self._subtitle_operation_timeout(timeline_index, minimum=300, per_item=0.28)
        elif action == "apply_style":
            timeout = self._subtitle_operation_timeout(timeline_index, minimum=300, per_item=0.20)
        data = self._run_resolve_python(
            rf'''
import json
import os
ACTION = {json.dumps(action)}
ITEM = json.loads({json.dumps(json.dumps(item or {}, ensure_ascii=False))})
FONT_NAME = {json.dumps(font_name, ensure_ascii=False)}
FONT_CANDIDATES = json.loads({json.dumps(json.dumps(candidates, ensure_ascii=False))})
STYLE_PAYLOAD = json.loads({json.dumps(json.dumps(style_payload or {}, ensure_ascii=False))})
CAPTION_TEMPLATE_PATH = {json.dumps(str(template_path))}
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
timeline = project.GetTimelineByIndex({int(timeline_index)}) if project else None
if not timeline:
    print(json.dumps({{"ok": False, "message": "未找到目标时间线。", "items": []}}, ensure_ascii=False))
    raise SystemExit(0)

def safe(callable_obj, default=None):
    try:
        return callable_obj()
    except Exception:
        return default

STYLE_SUFFIXES = [
    "Regular", "Bold", "Italic", "Medium", "Light", "Book", "Normal",
    "Demibold", "DemiBold", "Extrabold", "ExtraBold", "Heavy", "Black",
]

def parse_font_candidate(value):
    text = str(value or "").strip()
    if "|||" in text:
        parts = text.split("|||", 2)
        while len(parts) < 3:
            parts.append("")
        family, style, path = parts[:3]
        return family.strip(), style.strip(), path.strip()
    for style in STYLE_SUFFIXES:
        suffix = " " + style
        if text.endswith(suffix):
            return text[:-len(suffix)].strip(), style, ""
    return text, "", ""

def font_replace_result(ok, font, accepted_font, message, **extra):
    payload = dict(ok=bool(ok), font=font, accepted_font=accepted_font, message=message)
    payload.update(extra)
    return payload

def register_font_candidate(font_path, font_name):
    global FUSION_FONT_INDEX
    path = str(font_path or "").strip()
    name = str(font_name or "").strip()
    if not path or not name:
        return False
    try:
        fusion = dvr_script.scriptapp("Fusion")
        manager = fusion.FontManager if fusion else None
        if manager:
            added = bool(manager.AddFont(path, name))
            if added:
                FUSION_FONT_INDEX = None
            return added
    except Exception:
        return False
    return False

FUSION_FONT_INDEX = None

def fusion_font_index():
    global FUSION_FONT_INDEX
    if FUSION_FONT_INDEX is not None:
        return FUSION_FONT_INDEX
    names = set()
    basenames = set()
    basename_to_family = {{}}
    try:
        fusion = dvr_script.scriptapp("Fusion")
        manager = fusion.FontManager if fusion else None
        font_list = manager.GetFontList() if manager else {{}}
    except Exception:
        FUSION_FONT_INDEX = {{"available": False, "names": names, "basenames": basenames, "basename_to_family": basename_to_family}}
        return FUSION_FONT_INDEX
    if not isinstance(font_list, dict) or not font_list:
        FUSION_FONT_INDEX = {{"available": False, "names": names, "basenames": basenames, "basename_to_family": basename_to_family}}
        return FUSION_FONT_INDEX
    for family, styles in font_list.items():
        family_text = str(family or "").strip()
        if family_text:
            names.add(family_text)
        if isinstance(styles, dict):
            for _style, item_path in styles.items():
                basename = os.path.basename(str(item_path or ""))
                if basename:
                    basenames.add(basename)
                    if family_text:
                        basename_to_family.setdefault(basename, family_text)
    FUSION_FONT_INDEX = {{"available": True, "names": names, "basenames": basenames, "basename_to_family": basename_to_family}}
    return FUSION_FONT_INDEX

def fusion_font_available(font_name, font_path=""):
    name = str(font_name or "").strip()
    path = str(font_path or "").strip()
    basename = os.path.basename(path) if path else ""
    if not name and not basename:
        return True
    index = fusion_font_index()
    if not bool(index.get("available")):
        return True
    return (name and name in index.get("names", set())) or (basename and basename in index.get("basenames", set()))

def font_name_looks_corrupt(font_name):
    text = str(font_name or "").strip()
    if text.count("?") < 3:
        return False
    meaningful = "".join(ch for ch in text if ch not in "? ._-/|")
    if not meaningful:
        return True
    has_cjk = any("\\u4e00" <= ch <= "\\u9fff" for ch in meaningful)
    has_alnum = any(ch.isalnum() for ch in meaningful)
    if not has_cjk and not has_alnum:
        return True
    return text.count("?") >= max(3, len(text) // 2)

def fusion_font_resolved_name(font_name, font_path=""):
    name = str(font_name or "").strip()
    path = str(font_path or "").strip()
    basename = os.path.basename(path) if path else ""
    index = fusion_font_index()
    if name and name in index.get("names", set()):
        return name
    if basename:
        mapped = index.get("basename_to_family", {{}}).get(basename)
        if mapped:
            # Fusion's UI may show a localized Chinese family while the
            # scripting FontManager exposes a Mojibake-style internal key
            # (for example "???????"). If the key came from an exact font-file
            # match, use it; this mirrors manual selection from Fusion's font
            # dropdown better than writing the localized display name.
            return str(mapped)
    return name

def font_candidate_probe(candidate, accepted, registered, resolved_font, resolved_style):
    candidate_font, candidate_style, candidate_path = parse_font_candidate(candidate)
    return {{
        "candidate": str(candidate or ""),
        "font": candidate_font,
        "style": candidate_style,
        "path": candidate_path,
        "registered": bool(registered),
        "accepted": bool(accepted),
        "resolved_font": str(resolved_font or ""),
        "resolved_style": str(resolved_style or ""),
    }}

def all_traced_candidates_unavailable(candidate_trace, attempts):
    if int(attempts or 0) <= 0 or not candidate_trace:
        return False
    return all(bool(item.get("unavailable")) for item in candidate_trace)

def fusion_unavailable_message(font_name):
    name = str(font_name or "").strip()
    return "当前 Fusion 不可用：" + (name or "所选字体") + "。该字体虽然可能存在于系统字体库，但当前 Resolve/Fusion FontManager 未列出它；请换用 Fusion 可识别字体，或安装标准字体后重启 Resolve。"

def tc_from_frame(frame, fps):
    fps_int = max(1, int(round(float(fps or 25))))
    total = max(0, int(round(float(frame or 0))))
    ff = total % fps_int
    total_seconds = total // fps_int
    ss = total_seconds % 60
    mm = (total_seconds // 60) % 60
    hh = total_seconds // 3600
    return "%02d:%02d:%02d:%02d" % (hh, mm, ss, ff)

if ACTION == "check_font":
    candidate_trace = []
    candidate_attempts = 0
    for candidate in FONT_CANDIDATES or [FONT_NAME]:
        candidate_font, candidate_style, candidate_path = parse_font_candidate(candidate)
        candidate_attempts += 1
        available = fusion_font_available(candidate_font, candidate_path)
        registered = False
        if not available and candidate_path:
            registered = register_font_candidate(candidate_path, candidate_font)
            available = fusion_font_available(candidate_font, candidate_path)
        resolved_font = fusion_font_resolved_name(candidate_font, candidate_path) if available else ""
        trace_item = font_candidate_probe(candidate, available, registered, resolved_font, candidate_style if available else "")
        trace_item["unavailable"] = not bool(available)
        if len(candidate_trace) < 24:
            candidate_trace.append(trace_item)
        if available:
            print(json.dumps({{
                "ok": True,
                "available": True,
                "font": resolved_font or candidate_font,
                "style": candidate_style,
                "accepted_candidate": str(candidate or ""),
                "registered_font_path": str(candidate_path or ""),
                "registered_font_name": str(candidate_font or ""),
                "candidate_attempts": candidate_attempts,
                "candidate_trace": candidate_trace,
                "message": "当前 Fusion 可用：" + (resolved_font or candidate_font or FONT_NAME),
            }}, ensure_ascii=False))
            raise SystemExit(0)
    print(json.dumps({{
        "ok": False,
        "available": False,
        "font": FONT_NAME,
        "candidate_attempts": candidate_attempts,
        "candidate_trace": candidate_trace,
        "error_code": "fusion_font_unavailable",
        "message": fusion_unavailable_message(FONT_NAME),
    }}, ensure_ascii=False))
    raise SystemExit(0)

def timecode_to_frames(tc, fps):
    fps_int = max(1, int(round(float(fps or 25))))
    parts = str(tc or "00:00:00:00").split(":")
    if len(parts) != 4:
        return 0
    try:
        hh, mm, ss, ff = [int(float(part)) for part in parts]
    except Exception:
        return 0
    return (((hh * 60) + mm) * 60 + ss) * fps_int + ff

fps_raw = safe(lambda: timeline.GetSetting("timelineFrameRate"), None) or safe(lambda: project.GetSetting("timelineFrameRate"), None) or 25
try:
    fps = float(fps_raw)
except Exception:
    fps = 25.0
start_frame = safe(lambda: timeline.GetStartFrame(), 0) or 0
start_timecode = str(safe(lambda: timeline.GetStartTimecode(), None) or safe(lambda: timeline.GetSetting("timelineStartTimecode"), None) or "00:00:00:00")
SRT2TEXT_MARKER_NAME = "[QH-SRT2TEXT] 字幕 Text+"
SRT2TEXT_GROUP_THRESHOLD = 40
WRITE_SRT2TEXT_MARKERS = bool(ITEM.get("write_markers", False))

def tc_from_timeline_frame(frame):
    rel = int(round(float(frame or 0))) - int(round(float(start_frame or 0)))
    return tc_from_frame(timecode_to_frames(start_timecode, fps) + max(0, rel), fps)

def get_item(track_type, track_index, item_index):
    clips = safe(lambda: timeline.GetItemListInTrack(track_type, track_index), []) or []
    target_uid = str(ITEM.get("unique_id", "") or "")
    if target_uid:
        for clip in clips:
            uid = str(safe(lambda c=clip: c.GetUniqueId(), "") or "")
            if uid == target_uid:
                return clip
    if item_index < 0 or item_index >= len(clips):
        return None
    return clips[item_index]

def textplus_tools(clip):
    found = []
    fusion_count = int(safe(lambda: clip.GetFusionCompCount(), 0) or 0)
    for comp_index in range(1, fusion_count + 1):
        comp = safe(lambda ci=comp_index: clip.GetFusionCompByIndex(ci))
        tools = safe(lambda c=comp: c.GetToolList(False), {{}}) if comp else {{}}
        iterable = tools.items() if isinstance(tools, dict) else []
        for tool_name, tool in iterable:
            tool_id = str(safe(lambda t=tool: t.ID, "") or "")
            styled = safe(lambda t=tool: t.GetInput("StyledText"), None)
            font = safe(lambda t=tool: t.GetInput("Font"), None)
            style = safe(lambda t=tool: t.GetInput("Style"), None)
            if tool_id == "TextPlus" or styled not in (None, "") or font not in (None, ""):
                found.append((comp_index, str(tool_name), tool, str(styled or ""), str(font or ""), str(style or "")))
    return found

def clip_has_srt2text_marker(clip):
    markers = safe(lambda: clip.GetMarkers(), {{}}) or {{}}
    if not isinstance(markers, dict):
        return False
    for marker in markers.values():
        name = str(marker.get("name", "") or "")
        note = str(marker.get("note", "") or "")
        custom_data = str(marker.get("customData", "") or marker.get("custom_data", "") or "")
        if "QH-SRT2TEXT" in name or "QH-SRT2TEXT" in note or "qh-srt2text" in custom_data.lower():
            return True
    return False

def mark_srt2text_clip(clip, group_id, index, total):
    if not WRITE_SRT2TEXT_MARKERS:
        return False
    note = "清何插件 SRT 转 Text+ 内部标记；字体面板会按组折叠显示。"
    custom_data = "qh-srt2text|" + str(group_id) + "|" + str(index) + "|" + str(total)
    return safe(lambda: clip.AddMarker(0, "Blue", SRT2TEXT_MARKER_NAME, note, 1, custom_data), False)

TEXT_FONT_KEYS = [
    "Font", "Font Face", "FontFace", "Font Family", "FontFamily",
    "Typeface", "Type Face", "Text Font", "TextFont", "Title Font",
    "Font Name", "FontName", "FontStyle", "Style",
]
TEXT_VALUE_KEYS = ["Text", "StyledText", "Title", "Subtitle", "Caption", "Name", "Clip Name", "Comments"]
TEXTPLUS_STYLE_KEYS = [
    "Font", "Style", "Size", "LineSpacing", "CharacterSpacing",
    "Red1", "Green1", "Blue1", "Alpha1",
    "Opacity1",
    "Enabled2", "Red2", "Green2", "Blue2", "Alpha2", "Thickness2", "Softness2", "Opacity2",
    "Enabled3", "Red3", "Green3", "Blue3", "Alpha3", "Offset3", "Blur3", "Opacity3",
    "HorizontalJustification", "VerticalJustification", "Center",
    "LayoutType", "TransformRotation", "TransformSize", "Shear", "AngleZ",
    "Width", "Height", "Position", "Pivot", "Rotation", "UseFrameFormatSettings",
    "StyledTextFollow", "WriteOnStart", "WriteOnEnd",
    "ShadingGradient1", "ShadingMapping1", "ShadingMappingAngle1", "ShadingMappingSize1",
    "ShadingGradient2", "ShadingMapping2", "ShadingMappingAngle2", "ShadingMappingSize2",
    "ShadingGradient3", "ShadingMapping3", "ShadingMappingAngle3", "ShadingMappingSize3",
    "ElementShape1", "ElementShape2", "ElementShape3", "JoinStyle2", "Level2", "Level3",
    "AdvancedFontControls", "ManualFontKerningPlacement",
]
TEXTPLUS_POSITION_KEYS = [
    "Center", "CenterZ",
    "LayoutType", "LayoutSize", "LayoutWidth", "LayoutHeight",
    "Perspective", "FitCharacters", "PositionOnPath",
    "LayoutRotation", "RotationOrder", "AngleX", "AngleY", "AngleZ",
    "LineOffset", "LineOffsetZ", "WordOffset", "WordOffsetZ", "CharacterOffset", "CharacterOffsetZ",
    "TransformRotation", "LineRotationOrder", "LineAngleX", "LineAngleY", "LineAngleZ",
    "WordRotationOrder", "WordAngleX", "WordAngleY", "WordAngleZ",
    "CharacterRotationOrder", "CharacterAngleX", "CharacterAngleY", "CharacterAngleZ",
    "TransformPivot", "LinePivot", "LinePivotZ", "WordPivot", "WordPivotZ",
    "CharacterPivot", "CharacterPivotZ",
    "TransformShear", "LineShearX", "LineShearY", "WordShearX", "WordShearY",
    "CharacterShearX", "CharacterShearY",
    "TransformSize", "LineSizeX", "LineSizeY", "WordSizeX", "WordSizeY",
    "CharacterSizeX", "CharacterSizeY",
]
TIMELINE_POSITION_KEYS = [
    "Pan", "Tilt", "ZoomX", "ZoomY", "RotationAngle",
    "AnchorPointX", "AnchorPointY", "Pitch", "Yaw",
    "FlipX", "FlipY",
]
TEXTPLUS_STYLE_TEXT_KEYS = ("StyledText", "Text", "Name", "Clip Name", "Comments")
TEXTPLUS_STYLE_DANGEROUS_KEYS = {
    "styledtext",
    "text",
    "name",
    "clipname",
    "comments",
    "start",
    "end",
    "globalin",
    "globalout",
    "internal",
    "framerenderscript",
    "startrenderscript",
    "endrenderscript",
    "manualfontkerning",
    "manualfontplacement",
    "clearselectedkerning",
    "clearallkerning",
    "clearselectedplacement",
    "clearallplacement",
    "effectmask",
    "center",
    "centerz",
    "layouttype",
    "layoutsize",
    "layoutwidth",
    "layoutheight",
    "perspective",
    "fitcharacters",
    "position",
    "positiononpath",
    "layoutrotation",
    "rotationorder",
    "lineoffset",
    "lineoffsetz",
    "wordoffset",
    "wordoffsetz",
    "characteroffset",
    "characteroffsetz",
    "scrollposition",
}
TEXTPLUS_STYLE_DANGEROUS_PREFIXES = (
    "blank",
    "layout",
    "kerningseparator",
)
TEXTPLUS_STYLE_DANGEROUS_SUFFIXES = (
    "nest",
)

def should_skip_textplus_style_key(key):
    normalized = str(key or "").strip().lower().replace(" ", "")
    return (
        normalized in TEXTPLUS_STYLE_DANGEROUS_KEYS
        or any(normalized.startswith(prefix) for prefix in TEXTPLUS_STYLE_DANGEROUS_PREFIXES)
        or any(normalized.endswith(suffix) for suffix in TEXTPLUS_STYLE_DANGEROUS_SUFFIXES)
    )

def textplus_style_key_group(key):
    normalized = str(key or "").strip().lower().replace(" ", "")
    if any(token in normalized for token in ("gamut", "width", "height", "depth", "useframeformat", "pixelaspect", "imagesource", "colorimage", "colorfile", "image")):
        return "图像"
    if any(token in normalized for token in ("layout", "center", "background", "perspective", "fitcharacters", "positiononpath")):
        return "布局"
    if any(token in normalized for token in ("transform", "line", "word", "character", "pivot", "shear", "angle", "rotation", "size")):
        return "变换"
    if any(token in normalized for token in ("shading", "element", "red", "green", "blue", "alpha", "opacity", "thickness", "softness", "offset", "blur", "color", "gradient", "joinstyle", "level", "miter", "round")):
        return "着色"
    if any(token in normalized for token in ("font", "style", "justification", "spacing", "underline", "strikeout", "tab", "scroll", "direction", "ligature", "monospaced", "kerning", "reading", "orientation")):
        return "文本"
    return "设置"

def textplus_style_group_counts(values):
    counts = {{}}
    for key in (values or {{}}).keys():
        group = textplus_style_key_group(key)
        counts[group] = int(counts.get(group, 0)) + 1
    return counts

def style_value_is_json_safe(value):
    try:
        json.dumps(value, ensure_ascii=False)
        return True
    except Exception:
        return False

def plain_text_font_property(clip):
    props = safe(lambda: clip.GetProperty(), {{}}) or {{}}
    if not isinstance(props, dict):
        return "", "", ""
    key_map = {{str(key).lower().replace(" ", ""): key for key in props.keys()}}
    font_key = ""
    for candidate in TEXT_FONT_KEYS:
        lookup = candidate.lower().replace(" ", "")
        if lookup in key_map:
            value = props.get(key_map[lookup])
            if value not in (None, ""):
                font_key = str(key_map[lookup])
                break
            font_key = str(key_map[lookup])
    if not font_key:
        for key, value in props.items():
            lowered = str(key).lower()
            if "font" in lowered or "typeface" in lowered:
                font_key = str(key)
                break
    text_value = ""
    for key in TEXT_VALUE_KEYS:
        value = props.get(key)
        if value not in (None, ""):
            text_value = str(value)
            break
    font_value = str(props.get(font_key, "") or "") if font_key else ""
    return font_key, font_value, text_value

def target_textplus_tool(clip):
    requested_key = str(ITEM.get("font_key", "") or "")
    requested_comp = ""
    requested_tool = ""
    if requested_key and not requested_key.startswith("group:textplus:track:"):
        parts = requested_key.split(":")
        if len(parts) >= 2:
            requested_comp = parts[0]
            requested_tool = parts[1]
    fusion_count = int(safe(lambda: clip.GetFusionCompCount(), 0) or 0)
    for comp_index in range(1, fusion_count + 1):
        comp = safe(lambda ci=comp_index: clip.GetFusionCompByIndex(ci))
        if requested_comp and str(comp_index) != requested_comp:
            continue
        tools = safe(lambda c=comp: c.GetToolList(False), {{}}) if comp is not None else {{}}
        iterable = tools.items() if isinstance(tools, dict) else []
        for tool_name, tool in iterable:
            if requested_tool and str(tool_name) != requested_tool:
                continue
            tool_id = str(safe(lambda t=tool: t.ID, "") or "")
            current_font = safe(lambda t=tool: t.GetInput("Font"), None)
            styled_text = safe(lambda t=tool: t.GetInput("StyledText"), None)
            if tool_id == "TextPlus" or current_font not in (None, "") or styled_text not in (None, ""):
                return tool
    return None

def copy_textplus_style_from_tool(tool):
    values = {{}}
    input_list = safe(lambda: tool.GetInputList(), {{}}) or {{}}
    dynamic_keys = []
    if isinstance(input_list, dict):
        for key, input_obj in input_list.items():
            for candidate in (key,):
                text = str(candidate or "").strip()
                if text:
                    dynamic_keys.append(text)
            attrs = safe(lambda obj=input_obj: obj.GetAttrs(), {{}}) or {{}}
            if isinstance(attrs, dict):
                for attr_key in ("INPS_ID", "TOOLS_Name", "LINKS_Name", "LINK_Main"):
                    text = str(attrs.get(attr_key, "") or "").strip()
                    if text:
                        dynamic_keys.append(text)
    seen = set()
    for key in dynamic_keys + TEXTPLUS_STYLE_KEYS:
        if key in seen or should_skip_textplus_style_key(key):
            continue
        seen.add(key)
        value = safe(lambda k=key: tool.GetInput(k), None)
        if value not in (None, "") and style_value_is_json_safe(value):
            values[key] = value
    return values

def copy_textplus_position_from_tool(tool):
    values = {{}}
    for key in TEXTPLUS_POSITION_KEYS:
        value = safe(lambda k=key: tool.GetInput(k), None)
        if value not in (None, "") and style_value_is_json_safe(value):
            values[key] = value
    return values

def copy_timeline_position_from_clip(clip):
    values = {{}}
    props = safe(lambda: clip.GetProperty(), {{}}) or {{}}
    if not isinstance(props, dict):
        props = {{}}
    for key in TIMELINE_POSITION_KEYS:
        value = props.get(key)
        if value in (None, ""):
            value = safe(lambda k=key: clip.GetProperty(k), None)
        if value not in (None, "") and style_value_is_json_safe(value):
            values[key] = value
    return values

def apply_timeline_position_to_clip(clip, values):
    ok_count = 0
    fail_count = 0
    for key, value in (values or {{}}).items():
        if key not in TIMELINE_POSITION_KEYS:
            continue
        before = safe(lambda k=key: clip.GetProperty(k), None)
        ok = bool(safe(lambda k=key, v=value: clip.SetProperty(k, v), False))
        after = safe(lambda k=key: clip.GetProperty(k), None)
        if ok or after == value or str(after) == str(value) or (before == value and after == before):
            ok_count += 1
        else:
            fail_count += 1
    return ok_count, fail_count

def normalize_fusion_input_value(value):
    if isinstance(value, dict):
        converted = {{}}
        all_numeric = True
        for key, item_value in value.items():
            try:
                converted[int(key)] = item_value
            except Exception:
                all_numeric = False
                break
        if all_numeric:
            return converted
    return value

def apply_textplus_style_to_tool(tool, values):
    original_text = safe(lambda: tool.GetInput("StyledText"), None)
    ok_count = 0
    fail_count = 0
    is_position_payload = bool((values or {{}}).get("__textplus_position__"))
    for key, value in (values or {{}}).items():
        if str(key).startswith("__"):
            continue
        if should_skip_textplus_style_key(key) and not (is_position_payload and key in TEXTPLUS_POSITION_KEYS):
            continue
        value = normalize_fusion_input_value(value)
        before = safe(lambda k=key: tool.GetInput(k), None)
        safe(lambda k=key, v=value: tool.SetInput(k, v), None)
        after = safe(lambda k=key: tool.GetInput(k), None)
        if after == value or str(after) == str(value) or (before == value and after == before):
            ok_count += 1
        else:
            fail_count += 1
    if original_text not in (None, ""):
        safe(lambda text=original_text: tool.SetInput("StyledText", text), None)
    return ok_count, fail_count

def collect_font_items():
    records = []
    row = 1
    subtitle_count = int(safe(lambda: timeline.GetTrackCount("subtitle"), 0) or 0)
    for track_index in range(1, subtitle_count + 1):
        enabled = safe(lambda ti=track_index: timeline.GetIsTrackEnabled("subtitle", ti), True)
        if not enabled:
            continue
        clips = safe(lambda ti=track_index: timeline.GetItemListInTrack("subtitle", ti), []) or []
        if clips:
            first_clip = clips[0]
            start = int(safe(lambda c=first_clip: c.GetStart(), 0) or 0)
            end = int(safe(lambda c=clips[-1]: c.GetEnd(), start) or start)
            records.append({{
                "timeline_index": {int(timeline_index)}, "row": row, "kind": "SRT", "track_type": "subtitle",
                "track_index": track_index, "item_index": -1, "unique_id": "",
                "timecode": tc_from_timeline_frame(start), "start_frame": start, "end_frame": end,
                "text": "字幕轨道 " + str(track_index) + "（" + str(len(clips)) + " 条）", "font": "",
                "font_key": "", "supported": False, "reason": "Resolve 19 未公开 SRT 字幕轨道字体读写 API；SRT 按轨道合并显示。"
            }})
            row += 1
    video_count = int(safe(lambda: timeline.GetTrackCount("video"), 0) or 0)
    for track_index in range(1, video_count + 1):
        clips = safe(lambda ti=track_index: timeline.GetItemListInTrack("video", ti), []) or []
        if len(clips) >= SRT2TEXT_GROUP_THRESHOLD:
            sample_count = min(12, len(clips))
            sample_rows = []
            for sample_index in range(sample_count):
                clip = clips[sample_index]
                tools = textplus_tools(clip)
                if not tools:
                    continue
                comp_index, tool_name, tool, text_value, font_value, style_value = tools[0]
                center_value = safe(lambda t=tool: t.GetInput("Center"), None)
                display_font = font_value + ((" " + style_value) if style_value else "")
                sample_rows.append({{
                    "font": display_font,
                    "font_family": font_value,
                    "font_style": style_value,
                    "center": center_value,
                    "text": text_value,
                    "srt2text": clip_has_srt2text_marker(clip),
                }})
            if len(sample_rows) >= max(3, int(sample_count * 0.60)):
                sample_font_counts = {{}}
                sample_center_counts = {{}}
                for item in sample_rows:
                    font_key = str(item.get("font", "") or "").strip()
                    if font_key:
                        sample_font_counts[font_key] = sample_font_counts.get(font_key, 0) + 1
                    center = item.get("center")
                    if isinstance(center, (list, tuple)) and len(center) >= 2:
                        try:
                            bucket = (round(float(center[0]), 1), round(float(center[1]), 1))
                            sample_center_counts[bucket] = sample_center_counts.get(bucket, 0) + 1
                        except Exception:
                            pass
                sample_font_ratio = (max(sample_font_counts.values()) / float(len(sample_rows))) if sample_font_counts else 0.0
                sample_center_ratio = (max(sample_center_counts.values()) / float(len(sample_rows))) if sample_center_counts else 1.0
                sample_marked = any(bool(item.get("srt2text")) for item in sample_rows)
                if sample_marked or (sample_font_ratio >= 0.75 and sample_center_ratio >= 0.60):
                    first_clip = clips[0]
                    last_clip = clips[-1]
                    start = int(safe(lambda c=first_clip: c.GetStart(), 0) or 0)
                    end = int(safe(lambda c=last_clip: c.GetEnd(), start) or start)
                    first = sample_rows[0]
                    records.append({{
                        "timeline_index": {int(timeline_index)}, "row": row, "kind": "Text+组", "track_type": "video",
                        "track_index": track_index, "item_index": -1, "unique_id": "",
                        "timecode": tc_from_timeline_frame(start), "start_frame": start, "end_frame": end,
                        "text": "SRT 转 Text+ 字幕组 / V" + str(track_index) + " / " + str(len(clips)) + " 条",
                        "font": first.get("font", ""), "font_family": first.get("font_family", ""), "font_style": first.get("font_style", ""),
                        "font_key": "group:textplus:track:" + str(track_index),
                        "supported": True,
                        "group": True,
                        "member_count": len(clips),
                        "reason": "字幕 Text+ 已按轨道快速折叠显示；替换字体/应用样式会作用于本轨所有 Text+。依据：抽样数量、字体和位置一致。",
                    }})
                    row += 1
                    continue
        track_textplus_rows = []
        track_other_rows = []
        for item_index, clip in enumerate(clips):
            name = str(safe(lambda c=clip: c.GetName(), "") or "")
            start = int(safe(lambda c=clip: c.GetStart(), 0) or 0)
            end = int(safe(lambda c=clip: c.GetEnd(), start) or start)
            tools = textplus_tools(clip)
            if tools:
                for comp_index, tool_name, tool, text_value, font_value, style_value in tools:
                    display_font = font_value + ((" " + style_value) if style_value else "")
                    center_value = safe(lambda t=tool: t.GetInput("Center"), None)
                    record = {{
                        "timeline_index": {int(timeline_index)}, "row": row, "kind": "Text+", "track_type": "video",
                        "track_index": track_index, "item_index": item_index,
                        "unique_id": str(safe(lambda c=clip: c.GetUniqueId(), "") or ""),
                        "timecode": tc_from_timeline_frame(start), "start_frame": start, "end_frame": end,
                        "text": text_value or name, "font": display_font, "font_family": font_value, "font_style": style_value,
                        "font_key": str(comp_index) + ":" + tool_name + ":Font",
                        "supported": True, "reason": "Text+ Font 输入可写。",
                        "srt2text": clip_has_srt2text_marker(clip),
                        "center": center_value,
                    }}
                    track_textplus_rows.append(record)
                continue
            lower_name = name.lower()
            if "text" in lower_name or "title" in lower_name or "文本" in name or "标题" in name:
                text_font_key, text_font_value, text_value = plain_text_font_property(clip)
                text_supported = bool(text_font_key)
                track_other_rows.append({{
                    "timeline_index": {int(timeline_index)}, "row": row, "kind": "Text", "track_type": "video",
                    "track_index": track_index, "item_index": item_index,
                    "unique_id": str(safe(lambda c=clip: c.GetUniqueId(), "") or ""),
                    "timecode": tc_from_timeline_frame(start), "start_frame": start, "end_frame": end,
                    "text": text_value or name, "font": text_font_value, "font_key": "property:" + text_font_key if text_font_key else "",
                    "supported": text_supported,
                    "reason": ("普通 Text 字体属性可写：" + text_font_key) if text_supported else "当前 Resolve 未公开普通 Text 字体属性；建议改用 Text+。"
                }})
        marked_srt_group = any(bool(item.get("srt2text")) for item in track_textplus_rows)
        font_counts = {{}}
        center_buckets = {{}}
        for item in track_textplus_rows:
            font_key = str(item.get("font", "") or "").strip()
            if font_key:
                font_counts[font_key] = font_counts.get(font_key, 0) + 1
            center = item.get("center")
            if isinstance(center, (list, tuple)) and len(center) >= 2:
                try:
                    bucket = (round(float(center[0]), 1), round(float(center[1]), 1))
                    center_buckets[bucket] = center_buckets.get(bucket, 0) + 1
                except Exception:
                    pass
        dominant_font_ratio = (max(font_counts.values()) / float(len(track_textplus_rows))) if font_counts and track_textplus_rows else 0.0
        dominant_center_ratio = (max(center_buckets.values()) / float(len(track_textplus_rows))) if center_buckets and track_textplus_rows else 0.0
        legacy_srt_like_group = (
            len(track_textplus_rows) >= SRT2TEXT_GROUP_THRESHOLD
            and dominant_font_ratio >= 0.75
            and (not center_buckets or dominant_center_ratio >= 0.60)
        )
        should_group = bool(track_textplus_rows) and (marked_srt_group or legacy_srt_like_group)
        if should_group:
            first = track_textplus_rows[0]
            last = track_textplus_rows[-1]
            fonts = []
            for item in track_textplus_rows:
                font = str(item.get("font", "") or "").strip()
                if font and font not in fonts:
                    fonts.append(font)
            records.append({{
                "timeline_index": {int(timeline_index)}, "row": row, "kind": "Text+组", "track_type": "video",
                "track_index": track_index, "item_index": -1, "unique_id": "",
                "timecode": first.get("timecode", ""), "start_frame": first.get("start_frame", 0), "end_frame": last.get("end_frame", first.get("end_frame", 0)),
                "text": "SRT 转 Text+ 字幕组 / V" + str(track_index) + " / " + str(len(track_textplus_rows)) + " 条",
                "font": fonts[0] if fonts else "", "font_family": first.get("font_family", ""), "font_style": first.get("font_style", ""),
                "font_key": "group:textplus:track:" + str(track_index),
                "supported": True,
                "group": True,
                "member_count": len(track_textplus_rows),
                "reason": "字幕 Text+ 已按轨道折叠显示；替换字体/应用样式会作用于本轨所有 Text+。" + (" 依据：内部 SRT 转换标记。" if marked_srt_group else " 依据：同轨数量、字体和位置一致。"),
            }})
            row += 1
        else:
            for record in track_textplus_rows:
                record["row"] = row
                records.append(record)
                row += 1
        for record in track_other_rows:
            record["row"] = row
            records.append(record)
            row += 1
    records.sort(key=lambda item: (
        int(item.get("start_frame", 0) or 0),
        int(item.get("track_index", 0) or 0),
        int(item.get("item_index", -1) or -1),
        str(item.get("kind", "")),
    ))
    for sorted_row, record in enumerate(records, 1):
        record["row"] = sorted_row
    return records

if ACTION == "scan":
    items = collect_font_items()
    supported = len([item for item in items if item.get("supported")])
    print(json.dumps({{"ok": True, "message": "找到 " + str(len(items)) + " 个字体相关层，可替换 " + str(supported) + " 个。", "items": items}}, ensure_ascii=False))
    raise SystemExit(0)

def set_textplus_text(clip, text):
    text = normalize_subtitle_text(text)
    tools = textplus_tools(clip)
    for _comp_index, _tool_name, tool, _text_value, _font_value, _style_value in tools:
        before = safe(lambda t=tool: t.GetInput("StyledText"), None)
        safe(lambda t=tool, value=text: t.SetInput("StyledText", value), None)
        after = safe(lambda t=tool: t.GetInput("StyledText"), None)
        if after == text or str(after) == str(text) or before == text:
            return True
    return False

def normalize_subtitle_text(value):
    text = str(value or "")
    if "\\n" in text:
        text = text.replace("\\r\\n", "\n").replace("\\n", "\n")
    if "\\u" in text:
        try:
            decoded = text.encode("utf-8").decode("unicode_escape")
            if decoded and decoded != text:
                text = decoded
        except Exception:
            pass
    # Resolve may expose timeline item internals for subtitles. Keep the text
    # usable, but avoid writing obvious empty/internal names into Text+.
    stripped = text.strip()
    internal_prefixes = ("Subtitle ", "字幕 ", "Caption ")
    if any(stripped.startswith(prefix) and stripped[len(prefix):].strip().isdigit() for prefix in internal_prefixes):
        return ""
    return stripped

def subtitle_text_candidates(clip):
    values = []
    props = safe(lambda c=clip: c.GetProperty(), {{}}) or {{}}
    if isinstance(props, dict):
        for key in ("Text", "StyledText", "Subtitle", "Caption", "CustomName", "Comments", "Name", "Clip Name"):
            value = props.get(key)
            if value not in (None, ""):
                values.append(value)
    clip_props = safe(lambda c=clip: c.GetClipProperty(), {{}}) or {{}}
    if isinstance(clip_props, dict):
        for key in ("Text", "StyledText", "Subtitle", "Caption", "Comments", "Name", "Clip Name"):
            value = clip_props.get(key)
            if value not in (None, ""):
                values.append(value)
    values.append(safe(lambda c=clip: c.GetName(), "") or "")
    cleaned = []
    for value in values:
        text = normalize_subtitle_text(value)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned

def collect_subtitle_entries():
    entries = []
    subtitle_count = int(safe(lambda: timeline.GetTrackCount("subtitle"), 0) or 0)
    for track_index in range(1, subtitle_count + 1):
        enabled = safe(lambda ti=track_index: timeline.GetIsTrackEnabled("subtitle", ti), True)
        if not enabled:
            continue
        clips = safe(lambda ti=track_index: timeline.GetItemListInTrack("subtitle", ti), []) or []
        for item_index, clip in enumerate(clips):
            start = int(safe(lambda c=clip: c.GetStart(), 0) or 0)
            end = int(safe(lambda c=clip: c.GetEnd(), start) or start)
            candidates = subtitle_text_candidates(clip)
            text = candidates[0] if candidates else ""
            entries.append({{"track": track_index, "index": item_index, "start": start, "end": max(end, start + 1), "text": text, "text_candidates": candidates[:4]}})
    entries.sort(key=lambda entry: (entry["start"], entry["track"], entry["index"]))
    return entries

def folder_items_recursive(folder):
    items = []
    if not folder:
        return items
    clips = safe(lambda f=folder: f.GetClipList(), []) or []
    items.extend(clips)
    subfolders = safe(lambda f=folder: f.GetSubFolderList(), []) or []
    for child in subfolders:
        items.extend(folder_items_recursive(child))
    return items

def item_label(media_item):
    props = safe(lambda item=media_item: item.GetClipProperty(), {{}}) or {{}}
    if isinstance(props, dict):
        for key in ("Clip Name", "File Name", "Name"):
            value = props.get(key)
            if value not in (None, ""):
                return str(value)
    return str(
        safe(lambda item=media_item: item.GetClipProperty("Clip Name"), "")
        or safe(lambda item=media_item: item.GetClipProperty("File Name"), "")
        or safe(lambda item=media_item: item.GetName(), "")
        or ""
    )

def media_item_uid(media_item):
    return str(safe(lambda item=media_item: item.GetUniqueId(), "") or item_label(media_item))

def media_item_type(media_item):
    props = safe(lambda item=media_item: item.GetClipProperty(), {{}}) or {{}}
    value = ""
    if isinstance(props, dict):
        value = str(
            props.get("Type")
            or props.get("Clip Type")
            or props.get("Usage")
            or props.get("Media Type")
            or props.get("Format")
            or props.get("Codec")
            or ""
        )
    return value

def is_textplus_template_item(media_item):
    label = item_label(media_item)
    lower_label = label.lower()
    type_text = media_item_type(media_item)
    lower_type = type_text.lower()
    if "subtitle" in lower_type or "srt" in lower_type or "字幕轨" in type_text:
        return False
    if "text+" in lower_type or "text plus" in lower_type or "textplus" in lower_type:
        return True
    if "fusion title" in lower_type or ("fusion" in lower_type and "title" in lower_type):
        return True
    if "fusion" in lower_type and "标题" in type_text:
        return True
    if "text+" in lower_label or "text plus" in lower_label or "textplus" in lower_label:
        return True
    # Resolve 19/macOS often exposes user-made Text+ template media items as a
    # generic video/fusion object. If the user named it as a template, keep it
    # visible as a candidate instead of hiding the one item they just created.
    if any(token in label for token in ("模板", "模版", "字幕", "标题")):
        return True
    if any(token in lower_label for token in ("caption", "subtitle", "title", "template")):
        return True
    return False

def is_subtitle_or_audio_media_item(media_item):
    label = item_label(media_item).lower()
    type_text = media_item_type(media_item).lower()
    if any(token in type_text for token in ("subtitle", "srt", "audio", "wav", "mp3", "aac", "video", "视频", "音频", "timeline", "时间线")):
        return True
    if label.endswith(".srt") or label.endswith(".wav") or label.endswith(".mp3") or label.endswith(".aac"):
        return True
    return False

def template_kind(media_item):
    type_text = media_item_type(media_item).lower()
    raw_type_text = media_item_type(media_item)
    label = item_label(media_item).lower()
    if "text+" in type_text or "text plus" in type_text or "textplus" in type_text:
        return "Text+"
    if "fusion title" in type_text or ("fusion" in type_text and "title" in type_text):
        return "Fusion Title"
    if "fusion" in type_text and "标题" in raw_type_text:
        return "Fusion标题"
    if "text+" in label or "text plus" in label or "textplus" in label:
        return "Text+候选"
    return "候选Text+模板"

def parse_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default

def media_item_fps(media_item):
    props = safe(lambda item=media_item: item.GetClipProperty(), {{}}) or {{}}
    if isinstance(props, dict):
        for key in ("FPS", "Frame Rate", "Frame rate"):
            value = props.get(key)
            parsed = parse_float(value, 0.0)
            if parsed > 0:
                return parsed
    return fps

def source_frames_for_timeline_duration(timeline_frames, source_fps):
    duration = max(1, int(timeline_frames or 0))
    src_fps = parse_float(source_fps, fps)
    dst_fps = parse_float(fps, 25.0)
    if src_fps <= 0 or dst_fps <= 0 or abs(src_fps - dst_fps) < 0.001:
        return duration
    # AppendToTimeline endFrame is in source-template frames. Use the minimal
    # source length whose frame-rate-converted result covers the target duration.
    return max(1, int(((duration - 1) * src_fps) // dst_fps) + 1)

def caption_template_score(media_item):
    label = item_label(media_item)
    lower = label.lower()
    type_text = media_item_type(media_item).lower()
    score = 0
    if not is_textplus_template_item(media_item):
        return 0
    for token in ("caption", "subtitle", "text+", "text plus", "title"):
        if token in lower:
            score += 3
    for token in ("字幕", "标题", "模版", "模板"):
        if token in label:
            score += 3
    for token in ("title", "fusion", "text"):
        if token in type_text:
            score += 1
    return score

def list_caption_template_items(media_pool):
    root = safe(lambda: media_pool.GetRootFolder())
    current = safe(lambda: media_pool.GetCurrentFolder())
    selected = []
    for method_name in ("GetSelectedClips", "GetSelectedItems", "GetSelectedMediaPoolItems"):
        method = getattr(media_pool, method_name, None)
        if callable(method):
            selected = safe(lambda method=method: method(), []) or []
            if isinstance(selected, dict):
                selected = list(selected.values())
            if selected:
                break
    current_items = folder_items_recursive(current)
    current_uids = set(media_item_uid(item) for item in current_items)
    selected_uids = set(media_item_uid(item) for item in selected)
    seen = set()
    rows = []
    for media_item in list(selected or []) + current_items + folder_items_recursive(root):
        uid = media_item_uid(media_item)
        if not uid or uid in seen:
            continue
        seen.add(uid)
        score = caption_template_score(media_item)
        is_candidate = uid in selected_uids
        if score <= 0 and (not is_candidate or is_subtitle_or_audio_media_item(media_item)):
            continue
        if score <= 0:
            score = 1
        rows.append({{
            "uid": uid,
            "name": item_label(media_item) or "未命名模板",
            "type": media_item_type(media_item),
            "kind": template_kind(media_item) if caption_template_score(media_item) > 0 else ("媒体池选中候选" if uid in selected_uids else "当前文件夹候选"),
            "textplus": True,
            "fps": media_item_fps(media_item),
            "score": score,
        }})
    rows.sort(key=lambda item: (-int(item.get("score", 0)), str(item.get("name", ""))))
    return rows

def find_caption_template_by_uid(media_pool, uid):
    wanted = str(uid or "")
    if not wanted:
        return None
    root = safe(lambda: media_pool.GetRootFolder())
    current = safe(lambda: media_pool.GetCurrentFolder())
    for media_item in folder_items_recursive(current) + folder_items_recursive(root):
        if media_item_uid(media_item) == wanted:
            return media_item
    return None

def find_caption_template_item(media_pool, before_labels):
    root = safe(lambda: media_pool.GetRootFolder())
    current = safe(lambda: media_pool.GetCurrentFolder())
    candidates = folder_items_recursive(current) + folder_items_recursive(root)
    chosen = None
    for media_item in candidates:
        if not is_textplus_template_item(media_item):
            continue
        label = item_label(media_item)
        lower = label.lower()
        if "caption" in lower or "text" in lower or "subtitle" in lower or "标题" in label or "字幕" in label:
            if label not in before_labels:
                return media_item
            chosen = chosen or media_item
    return chosen

if ACTION == "list_caption_templates":
    media_pool = project.GetMediaPool() if project else None
    if not media_pool:
        print(json.dumps({{"ok": False, "message": "未找到媒体池。", "templates": []}}, ensure_ascii=False))
        raise SystemExit(0)
    templates = list_caption_template_items(media_pool)
    print(json.dumps({{
        "ok": True,
        "templates": templates,
        "message": "找到 " + str(len(templates)) + " 个可能的 Text+ 模板。"
    }}, ensure_ascii=False))
    raise SystemExit(0)

if ACTION == "caption_conversion_info":
    media_pool = project.GetMediaPool() if project else None
    if not media_pool:
        print(json.dumps({{"ok": False, "message": "未找到媒体池。"}}, ensure_ascii=False))
        raise SystemExit(0)
    selected_template_uid = str(ITEM.get("caption_template_uid", "") or "")
    template_item = find_caption_template_by_uid(media_pool, selected_template_uid) if selected_template_uid else None
    template_name = item_label(template_item) if template_item is not None else "内置默认 Text+ 模板"
    # Built-in Resolve 19-compatible template was authored at 25fps. If a user
    # selects a media-pool template, read its real FPS from Resolve.
    template_fps = media_item_fps(template_item) if template_item is not None else 25.0
    mismatch = abs(float(template_fps or fps) - float(fps or template_fps)) >= 0.001
    print(json.dumps({{
        "ok": True,
        "timeline_fps": fps,
        "template_fps": template_fps,
        "template_name": template_name,
        "fps_mismatch": mismatch,
        "message": ("模板帧率与当前时间线不同。") if mismatch else "模板帧率与当前时间线一致。",
    }}, ensure_ascii=False))
    raise SystemExit(0)

def find_textplus_clip_at(start_frame):
    video_count = int(safe(lambda: timeline.GetTrackCount("video"), 0) or 0)
    for track_index in range(video_count, 0, -1):
        clips = safe(lambda ti=track_index: timeline.GetItemListInTrack("video", ti), []) or []
        for item_index, clip in enumerate(clips):
            start = int(safe(lambda c=clip: c.GetStart(), -1) or -1)
            if abs(start - int(start_frame)) <= 1 and textplus_tools(clip):
                return clip
    return None

if ACTION == "convert_srt_textplus":
    try:
        import os
        media_pool = project.GetMediaPool() if project else None
        if not media_pool:
            print(json.dumps({{"ok": False, "message": "未找到媒体池，无法导入 Text+ 模板。"}}, ensure_ascii=False))
            raise SystemExit(0)
        safe(lambda: project.SetCurrentTimeline(timeline), False)
        entries = collect_subtitle_entries()
        if not entries:
            print(json.dumps({{"ok": False, "message": "当前时间线没有启用的 SRT 字幕。"}}, ensure_ascii=False))
            raise SystemExit(0)
        empty_text_count = len([entry for entry in entries if not str(entry.get("text", "")).strip()])
        if empty_text_count >= max(1, int(len(entries) * 0.5)):
            print(json.dumps({{
                "ok": False,
                "message": "已读取到 SRT 时间码，但多数字幕正文为空或是 Resolve 内部名，已停止转换，避免生成乱码 Text+。请先点文字页扫描确认 SRT 文本是否能被当前 Resolve API 读取。",
                "subtitle_count": len(entries),
                "empty_text_count": empty_text_count,
            }}, ensure_ascii=False))
            raise SystemExit(0)
        template_item = None
        imported = False
        template_warning = ""
        resolve_version = safe(lambda: resolve.GetVersion(), []) if resolve else []
        try:
            resolve_major = int(resolve_version[0]) if len(resolve_version) > 0 else 0
        except Exception:
            resolve_major = 0
        selected_template_uid = str(ITEM.get("caption_template_uid", "") or "")
        if selected_template_uid:
            template_item = find_caption_template_by_uid(media_pool, selected_template_uid)
            if template_item is None:
                template_warning = "未找到用户选择的媒体池模板，已改用默认模板/降级插入。"
            else:
                template_warning = "使用媒体池模板：" + item_label(template_item)
        if template_item is None and os.path.exists(CAPTION_TEMPLATE_PATH):
            before_labels = set(item_label(item) for item in folder_items_recursive(safe(lambda: media_pool.GetRootFolder())))
            imported = bool(safe(lambda: media_pool.ImportFolderFromFile(CAPTION_TEMPLATE_PATH), False))
            template_item = find_caption_template_item(media_pool, before_labels)
            if template_item is None:
                print(json.dumps({{"ok": False, "message": "内置 .drb 模板未被当前 Resolve 接受，已停止转换，避免插入到错误轨道。请在媒体池选择一个 Text+ 模板后重试。"}}, ensure_ascii=False))
                raise SystemExit(0)
        elif template_item is None:
            print(json.dumps({{"ok": False, "message": "缺少内置 .drb 模板，且未选择媒体池 Text+ 模板，已停止转换。"}}, ensure_ascii=False))
            raise SystemExit(0)
        old_video_count = int(safe(lambda: timeline.GetTrackCount("video"), 0) or 0)
        added_track = bool(safe(lambda: timeline.AddTrack("video"), False))
        new_video_count = int(safe(lambda: timeline.GetTrackCount("video"), old_video_count) or old_video_count)
        target_track = new_video_count if new_video_count > old_video_count else max(1, old_video_count)
        template_fps = media_item_fps(template_item) if template_item is not None else fps
        created = 0
        text_written = 0
        fallback_used = 0
        append_failed = 0
        markers_written = 0
        created_by_start = {{}}
        group_id = str(safe(lambda: timeline.GetUniqueId(), "") or "timeline") + "-" + str(len(entries))
        if template_item is not None:
            chunk_size = 100
            for offset in range(0, len(entries), chunk_size):
                chunk = entries[offset:offset + chunk_size]
                payload = []
                for entry in chunk:
                    dur = max(1, int(entry["end"]) - int(entry["start"]))
                    source_dur = source_frames_for_timeline_duration(dur, template_fps)
                    payload.append({{
                        "mediaPoolItem": template_item,
                        "startFrame": 0,
                        "endFrame": max(0, source_dur - 1),
                        "recordFrame": int(entry["start"]),
                        "trackIndex": target_track,
                    }})
                result = safe(lambda payload=payload: media_pool.AppendToTimeline(payload), None)
                result_items = result if isinstance(result, list) else []
                if not result:
                    append_failed += len(chunk)
                    continue
                for local_index, entry in enumerate(chunk):
                    created_clip = None
                    if local_index < len(result_items):
                        candidate = result_items[local_index]
                        if candidate and textplus_tools(candidate):
                            created_clip = candidate
                    if created_clip is None:
                        created_clip = find_textplus_clip_at(entry["start"])
                    if created_clip is None:
                        append_failed += 1
                        continue
                    dur = max(1, int(entry["end"]) - int(entry["start"]))
                    created_by_start[int(entry["start"])] = created_clip
                    created += 1
                    if mark_srt2text_clip(created_clip, group_id, created, len(entries)):
                        markers_written += 1
                    if set_textplus_text(created_clip, entry["text"]):
                        text_written += 1
                    safe(lambda clip=created_clip, dur=dur: clip.SetProperty("Duration", dur), None)
        message = "SRT 转 Text+ 完成：字幕 " + str(len(entries)) + " 条，创建 " + str(created) + " 条，写入文字 " + str(text_written) + " 条。"
        message += " 目标视频轨：V" + str(target_track) + ("（新建）" if added_track and new_video_count > old_video_count else "（未能新建，使用现有最上层）") + "。"
        if WRITE_SRT2TEXT_MARKERS:
            message += " 已写入内部标记 " + str(markers_written) + " 个。"
        else:
            message += " 内部标记默认关闭，转换会更快；如需字体面板更稳地折叠同批字幕，可下次勾选写入转换标记。"
        if fallback_used:
            message += " 其中 " + str(fallback_used) + " 条使用降级插入，位置/时长需抽查。"
        if append_failed:
            message += " AppendToTimeline 未接受 " + str(append_failed) + " 条。"
        if created <= 0:
            message += " 未执行降级插入，避免 Text+ 跑到错误轨道或覆盖视图。"
        if template_item is not None and abs(float(template_fps or fps) - float(fps or template_fps)) >= 0.001:
            message += " 已按模板 " + str(template_fps) + "fps → 时间线 " + str(fps) + "fps 补偿时长。"
        if template_warning:
            message += " " + template_warning
        print(json.dumps({{"ok": created > 0, "message": message, "count": created, "text_written": text_written, "subtitle_count": len(entries), "fallback": fallback_used, "imported": bool(imported), "markers_written": markers_written, "write_markers": bool(WRITE_SRT2TEXT_MARKERS)}}, ensure_ascii=False))
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({{"ok": False, "message": "SRT 转 Text+ 异常：" + str(exc)[:200]}}, ensure_ascii=False))
    raise SystemExit(0)

def group_textplus_clips(track_index):
    clips = safe(lambda ti=track_index: timeline.GetItemListInTrack("video", ti), []) or []
    return [clip for clip in clips if textplus_tools(clip)]

target_is_group = bool(ITEM.get("group")) or str(ITEM.get("font_key", "") or "").startswith("group:textplus:track:")
target_group_clips = group_textplus_clips(int(ITEM.get("track_index", 1))) if target_is_group else []
target = target_group_clips[0] if target_group_clips else get_item(str(ITEM.get("track_type", "video")), int(ITEM.get("track_index", 1)), int(ITEM.get("item_index", -1)))
if ACTION == "jump":
    tc = str(ITEM.get("timecode", ""))
    ok = bool(tc and timeline.SetCurrentTimecode(tc))
    if resolve:
        resolve.OpenPage("edit")
    print(json.dumps({{"ok": ok, "message": ("已跳转到 " + tc) if ok else "跳转失败。"}}, ensure_ascii=False))
elif ACTION == "copy_style":
    try:
        if target is None:
            print(json.dumps({{"ok": False, "message": "目标 Text+ 不存在。"}}, ensure_ascii=False))
            raise SystemExit(0)
        if str(ITEM.get("kind", "")).lower() not in ("text+", "text+组") or not bool(ITEM.get("supported")):
            print(json.dumps({{"ok": False, "message": "请选择状态为可替换的 Text+ 作为样式来源。"}}, ensure_ascii=False))
            raise SystemExit(0)
        tool = target_textplus_tool(target)
        if tool is None:
            print(json.dumps({{"ok": False, "message": "未找到对应的 Text+ 工具。"}}, ensure_ascii=False))
            raise SystemExit(0)
        values = copy_textplus_style_from_tool(tool)
        groups = textplus_style_group_counts(values)
        group_text = "，".join([str(key) + str(value) for key, value in sorted(groups.items())])
        print(json.dumps({{
            "ok": bool(values),
            "style": values,
            "count": len(values),
            "groups": groups,
            "message": ("已复制 Text+ 样式 " + str(len(values)) + " 项（" + group_text + "）；不会复制文字内容、Write-on、全局时段、位置/布局和内部脚本。") if values else "没有读取到可复制的 Text+ 样式。",
        }}, ensure_ascii=False))
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({{"ok": False, "message": "Text+ 样式复制异常：" + str(exc)[:200]}}, ensure_ascii=False))
elif ACTION == "copy_position":
    try:
        if target is None:
            print(json.dumps({{"ok": False, "message": "目标 Text+ 不存在。"}}, ensure_ascii=False))
            raise SystemExit(0)
        if str(ITEM.get("kind", "")).lower() not in ("text+", "text+组") or not bool(ITEM.get("supported")):
            print(json.dumps({{"ok": False, "message": "请选择状态为可替换的 Text+ 作为位置来源。"}}, ensure_ascii=False))
            raise SystemExit(0)
        tool = target_textplus_tool(target)
        if tool is None:
            print(json.dumps({{"ok": False, "message": "未找到对应的 Text+ 工具。"}}, ensure_ascii=False))
            raise SystemExit(0)
        values = copy_textplus_position_from_tool(tool)
        timeline_values = copy_timeline_position_from_clip(target)
        if values or timeline_values:
            values["__textplus_position__"] = True
        if timeline_values:
            values["__timeline_position__"] = timeline_values
        print(json.dumps({{
            "ok": bool(values),
            "style": values,
            "count": len(values),
            "fusion_count": len([key for key in values.keys() if not str(key).startswith("__")]),
            "timeline_count": len(timeline_values),
            "groups": textplus_style_group_counts({{key: value for key, value in values.items() if not str(key).startswith("__")}}),
            "message": ("已复制 Text+ 位置 " + str(len(values)) + " 项；包含 Fusion 布局/变换位置和检查器设置里的 X/Y/缩放/旋转/锚点。") if values else "没有读取到可复制的位置参数。",
        }}, ensure_ascii=False))
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({{"ok": False, "message": "Text+ 位置复制异常：" + str(exc)[:200]}}, ensure_ascii=False))
elif ACTION == "apply_style":
    try:
        if target is None:
            print(json.dumps({{"ok": False, "message": "目标 Text+ 不存在。"}}, ensure_ascii=False))
            raise SystemExit(0)
        if str(ITEM.get("kind", "")).lower() not in ("text+", "text+组") or not bool(ITEM.get("supported")):
            print(json.dumps({{"ok": False, "message": "请选择状态为可替换的 Text+。"}}, ensure_ascii=False))
            raise SystemExit(0)
        if not isinstance(STYLE_PAYLOAD, dict) or not STYLE_PAYLOAD:
            print(json.dumps({{"ok": False, "message": "请先复制 Text+ 样式。"}}, ensure_ascii=False))
            raise SystemExit(0)
        targets = target_group_clips if target_is_group else [target]
        ok_count = 0
        fail_count = 0
        changed_clips = 0
        timeline_position_values = STYLE_PAYLOAD.get("__timeline_position__") if isinstance(STYLE_PAYLOAD.get("__timeline_position__"), dict) else {{}}
        for target_clip in targets:
            tool = target_textplus_tool(target_clip)
            if tool is None:
                fail_count += 1
                continue
            clip_ok, clip_fail = apply_textplus_style_to_tool(tool, STYLE_PAYLOAD)
            if timeline_position_values:
                prop_ok, prop_fail = apply_timeline_position_to_clip(target_clip, timeline_position_values)
                clip_ok += prop_ok
                clip_fail += prop_fail
            ok_count += clip_ok
            fail_count += clip_fail
            if clip_ok > 0:
                changed_clips += 1
        if ok_count <= 0:
            print(json.dumps({{"ok": False, "message": "未找到对应的 Text+ 工具。"}}, ensure_ascii=False))
            raise SystemExit(0)
        print(json.dumps({{
            "ok": ok_count > 0,
            "applied": ok_count,
            "failed": fail_count,
            "changed_clips": changed_clips,
            "message": "已应用 Text+ 样式：" + str(ok_count) + " 项，失败 " + str(fail_count) + " 项；已跳过文字内容、Write-on、全局时段、位置/布局和内部脚本。" + ((" 已处理字幕组 " + str(changed_clips) + " 条。") if target_is_group else ""),
        }}, ensure_ascii=False))
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({{"ok": False, "message": "Text+ 样式应用异常：" + str(exc)[:200]}}, ensure_ascii=False))
elif ACTION == "replace":
    try:
        if not FONT_NAME:
            print(json.dumps({{"ok": False, "message": "未选择目标字体。"}}, ensure_ascii=False))
            raise SystemExit(0)
        if not bool(ITEM.get("supported")):
            print(json.dumps({{"ok": False, "message": str(ITEM.get("reason", "该字体层不支持程序化替换。"))}}, ensure_ascii=False))
            raise SystemExit(0)
        if target is None:
            print(json.dumps({{"ok": False, "message": "目标字体层不存在。"}}, ensure_ascii=False))
            raise SystemExit(0)
        if target_is_group:
            changed_clips = 0
            accepted_font = ""
            accepted_candidate = ""
            registered_font_path = ""
            registered_font_name = ""
            candidate_attempts = 0
            candidate_trace = []
            current_font = ""
            for target_clip in target_group_clips:
                tool = target_textplus_tool(target_clip)
                if tool is None:
                    continue
                before_font = str(safe(lambda t=tool: t.GetInput("Font"), "") or "")
                styled_text = safe(lambda t=tool: t.GetInput("StyledText"), None)
                for candidate in FONT_CANDIDATES or [FONT_NAME]:
                    candidate_font, candidate_style, candidate_path = parse_font_candidate(candidate)
                    registered = register_font_candidate(candidate_path, candidate_font)
                    candidate_attempts += 1
                    if not fusion_font_available(candidate_font, candidate_path):
                        if len(candidate_trace) < 24:
                            trace_item = font_candidate_probe(candidate, False, registered, "", "")
                            trace_item["unavailable"] = True
                            candidate_trace.append(trace_item)
                        continue
                    set_font_name = fusion_font_resolved_name(candidate_font, candidate_path)
                    set_result = safe(lambda t=tool, name=set_font_name: t.SetInput("Font", name), None)
                    if candidate_style:
                        safe(lambda t=tool, style=candidate_style: t.SetInput("Style", style), None)
                    if styled_text not in (None, ""):
                        safe(lambda t=tool, text=styled_text: t.SetInput("StyledText", text), None)
                    current_font = str(safe(lambda t=tool: t.GetInput("Font"), "") or "")
                    current_style = str(safe(lambda t=tool: t.GetInput("Style"), "") or "")
                    path_backed = bool(candidate_path)
                    accepted = (
                        current_font in {{candidate_font, set_font_name}}
                        or (current_font and current_font != before_font)
                        or (path_backed and set_result is not False and current_font == set_font_name)
                    )
                    if len(candidate_trace) < 24:
                        candidate_trace.append(font_candidate_probe(candidate, accepted, registered, current_font, current_style))
                    if accepted:
                        changed_clips += 1
                        accepted_font = FONT_NAME or (candidate_font + ((" " + current_style) if current_style else ""))
                        if not accepted_candidate:
                            accepted_candidate = str(candidate or "")
                            registered_font_path = str(candidate_path or "")
                            registered_font_name = candidate_font
                        break
            fusion_unavailable = (changed_clips <= 0 and all_traced_candidates_unavailable(candidate_trace, candidate_attempts))
            print(json.dumps(font_replace_result(changed_clips > 0, current_font, accepted_font, ("字幕 Text+ 组字体已替换为 " + (accepted_font or FONT_NAME) + "：" + str(changed_clips) + " 条。") if changed_clips else (fusion_unavailable_message(FONT_NAME) if fusion_unavailable else "Resolve 未接受该字体名，请尝试字体的中文/英文/PostScript 名称。"), changed_clips=changed_clips, accepted_candidate=accepted_candidate, registered_font_path=registered_font_path, registered_font_name=registered_font_name, candidate_attempts=candidate_attempts, candidate_trace=candidate_trace, error_code=("fusion_font_unavailable" if fusion_unavailable else ""), probe_warning=""), ensure_ascii=False))
            raise SystemExit(0)
        ok = False
        current_font = ""
        accepted_font = ""
        accepted_candidate = ""
        registered_font_path = ""
        registered_font_name = ""
        candidate_attempts = 0
        candidate_trace = []
        requested_key = str(ITEM.get("font_key", "") or "")
        requested_comp = ""
        requested_tool = ""
        if requested_key:
            parts = requested_key.split(":")
            if len(parts) >= 2:
                requested_comp = parts[0]
                requested_tool = parts[1]
        if requested_key.startswith("property:"):
            property_key = requested_key.split(":", 1)[1]
            before_font = str(safe(lambda: target.GetProperty().get(property_key, ""), "") or "")
            for candidate in FONT_CANDIDATES or [FONT_NAME]:
                candidate_font, candidate_style, candidate_path = parse_font_candidate(candidate)
                registered = register_font_candidate(candidate_path, candidate_font)
                candidate_attempts += 1
                if not fusion_font_available(candidate_font, candidate_path):
                    if len(candidate_trace) < 24:
                        trace_item = font_candidate_probe(candidate, False, registered, "", "")
                        trace_item["unavailable"] = True
                        candidate_trace.append(trace_item)
                    continue
                set_font_name = fusion_font_resolved_name(candidate_font, candidate_path)
                set_ok = bool(safe(lambda key=property_key, name=set_font_name: target.SetProperty(key, name), False))
                if set_ok:
                    current_font = str(safe(lambda key=property_key: target.GetProperty().get(key, ""), "") or "")
                accepted = set_ok and (current_font in {{candidate_font, set_font_name}} or (current_font and current_font != before_font))
                if len(candidate_trace) < 24:
                    candidate_trace.append(font_candidate_probe(candidate, accepted, registered, current_font, ""))
                if accepted:
                    ok = True
                    accepted_font = FONT_NAME or (candidate_font + ((" " + candidate_style) if candidate_style else ""))
                    accepted_candidate = str(candidate or "")
                    registered_font_path = str(candidate_path or "")
                    registered_font_name = candidate_font
                    break
            fusion_unavailable = (not ok and all_traced_candidates_unavailable(candidate_trace, candidate_attempts))
            print(json.dumps(font_replace_result(ok, current_font, accepted_font, ("普通 Text 字体已替换为 " + (accepted_font or FONT_NAME)) if ok else (fusion_unavailable_message(FONT_NAME) if fusion_unavailable else "Resolve 未接受普通 Text 字体写入，请尝试字体的中文/英文/PostScript 名称。"), accepted_candidate=accepted_candidate, registered_font_path=registered_font_path, registered_font_name=registered_font_name, candidate_attempts=candidate_attempts, candidate_trace=candidate_trace, error_code=("fusion_font_unavailable" if fusion_unavailable else ""), probe_warning=""), ensure_ascii=False))
            raise SystemExit(0)
        fusion_count = int(safe(lambda: target.GetFusionCompCount(), 0) or 0)
        for comp_index in range(1, fusion_count + 1):
            comp = safe(lambda: target.GetFusionCompByIndex(comp_index))
            tools = safe(lambda c=comp: c.GetToolList(False), {{}}) if comp is not None else {{}}
            iterable = tools.items() if isinstance(tools, dict) else []
            for tool_name, tool in iterable:
                if requested_comp and str(comp_index) != requested_comp:
                    continue
                if requested_tool and str(tool_name) != requested_tool:
                    continue
                tool_id = str(safe(lambda t=tool: t.ID, "") or "")
                current_font = str(safe(lambda t=tool: t.GetInput("Font"), "") or "")
                if tool_id == "TextPlus" or current_font:
                    before_font = current_font
                    styled_text = safe(lambda t=tool: t.GetInput("StyledText"), None)
                    for candidate in FONT_CANDIDATES or [FONT_NAME]:
                        candidate_font, candidate_style, candidate_path = parse_font_candidate(candidate)
                        registered = register_font_candidate(candidate_path, candidate_font)
                        candidate_attempts += 1
                        if not fusion_font_available(candidate_font, candidate_path):
                            if len(candidate_trace) < 24:
                                trace_item = font_candidate_probe(candidate, False, registered, current_font, "")
                                trace_item["unavailable"] = True
                                candidate_trace.append(trace_item)
                            continue
                        set_font_name = fusion_font_resolved_name(candidate_font, candidate_path)
                        set_result = safe(lambda t=tool, name=set_font_name: t.SetInput("Font", name), None)
                        if candidate_style:
                            safe(lambda t=tool, style=candidate_style: t.SetInput("Style", style), None)
                        if styled_text not in (None, ""):
                            safe(lambda t=tool, text=styled_text: t.SetInput("StyledText", text), None)
                        current_font = str(safe(lambda t=tool: t.GetInput("Font"), "") or "")
                        current_style = str(safe(lambda t=tool: t.GetInput("Style"), "") or "")
                        path_backed = bool(candidate_path)
                        accepted = (
                            current_font in {{candidate_font, set_font_name}}
                            or (current_font and current_font != before_font)
                            or (path_backed and set_result is not False and current_font == set_font_name)
                        )
                        if len(candidate_trace) < 24:
                            candidate_trace.append(font_candidate_probe(candidate, accepted, registered, current_font, current_style))
                        if accepted:
                            ok = True
                            accepted_font = FONT_NAME or (candidate_font + ((" " + current_style) if current_style else ""))
                            accepted_candidate = str(candidate or "")
                            registered_font_path = str(candidate_path or "")
                            registered_font_name = candidate_font
                            break
                    break
            if ok:
                break
        fusion_unavailable = (not ok and all_traced_candidates_unavailable(candidate_trace, candidate_attempts))
        print(json.dumps(font_replace_result(ok, current_font, accepted_font, ("字体已替换为 " + (accepted_font or FONT_NAME)) if ok else (fusion_unavailable_message(FONT_NAME) if fusion_unavailable else "Resolve 未接受该字体名，请尝试字体的中文/英文/PostScript 名称。"), accepted_candidate=accepted_candidate, registered_font_path=registered_font_path, registered_font_name=registered_font_name, candidate_attempts=candidate_attempts, candidate_trace=candidate_trace, error_code=("fusion_font_unavailable" if fusion_unavailable else ""), probe_warning=""), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({{"ok": False, "message": "字体替换异常：" + str(exc)[:200]}}, ensure_ascii=False))
''',
            timeout=timeout,
        )
        if not data:
            return {"ok": False, "message": "字体操作失败：Resolve API 未返回结果。", "items": []}
        return data

    def _text_action(
        self,
        timeline_index: int,
        action: str,
        query: str = "",
        scan_types: list[str] | None = None,
        item: dict[str, Any] | None = None,
        text: str = "",
    ) -> dict[str, Any]:
        action = action if action in {"scan", "jump", "replace", "delete", "restore_delete"} else "scan"
        template_path = Path(__file__).resolve().with_name("templates") / "caption-bin.drb"
        data = self._run_resolve_python(
            rf'''
import json
ACTION = {json.dumps(action)}
QUERY = {json.dumps(query)}
SCAN_TYPES = {json.dumps(scan_types or ["srt"])}
ITEM = {json.dumps(item or {}, ensure_ascii=False)}
NEW_TEXT = {json.dumps(text, ensure_ascii=False)}
CAPTION_TEMPLATE_PATH = {json.dumps(str(template_path))}
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
timeline = project.GetTimelineByIndex({int(timeline_index)}) if project else None
media_pool = project.GetMediaPool() if project else None
if not timeline:
    print(json.dumps({{"ok": False, "message": "未找到目标时间线。", "items": []}}, ensure_ascii=False))
    raise SystemExit(0)

def safe(callable_obj, default=None):
    try:
        return callable_obj()
    except Exception:
        return default

def tc_from_frame(frame, fps):
    fps_int = max(1, int(round(float(fps or 25))))
    total = max(0, int(round(float(frame or 0))))
    ff = total % fps_int
    total_seconds = total // fps_int
    ss = total_seconds % 60
    mm = (total_seconds // 60) % 60
    hh = total_seconds // 3600
    return "%02d:%02d:%02d:%02d" % (hh, mm, ss, ff)

fps_raw = safe(lambda: timeline.GetSetting("timelineFrameRate"), None) or safe(lambda: project.GetSetting("timelineFrameRate"), None) or 25
try:
    fps = float(fps_raw)
except Exception:
    fps = 25.0
start_frame = safe(lambda: timeline.GetStartFrame(), 0) or 0
start_timecode = str(safe(lambda: timeline.GetStartTimecode(), None) or safe(lambda: timeline.GetSetting("timelineStartTimecode"), None) or "00:00:00:00")
TEXT_KEYS = ["Text", "StyledText", "Text+", "Title", "Subtitle", "Caption", "Name", "Clip Name", "CustomName", "Comments"]
TITLE_HINT_KEYS = {"Text", "StyledText", "Text+", "Title", "Subtitle", "Caption", "CustomName"}
SCAN_TYPE_SET = set(SCAN_TYPES or ["srt"])
CURRENT_TRACK_TYPE = ""

def timecode_to_frames(tc, fps):
    fps_int = max(1, int(round(float(fps or 25))))
    parts = str(tc or "00:00:00:00").split(":")
    if len(parts) != 4:
        return 0
    try:
        hh, mm, ss, ff = [int(float(part)) for part in parts]
    except Exception:
        return 0
    return (((hh * 60) + mm) * 60 + ss) * fps_int + ff

def tc_from_timeline_frame(frame, fps, timeline_start_frame, timeline_start_tc):
    rel = int(round(float(frame or 0))) - int(round(float(timeline_start_frame or 0)))
    return tc_from_frame(timecode_to_frames(timeline_start_tc, fps) + max(0, rel), fps)

def get_item(track_type, track_index, item_index):
    clips = safe(lambda: timeline.GetItemListInTrack(track_type, track_index), []) or []
    target_uid = str(ITEM.get("unique_id", "") or "")
    if target_uid:
        for clip in clips:
            uid = str(safe(lambda c=clip: c.GetUniqueId(), "") or "")
            if uid == target_uid:
                return clip
    if item_index < 0 or item_index >= len(clips):
        return None
    return clips[item_index]

def item_text(clip):
    if str(CURRENT_TRACK_TYPE) == "subtitle":
        return str(safe(lambda: clip.GetName(), "") or ""), "Name", "name"

    # Text+ is a Fusion title. Prefer its live StyledText over timeline item
    # properties such as Name/Clip Name, otherwise edits update metadata instead
    # of the visible text in Resolve.
    fusion_count = int(safe(lambda: clip.GetFusionCompCount(), 0) or 0)
    for comp_index in range(1, fusion_count + 1):
        comp = safe(lambda ci=comp_index: clip.GetFusionCompByIndex(ci))
        tools = safe(lambda c=comp: c.GetToolList(False), {{}}) if comp else {{}}
        iterable = tools.items() if isinstance(tools, dict) else []
        for tool_name, tool in iterable:
            for input_key in ("StyledText", "Text", "Input"):
                value = safe(lambda t=tool, k=input_key: t.GetInput(k))
                if value not in (None, ""):
                    return str(value), str(tool_name) + ":" + input_key, "fusion"

    props = safe(lambda: clip.GetProperty(), {{}}) or {{}}
    for key in TEXT_KEYS:
        value = props.get(key)
        if value not in (None, ""):
            return str(value), key, "property"
    return str(safe(lambda: clip.GetName(), "") or ""), "Name", "name"

def classify_text_item(track_type, text_key, source, clip):
    if track_type == "subtitle":
        return "srt"
    key = str(text_key or "").lower()
    name = str(safe(lambda: clip.GetName(), "") or "").lower()
    if source == "fusion" or "text+" in key or "textplus" in name or "text+" in name:
        return "text_plus"
    return "text"

def set_item_text(clip, key, source, new_text):
    """Try to set text on a clip. Returns (ok, method_used)."""
    def try_write(writer):
        return bool(safe(writer, False))

    def find_tool_by_key(tools, wanted_name):
        if not isinstance(tools, dict):
            return None
        wanted = str(wanted_name)
        for tool_key, tool_value in tools.items():
            if str(tool_key) == wanted:
                return tool_value
            tool_name = str(safe(lambda t=tool_value: t.GetAttrs().get("TOOLS_Name"), "") or "")
            if tool_name and tool_name == wanted:
                return tool_value
        return None

    # Fusion clip: write into the Text+ tool input
    if source == "fusion" and ":" in str(key):
        tool_name, input_key = str(key).split(":", 1)
        fusion_count = int(safe(lambda: clip.GetFusionCompCount(), 0) or 0)
        for comp_index in range(1, fusion_count + 1):
            comp = safe(lambda ci=comp_index: clip.GetFusionCompByIndex(ci))
            tools = safe(lambda c=comp: c.GetToolList(False), {{}}) if comp else {{}}
            tool = find_tool_by_key(tools, tool_name)
            if not tool:
                continue
            safe(lambda t=tool, k=input_key, value=new_text: t.SetInput(k, value), None)
            after = safe(lambda t=tool, k=input_key: t.GetInput(k), None)
            if str(after or "") == str(new_text):
                return True, "Fusion:" + str(tool_name) + "." + str(input_key)

    # Non-fusion subtitle / text / Text+ clips
    prop_keys = []
    if key and key not in ("Name",):
        prop_keys.append(key)
    prop_keys.extend(["StyledText", "Text", "Subtitle", "Caption", "Name", "Clip Name", "Comments"])
    for prop_key in prop_keys:
        if not prop_key:
            continue
        pk = prop_key  # capture for closure
        if try_write(lambda pk=pk: clip.SetProperty(pk, new_text)):
            return True, "SetProperty(" + str(pk) + ")"

    # SetName is NOT available on subtitle clips in Resolve API
    setname_fn = getattr(clip, "SetName", None)
    if callable(setname_fn) and try_write(lambda: setname_fn(new_text)):
        return True, "SetName"

    return False, ""

def json_safe(value):
    try:
        json.dumps(value, ensure_ascii=False)
        return True
    except Exception:
        return False

def textplus_restore_style(clip, key):
    if not clip:
        return {{}}
    wanted_tool_name = ""
    if ":" in str(key or ""):
        wanted_tool_name, _input_key = str(key).split(":", 1)
    fusion_count = int(safe(lambda: clip.GetFusionCompCount(), 0) or 0)
    snapshot = {{
        "snapshot_version": 2,
        "clip_name": str(safe(lambda: clip.GetName(), "") or ""),
        "timeline_properties": {{}},
        "fusion_inputs": {{}},
    }}
    props = safe(lambda: clip.GetProperty(), {{}}) or {{}}
    if isinstance(props, dict):
        for prop_key, prop_value in props.items():
            prop_key_text = str(prop_key or "").strip()
            if prop_key_text and json_safe(prop_value):
                snapshot["timeline_properties"][prop_key_text] = prop_value
    for comp_index in range(1, fusion_count + 1):
        comp = safe(lambda ci=comp_index: clip.GetFusionCompByIndex(ci))
        tools = safe(lambda c=comp: c.GetToolList(False), {{}}) if comp else {{}}
        tool = None
        if isinstance(tools, dict):
            for tool_key, tool_value in tools.items():
                tool_id = str(safe(lambda t=tool_value: t.ID, "") or "")
                styled = safe(lambda t=tool_value: t.GetInput("StyledText"), None)
                font = safe(lambda t=tool_value: t.GetInput("Font"), None)
                if wanted_tool_name and str(tool_key) == str(wanted_tool_name):
                    tool = tool_value
                    break
                attr_name = str(safe(lambda t=tool_value: t.GetAttrs().get("TOOLS_Name"), "") or "")
                if wanted_tool_name and attr_name and attr_name == str(wanted_tool_name):
                    tool = tool_value
                    break
                if not wanted_tool_name and (tool_id == "TextPlus" or styled not in (None, "") or font not in (None, "")):
                    tool = tool_value
                    break
        if not tool:
            continue
        input_list = safe(lambda t=tool: t.GetInputList(), {{}}) or {{}}
        keys = []
        if isinstance(input_list, dict):
            for input_key, input_obj in input_list.items():
                text_key = str(input_key or "").strip()
                if text_key:
                    keys.append(text_key)
                attrs = safe(lambda obj=input_obj: obj.GetAttrs(), {{}}) or {{}}
                if isinstance(attrs, dict):
                    for attr_key in ("INPS_ID", "LINKS_Name", "TOOLS_Name"):
                        attr_value = str(attrs.get(attr_key, "") or "").strip()
                        if attr_value:
                            keys.append(attr_value)
        for restore_key in keys:
            if restore_key in snapshot["fusion_inputs"]:
                continue
            value = safe(lambda t=tool, k=restore_key: t.GetInput(k), None)
            if value not in (None, "") and json_safe(value):
                snapshot["fusion_inputs"][restore_key] = value
        return snapshot
    return snapshot

def apply_textplus_restore_style(clip, values):
    if not clip:
        return 0, 0
    if isinstance(values, dict) and "fusion_inputs" in values:
        fusion_values = values.get("fusion_inputs") if isinstance(values.get("fusion_inputs"), dict) else {{}}
    else:
        fusion_values = values or {{}}
    tool = None
    fusion_count = int(safe(lambda: clip.GetFusionCompCount(), 0) or 0)
    for comp_index in range(1, fusion_count + 1):
        comp = safe(lambda ci=comp_index: clip.GetFusionCompByIndex(ci))
        tools = safe(lambda c=comp: c.GetToolList(False), {{}}) if comp else {{}}
        iterable = tools.items() if isinstance(tools, dict) else []
        for _tool_name, candidate in iterable:
            styled = safe(lambda t=candidate: t.GetInput("StyledText"), None)
            font = safe(lambda t=candidate: t.GetInput("Font"), None)
            tool_id = str(safe(lambda t=candidate: t.ID, "") or "")
            if tool_id == "TextPlus" or styled not in (None, "") or font not in (None, ""):
                tool = candidate
                break
        if tool:
            break
    if not tool:
        return 0, len(fusion_values or {{}})
    ok_count = 0
    fail_count = 0
    for restore_key, value in (fusion_values or {{}}).items():
        safe(lambda t=tool, k=restore_key, v=value: t.SetInput(k, v), None)
        after = safe(lambda t=tool, k=restore_key: t.GetInput(k), None)
        if after == value or str(after) == str(value):
            ok_count += 1
        else:
            fail_count += 1
    return ok_count, fail_count

def apply_textplus_timeline_snapshot(clip, snapshot):
    if not clip or not isinstance(snapshot, dict):
        return 0, 0
    props = snapshot.get("timeline_properties") if isinstance(snapshot.get("timeline_properties"), dict) else {{}}
    blocked = {{
        "File Path", "File Name", "Type", "Resolution", "FPS", "Frames", "Duration",
        "Start", "End", "Media Start", "Media End", "Offline Reference",
        "Data Level", "Alpha mode", "Super Scale", "Input Sizing Preset",
    }}
    ok_count = 0
    fail_count = 0
    for prop_key, prop_value in props.items():
        prop_name = str(prop_key or "").strip()
        if not prop_name or prop_name in blocked:
            continue
        wrote = bool(safe(lambda k=prop_name, v=prop_value: clip.SetProperty(k, v), False))
        if wrote:
            ok_count += 1
        else:
            fail_count += 1
    clip_name = str(snapshot.get("clip_name", "") or "").strip()
    if clip_name:
        setname_fn = getattr(clip, "SetName", None)
        if callable(setname_fn) and bool(safe(lambda: setname_fn(clip_name), False)):
            ok_count += 1
        elif bool(safe(lambda: clip.SetProperty("Name", clip_name), False)):
            ok_count += 1
    return ok_count, fail_count

def frame_to_srt(f):
    rel = max(0, int(f) - int(start_frame or 0))
    total_sec = rel / max(1.0, float(fps or 25))
    h = int(total_sec // 3600)
    m = int((total_sec % 3600) // 60)
    s = int(total_sec % 60)
    ms = int((total_sec - int(total_sec)) * 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)

def cleanup_imported_media_pool_item(imported_item):
    if not media_pool or not imported_item:
        return False
    return bool(safe(lambda: media_pool.DeleteClips([imported_item]), False))

def import_builtin_textplus_template():
    if not media_pool:
        return None, "未找到媒体池。"
    import os
    if not os.path.exists(CAPTION_TEMPLATE_PATH):
        return None, "缺少内置 Text+ 模板。"
    folder = safe(lambda: media_pool.GetCurrentFolder(), None)
    before = set()
    clips = safe(lambda: folder.GetClipList(), []) if folder else []
    for media_item in clips or []:
        label = str(safe(lambda item=media_item: item.GetName(), "") or "")
        uid = str(safe(lambda item=media_item: item.GetUniqueId(), "") or "")
        before.add(uid + "|" + label)
    ok = bool(safe(lambda: media_pool.ImportFolderFromFile(CAPTION_TEMPLATE_PATH), False))
    if not ok:
        return None, "内置 Text+ 模板导入失败。"
    clips = safe(lambda: folder.GetClipList(), []) if folder else []
    fallback = None
    for media_item in clips or []:
        label = str(safe(lambda item=media_item: item.GetName(), "") or "")
        uid = str(safe(lambda item=media_item: item.GetUniqueId(), "") or "")
        if uid + "|" + label not in before:
            return media_item, ""
        if "text" in label.lower() or "caption" in label.lower() or "字幕" in label:
            fallback = media_item
    return fallback, "" if fallback else "未找到导入后的 Text+ 模板。"

def find_textplus_clip_at(track_index, start_frame):
    clips = safe(lambda: timeline.GetItemListInTrack("video", int(track_index)), []) or []
    for clip in clips:
        s = int(safe(lambda c=clip: c.GetStart(), -1) or -1)
        if abs(s - int(start_frame)) <= 1 and int(safe(lambda c=clip: c.GetFusionCompCount(), 0) or 0) > 0:
            return clip
    return None

def rewrite_subtitle_track_text(target_track_index, target_item_index, new_text):
    if not media_pool:
        return False, "未找到媒体池，无法重建字幕。"
    entries = []
    track_count = int(safe(lambda: timeline.GetTrackCount("subtitle"), 0) or 0)
    for ti in range(1, track_count + 1):
        enabled = safe(lambda ti2=ti: timeline.GetIsTrackEnabled("subtitle", ti2), True)
        if not enabled:
            continue
        clips = safe(lambda ti2=ti: timeline.GetItemListInTrack("subtitle", ti2), []) or []
        for item_index, clip in enumerate(clips):
            s = int(safe(lambda c=clip: c.GetStart(), 0) or 0)
            e = int(safe(lambda c=clip: c.GetEnd(), s) or s)
            text_value = str(safe(lambda c=clip: c.GetName(), "") or "")
            if ti == target_track_index and item_index == target_item_index:
                text_value = new_text
            entries.append((s, e, text_value))
    if not entries:
        return False, "未找到可重建的字幕。"
    entries.sort(key=lambda row: row[0])
    lines = []
    for idx, (s, e, text_value) in enumerate(entries, 1):
        lines.append(str(idx))
        lines.append(frame_to_srt(s) + " --> " + frame_to_srt(e))
        lines.append(str(text_value))
        lines.append("")
    import os, tempfile
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False, encoding="utf-8")
    tmp.write("\r\n".join(lines))
    tmp.close()
    try:
        imported = media_pool.ImportMedia(tmp.name)
        if not imported or len(imported) <= 0:
            return False, "SRT重建失败：无法添加到媒体池。"
        deleted = 0
        for ti in range(1, track_count + 1):
            enabled = safe(lambda ti2=ti: timeline.GetIsTrackEnabled("subtitle", ti2), True)
            if not enabled:
                continue
            clips = safe(lambda ti2=ti: timeline.GetItemListInTrack("subtitle", ti2), []) or []
            if clips and bool(safe(lambda c=clips: timeline.DeleteClips(list(c), False), False)):
                deleted += len(clips)
        if media_pool.AppendToTimeline([imported[0]]):
            cleanup_imported_media_pool_item(imported[0])
            return True, "字幕已通过SRT重建替换，位置按原时间码恢复，临时SRT素材已清理。"
        return False, "SRT重建失败：Resolve 未接受导入字幕，已删除 " + str(deleted) + " 条旧字幕。"
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def collect_items():
    found = []
    for track_type in ("subtitle", "video"):
        track_count = int(safe(lambda tt=track_type: timeline.GetTrackCount(tt), 0) or 0)
        for track_index in range(1, track_count + 1):
            if track_type == "subtitle":
                enabled = safe(lambda ti2=track_index: timeline.GetIsTrackEnabled("subtitle", ti2), True)
                if not enabled:
                    continue
            clips = safe(lambda tt=track_type, ti=track_index: timeline.GetItemListInTrack(tt, ti), []) or []
            for item_index, clip in enumerate(clips):
                globals()["CURRENT_TRACK_TYPE"] = track_type
                text_value, text_key, source = item_text(clip)
                item_kind = classify_text_item(track_type, text_key, source, clip)
                if item_kind not in SCAN_TYPE_SET:
                    continue
                if track_type == "video":
                    has_fusion = int(safe(lambda c=clip: c.GetFusionCompCount(), 0) or 0) > 0
                    item_name = str(safe(lambda c=clip: c.GetName(), "") or "")
                    props = safe(lambda c=clip: c.GetProperty(), {{}}) or {{}}
                    item_name_lower = item_name.lower()
                    maybe_title = (
                        has_fusion
                        or any(str(k) in TITLE_HINT_KEYS for k in props.keys())
                        or "title" in item_name_lower
                        or "text" in item_name_lower
                        or "文本" in item_name
                    )
                    if not maybe_title:
                        continue
                raw_start = int(safe(lambda c=clip: c.GetStart(), 0) or 0)
                raw_end = int(safe(lambda c=clip: c.GetEnd(), raw_start) or raw_start)
                abs_start = raw_start
                abs_end = raw_end
                found.append({{
                    "timeline_index": {int(timeline_index)},
                    "track_type": track_type,
                    "text_kind": item_kind,
                    "track_index": track_index,
                    "item_index": item_index,
                    "unique_id": "" if track_type == "subtitle" else str(safe(lambda c=clip: c.GetUniqueId(), "") or ""),
                    "timecode": tc_from_timeline_frame(abs_start, fps, start_frame, start_timecode),
                    "start_frame": abs_start,
                    "end_frame": abs_end,
                    "text": text_value,
                    "text_key": text_key,
                    "text_source": source,
                    "name": str(safe(lambda c=clip: c.GetName(), "") or ""),
                }})
    return found

def restore_deleted_subtitle_item():
    if not media_pool:
        return False, "未找到媒体池，无法恢复字幕。"
    track_count = int(safe(lambda: timeline.GetTrackCount("subtitle"), 0) or 0)
    entries = []
    clips_by_track = {{}}
    for ti in range(1, track_count + 1):
        enabled = safe(lambda ti2=ti: timeline.GetIsTrackEnabled("subtitle", ti2), True)
        if not enabled:
            continue
        clips = safe(lambda ti2=ti: timeline.GetItemListInTrack("subtitle", ti2), []) or []
        clips_by_track[ti] = list(clips or [])
        for clip in clips or []:
            s = int(safe(lambda c=clip: c.GetStart(), 0) or 0)
            e = int(safe(lambda c=clip: c.GetEnd(), s) or s)
            text_value = str(safe(lambda c=clip: c.GetName(), "") or "")
            entries.append((s, e, text_value))
    deleted_start = int(ITEM.get("start_frame", 0) or 0)
    deleted_end = int(ITEM.get("end_frame", deleted_start) or deleted_start)
    deleted_text = str(ITEM.get("text", "") or ITEM.get("name", "") or "")
    for s, e, text_value in entries:
        if s == deleted_start and e == deleted_end and text_value == deleted_text:
            return True, "字幕已存在，无需恢复。"
    entries.append((deleted_start, deleted_end, deleted_text))
    entries.sort(key=lambda row: (row[0], row[1], row[2]))
    lines = []
    for idx, (s, e, text_value) in enumerate(entries, 1):
        lines.append(str(idx))
        lines.append(frame_to_srt(s) + " --> " + frame_to_srt(e))
        lines.append(str(text_value))
        lines.append("")
    import os, tempfile
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False, encoding="utf-8")
    tmp.write("\r\n".join(lines))
    tmp.close()
    deleted = 0
    try:
        imported = media_pool.ImportMedia(tmp.name)
        if not imported or len(imported) <= 0:
            return False, "恢复失败：无法导入临时SRT。"
        for clips in clips_by_track.values():
            if clips and bool(safe(lambda c=clips: timeline.DeleteClips(list(c), False), False)):
                deleted += len(clips)
        if media_pool.AppendToTimeline([imported[0]]):
            cleanup_imported_media_pool_item(imported[0])
            return True, "已撤回删除：字幕已恢复，临时SRT素材已清理。"
        return False, "恢复失败：Resolve 未接受导入字幕，已删除 " + str(deleted) + " 条旧字幕。"
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

def restore_deleted_textplus_item():
    template_item, error = import_builtin_textplus_template()
    if template_item is None:
        return False, error or "未找到可用于恢复的 Text+ 模板。"
    target_track = int(ITEM.get("track_index", 1) or 1)
    start = int(ITEM.get("start_frame", 0) or 0)
    end = int(ITEM.get("end_frame", start + 1) or (start + 1))
    dur = max(1, end - start)
    payload = [{{
        "mediaPoolItem": template_item,
        "startFrame": 0,
        "endFrame": max(0, dur - 1),
        "recordFrame": start,
        "trackIndex": target_track,
    }}]
    result = safe(lambda: media_pool.AppendToTimeline(payload), None)
    created = None
    if isinstance(result, list) and result:
        created = result[0]
    if created is None:
        created = find_textplus_clip_at(target_track, start)
    if created is None:
        return False, "Text+ 模板已导入，但未能追加到原轨道原时间。"
    values = ITEM.get("restore_style") if isinstance(ITEM.get("restore_style"), dict) else {{}}
    timeline_ok = 0
    timeline_fail = 0
    if values:
        timeline_ok, timeline_fail = apply_textplus_timeline_snapshot(created, values)
        ok_count, fail_count = apply_textplus_restore_style(created, values)
    else:
        ok_count, fail_count = 0, 0
        set_item_text(created, "0:StyledText", "fusion", str(ITEM.get("text", "") or ""))
    return True, "已撤回删除：Text+ 已重建到原时间，恢复 Fusion 参数 " + str(ok_count) + " 项，时间线属性 " + str(timeline_ok) + " 项，失败 " + str(fail_count + timeline_fail) + " 项。"

if ACTION == "scan":
    items = collect_items()
    print(json.dumps({{"ok": True, "message": "找到 " + str(len(items)) + " 条文字/字幕素材。", "items": items}}, ensure_ascii=False))
    raise SystemExit(0)

target = get_item(str(ITEM.get("track_type", "video")), int(ITEM.get("track_index", 1)), int(ITEM.get("item_index", -1)))
if ACTION != "restore_delete" and not target:
    print(json.dumps({{"ok": False, "message": "目标文字素材不存在。"}}, ensure_ascii=False))
    raise SystemExit(0)

if ACTION == "jump":
    tc = str(ITEM.get("timecode", ""))
    ok = bool(tc and timeline.SetCurrentTimecode(tc))
    if resolve:
        resolve.OpenPage("edit")
    print(json.dumps({{"ok": ok, "message": ("已跳转到 " + tc) if ok else "跳转失败。"}}, ensure_ascii=False))
elif ACTION == "replace":
    if NEW_TEXT == str(ITEM.get("text", "")):
        print(json.dumps({{"ok": True, "message": "文字未变化。"}}, ensure_ascii=False))
        raise SystemExit(0)
    if str(ITEM.get("track_type", "")) == "subtitle":
        ok, method = rewrite_subtitle_track_text(
            int(ITEM.get("track_index", 1)),
            int(ITEM.get("item_index", -1)),
            NEW_TEXT,
        )
    else:
        ok, method = set_item_text(target, str(ITEM.get("text_key", "")), str(ITEM.get("text_source", "")), NEW_TEXT)
    if ok:
        msg = "文字已替换 (via " + str(method) + ")。"
    else:
        # Resolve API cannot modify subtitle/text item content.
        # Jump playhead to the item position so user can manually edit.
        saved_tc = str(ITEM.get("timecode", "00:00:00:00"))
        tc_ok = bool(saved_tc and timeline.SetCurrentTimecode(saved_tc))
        if resolve:
            resolve.OpenPage("edit")
        track_type_str = str(ITEM.get("track_type", ""))
        if track_type_str == "subtitle":
            msg = "Resolve API不支持修改字幕文字。已跳转到字幕位置，请在达芬奇中双击字幕直接编辑。(删除功能可用)"
        elif str(ITEM.get("text_source", "")) == "fusion":
            msg = "Resolve API不支持修改Fusion文字层。已跳转到该位置，请手动编辑。"
        else:
            msg = "该文字层不支持程序化写入。已跳转到该位置，请手动编辑。"
    print(json.dumps({{"ok": ok, "message": msg}}, ensure_ascii=False))
elif ACTION == "delete":
    restore_style = {{}}
    if str(ITEM.get("track_type", "")) != "subtitle":
        restore_style = textplus_restore_style(target, str(ITEM.get("text_key", "")))
    ok = bool(safe(lambda: timeline.DeleteClips([target], False), False))
    print(json.dumps({{
        "ok": ok,
        "message": "文字层已删除。" if ok else "删除失败，Resolve 未接受该文字层。",
        "restore_style": restore_style,
    }}, ensure_ascii=False))
elif ACTION == "restore_delete":
    if str(ITEM.get("track_type", "")) == "subtitle":
        ok, msg = restore_deleted_subtitle_item()
    else:
        ok, msg = restore_deleted_textplus_item()
    print(json.dumps({{"ok": ok, "message": msg}}, ensure_ascii=False))
''',
            timeout=240 if action == "scan" else 180,
        )
        if not data:
            return {"ok": False, "message": "文字层操作失败：Resolve API 未返回结果。", "items": []}
        return data

    def export_subtitles_srt(self, timeline_index: int = 1) -> dict[str, Any]:
        """Export all subtitle items from a timeline as SRT content."""
        timeout = self._subtitle_operation_timeout(timeline_index, minimum=120, per_item=0.12)
        data = self._run_resolve_python(
            rf'''
import json
resolve = dvr_script.scriptapp("Resolve")
project = resolve.GetProjectManager().GetCurrentProject() if resolve else None
timeline = project.GetTimelineByIndex({int(timeline_index)}) if project else None
if not timeline:
    print(json.dumps({{"ok": False, "srt": "", "count": 0, "message": "未找到时间线。"}}, ensure_ascii=False))
    raise SystemExit(0)

def safe(cb, d=None):
    try: return cb()
    except: return d

def cleanup_imported_media_pool_item(imported_item):
    if not media_pool or not imported_item:
        return False
    return bool(safe(lambda: media_pool.DeleteClips([imported_item]), False))

fps = float(safe(lambda: timeline.GetSetting("timelineFrameRate"), 25) or 25)
start_frame = int(safe(lambda: timeline.GetStartFrame(), 0) or 0)

# Collect clips from all enabled subtitle tracks
all_clips = []
track_count = int(safe(lambda: timeline.GetTrackCount("subtitle"), 0) or 0)
for ti in range(1, track_count + 1):
    enabled = safe(lambda ti2=ti: timeline.GetIsTrackEnabled("subtitle", ti2), True)
    if not enabled:
        continue
    clips = safe(lambda ti2=ti: timeline.GetItemListInTrack("subtitle", ti2), []) or []
    for clip in (clips or []):
        all_clips.append(clip)

# Sort by start frame for consistent SRT ordering
all_clips.sort(key=lambda c: int(safe(lambda: c.GetStart(), 0) or 0))

def frame_to_srt(f):
    rel = max(0, int(f) - start_frame)
    total_sec = rel / max(1.0, fps)
    h = int(total_sec // 3600)
    m = int((total_sec % 3600) // 60)
    s = int(total_sec % 60)
    ms = int((total_sec - int(total_sec)) * 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)

lines = []
for i, clip in enumerate(all_clips or [], 1):
    name = str(safe(lambda: clip.GetName(), "") or "")
    s = int(safe(lambda: clip.GetStart(), 0) or 0)
    e = int(safe(lambda: clip.GetEnd(), s) or s)
    lines.append(str(i))
    lines.append(frame_to_srt(s) + " --> " + frame_to_srt(e))
    lines.append(name)
    lines.append("")

srt = "\r\n".join(lines)
print(json.dumps({{"ok": True, "srt": srt, "count": len(all_clips) if all_clips else 0, "message": "已导出 " + str(len(all_clips) if all_clips else 0) + " 条字幕。"}}, ensure_ascii=False))
''',
            timeout=timeout,
        )
        if not data:
            return {"ok": False, "srt": "", "count": 0, "message": "导出失败：Resolve API 未返回结果。"}
        return data

    def replace_subtitles_from_srt(self, timeline_index: int = 1, srt_content: str = "", original_srt: str = "") -> dict[str, Any]:
        """Replace all subtitles with new SRT content (full replace: delete all + import all)."""
        entry_count = len(re.findall(r"(?m)^\s*\d+\s*$", srt_content or ""))
        timeout = max(
            self._subtitle_operation_timeout(timeline_index, minimum=180, per_item=0.2),
            min(900, 180 + entry_count * 0.18),
        )
        data = self._run_resolve_python(
            rf'''
import json, os, tempfile, re
resolve = dvr_script.scriptapp("Resolve")
project = resolve.GetProjectManager().GetCurrentProject() if resolve else None
timeline = project.GetTimelineByIndex({int(timeline_index)}) if project else None
media_pool = project.GetMediaPool() if project else None
if not timeline or not media_pool:
    print(json.dumps({{"ok": False, "count": 0, "message": "未找到时间线或媒体池。"}}, ensure_ascii=False))
    raise SystemExit(0)

SRT_CONTENT = {json.dumps(srt_content, ensure_ascii=False)}
ORIGINAL_SRT = {json.dumps(original_srt, ensure_ascii=False)}

def safe(cb, d=None):
    try: return cb()
    except: return d

def parse_srt(text):
    entries = {{}}
    blocks = re.split(r'\n\s*\n', text.strip())
    for block in blocks:
        lines = [line.rstrip('\r') for line in block.strip().split('\n')]
        if len(lines) >= 3:
            try:
                idx = int(lines[0].strip())
                tc = lines[1].strip()
                txt = '\n'.join(lines[2:]).strip()
                entries[idx] = (tc, txt)
            except ValueError:
                pass
    return entries

# Count changes for user info
changed_count = 0
if ORIGINAL_SRT and ORIGINAL_SRT != SRT_CONTENT:
    old_entries = parse_srt(ORIGINAL_SRT)
    new_entries = parse_srt(SRT_CONTENT)
    all_ids = set(list(old_entries.keys()) + list(new_entries.keys()))
    for idx in sorted(all_ids):
        if old_entries.get(idx) != new_entries.get(idx):
            changed_count += 1

def collect_subtitle_clips():
    all_clips = []
    track_count = int(safe(lambda: timeline.GetTrackCount("subtitle"), 0) or 0)
    for ti in range(1, track_count + 1):
        enabled = safe(lambda ti2=ti: timeline.GetIsTrackEnabled("subtitle", ti2), True)
        if not enabled:
            continue
        clips = safe(lambda ti2=ti: timeline.GetItemListInTrack("subtitle", ti2), []) or []
        for clip in clips:
            all_clips.append(clip)
    all_clips.sort(key=lambda c: int(safe(lambda: c.GetStart(), 0) or 0))
    return all_clips

def set_subtitle_text(clip, text):
    keys = ["Text", "StyledText", "Subtitle", "Caption", "Name", "Clip Name", "Comments"]
    props = safe(lambda: clip.GetProperty(), {{}}) or {{}}
    preferred = [key for key in keys if props.get(key) not in (None, "")]
    for key in preferred + [key for key in keys if key not in preferred]:
        if bool(safe(lambda k=key: clip.SetProperty(k, text), False)):
            return True, "SetProperty(" + key + ")"
    set_name = getattr(clip, "SetName", None)
    if callable(set_name) and bool(safe(lambda: set_name(text), False)):
        return True, "SetName"
    return False, ""

old_entries = parse_srt(ORIGINAL_SRT) if ORIGINAL_SRT else {{}}
new_entries = parse_srt(SRT_CONTENT)
same_structure = (
    bool(old_entries)
    and set(old_entries.keys()) == set(new_entries.keys())
    and all(old_entries[idx][0] == new_entries[idx][0] for idx in old_entries)
)

if same_structure:
    clips = collect_subtitle_clips()
    if len(clips) >= len(new_entries):
        updated = 0
        failed = 0
        methods = []
        for idx in sorted(new_entries.keys()):
            old_tc, old_text = old_entries[idx]
            new_tc, new_text = new_entries[idx]
            if old_text == new_text:
                continue
            clip = clips[idx - 1] if 0 <= idx - 1 < len(clips) else None
            ok, method = set_subtitle_text(clip, new_text) if clip else (False, "")
            if ok:
                updated += 1
                if method and method not in methods:
                    methods.append(method)
            else:
                failed += 1
        if failed == 0:
            msg = "已增量更新字幕：修改 " + str(updated) + " 处，位置保持不变。"
            if methods:
                msg += " (" + ", ".join(methods[:3]) + ")"
            print(json.dumps({{
                "ok": True,
                "count": len(clips),
                "deleted": 0,
                "changed": updated,
                "incremental": True,
                "message": msg
            }}, ensure_ascii=False))
            raise SystemExit(0)

# Full replace fallback: Delete all enabled-track subtitles, then import full SRT
track_count = int(safe(lambda: timeline.GetTrackCount("subtitle"), 0) or 0)
deleted = 0
for ti in range(1, track_count + 1):
    enabled = safe(lambda ti2=ti: timeline.GetIsTrackEnabled("subtitle", ti2), True)
    if not enabled:
        continue
    clips = safe(lambda ti2=ti: timeline.GetItemListInTrack("subtitle", ti2), []) or []
    if clips:
        ok = safe(lambda c=clips: timeline.DeleteClips(list(c), False), False)
        if ok:
            deleted += len(clips)

try:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False, encoding="utf-8")
    tmp.write(SRT_CONTENT)
    tmp.close()

    imported = media_pool.ImportMedia(tmp.name)
    if imported and len(imported) > 0:
        result = media_pool.AppendToTimeline([imported[0]])
        cleaned_temp_item = cleanup_imported_media_pool_item(imported[0]) if result else False
        os.unlink(tmp.name)

        new_count = 0
        for ti in range(1, int(safe(lambda: timeline.GetTrackCount("subtitle"), 0) or 0) + 1):
            new_clips = safe(lambda ti2=ti: timeline.GetItemListInTrack("subtitle", ti2), []) or []
            new_count += len(new_clips) if new_clips else 0

        if changed_count > 0:
            msg = "已替换字幕：修改 " + str(changed_count) + " 处，删除 " + str(deleted) + " 条，导入 " + str(new_count) + " 条。"
        else:
            msg = "已替换字幕：删除 " + str(deleted) + " 条，导入 " + str(new_count) + " 条。"
        if cleaned_temp_item:
            msg += " 临时SRT素材已清理。"
        print(json.dumps({{
            "ok": True,
            "count": new_count,
            "deleted": deleted,
            "changed": changed_count,
            "cleaned_temp_item": cleaned_temp_item,
            "message": msg
        }}, ensure_ascii=False))
    else:
        os.unlink(tmp.name)
        print(json.dumps({{"ok": False, "count": 0, "deleted": deleted, "message": "导入SRT失败：无法添加到媒体池。"}}, ensure_ascii=False))
except Exception as e:
    print(json.dumps({{"ok": False, "count": 0, "deleted": deleted, "message": "导入SRT异常：" + str(e)[:200]}}, ensure_ascii=False))
''',
            timeout=timeout,
        )
        if not data:
            return {"ok": False, "count": 0, "message": "替换失败：Resolve API 未返回结果。"}
        return data

    def _audio_action(self, timeline_index: int, action: str, io_in: str = "", io_out: str = "") -> dict[str, Any]:
        action = action if action in {"scan", "mark", "fix"} else "scan"
        ffprobe_path = self._find_ffprobe_binary()
        data = self._run_resolve_python(
            rf'''
import json
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlparse
ACTION = {json.dumps(action)}
IO_IN_TEXT = {json.dumps(io_in)}
IO_OUT_TEXT = {json.dumps(io_out)}
FFPROBE_PATH = {json.dumps(ffprobe_path)}
AUDIO_MARK_COLOR = "Chocolate"
AUDIO_MARK_FALLBACK_COLORS = ("Brown", "Cocoa", "Orange")
AUDIO_CLIP_MARKER_COLOR = "Red"
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
timeline = project.GetCurrentTimeline() if project else None
if not timeline and project:
    timeline = project.GetTimelineByIndex({int(timeline_index)})
if not timeline:
    print(json.dumps({{"ok": False, "message": "未找到目标时间线。"}}, ensure_ascii=False))
    raise SystemExit(0)

def safe(callable_obj, default=None):
    try:
        return callable_obj()
    except Exception:
        return default

def as_items(value):
    if value is None:
        return []
    if isinstance(value, dict):
        return [item for item in value.values() if item]
    if isinstance(value, (list, tuple)):
        return [item for item in value if item]
    return [value]

resolve_version = safe(lambda: resolve.GetVersion(), []) if resolve else []
try:
    resolve_major = int(resolve_version[0]) if len(resolve_version) > 0 else 0
except Exception:
    resolve_major = 0
try:
    resolve_minor = int(resolve_version[1]) if len(resolve_version) > 1 else 0
except Exception:
    resolve_minor = 0
try:
    resolve_patch = int(resolve_version[2]) if len(resolve_version) > 2 else 0
except Exception:
    resolve_patch = 0
timeline_audio_mapping_supported = resolve_major > 19 or (
    resolve_major == 19 and (resolve_minor > 0 or resolve_patch >= 1)
)
resolve_version_label = ".".join(str(part) for part in [resolve_major, resolve_minor, resolve_patch] if part is not None)
mono_mark_supported = resolve_major == 0 or resolve_major >= 20
external_mono_scan = ACTION == "mark" and not mono_mark_supported

def decode_mapping(raw):
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return json.loads(raw)
        except Exception:
            return {{}}
    return {{}}

def mapping_is_mono(mapping):
    if not isinstance(mapping, dict):
        return False
    try:
        if mapping.get("embedded_audio_channels") is not None and int(mapping.get("embedded_audio_channels")) == 1:
            return True
    except Exception:
        pass
    track_mapping = mapping.get("track_mapping")
    if isinstance(track_mapping, dict):
        for entry in track_mapping.values():
            if not isinstance(entry, dict):
                continue
            if str(entry.get("type", "")).lower() == "mono":
                return True
            channel_idx = entry.get("channel_idx")
            if not entry.get("type") and isinstance(channel_idx, list) and len(channel_idx) == 1:
                return True
    return False

def item_name(item):
    media_pool_item = safe(lambda: item.GetMediaPoolItem())
    if media_pool_item:
        name = safe(lambda: media_pool_item.GetClipProperty("Clip Name"))
        if name:
            return str(name)
        name = safe(lambda: media_pool_item.GetClipProperty("File Name"))
        if name:
            return str(name)
    return str(safe(lambda: item.GetName(), "未命名音频"))

def read_properties(target):
    if not target:
        return {{}}
    for method_name in ("GetClipProperty", "GetProperty"):
        method = getattr(target, method_name, None)
        if not callable(method):
            continue
        props = safe(lambda method=method: method(), {{}})
        if isinstance(props, dict):
            return props
    return {{}}

def tag_name(element):
    return str(getattr(element, "tag", "")).split("}}")[-1]

def load_fcpxml_audio_index():
    result = {{
        "ok": False,
        "message": "",
        "path": "",
        "by_ref": {{}},
        "by_name": {{}},
        "by_path": {{}},
        "attempts": [],
    }}
    tmp_dir = ""
    try:
        tmp_dir = tempfile.mkdtemp(prefix="qh_bfd_audio_fcpxml_")
        export_types = ("EXPORT_FCPXML_1_10", "EXPORT_FCPXML_1_9", "EXPORT_FCPXML_1_8", "EXPORT_FCPXML_1_7")
        info_path = ""
        for export_name in export_types:
            export_type = getattr(resolve, export_name, None)
            if export_type is None:
                result["attempts"].append({{"name": export_name, "available": False}})
                continue
            export_path = os.path.join(tmp_dir, export_name + ".fcpxml")
            try:
                ok = bool(timeline.Export(export_path, export_type))
            except Exception as exc:
                result["attempts"].append({{"name": export_name, "ok": False, "error": str(exc)[:120]}})
                continue
            candidate = os.path.join(export_path, "Info.fcpxml") if os.path.isdir(export_path) else export_path
            result["attempts"].append({{"name": export_name, "ok": ok, "path": candidate, "exists": os.path.exists(candidate)}})
            if ok and os.path.exists(candidate):
                info_path = candidate
                break
        if not info_path:
            result["message"] = "FCPXML 导出失败"
            return result
        root = ET.parse(info_path).getroot()
        result["path"] = info_path
        for element in root.iter():
            if tag_name(element) != "asset":
                continue
            ref = str(element.attrib.get("id") or "")
            name = str(element.attrib.get("name") or "")
            try:
                channels = int(element.attrib.get("audioChannels") or 0)
            except Exception:
                channels = 0
            src_path = ""
            for child in list(element):
                if tag_name(child) != "media-rep":
                    continue
                src = str(child.attrib.get("src") or "")
                parsed = urlparse(src)
                src_path = unquote(parsed.path) if parsed.scheme == "file" else unquote(src)
                break
            entry = {{"ref": ref, "name": name, "channels": channels, "path": src_path}}
            if ref:
                result["by_ref"][ref] = entry
            if name:
                result["by_name"][name.lower()] = entry
            if src_path:
                result["by_path"][os.path.normpath(src_path)] = entry
        for element in root.iter():
            if tag_name(element) != "asset-clip":
                continue
            ref = str(element.attrib.get("ref") or "")
            name = str(element.attrib.get("name") or "")
            entry = result["by_ref"].get(ref)
            if entry and name:
                result["by_name"][name.lower()] = entry
        result["ok"] = bool(result["by_ref"] or result["by_name"] or result["by_path"])
        result["message"] = "FCPXML 音频索引完成" if result["ok"] else "FCPXML 未找到音频素材"
        return result
    except Exception as exc:
        result["message"] = "FCPXML 解析失败：" + str(exc)[:160]
        return result
    finally:
        if tmp_dir:
            try:
                import shutil as _shutil
                _shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

def fcpxml_audio_for_item(source_path, clip_name):
    if not isinstance(fcpxml_audio_index, dict) or not fcpxml_audio_index.get("ok"):
        return {{}}
    source_path = str(source_path or "").strip()
    if source_path:
        entry = fcpxml_audio_index.get("by_path", {{}}).get(os.path.normpath(source_path))
        if entry:
            return entry
    clip_name = str(clip_name or "").strip().lower()
    if clip_name:
        entry = fcpxml_audio_index.get("by_name", {{}}).get(clip_name)
        if entry:
            return entry
    return {{}}

def file_path_from_props(props):
    if not isinstance(props, dict):
        return ""
    keys = (
        "File Path", "FilePath", "Path", "Full Path", "FullPath", "Filename", "File Name",
        "Source File", "Source Path", "源文件", "文件路径",
    )
    for key in keys:
        value = props.get(key)
        if value:
            return str(value)
    for key, value in props.items():
        key_text = str(key).lower()
        if ("path" in key_text or "file" in key_text or "文件" in key_text) and value:
            return str(value)
    return ""

def ffprobe_audio_channels(path):
    path = str(path or "").strip()
    if not FFPROBE_PATH:
        return {{"ok": False, "reason": "未找到 ffprobe"}}
    if not path or not os.path.exists(path):
        return {{"ok": False, "reason": "源文件路径不可访问"}}
    cmd = [
        FFPROBE_PATH,
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=channels,channel_layout,codec_name",
        "-of", "json",
        path,
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=12)
    except Exception as exc:
        return {{"ok": False, "reason": "ffprobe异常：" + str(exc)[:120]}}
    if proc.returncode != 0:
        return {{"ok": False, "reason": "ffprobe读取失败：" + proc.stderr.decode("utf-8", errors="ignore")[:120]}}
    try:
        payload = json.loads(proc.stdout.decode("utf-8", errors="ignore") or "{{}}")
    except Exception:
        payload = {{}}
    streams = payload.get("streams") if isinstance(payload, dict) else []
    stream = streams[0] if isinstance(streams, list) and streams else {{}}
    try:
        channels = int(stream.get("channels") or 0)
    except Exception:
        channels = 0
    return {{
        "ok": channels > 0,
        "channels": channels,
        "channel_layout": str(stream.get("channel_layout") or ""),
        "codec_name": str(stream.get("codec_name") or ""),
        "reason": "ffprobe channels=" + str(channels),
    }}

def property_value_says_mono(value):
    text = str(value or "").strip().lower()
    if not text:
        return False
    mono_values = ("mono", "1.0", "1", "1ch", "1 ch", "1 channel", "1 channels", "single channel")
    if text in mono_values:
        return True
    return "mono" in text or "单声道" in text

def properties_say_mono(props):
    if not isinstance(props, dict):
        return False, ""
    likely_keys = (
        "audio channels",
        "audio channel",
        "audio format",
        "audio type",
        "track type",
        "channel format",
        "source channel",
        "source audio",
        "声道",
        "音频",
    )
    for key, value in props.items():
        key_text = str(key or "").strip().lower()
        if any(part in key_text for part in likely_keys) and property_value_says_mono(value):
            return True, str(key)
    return False, ""

def mapping_is_stereo(mapping):
    if not isinstance(mapping, dict):
        return False
    track_mapping = mapping.get("track_mapping")
    if isinstance(track_mapping, dict):
        for entry in track_mapping.values():
            if not isinstance(entry, dict):
                continue
            channel_idx = entry.get("channel_idx")
            if str(entry.get("type", "")).lower() == "stereo":
                return True
            if isinstance(channel_idx, list) and len(channel_idx) >= 2:
                return True
    return False

def first_mono_channel(mapping):
    if not isinstance(mapping, dict):
        return 1
    track_mapping = mapping.get("track_mapping")
    if isinstance(track_mapping, dict):
        for entry in track_mapping.values():
            if not isinstance(entry, dict):
                continue
            channel_idx = entry.get("channel_idx")
            if isinstance(channel_idx, list) and channel_idx:
                try:
                    return max(1, int(channel_idx[0]))
                except Exception:
                    return 1
    return 1

def mono_channel_label(mapping):
    channel = first_mono_channel(mapping)
    if channel == 1:
        return "left-only"
    if channel == 2:
        return "right-only"
    return f"channel-{{channel}}-only"

def stereo_mapping_from(source_mapping, media_mapping):
    base = media_mapping if mapping_is_stereo(media_mapping) else source_mapping
    embedded = 2
    if isinstance(base, dict):
        try:
            embedded = max(2, int(base.get("embedded_audio_channels") or 2))
        except Exception:
            embedded = 2
    channel = first_mono_channel(source_mapping)
    if isinstance(media_mapping, dict) and mapping_is_mono(media_mapping):
        channel = first_mono_channel(media_mapping)
    return {{
        "embedded_audio_channels": embedded,
        "linked_audio": base.get("linked_audio", {{}}) if isinstance(base, dict) else {{}},
        "track_mapping": {{
            "1": {{"channel_idx": [channel, channel], "mute": False, "type": "stereo"}}
        }},
    }}

def try_set_stereo_mapping(item, media_pool_item, source_mapping, media_mapping):
    desired = stereo_mapping_from(source_mapping, media_mapping)
    payloads = [desired, json.dumps(desired, ensure_ascii=False)]
    targets = [
        (item, ("SetSourceAudioChannelMapping", "SetAudioMapping")),
        (media_pool_item, ("SetAudioMapping", "SetSourceAudioChannelMapping")),
    ]
    for target, methods in targets:
        if not target:
            continue
        for method_name in methods:
            method = getattr(target, method_name, None)
            if not callable(method):
                continue
            for payload in payloads:
                ok = safe(lambda method=method, payload=payload: method(payload), False)
                if ok:
                    new_source = decode_mapping(safe(lambda item=item: item.GetSourceAudioChannelMapping()))
                    new_media = decode_mapping(safe(lambda mpi=media_pool_item: mpi.GetAudioMapping()) if media_pool_item else None)
                    if mapping_is_stereo(new_source) or mapping_is_stereo(new_media):
                        return True, method_name
    return False, ""

def track_subtype_is_mono(subtype):
    value = str(subtype or "").strip().lower()
    return value in ("mono", "1.0", "1") or "mono" in value or value in ("left", "right", "left mono", "right mono")

def display_track_format(subtype):
    value = str(subtype or "").strip()
    lower = value.lower()
    if track_subtype_is_mono(value):
        return "1.0"
    if lower in ("stereo", "2.0", "2"):
        return "2.0"
    return value or "unknown"

def try_set_track_stereo(track_index):
    payloads = ("stereo", "Stereo", "2.0", 2, {{"audioType": "stereo"}}, {{"audio_type": "stereo"}})
    method_names = ("SetTrackSubType", "SetTrackFormat", "SetAudioTrackType", "SetTrackAudioType")
    for method_name in method_names:
        method = getattr(timeline, method_name, None)
        if not callable(method):
            continue
        for payload in payloads:
            attempts = (
                lambda method=method, payload=payload: method("audio", track_index, payload),
                lambda method=method, payload=payload: method(track_index, payload),
                lambda method=method, payload=payload: method(track_index, "audio", payload),
            )
            for attempt in attempts:
                if safe(attempt, False):
                    new_subtype = safe(lambda idx=track_index: timeline.GetTrackSubType("audio", idx), "")
                    if not track_subtype_is_mono(new_subtype):
                        return True, method_name
    return False, ""

track_count = int(safe(lambda: timeline.GetTrackCount("audio"), 0) or 0)
timeline_start_frame = int(safe(lambda: timeline.GetStartFrame(), 0) or 0)
timeline_start_timecode = str(safe(lambda: timeline.GetStartTimecode(), None) or safe(lambda: timeline.GetSetting("timelineStartTimecode"), None) or "00:00:00:00")
fps_raw = safe(lambda: timeline.GetSetting("timelineFrameRate"), None) or safe(lambda: project.GetSetting("timelineFrameRate"), None) or 25
try:
    timeline_fps = float(fps_raw)
except Exception:
    timeline_fps = 25.0
tracks = []
clips = []
mono_track_indices = []
mapping_fixed = 0
mapping_fix_attempts = 0
track_format_fix_attempts = 0
track_format_fixed = 0
fcpxml_audio_index = load_fcpxml_audio_index() if (external_mono_scan or (ACTION == "scan" and not timeline_audio_mapping_supported)) else {{"ok": False, "message": "未启用 FCPXML 兜底"}}

def tc_to_frames(tc):
    fps_int = max(1, int(round(float(timeline_fps or 25))))
    parts = str(tc or "").split(":")
    if len(parts) != 4:
        return None
    try:
        hh, mm, ss, ff = [int(float(part)) for part in parts]
    except Exception:
        return None
    return (((hh * 60) + mm) * 60 + ss) * fps_int + ff

def display_tc_to_timeline_frame(tc):
    display_frame = tc_to_frames(tc)
    start_display_frame = tc_to_frames(timeline_start_timecode) or 0
    if display_frame is None:
        return None
    return timeline_start_frame + max(0, display_frame - start_display_frame)

io_in_frame = display_tc_to_timeline_frame(IO_IN_TEXT)
io_out_frame = display_tc_to_timeline_frame(IO_OUT_TEXT)

def normalize_item_frame(raw):
    frame = int(raw or 0)
    return frame if frame >= timeline_start_frame else timeline_start_frame + frame

def item_overlaps_io(item):
    if io_in_frame is None or io_out_frame is None:
        return True
    start = normalize_item_frame(safe(lambda item=item: item.GetStart(), 0))
    end = normalize_item_frame(safe(lambda item=item: item.GetEnd(), start))
    return end > io_in_frame and start < io_out_frame

def add_audio_marker(item, track_index, reason, start_frame, end_frame):
    duration = max(1, int(end_frame or 0) - int(start_frame or 0))
    mid_offset = max(0, duration // 2)
    mid_frame = int(start_frame) + mid_offset
    name = "[BFD-AUDIO] 单声道音频"
    title = "单声道音频"
    custom_root = "qinghe-bfd-audio-mono"
    note = title + "：" + item_name(item) + "\\n轨道 A" + str(track_index) + "\\n原因：" + reason
    custom_data = custom_root + "-" + str(track_index) + "-" + str(mid_frame)
    attempts = [
        ("clip", lambda: item.AddMarker(mid_offset, AUDIO_CLIP_MARKER_COLOR, name, note, 1, custom_data)),
        ("clip", lambda: item.AddMarker(mid_offset, AUDIO_CLIP_MARKER_COLOR, name, note, 1)),
        ("timeline", lambda: timeline.AddMarker(mid_frame, AUDIO_CLIP_MARKER_COLOR, name, note, 1, custom_data)),
        ("timeline", lambda: timeline.AddMarker(mid_frame, AUDIO_CLIP_MARKER_COLOR, name, note, 1)),
    ]
    result = {{"ok": False, "scope": "", "frame": mid_frame, "offset": mid_offset}}
    for attempt in attempts:
        scope, call = attempt
        if safe(call, False):
            result.update({{"ok": True, "scope": scope}})
            return result
    return result

for track_index in range(1, track_count + 1):
    subtype = str(safe(lambda idx=track_index: timeline.GetTrackSubType("audio", idx), "") or "")
    track_name = str(safe(lambda idx=track_index: timeline.GetTrackName("audio", idx), f"Audio {{track_index}}") or f"Audio {{track_index}}")
    enabled = safe(lambda idx=track_index: timeline.GetIsTrackEnabled("audio", idx), True)
    items = as_items(safe(lambda idx=track_index: timeline.GetItemListInTrack("audio", idx), []))
    track_is_mono = track_subtype_is_mono(subtype)
    track_format_fixed_now = False
    track_format_fix_method = ""
    if track_is_mono:
        mono_track_indices.append(track_index)
        if ACTION == "fix" and items:
            track_format_fix_attempts += 1
            track_format_fixed_now, track_format_fix_method = try_set_track_stereo(track_index)
            if track_format_fixed_now:
                track_format_fixed += 1
                subtype = str(safe(lambda idx=track_index: timeline.GetTrackSubType("audio", idx), subtype) or subtype)
                track_is_mono = track_subtype_is_mono(subtype)
    tracks.append({{
        "index": track_index,
        "name": track_name,
        "subtype": subtype or "unknown",
        "format": display_track_format(subtype),
        "enabled": bool(enabled),
        "item_count": len(items),
        "mono": track_is_mono,
        "format_fixed": track_format_fixed_now,
        "format_fix_method": track_format_fix_method,
    }})
    for item in items:
        if not item_overlaps_io(item):
            continue
        source_mapping = decode_mapping(safe(lambda item=item: item.GetSourceAudioChannelMapping()))
        media_pool_item = safe(lambda item=item: item.GetMediaPoolItem())
        media_mapping = decode_mapping(safe(lambda mpi=media_pool_item: mpi.GetAudioMapping()) if media_pool_item else None)
        item_props = read_properties(item)
        media_props = read_properties(media_pool_item)
        clip_display_name = item_name(item)
        source_path = file_path_from_props(media_props) or file_path_from_props(item_props)
        fcpxml_result = fcpxml_audio_for_item(source_path, clip_display_name)
        if not source_path and fcpxml_result.get("path"):
            source_path = str(fcpxml_result.get("path") or "")
        ffprobe_result = ffprobe_audio_channels(source_path) if (external_mono_scan or ACTION == "scan") else {{}}
        ffprobe_is_mono = bool(ffprobe_result.get("ok") and int(ffprobe_result.get("channels") or 0) == 1)
        fcpxml_is_mono = bool(fcpxml_result.get("channels") == 1)
        source_mapping_is_mono = mapping_is_mono(source_mapping)
        media_mapping_is_mono = mapping_is_mono(media_mapping)
        item_props_is_mono, item_props_key = properties_say_mono(item_props)
        media_props_is_mono, media_props_key = properties_say_mono(media_props)
        property_is_mono = item_props_is_mono or media_props_is_mono
        source_is_mono = source_mapping_is_mono or media_mapping_is_mono or property_is_mono or fcpxml_is_mono or ffprobe_is_mono
        if track_is_mono or source_is_mono:
            fixed = False
            fix_method = ""
            if ACTION == "fix" and source_is_mono:
                mapping_fix_attempts += 1
                fixed, fix_method = try_set_stereo_mapping(item, media_pool_item, source_mapping, media_mapping)
                if fixed:
                    mapping_fixed += 1
            if track_is_mono:
                reason = "mono track"
            elif source_mapping_is_mono:
                reason = mono_channel_label(source_mapping)
            elif media_mapping_is_mono:
                reason = "media " + mono_channel_label(media_mapping)
            elif item_props_is_mono:
                reason = "clip property " + item_props_key
            elif media_props_is_mono:
                reason = "media property " + media_props_key
            elif fcpxml_is_mono:
                reason = "external fcpxml mono source"
            elif ffprobe_is_mono:
                reason = "external ffprobe mono source"
            else:
                reason = "mono source"
            start_frame = normalize_item_frame(safe(lambda item=item: item.GetStart(), 0))
            end_frame = normalize_item_frame(safe(lambda item=item: item.GetEnd(), start_frame))
            color_changed = False
            audio_marker = {{"ok": False, "scope": "", "frame": 0, "offset": 0}}
            if ACTION in {{"mark", "fix"}}:
                for clip_color in (AUDIO_MARK_COLOR,) + AUDIO_MARK_FALLBACK_COLORS:
                    if safe(lambda item=item, clip_color=clip_color: item.SetClipColor(clip_color), False):
                        color_changed = True
                        break
            if ACTION in {{"mark", "fix"}}:
                audio_marker = add_audio_marker(item, track_index, reason, start_frame, end_frame)
            clips.append({{
                "track_index": track_index,
                "track_subtype": subtype or "unknown",
                "track_format": display_track_format(subtype),
                "name": clip_display_name,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "color": safe(lambda item=item: item.GetClipColor(), ""),
                "color_changed": color_changed,
                "clip_marker_added": bool(audio_marker.get("ok")),
                "timeline_marker_added": bool(audio_marker.get("ok") and audio_marker.get("scope") == "timeline"),
                "audio_marker_scope": audio_marker.get("scope"),
                "audio_marker_frame": audio_marker.get("frame"),
                "audio_marker_offset": audio_marker.get("offset"),
                "reason": reason,
                "source_mapping": source_mapping,
                "media_mapping": media_mapping,
                "source_path": source_path,
                "fcpxml": fcpxml_result,
                "ffprobe": ffprobe_result,
                "item_properties": item_props,
                "media_properties": media_props,
                "mapping_fixed": fixed,
                "fix_method": fix_method,
            }})

created_tracks = 0

clip_color_changed = sum(1 for clip in clips if clip.get("color_changed"))
clip_markers_added = sum(1 for clip in clips if clip.get("clip_marker_added"))
clip_scope_markers_added = sum(1 for clip in clips if clip.get("audio_marker_scope") == "clip")
timeline_scope_markers_added = sum(1 for clip in clips if clip.get("audio_marker_scope") == "timeline")

if ACTION == "mark":
    if len(clips) == 0:
        if external_mono_scan:
            message = f"Resolve {{resolve_version_label}} 的音频片段声道 API 受限，已改用 FCPXML + ffprobe 外部扫描源文件；未识别到单声道源音频，未写入标记。"
        elif resolve_major and not timeline_audio_mapping_supported:
            message = f"Resolve {{resolve_version_label}} 不支持读取时间线单个音频片段的声道映射；Resolve 19.0.1 起才有相关 API。未写入任何标记。"
        else:
            message = "已尝试读取当前 Resolve 的轨道、片段和素材声道字段，但未识别到单声道音频片段；未写入任何标记。"
    else:
        if external_mono_scan:
            message = f"低版本外部扫描完成：用 FCPXML + ffprobe 识别单声道源音频 {{len(clips)}} 个，写入音频片段中点标记 {{clip_scope_markers_added}} 个，时间线中点兜底标记 {{timeline_scope_markers_added}} 个。"
        else:
            message = f"单声道音频标记完成：片段颜色 {{clip_color_changed}} 个，音频片段中点标记 {{clip_scope_markers_added}} 个，时间线中点兜底标记 {{timeline_scope_markers_added}} 个。"
elif ACTION == "fix":
    message = (
        f"轨道格式修正 {{track_format_fixed}}/{{track_format_fix_attempts}}；"
        f"已尝试修正 {{mapping_fix_attempts}} 个声道映射，成功 {{mapping_fixed}} 个；"
        f"片段颜色 {{clip_color_changed}} 个，音频片段中点标记 {{clip_scope_markers_added}} 个，时间线中点兜底标记 {{timeline_scope_markers_added}} 个。"
        + (" 未成功写入的项目表示 Resolve API 未接受该片段/素材的声道映射写入。" if mapping_fixed < mapping_fix_attempts else "")
    )
else:
    message = f"扫描完成：发现 {{len(clips)}} 个单声道音频片段。"

print(json.dumps({{
    "ok": True,
    "message": message,
    "summary": {{
        "tracks": track_count,
        "mono_tracks": len(mono_track_indices),
        "mono_clips": len(clips),
        "resolve_major": resolve_major,
        "resolve_minor": resolve_minor,
        "resolve_patch": resolve_patch,
        "timeline_audio_mapping_supported": timeline_audio_mapping_supported,
        "clip_color_attempted": ACTION in {{"mark", "fix"}},
        "external_mono_scan": external_mono_scan,
        "ffprobe_available": bool(FFPROBE_PATH),
        "fcpxml_audio_index": {{
            "ok": bool(fcpxml_audio_index.get("ok")) if isinstance(fcpxml_audio_index, dict) else False,
            "message": str(fcpxml_audio_index.get("message", "")) if isinstance(fcpxml_audio_index, dict) else "",
            "asset_count": len(fcpxml_audio_index.get("by_ref", {{}})) if isinstance(fcpxml_audio_index, dict) else 0,
        }},
        "clip_color_changed": clip_color_changed,
        "clip_markers_added": clip_markers_added,
        "clip_scope_markers_added": clip_scope_markers_added,
        "timeline_scope_markers_added": timeline_scope_markers_added,
        "created_stereo_tracks": created_tracks,
        "mapping_fix_attempts": mapping_fix_attempts,
        "mapping_fixed": mapping_fixed,
        "track_format_fix_attempts": track_format_fix_attempts,
        "track_format_fixed": track_format_fixed,
    }},
    "tracks": tracks,
    "clips": clips,
}}, ensure_ascii=False))
'''
        )
        if not data:
            return {"ok": False, "message": "音频扫描失败：Resolve API 未返回结果。", "summary": {}, "tracks": [], "clips": []}
        return data

    def run_lua_entry_with_fuscript(self, params_path: Path) -> tuple[bool, str]:
        fuscript = self._find_fuscript()
        if not fuscript:
            if platform.system().lower() == "darwin":
                self._prepare_menu_fallback_params(params_path)
                return self._trigger_resolve_menu_script()
            return False, "fuscript was not found."
        ok, message = self._launch_lua_entry_with_fuscript(fuscript, params_path)
        if ok:
            return ok, message
        if platform.system().lower() == "darwin":
            self._prepare_menu_fallback_params(params_path)
            menu_ok, menu_message = self._trigger_resolve_menu_script()
            if menu_ok:
                return menu_ok, f"{menu_message}（fuscript 启动失败，已改用菜单兜底：{message}）"
        return ok, message

    @staticmethod
    def _prepare_menu_fallback_params(params_path: Path) -> None:
        try:
            target = default_params_path()
            if Path(params_path) != target:
                shutil.copyfile(params_path, target)
        except Exception:
            pass

    @staticmethod
    def _launch_lua_entry_with_fuscript(fuscript: Path, params_path: Path) -> tuple[bool, str]:
        lua_entry = find_lua_entry()
        if not lua_entry:
            return False, "检测入口未找到。"

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["BFD_PARAMS_FILE"] = str(params_path)
        env["BFD_DISABLE_EXTERNAL_UI"] = "1"
        command = [str(fuscript), "-l", "lua", str(lua_entry)]
        try:
            subprocess.Popen(
                command,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                **hidden_subprocess_kwargs(),
            )
        except Exception as exc:
            return False, str(exc)
        return True, "检测已交给 Resolve 后台执行。"

    @staticmethod
    def _trigger_resolve_menu_script() -> tuple[bool, str]:
        script = r'''
tell application "DaVinci Resolve" to activate
delay 0.25
tell application "System Events"
  tell process "DaVinci Resolve"
    try
      click menu bar item "工作区" of menu bar 1
      delay 0.15
      click menu item "脚本" of menu of menu bar item "工作区" of menu bar 1
      delay 0.15
      click menu item "清何黑帧夹帧检测" of menu of menu item "脚本" of menu of menu bar item "工作区" of menu bar 1
      return "ok"
    on error zhErr
      try
        click menu bar item "Workspace" of menu bar 1
        delay 0.15
        click menu item "Scripts" of menu of menu bar item "Workspace" of menu bar 1
        delay 0.15
        click menu item "清何黑帧夹帧检测" of menu of menu item "Scripts" of menu of menu bar item "Workspace" of menu bar 1
        return "ok"
      on error enErr
        return "zh=" & zhErr & "; en=" & enErr
      end try
    end try
  end tell
end tell
'''
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                text=True,
                capture_output=True,
                timeout=8,
                **hidden_subprocess_kwargs(),
            )
        except Exception as exc:
            return False, f"无法触发 Resolve 内部脚本菜单：{exc}"
        output = (result.stdout or result.stderr or "").strip()
        if result.returncode == 0 and output == "ok":
            return True, "检测已交给 Resolve 内部脚本执行。"
        return False, output or f"osascript exited with {result.returncode}"

    @staticmethod
    def _find_fuscript() -> Path | None:
        system = platform.system().lower()
        candidates: list[Path] = []
        if system == "windows":
            candidates.append(Path(r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fuscript.exe"))
        elif system == "darwin":
            candidates.append(
                Path("/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fuscript")
            )
        else:
            candidates.append(Path("/opt/resolve/bin/fuscript"))
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _probe_connected(self) -> bool:
        data = self._run_resolve_python(
            r'''
import json
resolve = dvr_script.scriptapp("Resolve")
print(json.dumps({"connected": resolve is not None}))
'''
        )
        return bool(data and data.get("connected"))

    @staticmethod
    def _run_resolve_python(body: str, timeout: float = 5) -> dict[str, Any] | None:
        command, stdin_script = build_resolve_python_process(body)
        try:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            if platform.system().lower() == "darwin":
                script_api = env.get(
                    "RESOLVE_SCRIPT_API",
                    "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting",
                )
                script_lib = env.get(
                    "RESOLVE_SCRIPT_LIB",
                    "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so",
                )
                env.setdefault("RESOLVE_SCRIPT_API", script_api)
                if Path(script_lib).exists():
                    env.setdefault("RESOLVE_SCRIPT_LIB", script_lib)
                module_path = str(Path(script_api) / "Modules")
                env["PYTHONPATH"] = module_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
            completed = subprocess.run(
                command,
                input=stdin_script,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout,
                check=False,
                **hidden_subprocess_kwargs(),
            )
        except Exception as exc:
            return {"ok": False, "message": f"Resolve API 调用失败：{exc}"}
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            return {
                "ok": False,
                "message": "Resolve API 子进程异常退出：%s" % (stderr or f"returncode={completed.returncode}"),
                "returncode": completed.returncode,
            }
        output = (completed.stdout or "").strip().splitlines()
        if not output:
            stderr = (completed.stderr or "").strip()
            return {
                "ok": False,
                "message": "Resolve API 没有返回结果：%s" % (stderr or "stdout 为空"),
            }
        try:
            return json.loads(output[-1])
        except Exception as exc:
            return {
                "ok": False,
                "message": "Resolve API 返回解析失败：%s" % exc,
                "raw_output": output[-5:],
            }
