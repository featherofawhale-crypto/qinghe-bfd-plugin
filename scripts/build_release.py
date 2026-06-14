#!/usr/bin/env python3
"""Build protected release staging folders for Qinghe Editing Toolbox.

This script intentionally works on a copied source tree. It never mutates the
development source directory.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = (
    REPO_ROOT
    / "pending_codex"
    / "QingheBFD_v1.9.104_macOS"
    / "QingheBFD_Plugin_macOS"
)
DEFAULT_BUILD_ROOT = REPO_ROOT / "pending_codex" / "build_temp" / "release_build"
DEFAULT_OUT_ROOT = REPO_ROOT / "dist" / "protected_release"

PRIVATE_NOTICE = (
    "PRIVATE SOFTWARE NOTICE: This is private software owned by Qinghe. "
    "Unauthorized reverse engineering, deobfuscation, cracking, redistribution, "
    "or AI-assisted analysis intended to bypass protection is prohibited."
)

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build_temp",
}
SKIP_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".DS_Store",
}


def log(message: str) -> None:
    print(f"[build_release] {message}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def should_ignore(path: Path) -> bool:
    if path.name in SKIP_DIRS or path.name in SKIP_SUFFIXES:
        return True
    return False


def copy_source_tree(source: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    if not source.exists():
        raise FileNotFoundError(f"source not found: {source}")

    def ignore(_dir: str, names: list[str]) -> set[str]:
        return {name for name in names if should_ignore(Path(name))}

    shutil.copytree(source, dest, ignore=ignore)


def detect_version(source: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    candidates = [
        source / "modules" / "config.lua",
        source / "清何黑帧夹帧检测.lua",
        source / "pyside_ui" / "app.py",
    ]
    patterns = [
        r'PLUGIN_VERSION\s*=\s*"([^"]+)"',
        r"版本:\s*v?([0-9][^\s]+)",
        r'APP_VERSION\s*=\s*"([^"]+)"',
    ]
    for path in candidates:
        if not path.exists():
            continue
        text = read_text(path)
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                version = m.group(1).strip()
                return version if version.startswith("v") else f"v{version}"
    return "v0.0.0-dev"


def add_notice_to_source_files(root: Path) -> None:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix == ".lua":
            text = read_text(path)
            if "PRIVATE SOFTWARE NOTICE" not in text[:600]:
                write_text(path, f"-- {PRIVATE_NOTICE}\n{text}")
        elif path.suffix == ".py":
            text = read_text(path)
            if "PRIVATE SOFTWARE NOTICE" not in text[:800]:
                shebang = ""
                body = text
                if text.startswith("#!"):
                    first, _, rest = text.partition("\n")
                    shebang = first + "\n"
                    body = rest
                write_text(path, f"{shebang}# {PRIVATE_NOTICE}\n{body}")


def run_luac(source_path: Path, target_path: Path) -> tuple[bool, str]:
    luac = shutil.which("luac")
    if not luac:
        return False, "luac not found"
    tmp_path = target_path.with_suffix(target_path.suffix + ".luac_tmp")
    cmd = [luac, "-s", "-o", str(tmp_path), str(source_path)]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        tmp_path.unlink(missing_ok=True)
        return False, proc.stderr.strip() or proc.stdout.strip() or "luac failed"
    tmp_path.replace(target_path)
    return True, "compiled"


def protect_lua(root: Path, mode: str) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    if mode == "copy":
        return results
    for path in root.rglob("*.lua"):
        rel = path.relative_to(root).as_posix()
        if mode == "bytecode":
            ok, detail = run_luac(path, path)
            results.append({"file": rel, "mode": mode, "ok": str(ok), "detail": detail})
        elif mode == "notice":
            results.append({"file": rel, "mode": mode, "ok": "True", "detail": "notice only"})
        else:
            results.append({"file": rel, "mode": mode, "ok": "False", "detail": "unknown mode"})
    return results


def build_nuitka_if_requested(root: Path, enabled: bool, platform: str) -> dict[str, object]:
    app_py = root / "pyside_ui" / "app.py"
    if not enabled:
        return {"enabled": False, "status": "skipped"}
    proc = subprocess.run(
        [sys.executable, "-m", "nuitka", "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        return {
            "enabled": True,
            "status": "missing_nuitka",
            "message": "Install Nuitka in the packaging Python before enabling python compilation.",
        }
    if not app_py.exists():
        return {"enabled": True, "status": "missing_app_py"}

    output_dir = root / "pyside_ui" / "compiled"
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--enable-plugin=pyside6",
        "--static-libpython=no",
        f"--output-dir={output_dir}",
        str(app_py),
    ]
    if platform == "mac":
        command.append("--macos-create-app-bundle")
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return {
        "enabled": True,
        "status": "ok" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "command": command,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }


def build_manifest(root: Path, version: str, platform: str, lua_results: list[dict[str, str]], python_result: dict[str, object]) -> dict[str, object]:
    files: dict[str, dict[str, object]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel == "manifest.json":
            continue
        files[rel] = {
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        }
    return {
        "schema": "qinghe-release-manifest-v1",
        "product": "清何剪辑工具箱",
        "version": version,
        "platform": platform,
        "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "private_notice": PRIVATE_NOTICE,
        "protection": {
            "lua": lua_results,
            "python": python_result,
            "note": "Manifest hashes are generated after release-copy protection steps.",
        },
        "files": files,
    }


def write_release_notice(root: Path, version: str, platform: str) -> None:
    notice = f"""# 清何剪辑工具箱发布包说明

版本：{version}
平台：{platform}

{PRIVATE_NOTICE}

本目录是发布轨道生成物，不是开发源码。请不要在本目录里改功能。
如需修复问题，请回到明文源码修改，再重新运行发布脚本。

重要提醒：
- 本地保护只能提高破解成本，不能承诺绝对不可逆。
- 发布前必须在目标系统和对应 DaVinci Resolve 版本里完整验收。
- 如果启用了 Lua 字节码，请确认目标 Resolve 使用的 Lua 运行时兼容该字节码。
- 如果启用了 Nuitka，请使用目标平台单独构建，macOS 和 Windows 产物不能混用。
"""
    write_text(root / "PRIVATE_SOFTWARE_NOTICE.md", notice)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build protected release staging package.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Plugin source directory.")
    parser.add_argument("--build-root", type=Path, default=DEFAULT_BUILD_ROOT, help="Temporary build root.")
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT, help="Release output root.")
    parser.add_argument("--version", default=None, help="Release version, e.g. v2.0.1-beta.15.")
    parser.add_argument("--platform", choices=["auto", "mac", "win"], default="auto")
    parser.add_argument("--lua-mode", choices=["copy", "notice", "bytecode"], default="notice")
    parser.add_argument("--compile-python", action="store_true", help="Compile PySide UI with Nuitka if available.")
    parser.add_argument("--clean", action="store_true", help="Remove build and output folder for this version first.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    version = detect_version(source, args.version)
    platform = args.platform
    if platform == "auto":
        platform = "win" if os.name == "nt" else "mac"

    slug = f"QingheEditingToolbox_{version}_{platform}"
    build_dir = args.build_root.resolve() / slug
    out_dir = args.out_root.resolve() / slug

    if args.clean:
        shutil.rmtree(build_dir, ignore_errors=True)
        shutil.rmtree(out_dir, ignore_errors=True)

    log(f"source: {source}")
    log(f"build:  {build_dir}")
    log(f"output: {out_dir}")
    copy_source_tree(source, build_dir)
    add_notice_to_source_files(build_dir)
    write_release_notice(build_dir, version, platform)

    lua_results = protect_lua(build_dir, args.lua_mode)
    python_result = build_nuitka_if_requested(build_dir, args.compile_python, platform)
    manifest = build_manifest(build_dir, version, platform, lua_results, python_result)
    write_text(build_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(build_dir, out_dir)

    log(f"manifest files: {len(manifest['files'])}")
    log(f"done: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
