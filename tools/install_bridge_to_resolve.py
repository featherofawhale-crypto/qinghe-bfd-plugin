#!/usr/bin/env python3
from __future__ import annotations

import os
import platform
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MODULES = ROOT / "清何黑帧夹帧检测_v1.9.48_Windows" / "black_frame_detector"
FILES = ["ui_bridge.lua", "py_params_bridge.lua", "progress_bridge.lua"]


def resolve_modules_dir() -> Path:
    system = platform.system().lower()
    if system == "windows":
        appdata = Path(os.environ["APPDATA"])
        return (
            appdata
            / "Blackmagic Design"
            / "DaVinci Resolve"
            / "Support"
            / "Fusion"
            / "Scripts"
            / "Modules"
            / "black_frame_detector"
        )
    if system == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Blackmagic Design"
            / "DaVinci Resolve"
            / "Fusion"
            / "Scripts"
            / "Modules"
            / "black_frame_detector"
        )
    return (
        Path.home()
        / ".local"
        / "share"
        / "DaVinciResolve"
        / "Fusion"
        / "Scripts"
        / "Modules"
        / "black_frame_detector"
    )


def main() -> int:
    target = resolve_modules_dir()
    target.mkdir(parents=True, exist_ok=True)
    backup_dir = target / ("backup_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    backup_dir.mkdir(parents=True, exist_ok=True)

    for name in FILES:
        source = SOURCE_MODULES / name
        dest = target / name
        if not source.exists():
            raise SystemExit(f"Missing source file: {source}")
        if dest.exists():
            shutil.copy2(dest, backup_dir / name)
        shutil.copy2(source, dest)
        print(f"Installed {name} -> {dest}")

    print(f"Backup folder: {backup_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
