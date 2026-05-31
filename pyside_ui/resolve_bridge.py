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


@dataclass
class TimelineInfo:
    index: int
    name: str
    fps: float


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


def write_lua_params(params: dict[str, Any], target: Path | None = None) -> Path:
    target = target or runtime_dir() / "last_params.lua"
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = ["return {"]
    for key, value in params.items():
        lines.append(f"  {key} = {lua_value(value)},")
    lines.append("}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


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
        self._connected = self._probe_connected()

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
items = []
count = int(project.GetTimelineCount() or 0)
for index in range(1, count + 1):
    timeline = project.GetTimelineByIndex(index)
    if not timeline:
        continue
    name = timeline.GetName() or f"Timeline {index}"
    fps_raw = timeline.GetSetting("timelineFrameRate") or 24
    try:
        fps = float(fps_raw)
    except Exception:
        fps = 24.0
    if name == current_name:
        name = name + "  (当前)"
    items.append({"index": index, "name": name, "fps": fps})
print(json.dumps({"connected": True, "timelines": items}, ensure_ascii=False))
'''
        )
        if not data:
            return [TimelineInfo(1, "当前时间线", 24.0)]
        timelines = [
            TimelineInfo(int(item["index"]), str(item["name"]), float(item["fps"]))
            for item in data.get("timelines", [])
        ]
        return timelines or [TimelineInfo(1, "当前时间线", 24.0)]

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

    def run_lua_entry_with_fuscript(self, params_path: Path) -> tuple[bool, str]:
        fuscript = self._find_fuscript()
        if not fuscript:
            return False, "fuscript was not found."
        if not LUA_ENTRY.exists():
            return False, f"Lua entry was not found: {LUA_ENTRY}"

        env = os.environ.copy()
        env["BFD_PARAMS_FILE"] = str(params_path)
        command = [str(fuscript), "-l", "lua", str(LUA_ENTRY)]
        try:
            completed = subprocess.run(
                command,
                env=env,
                text=True,
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
        bootstrap = r'''
import importlib.util
import json
import os
import platform
import sys

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
        script = bootstrap + "\n" + body
        try:
            completed = subprocess.run(
                [sys.executable, "-c", script],
                text=True,
                capture_output=True,
                timeout=8,
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
