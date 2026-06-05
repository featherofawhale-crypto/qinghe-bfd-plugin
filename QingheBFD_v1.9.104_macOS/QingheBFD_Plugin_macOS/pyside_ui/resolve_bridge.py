from __future__ import annotations

import os
import platform
import subprocess
import sys
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
LUA_ENTRY = REPO_ROOT / "清何黑帧夹帧检测_v1.9.48_Windows" / "清何黑帧夹帧检测.lua"
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
    return [sys.executable, "-c", script], None


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
    target = target or runtime_dir() / "last_params.lua"
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
        params["enabled"] = True
        params["progress_file"] = str(progress_path())
        progress_path().write_text(
            json.dumps(
                {"percent": 1, "stage": "参数已提交，等待 Resolve 执行", "state": "pending"},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return write_lua_params(params)

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
timeline = project.GetTimelineByIndex({int(timeline_index)}) if project else None
if not timeline:
    print(json.dumps({{"ok": False, "message": "未找到目标时间线。"}}, ensure_ascii=False))
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
timeline = project.GetTimelineByIndex({int(timeline_index)}) if project else None
if not timeline:
    print(json.dumps({{"ok": False, "message": "未找到目标时间线。"}}, ensure_ascii=False))
    raise SystemExit(0)
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

fps_raw = safe(lambda: timeline.GetSetting("timelineFrameRate"), 25) or 25
try:
    fps = float(fps_raw)
except Exception:
    fps = 25.0
long_clip_frames = max(1, int(round(fps * 30)))
track_count = int(safe(lambda: timeline.GetTrackCount("video"), 0) or 0)
same_source = {{}}
candidates = []

for track_index in range(1, track_count + 1):
    items = safe(lambda track_index=track_index: timeline.GetItemListInTrack("video", track_index), []) or []
    for item_index, item in enumerate(items):
        media_pool_item = safe(lambda item=item: item.GetMediaPoolItem())
        name = clip_name(item, media_pool_item)
        path = clip_file_path(media_pool_item)
        start = int(safe(lambda item=item: item.GetStart(), 0) or 0)
        end = int(safe(lambda item=item: item.GetEnd(), start) or start)
        duration = max(0, end - start)
        fusion_count = int(safe(lambda item=item: item.GetFusionCompCount(), 0) or 0)
        lower_name = name.lower()
        if path:
            same_source.setdefault(path, []).append({{
                "name": name,
                "track_index": track_index,
                "item_index": item_index,
                "duration": duration,
            }})
        if not path and duration > 0:
            candidates.append({{
                "name": name,
                "track_index": track_index,
                "reason": "复合片段/Fusion片段或无源文件路径，需要复杂模式看最终画面",
            }})
        elif duration >= long_clip_frames and any(token in lower_name for token in ("mix", "final", "output", "成片", "混剪", "合集")):
            candidates.append({{
                "name": name,
                "track_index": track_index,
                "reason": "长成片命名疑似多镜头导出文件",
            }})
        elif fusion_count > 0:
            candidates.append({{
                "name": name,
                "track_index": track_index,
                "reason": "片段含 Fusion 合成，普通模式不分析最终画面",
            }})

for path, refs in same_source.items():
    if len(refs) <= 1:
        continue
    first = refs[0]
    candidates.append({{
        "name": first.get("name", "同源片段"),
        "track_index": first.get("track_index", 1),
        "reason": f"同一源文件在时间线出现 {{len(refs)}} 次，可能是混剪成片或源内多镜头复用",
        "source_file": path,
    }})

deduped = []
seen = set()
for item in candidates:
    key = (item.get("name"), item.get("reason"), item.get("source_file", ""))
    if key in seen:
        continue
    seen.add(key)
    deduped.append(item)

message = f"发现 {{len(deduped)}} 个疑似混剪/多镜头成片，建议启用复杂模式。" if deduped else "未发现明显混剪成片风险。"
print(json.dumps({{
    "ok": True,
    "count": len(deduped),
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
timeline = project.GetTimelineByIndex({int(timeline_index)}) if project else None
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
        family, style = text.split("|||", 1)
        return family.strip(), style.strip()
    for style in STYLE_SUFFIXES:
        suffix = " " + style
        if text.endswith(suffix):
            return text[:-len(suffix)].strip(), style
    return text, ""

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
counts = {{"total": 0, "error": 0, "suspect": 0, "scene": 0, "gap": 0, "duplicate": 0, "content_dup": 0, "opacity": 0, "corrupt": 0}}

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

    def copy_textplus_style(self, item: dict[str, Any]) -> dict[str, Any]:
        return self._font_action(int(item.get("timeline_index", 1)), "copy_style", item=item)

    def apply_textplus_style(self, item: dict[str, Any], style: dict[str, Any]) -> dict[str, Any]:
        return self._font_action(int(item.get("timeline_index", 1)), "apply_style", item=item, style_payload=style)

    def convert_srt_to_textplus(self, timeline_index: int = 1) -> dict[str, Any]:
        return self._font_action(int(timeline_index), "convert_srt_textplus")

    def _font_action(
        self,
        timeline_index: int,
        action: str,
        item: dict[str, Any] | None = None,
        font_name: str = "",
        font_candidates: list[str] | None = None,
        style_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        action = action if action in {"scan", "jump", "replace", "copy_style", "apply_style", "convert_srt_textplus"} else "scan"
        candidates: list[str] = []
        ordered_candidates = [*(font_candidates or []), font_name]
        for candidate in ordered_candidates:
            text = str(candidate or "").strip()
            if text and text not in candidates:
                candidates.append(text)
        template_path = Path(__file__).resolve().with_name("templates") / "caption-bin.drb"
        data = self._run_resolve_python(
            rf'''
import json
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
        family, style = text.split("|||", 1)
        return family.strip(), style.strip()
    for style in STYLE_SUFFIXES:
        suffix = " " + style
        if text.endswith(suffix):
            return text[:-len(suffix)].strip(), style
    return text, ""

def tc_from_frame(frame, fps):
    fps_int = max(1, int(round(float(fps or 25))))
    total = max(0, int(round(float(frame or 0))))
    ff = total % fps_int
    total_seconds = total // fps_int
    ss = total_seconds % 60
    mm = (total_seconds // 60) % 60
    hh = total_seconds // 3600
    return "%02d:%02d:%02d:%02d" % (hh, mm, ss, ff)

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

TEXT_FONT_KEYS = [
    "Font", "Font Face", "FontFace", "Font Family", "FontFamily",
    "Typeface", "Type Face", "Text Font", "TextFont", "Title Font",
    "Font Name", "FontName", "FontStyle", "Style",
]
TEXT_VALUE_KEYS = ["Text", "StyledText", "Title", "Subtitle", "Caption", "Name", "Clip Name", "Comments"]
TEXTPLUS_STYLE_KEYS = [
    "Font", "Style", "Size", "LineSpacing", "CharacterSpacing",
    "Red1", "Green1", "Blue1", "Alpha1",
    "Enabled2", "Red2", "Green2", "Blue2", "Alpha2", "Thickness2", "Softness2", "Opacity2",
    "Enabled3", "Red3", "Green3", "Blue3", "Alpha3", "Offset3", "Blur3", "Opacity3",
    "HorizontalJustification", "VerticalJustification", "Center",
    "LayoutType", "TransformRotation", "TransformSize", "Shear", "AngleZ",
    "AdvancedFontControls", "ManualFontKerningPlacement",
]
TEXTPLUS_STYLE_TEXT_KEYS = ("StyledText", "Text", "Name", "Clip Name", "Comments")

def should_skip_textplus_style_key(key):
    normalized = str(key or "").strip().lower().replace(" ", "")
    return normalized in ("styledtext", "text", "name", "clipname", "comments")

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
    if requested_key:
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
        dynamic_keys = [str(key) for key in input_list.keys()]
    seen = set()
    for key in dynamic_keys + TEXTPLUS_STYLE_KEYS:
        if key in seen or should_skip_textplus_style_key(key):
            continue
        seen.add(key)
        value = safe(lambda k=key: tool.GetInput(k), None)
        if value not in (None, "") and style_value_is_json_safe(value):
            values[key] = value
    return values

def apply_textplus_style_to_tool(tool, values):
    original_text = safe(lambda: tool.GetInput("StyledText"), None)
    ok_count = 0
    fail_count = 0
    for key, value in (values or {{}}).items():
        if should_skip_textplus_style_key(key):
            continue
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
        for item_index, clip in enumerate(clips):
            name = str(safe(lambda c=clip: c.GetName(), "") or "")
            start = int(safe(lambda c=clip: c.GetStart(), 0) or 0)
            end = int(safe(lambda c=clip: c.GetEnd(), start) or start)
            tools = textplus_tools(clip)
            if tools:
                for comp_index, tool_name, tool, text_value, font_value, style_value in tools:
                    display_font = font_value + ((" " + style_value) if style_value else "")
                    records.append({{
                        "timeline_index": {int(timeline_index)}, "row": row, "kind": "Text+", "track_type": "video",
                        "track_index": track_index, "item_index": item_index,
                        "unique_id": str(safe(lambda c=clip: c.GetUniqueId(), "") or ""),
                        "timecode": tc_from_timeline_frame(start), "start_frame": start, "end_frame": end,
                        "text": text_value or name, "font": display_font, "font_family": font_value, "font_style": style_value,
                        "font_key": str(comp_index) + ":" + tool_name + ":Font",
                        "supported": True, "reason": "Text+ Font 输入可写。"
                    }})
                    row += 1
                continue
            lower_name = name.lower()
            if "text" in lower_name or "title" in lower_name or "文本" in name or "标题" in name:
                text_font_key, text_font_value, text_value = plain_text_font_property(clip)
                text_supported = bool(text_font_key)
                records.append({{
                    "timeline_index": {int(timeline_index)}, "row": row, "kind": "Text", "track_type": "video",
                    "track_index": track_index, "item_index": item_index,
                    "unique_id": str(safe(lambda c=clip: c.GetUniqueId(), "") or ""),
                    "timecode": tc_from_timeline_frame(start), "start_frame": start, "end_frame": end,
                    "text": text_value or name, "font": text_font_value, "font_key": "property:" + text_font_key if text_font_key else "",
                    "supported": text_supported,
                    "reason": ("普通 Text 字体属性可写：" + text_font_key) if text_supported else "当前 Resolve 未公开普通 Text 字体属性；建议改用 Text+。"
                }})
                row += 1
    return records

if ACTION == "scan":
    items = collect_font_items()
    supported = len([item for item in items if item.get("supported")])
    print(json.dumps({{"ok": True, "message": "找到 " + str(len(items)) + " 个字体相关层，可替换 " + str(supported) + " 个。", "items": items}}, ensure_ascii=False))
    raise SystemExit(0)

def set_textplus_text(clip, text):
    tools = textplus_tools(clip)
    for _comp_index, _tool_name, tool, _text_value, _font_value, _style_value in tools:
        before = safe(lambda t=tool: t.GetInput("StyledText"), None)
        safe(lambda t=tool, value=text: t.SetInput("StyledText", value), None)
        after = safe(lambda t=tool: t.GetInput("StyledText"), None)
        if after == text or str(after) == str(text) or before == text:
            return True
    return False

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
            text = str(safe(lambda c=clip: c.GetName(), "") or "")
            props = safe(lambda c=clip: c.GetProperty(), {{}}) or {{}}
            if isinstance(props, dict):
                for key in ("Text", "StyledText", "Subtitle", "Caption", "Name"):
                    value = props.get(key)
                    if value not in (None, ""):
                        text = str(value)
                        break
            entries.append({{"track": track_index, "index": item_index, "start": start, "end": max(end, start + 1), "text": text}})
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
    return str(
        safe(lambda item=media_item: item.GetClipProperty("Clip Name"), "")
        or safe(lambda item=media_item: item.GetClipProperty("File Name"), "")
        or safe(lambda item=media_item: item.GetName(), "")
        or ""
    )

def find_caption_template_item(media_pool, before_labels):
    root = safe(lambda: media_pool.GetRootFolder())
    current = safe(lambda: media_pool.GetCurrentFolder())
    candidates = folder_items_recursive(current) + folder_items_recursive(root)
    chosen = None
    for media_item in candidates:
        label = item_label(media_item)
        lower = label.lower()
        if "caption" in lower or "text" in lower or "subtitle" in lower or "标题" in label or "字幕" in label:
            if label not in before_labels:
                return media_item
            chosen = chosen or media_item
    return chosen

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
        if not os.path.exists(CAPTION_TEMPLATE_PATH):
            print(json.dumps({{"ok": False, "message": "缺少 Text+ 模板：pyside_ui/templates/caption-bin.drb。请先放入内置 .drb 字幕模板。"}}, ensure_ascii=False))
            raise SystemExit(0)
        media_pool = project.GetMediaPool() if project else None
        if not media_pool:
            print(json.dumps({{"ok": False, "message": "未找到媒体池，无法导入 Text+ 模板。"}}, ensure_ascii=False))
            raise SystemExit(0)
        entries = collect_subtitle_entries()
        if not entries:
            print(json.dumps({{"ok": False, "message": "当前时间线没有启用的 SRT 字幕。"}}, ensure_ascii=False))
            raise SystemExit(0)
        before_labels = set(item_label(item) for item in folder_items_recursive(safe(lambda: media_pool.GetRootFolder())))
        imported = safe(lambda: media_pool.ImportFolderFromFile(CAPTION_TEMPLATE_PATH), None)
        template_item = find_caption_template_item(media_pool, before_labels)
        if template_item is None:
            print(json.dumps({{"ok": False, "message": "已尝试导入 .drb，但未在媒体池找到字幕 Text+ 模板。"}}, ensure_ascii=False))
            raise SystemExit(0)
        old_video_count = int(safe(lambda: timeline.GetTrackCount("video"), 0) or 0)
        safe(lambda: timeline.AddTrack("video"), False)
        target_track = int(safe(lambda: timeline.GetTrackCount("video"), old_video_count) or old_video_count)
        created = 0
        text_written = 0
        fallback_used = 0
        append_failed = 0
        for entry in entries:
            dur = max(1, int(entry["end"]) - int(entry["start"]))
            created_clip = None
            append_payloads = [
                [{{"mediaPoolItem": template_item, "startFrame": 0, "endFrame": dur, "recordFrame": int(entry["start"]), "trackIndex": target_track}}],
                [{{"mediaPoolItem": template_item, "startFrame": 0, "endFrame": dur, "recordFrame": int(entry["start"])}}],
            ]
            for payload in append_payloads:
                result = safe(lambda payload=payload: media_pool.AppendToTimeline(payload), None)
                if result:
                    created += 1
                    created_clip = find_textplus_clip_at(entry["start"])
                    break
            if created_clip is None:
                append_failed += 1
                tc = tc_from_timeline_frame(entry["start"])
                if tc and safe(lambda tc=tc: timeline.SetCurrentTimecode(tc), False):
                    created_clip = safe(lambda: timeline.InsertFusionTitleIntoTimeline("Text+"), None)
                    if created_clip:
                        created += 1
                        fallback_used += 1
            if created_clip is not None:
                if set_textplus_text(created_clip, entry["text"]):
                    text_written += 1
                safe(lambda clip=created_clip, dur=dur: clip.SetProperty("Duration", dur), None)
        message = "SRT 转 Text+ 完成：字幕 " + str(len(entries)) + " 条，创建 " + str(created) + " 条，写入文字 " + str(text_written) + " 条。"
        if fallback_used:
            message += " 其中 " + str(fallback_used) + " 条使用降级插入，位置/时长需抽查。"
        if append_failed:
            message += " AppendToTimeline 未接受 " + str(append_failed) + " 条。"
        print(json.dumps({{"ok": created > 0, "message": message, "count": created, "text_written": text_written, "subtitle_count": len(entries), "fallback": fallback_used, "imported": bool(imported)}}, ensure_ascii=False))
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({{"ok": False, "message": "SRT 转 Text+ 异常：" + str(exc)[:200]}}, ensure_ascii=False))
    raise SystemExit(0)

target = get_item(str(ITEM.get("track_type", "video")), int(ITEM.get("track_index", 1)), int(ITEM.get("item_index", -1)))
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
        if str(ITEM.get("kind", "")).lower() != "text+" or not bool(ITEM.get("supported")):
            print(json.dumps({{"ok": False, "message": "请选择状态为可替换的 Text+ 作为样式来源。"}}, ensure_ascii=False))
            raise SystemExit(0)
        tool = target_textplus_tool(target)
        if tool is None:
            print(json.dumps({{"ok": False, "message": "未找到对应的 Text+ 工具。"}}, ensure_ascii=False))
            raise SystemExit(0)
        values = copy_textplus_style_from_tool(tool)
        print(json.dumps({{
            "ok": bool(values),
            "style": values,
            "count": len(values),
            "message": ("已复制 Text+ 样式 " + str(len(values)) + " 项；不会复制文字内容。") if values else "没有读取到可复制的 Text+ 样式。",
        }}, ensure_ascii=False))
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({{"ok": False, "message": "Text+ 样式复制异常：" + str(exc)[:200]}}, ensure_ascii=False))
elif ACTION == "apply_style":
    try:
        if target is None:
            print(json.dumps({{"ok": False, "message": "目标 Text+ 不存在。"}}, ensure_ascii=False))
            raise SystemExit(0)
        if str(ITEM.get("kind", "")).lower() != "text+" or not bool(ITEM.get("supported")):
            print(json.dumps({{"ok": False, "message": "请选择状态为可替换的 Text+。"}}, ensure_ascii=False))
            raise SystemExit(0)
        if not isinstance(STYLE_PAYLOAD, dict) or not STYLE_PAYLOAD:
            print(json.dumps({{"ok": False, "message": "请先复制 Text+ 样式。"}}, ensure_ascii=False))
            raise SystemExit(0)
        tool = target_textplus_tool(target)
        if tool is None:
            print(json.dumps({{"ok": False, "message": "未找到对应的 Text+ 工具。"}}, ensure_ascii=False))
            raise SystemExit(0)
        ok_count, fail_count = apply_textplus_style_to_tool(tool, STYLE_PAYLOAD)
        print(json.dumps({{
            "ok": ok_count > 0,
            "applied": ok_count,
            "failed": fail_count,
            "message": "已应用 Text+ 样式：" + str(ok_count) + " 项，失败 " + str(fail_count) + " 项；文字内容已保留。",
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
        ok = False
        current_font = ""
        accepted_font = ""
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
                candidate_font, candidate_style = parse_font_candidate(candidate)
                if bool(safe(lambda key=property_key, name=candidate_font: target.SetProperty(key, name), False)):
                    current_font = str(safe(lambda key=property_key: target.GetProperty().get(key, ""), "") or "")
                    if current_font == candidate_font or (current_font and current_font != before_font):
                        ok = True
                        accepted_font = candidate_font + ((" " + candidate_style) if candidate_style else "")
                        break
            print(json.dumps({{"ok": ok, "font": current_font, "accepted_font": accepted_font, "message": ("普通 Text 字体已替换为 " + (current_font or accepted_font or FONT_NAME)) if ok else "Resolve 未接受普通 Text 字体写入，请尝试字体的中文/英文/PostScript 名称。"}}, ensure_ascii=False))
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
                        candidate_font, candidate_style = parse_font_candidate(candidate)
                        safe(lambda t=tool, name=candidate_font: t.SetInput("Font", name), None)
                        if candidate_style:
                            safe(lambda t=tool, style=candidate_style: t.SetInput("Style", style), None)
                        if styled_text not in (None, ""):
                            safe(lambda t=tool, text=styled_text: t.SetInput("StyledText", text), None)
                        current_font = str(safe(lambda t=tool: t.GetInput("Font"), "") or "")
                        current_style = str(safe(lambda t=tool: t.GetInput("Style"), "") or "")
                        if current_font == candidate_font or (current_font and current_font != before_font):
                            ok = True
                            accepted_font = candidate_font + ((" " + current_style) if current_style else "")
                            break
                    break
            if ok:
                break
        print(json.dumps({{"ok": ok, "font": current_font, "accepted_font": accepted_font, "message": ("字体已替换为 " + (current_font or accepted_font or FONT_NAME)) if ok else "Resolve 未接受该字体名，请尝试字体的中文/英文/PostScript 名称。"}}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({{"ok": False, "message": "字体替换异常：" + str(exc)[:200]}}, ensure_ascii=False))
''',
            timeout=90 if action == "convert_srt_textplus" else 45,
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
        data = self._run_resolve_python(
            rf'''
import json
ACTION = {json.dumps(action)}
QUERY = {json.dumps(query)}
SCAN_TYPES = {json.dumps(scan_types or ["srt"])}
ITEM = {json.dumps(item or {}, ensure_ascii=False)}
NEW_TEXT = {json.dumps(text, ensure_ascii=False)}
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
    props = safe(lambda: clip.GetProperty(), {{}}) or {{}}
    for key in TEXT_KEYS:
        value = props.get(key)
        if value not in (None, ""):
            return str(value), key, "property"
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

    # Fusion clip: write into the Text+ tool input
    if source == "fusion" and ":" in str(key):
        tool_name, input_key = str(key).split(":", 1)
        fusion_count = int(safe(lambda: clip.GetFusionCompCount(), 0) or 0)
        for comp_index in range(1, fusion_count + 1):
            comp = safe(lambda ci=comp_index: clip.GetFusionCompByIndex(ci))
            tools = safe(lambda c=comp: c.GetToolList(False), {{}}) if comp else {{}}
            tool = tools.get(tool_name) if isinstance(tools, dict) else None
            if tool and try_write(lambda: tool.SetInput(input_key, new_text)):
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
                    maybe_title = has_fusion or any(str(k) in TITLE_HINT_KEYS for k in props.keys()) or "title" in item_name.lower() or "text" in item_name.lower()
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
    ok, method = set_item_text(target, str(ITEM.get("text_key", "")), str(ITEM.get("text_source", "")), NEW_TEXT)
    if not ok and str(ITEM.get("track_type", "")) == "subtitle":
        ok, method = rewrite_subtitle_track_text(
            int(ITEM.get("track_index", 1)),
            int(ITEM.get("item_index", -1)),
            NEW_TEXT,
        )
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
    ok = bool(safe(lambda: timeline.DeleteClips([target], False), False))
    print(json.dumps({{"ok": ok, "message": "文字层已删除。" if ok else "删除失败，Resolve 未接受该文字层。"}}, ensure_ascii=False))
elif ACTION == "restore_delete":
    if str(ITEM.get("track_type", "")) == "subtitle":
        ok, msg = restore_deleted_subtitle_item()
    else:
        ok, msg = False, "撤回删除暂只支持SRT字幕；普通文字层删除后 Resolve API 不能可靠重建。"
    print(json.dumps({{"ok": ok, "message": msg}}, ensure_ascii=False))
''',
            timeout=60,
        )
        if not data:
            return {"ok": False, "message": "文字层操作失败：Resolve API 未返回结果。", "items": []}
        return data

    def export_subtitles_srt(self, timeline_index: int = 1) -> dict[str, Any]:
        """Export all subtitle items from a timeline as SRT content."""
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
            timeout=15,
        )
        if not data:
            return {{"ok": False, "srt": "", "count": 0, "message": "导出失败：Resolve API 未返回结果。"}}
        return data

    def replace_subtitles_from_srt(self, timeline_index: int = 1, srt_content: str = "", original_srt: str = "") -> dict[str, Any]:
        """Replace all subtitles with new SRT content (full replace: delete all + import all)."""
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
            timeout=30,
        )
        if not data:
            return {{"ok": False, "count": 0, "message": "替换失败：Resolve API 未返回结果。"}}
        return data

    def _audio_action(self, timeline_index: int, action: str, io_in: str = "", io_out: str = "") -> dict[str, Any]:
        action = action if action in {"scan", "mark", "fix"} else "scan"
        data = self._run_resolve_python(
            rf'''
import json
ACTION = {json.dumps(action)}
IO_IN_TEXT = {json.dumps(io_in)}
IO_OUT_TEXT = {json.dumps(io_out)}
AUDIO_MARK_COLOR = "Chocolate"
AUDIO_MARK_FALLBACK_COLORS = ("Brown", "Cocoa", "Orange")
AUDIO_CLIP_MARKER_COLOR = "Red"
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
timeline = project.GetTimelineByIndex({int(timeline_index)}) if project else None
if not timeline:
    print(json.dumps({{"ok": False, "message": "未找到目标时间线。"}}, ensure_ascii=False))
    raise SystemExit(0)

def safe(callable_obj, default=None):
    try:
        return callable_obj()
    except Exception:
        return default

resolve_version = safe(lambda: resolve.GetVersion(), []) if resolve else []
try:
    resolve_major = int(resolve_version[0]) if len(resolve_version) > 0 else 0
except Exception:
    resolve_major = 0
prefer_clip_color = resolve_major == 0 or resolve_major >= 20

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

def add_audio_clip_marker(item, track_index, reason, start_frame, end_frame):
    duration = max(1, int(end_frame or 0) - int(start_frame or 0))
    name = "[BFD-AUDIO] 单声道音频"
    note = "单声道音频：" + item_name(item) + "\\n轨道 A" + str(track_index) + "\\n原因：" + reason
    custom_data = "qinghe-bfd-audio-mono-" + str(track_index) + "-" + str(start_frame)
    attempts = (
        lambda: item.AddMarker(0, AUDIO_CLIP_MARKER_COLOR, name, note, duration, custom_data),
        lambda: item.AddMarker(0, AUDIO_CLIP_MARKER_COLOR, name, note, duration),
    )
    for attempt in attempts:
        if safe(attempt, False):
            return True
    return False

for track_index in range(1, track_count + 1):
    subtype = str(safe(lambda idx=track_index: timeline.GetTrackSubType("audio", idx), "") or "")
    track_name = str(safe(lambda idx=track_index: timeline.GetTrackName("audio", idx), f"Audio {{track_index}}") or f"Audio {{track_index}}")
    enabled = safe(lambda idx=track_index: timeline.GetIsTrackEnabled("audio", idx), True)
    items = safe(lambda idx=track_index: timeline.GetItemListInTrack("audio", idx), []) or []
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
        source_mapping_is_mono = mapping_is_mono(source_mapping)
        media_mapping_is_mono = mapping_is_mono(media_mapping)
        source_is_mono = source_mapping_is_mono or media_mapping_is_mono
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
            else:
                reason = "mono source"
            start_frame = normalize_item_frame(safe(lambda item=item: item.GetStart(), 0))
            end_frame = normalize_item_frame(safe(lambda item=item: item.GetEnd(), start_frame))
            color_changed = False
            clip_marker_added = False
            if ACTION in {{"mark", "fix"}} and prefer_clip_color:
                for clip_color in (AUDIO_MARK_COLOR,) + AUDIO_MARK_FALLBACK_COLORS:
                    if safe(lambda item=item, clip_color=clip_color: item.SetClipColor(clip_color), False):
                        color_changed = True
                        break
            if ACTION in {{"mark", "fix"}} and not color_changed:
                clip_marker_added = add_audio_clip_marker(item, track_index, reason, start_frame, end_frame)
            clips.append({{
                "track_index": track_index,
                "track_subtype": subtype or "unknown",
                "track_format": display_track_format(subtype),
                "name": item_name(item),
                "start_frame": start_frame,
                "end_frame": end_frame,
                "color": safe(lambda item=item: item.GetClipColor(), ""),
                "color_changed": color_changed,
                "clip_marker_added": clip_marker_added,
                "reason": reason,
                "source_mapping": source_mapping,
                "media_mapping": media_mapping,
                "mapping_fixed": fixed,
                "fix_method": fix_method,
            }})

created_tracks = 0
clip_color_changed = sum(1 for clip in clips if clip.get("color_changed"))
clip_markers_added = sum(1 for clip in clips if clip.get("clip_marker_added"))

if ACTION == "mark":
    message = f"单声道音频标记完成：片段颜色 {{clip_color_changed}} 个，片段红色区域标记 {{clip_markers_added}} 个。"
elif ACTION == "fix":
    message = (
        f"轨道格式修正 {{track_format_fixed}}/{{track_format_fix_attempts}}；"
        f"已尝试修正 {{mapping_fix_attempts}} 个声道映射，成功 {{mapping_fixed}} 个；"
        f"片段颜色 {{clip_color_changed}} 个，片段红色区域标记 {{clip_markers_added}} 个。"
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
        "clip_color_supported": prefer_clip_color,
        "clip_color_changed": clip_color_changed,
        "clip_markers_added": clip_markers_added,
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
            return False, "fuscript was not found."
        lua_entry = find_lua_entry()
        if not lua_entry:
            return False, "检测入口未找到。"

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["BFD_PARAMS_FILE"] = str(params_path)
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
print(json.dumps({"connected": bool(resolve)}))
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
        except Exception:
            return None
        if completed.returncode != 0:
            return None
        output = (completed.stdout or "").strip().splitlines()
        if not output:
            return None
        try:
            return json.loads(output[-1])
        except Exception:
            return None
