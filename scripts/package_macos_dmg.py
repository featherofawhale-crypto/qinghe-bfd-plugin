#!/usr/bin/env python3
"""Package a protected macOS plugin folder into a DMG."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WRAPPER = REPO_ROOT / "pending_codex" / "QingheBFD_v1.9.104_macOS"
DEFAULT_OUT = REPO_ROOT / "dist" / "protected_release"


def copy_file_if_exists(src: Path, dst: Path) -> None:
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create macOS DMG from protected plugin folder.")
    parser.add_argument("protected_plugin_dir", type=Path, help="Protected plugin root containing 清何黑帧夹帧检测.lua.")
    parser.add_argument("--wrapper", type=Path, default=DEFAULT_WRAPPER, help="Folder that contains install_macos.command.")
    parser.add_argument("--version", default=None, help="Version label used in folder and DMG names.")
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plugin = args.protected_plugin_dir.resolve()
    wrapper = args.wrapper.resolve()
    if not plugin.exists():
        raise FileNotFoundError(plugin)
    if not (plugin / "清何黑帧夹帧检测.lua").exists():
        raise FileNotFoundError(f"not a plugin root: {plugin}")
    if not (wrapper / "install_macos.command").exists():
        raise FileNotFoundError(f"missing installer: {wrapper / 'install_macos.command'}")

    version = args.version or plugin.name.replace("QingheEditingToolbox_", "")
    package_name = f"清何剪辑工具箱_{version}_macOS"
    stage = args.out_root.resolve() / package_name
    dmg = args.out_root.resolve() / f"{package_name}.dmg"
    if args.clean:
        shutil.rmtree(stage, ignore_errors=True)
        dmg.unlink(missing_ok=True)

    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True, exist_ok=True)

    shutil.copytree(plugin, stage / "QingheBFD_Plugin_macOS")
    for name in [
        "install_macos.command",
        "uninstall_macos.command",
        "README.md",
        "check_components_macos.sh",
        "macos_release.md",
    ]:
        copy_file_if_exists(wrapper / name, stage / name)
    copy_file_if_exists(plugin / "PRIVATE_SOFTWARE_NOTICE.md", stage / "PRIVATE_SOFTWARE_NOTICE.md")
    copy_file_if_exists(plugin / "manifest.json", stage / "manifest.json")

    for script in ["install_macos.command", "uninstall_macos.command", "check_components_macos.sh"]:
        path = stage / script
        if path.exists():
            path.chmod(path.stat().st_mode | 0o111)

    cmd = [
        "hdiutil",
        "create",
        "-volname",
        package_name,
        "-srcfolder",
        str(stage),
        "-ov",
        "-format",
        "UDZO",
        str(dmg),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        return proc.returncode
    print(proc.stdout.strip())
    print(f"DMG: {dmg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
