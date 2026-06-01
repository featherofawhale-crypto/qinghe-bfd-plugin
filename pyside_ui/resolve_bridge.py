from __future__ import annotations

import os
import platform
import subprocess
import sys
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
LUA_ENTRY = REPO_ROOT / "清何黑帧夹帧检测_v1.9.48_Windows" / "清何黑帧夹帧检测.lua"
BRIDGE_WORKER_ARG = "--resolve-bridge"


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


def read_progress_file(path: Path | None = None) -> dict[str, Any] | None:
    path = path or progress_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def frames_to_timecode(frame: int | float, fps: int | float) -> str:
    fps_int = max(1, int(round(float(fps or 24))))
    total_frames = max(0, int(round(float(frame or 0))))
    frames = total_frames % fps_int
    total_seconds = total_frames // fps_int
    seconds = total_seconds % 60
    minutes = (total_seconds // 60) % 60
    hours = total_seconds // 3600
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"


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
        path = os.path.join(base, "Blackmagic Design", "DaVinci Resolve", "Support", "Developer", "Scripting", "Modules")
    elif system == "darwin":
        path = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
    else:
        path = "/opt/resolve/Developer/Scripting/Modules"
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

    def list_timelines(self) -> list[TimelineInfo]:
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
'''
        )
        if not data:
            return [TimelineInfo(1, "当前时间线", 25.0)]
        self._connected = bool(data.get("connected", True))
        timelines = [
            TimelineInfo(
                int(item["index"]),
                clean_resolve_text(item.get("name")),
                float(item["fps"]),
                clean_resolve_text(item.get("uid")),
            )
            for item in data.get("timelines", [])
        ]
        return timelines or [TimelineInfo(1, "当前时间线", 25.0)]

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
'''
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
fps_raw = timeline.GetSetting("timelineFrameRate") or 25
try:
    fps = float(fps_raw)
except Exception:
    fps = 25.0

def as_number(value):
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except Exception:
        return None

def try_method(name):
    try:
        fn = getattr(timeline, name, None)
        if fn:
            return as_number(fn())
    except Exception:
        return None
    return None

in_frame = None
out_frame = None
for in_name, out_name in [
    ("GetInPoint", "GetOutPoint"),
    ("GetMarkIn", "GetMarkOut"),
    ("GetRenderIn", "GetRenderOut"),
    ("GetTimelineIn", "GetTimelineOut"),
]:
    if in_frame is None:
        in_frame = try_method(in_name)
    if out_frame is None:
        out_frame = try_method(out_name)

if in_frame is None or out_frame is None:
    for in_key, out_key in [
        ("timelineIn", "timelineOut"),
        ("InPoint", "OutPoint"),
        ("markIn", "markOut"),
        ("renderIn", "renderOut"),
    ]:
        try:
            if in_frame is None:
                in_frame = as_number(timeline.GetSetting(in_key))
            if out_frame is None:
                out_frame = as_number(timeline.GetSetting(out_key))
        except Exception:
            pass

ok = in_frame is not None and out_frame is not None and out_frame > in_frame
print(json.dumps({{
    "ok": ok,
    "in_frame": in_frame,
    "out_frame": out_frame,
    "fps": fps,
    "message": "已读取当前时间线入出点。" if ok else "当前时间线没有可读取的入出点。"
}}, ensure_ascii=False))
'''
        )
        if not data:
            return {"ok": False, "message": "读取失败：Resolve API 未返回结果。"}
        if data.get("ok"):
            fps = float(data.get("fps", 25.0))
            data["in_tc"] = frames_to_timecode(data.get("in_frame", 0), fps)
            data["out_tc"] = frames_to_timecode(data.get("out_frame", 0), fps)
        return data

    def scan_mono_audio(self, timeline_index: int = 1) -> dict[str, Any]:
        return self._audio_action(timeline_index, "scan")

    def mark_mono_audio(self, timeline_index: int = 1) -> dict[str, Any]:
        return self._audio_action(timeline_index, "mark")

    def fix_mono_audio_to_stereo(self, timeline_index: int = 1) -> dict[str, Any]:
        return self._audio_action(timeline_index, "fix")

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

def tc_from_frame(frame, fps):
    fps_int = max(1, int(round(float(fps or 24))))
    total = max(0, int(round(float(frame or 0))))
    ff = total % fps_int
    total_seconds = total // fps_int
    ss = total_seconds % 60
    mm = (total_seconds // 60) % 60
    hh = total_seconds // 3600
    return f"{{hh:02d}}:{{mm:02d}}:{{ss:02d}}:{{ff:02d}}"

fps_raw = safe(lambda: timeline.GetSetting("timelineFrameRate"), 24) or 24
try:
    fps = float(fps_raw)
except Exception:
    fps = 24.0
start_frame = safe(lambda: timeline.GetStartFrame(), 0) or 0
markers = timeline.GetMarkers() or {{}}
records = []
counts = {{"total": 0, "error": 0, "suspect": 0, "scene": 0, "gap": 0, "duplicate": 0, "content_dup": 0, "opacity": 0, "corrupt": 0}}

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
        "timecode": tc_from_frame(abs_frame, fps),
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

    def scan_text_items(self, timeline_index: int = 1, query: str = "") -> dict[str, Any]:
        return self._text_action(timeline_index, "scan", query=query)

    def jump_to_text_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return self._text_action(int(item.get("timeline_index", 1)), "jump", item=item)

    def replace_text_item(self, item: dict[str, Any], text: str) -> dict[str, Any]:
        return self._text_action(int(item.get("timeline_index", 1)), "replace", item=item, text=text)

    def delete_text_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return self._text_action(int(item.get("timeline_index", 1)), "delete", item=item)

    def _text_action(
        self,
        timeline_index: int,
        action: str,
        query: str = "",
        item: dict[str, Any] | None = None,
        text: str = "",
    ) -> dict[str, Any]:
        action = action if action in {"scan", "jump", "replace", "delete"} else "scan"
        data = self._run_resolve_python(
            rf'''
import json
ACTION = {json.dumps(action)}
QUERY = {json.dumps(query)}
ITEM = {json.dumps(item or {}, ensure_ascii=False)}
NEW_TEXT = {json.dumps(text, ensure_ascii=False)}
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

def tc_from_frame(frame, fps):
    fps_int = max(1, int(round(float(fps or 24))))
    total = max(0, int(round(float(frame or 0))))
    ff = total % fps_int
    total_seconds = total // fps_int
    ss = total_seconds % 60
    mm = (total_seconds // 60) % 60
    hh = total_seconds // 3600
    return f"{{hh:02d}}:{{mm:02d}}:{{ss:02d}}:{{ff:02d}}"

fps_raw = safe(lambda: timeline.GetSetting("timelineFrameRate"), 24) or 24
try:
    fps = float(fps_raw)
except Exception:
    fps = 24.0
start_frame = safe(lambda: timeline.GetStartFrame(), 0) or 0
TEXT_KEYS = ["Text", "StyledText", "Text+", "Title", "Subtitle", "Caption", "Name", "Clip Name", "CustomName", "Comments"]
TITLE_HINT_KEYS = {"Text", "StyledText", "Text+", "Title", "Subtitle", "Caption", "CustomName"}

def get_item(track_type, track_index, item_index):
    clips = safe(lambda: timeline.GetItemListInTrack(track_type, track_index), []) or []
    if item_index < 0 or item_index >= len(clips):
        return None
    return clips[item_index]

def item_text(clip):
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

def set_item_text(clip, key, source, new_text):
    if source == "fusion" and ":" in str(key):
        tool_name, input_key = str(key).split(":", 1)
        fusion_count = int(safe(lambda: clip.GetFusionCompCount(), 0) or 0)
        for comp_index in range(1, fusion_count + 1):
            comp = safe(lambda ci=comp_index: clip.GetFusionCompByIndex(ci))
            tools = safe(lambda c=comp: c.GetToolList(False), {{}}) if comp else {{}}
            tool = tools.get(tool_name) if isinstance(tools, dict) else None
            if tool and safe(lambda: tool.SetInput(input_key, new_text), False) is not False:
                return True
    for prop_key in [key, "Text", "StyledText", "Name", "Clip Name", "Comments"]:
        if prop_key and safe(lambda pk=prop_key: clip.SetProperty(pk, new_text), False):
            return True
    return False

def collect_items():
    found = []
    for track_type in ("subtitle", "video"):
        track_count = int(safe(lambda tt=track_type: timeline.GetTrackCount(tt), 0) or 0)
        for track_index in range(1, track_count + 1):
            clips = safe(lambda tt=track_type, ti=track_index: timeline.GetItemListInTrack(tt, ti), []) or []
            for item_index, clip in enumerate(clips):
                text_value, text_key, source = item_text(clip)
                if track_type == "video":
                    has_fusion = int(safe(lambda c=clip: c.GetFusionCompCount(), 0) or 0) > 0
                    item_name = str(safe(lambda c=clip: c.GetName(), "") or "")
                    props = safe(lambda c=clip: c.GetProperty(), {{}}) or {{}}
                    maybe_title = has_fusion or any(str(k) in TITLE_HINT_KEYS for k in props.keys()) or "title" in item_name.lower() or "text" in item_name.lower()
                    if not maybe_title:
                        continue
                haystack = (text_value or "") + " " + str(safe(lambda c=clip: c.GetName(), "") or "")
                if QUERY and QUERY.lower() not in haystack.lower():
                    continue
                rel_start = int(safe(lambda c=clip: c.GetStart(), 0) or 0)
                rel_end = int(safe(lambda c=clip: c.GetEnd(), rel_start) or rel_start)
                abs_start = int(start_frame) + rel_start
                found.append({{
                    "timeline_index": {int(timeline_index)},
                    "track_type": track_type,
                    "track_index": track_index,
                    "item_index": item_index,
                    "timecode": tc_from_frame(abs_start, fps),
                    "start_frame": abs_start,
                    "end_frame": int(start_frame) + rel_end,
                    "text": text_value,
                    "text_key": text_key,
                    "text_source": source,
                    "name": str(safe(lambda c=clip: c.GetName(), "") or ""),
                }})
    return found

if ACTION == "scan":
    items = collect_items()
    print(json.dumps({{"ok": True, "message": f"找到 {{len(items)}} 条文字/字幕素材。", "items": items}}, ensure_ascii=False))
    raise SystemExit(0)

target = get_item(str(ITEM.get("track_type", "video")), int(ITEM.get("track_index", 1)), int(ITEM.get("item_index", -1)))
if not target:
    print(json.dumps({{"ok": False, "message": "目标文字素材不存在。"}}, ensure_ascii=False))
    raise SystemExit(0)

if ACTION == "jump":
    tc = str(ITEM.get("timecode", ""))
    ok = bool(tc and timeline.SetCurrentTimecode(tc))
    if resolve:
        resolve.OpenPage("edit")
    print(json.dumps({{"ok": ok, "message": ("已跳转到 " + tc) if ok else "跳转失败。"}}, ensure_ascii=False))
elif ACTION == "replace":
    ok = set_item_text(target, str(ITEM.get("text_key", "")), str(ITEM.get("text_source", "")), NEW_TEXT)
    print(json.dumps({{"ok": ok, "message": "文字已替换。" if ok else "该文字层未暴露可写文字属性。"}}, ensure_ascii=False))
elif ACTION == "delete":
    ok = bool(safe(lambda: timeline.DeleteClips([target], False), False))
    print(json.dumps({{"ok": ok, "message": "文字层已删除。" if ok else "删除失败，Resolve 未接受该文字层。"}}, ensure_ascii=False))
'''
        )
        if not data:
            return {"ok": False, "message": "文字层操作失败：Resolve API 未返回结果。", "items": []}
        return data

    def _audio_action(self, timeline_index: int, action: str) -> dict[str, Any]:
        action = action if action in {"scan", "mark", "fix"} else "scan"
        data = self._run_resolve_python(
            rf'''
import json
ACTION = {json.dumps(action)}
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

track_count = int(safe(lambda: timeline.GetTrackCount("audio"), 0) or 0)
tracks = []
clips = []
mono_track_indices = []
markers_added = 0
for track_index in range(1, track_count + 1):
    subtype = str(safe(lambda idx=track_index: timeline.GetTrackSubType("audio", idx), "") or "")
    track_name = str(safe(lambda idx=track_index: timeline.GetTrackName("audio", idx), f"Audio {{track_index}}") or f"Audio {{track_index}}")
    enabled = safe(lambda idx=track_index: timeline.GetIsTrackEnabled("audio", idx), True)
    items = safe(lambda idx=track_index: timeline.GetItemListInTrack("audio", idx), []) or []
    track_is_mono = subtype.lower() == "mono"
    if track_is_mono:
        mono_track_indices.append(track_index)
    tracks.append({{
        "index": track_index,
        "name": track_name,
        "subtype": subtype or "unknown",
        "enabled": bool(enabled),
        "item_count": len(items),
        "mono": track_is_mono,
    }})
    for item in items:
        source_mapping = decode_mapping(safe(lambda item=item: item.GetSourceAudioChannelMapping()))
        media_pool_item = safe(lambda item=item: item.GetMediaPoolItem())
        media_mapping = decode_mapping(safe(lambda mpi=media_pool_item: mpi.GetAudioMapping()) if media_pool_item else None)
        source_is_mono = mapping_is_mono(source_mapping) or mapping_is_mono(media_mapping)
        if track_is_mono or source_is_mono:
            if ACTION in {{"mark", "fix"}}:
                safe(lambda item=item: item.SetClipColor("Orange"))
                start_frame = safe(lambda item=item: item.GetStart(), 0) or 0
                duration = max(1, int((safe(lambda item=item: item.GetEnd(), 0) or 0) - int(start_frame or 0)))
                marker_ok = safe(
                    lambda sf=start_frame, dur=duration, nm=item_name(item), reason=("mono track" if track_is_mono else "mono source"):
                        timeline.AddMarker(
                            int(sf),
                            "Orange",
                            "[BFD-AUDIO] 单声道音频",
                            f"{{nm}} / {{reason}}",
                            int(dur),
                            "BFD_AUDIO_MONO",
                        ),
                    False,
                )
                if marker_ok:
                    markers_added += 1
            reason = "mono track" if track_is_mono else "mono source"
            clips.append({{
                "track_index": track_index,
                "track_subtype": subtype or "unknown",
                "name": item_name(item),
                "start_frame": safe(lambda item=item: item.GetStart(), 0),
                "end_frame": safe(lambda item=item: item.GetEnd(), 0),
                "color": safe(lambda item=item: item.GetClipColor(), ""),
                "reason": reason,
            }})

created_tracks = 0
if ACTION == "fix":
    for _ in mono_track_indices:
        if safe(lambda: timeline.AddTrack("audio", {{"audioType": "stereo"}}), False):
            created_tracks += 1

if ACTION == "mark":
    message = f"已标记 {{len(clips)}} 个单声道音频片段为 Orange，并写入 {{markers_added}} 个时间线标记。"
elif ACTION == "fix":
    message = (
        f"已创建 {{created_tracks}} 条 stereo 音轨，并标记 {{len(clips)}} 个单声道片段、{{markers_added}} 个时间线标记。"
        " Resolve 公开 API 未提供直接改片段声道映射的接口。"
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
        "markers_added": markers_added,
        "created_stereo_tracks": created_tracks,
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
            completed = subprocess.run(
                command,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=10,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return True, "fuscript started; Resolve may still be running the script."
        except Exception as exc:
            return False, str(exc)

        output = (completed.stdout or "") + (completed.stderr or "")
        return completed.returncode == 0, output.strip()

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
    def _run_resolve_python(body: str) -> dict[str, Any] | None:
        command, stdin_script = build_resolve_python_process(body)
        try:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            completed = subprocess.run(
                command,
                input=stdin_script,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=4,
                check=False,
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
