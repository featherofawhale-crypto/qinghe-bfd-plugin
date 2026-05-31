#!/usr/bin/env python3
"""
Build protected LuaJIT bytecode modules for the DaVinci Resolve plugin.

This is obfuscation, not real cryptographic protection. Keep your source code in
a private repository and ship bytecode only for the modules that contain your
core algorithm.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_CORE_MODULES = [
    "black_frame_analyzer.lua",
    "duplicate_detector.lua",
]


def find_luajit(explicit: str | None, required: bool = True) -> str | None:
    if explicit:
        exe = Path(explicit).expanduser()
        if exe.exists():
            return str(exe)
        found = shutil.which(explicit)
        if found:
            return found
        raise SystemExit(f"luajit not found: {explicit}")

    found = shutil.which("luajit")
    if found:
        return found

    candidates = [
        Path("C:/Program Files/LuaJIT/luajit.exe"),
        Path("C:/Program Files (x86)/LuaJIT/luajit.exe"),
        Path("/usr/local/bin/luajit"),
        Path("/opt/homebrew/bin/luajit"),
        Path("/usr/bin/luajit"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    if required:
        raise SystemExit(
            "luajit was not found. Install LuaJIT or pass --luajit /path/to/luajit."
        )
    return None


def find_fuscript(explicit: str | None) -> str | None:
    if explicit:
        exe = Path(explicit).expanduser()
        if exe.exists():
            return str(exe)
        found = shutil.which(explicit)
        if found:
            return found
        raise SystemExit(f"fuscript not found: {explicit}")

    found = shutil.which("fuscript")
    if found:
        return found

    candidates = [
        Path("C:/Program Files/Blackmagic Design/DaVinci Resolve/fuscript.exe"),
        Path("/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fuscript"),
        Path("/opt/resolve/bin/fuscript"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def copy_tree_without_core(src: Path, dst: Path, core_names: set[str]) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)

    for item in src.rglob("*"):
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if item.name in core_names and item.suffix == ".lua":
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def compile_module_luajit(luajit: str, src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([luajit, "-b", str(src), str(dst)], check=True)


def compile_module_fuscript(fuscript: str, src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bfd_lua_protect_") as tmp_raw:
        tmp = Path(tmp_raw)
        ascii_src = tmp / src.name
        ascii_dst = tmp / dst.name
        shutil.copy2(src, ascii_src)
        script = tmp / "dump.lua"
        script.write_text(
            "\n".join(
                [
                    f"local input = [[{ascii_src}]]",
                    f"local output = [[{ascii_dst}]]",
                    "local chunk, err = loadfile(input)",
                    "if not chunk then error(err) end",
                    "local dumped = string.dump(chunk)",
                    "local f, ferr = io.open(output, 'wb')",
                    "if not f then error(ferr) end",
                    "f:write(dumped)",
                    "f:close()",
                    "print('compiled ' .. input .. ' -> ' .. output)",
                ]
            ),
            encoding="ascii",
        )
        subprocess.run([fuscript, "-l", "lua", str(script)], check=True)
        shutil.copy2(ascii_dst, dst)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile selected Lua modules to LuaJIT bytecode."
    )
    parser.add_argument(
        "--modules-dir",
        required=True,
        help="Path to the black_frame_detector module folder.",
    )
    parser.add_argument(
        "--out-dir",
        default="dist/Modules/black_frame_detector",
        help="Output folder for protected modules.",
    )
    parser.add_argument(
        "--core",
        nargs="+",
        default=DEFAULT_CORE_MODULES,
        help="Lua module filenames to compile with luajit -b.",
    )
    parser.add_argument(
        "--bytecode-extension",
        choices=["lua", "ljbc"],
        default="lua",
        help=(
            "Use lua to keep require() unchanged. Use ljbc only if you also add "
            "?.ljbc to package.path."
        ),
    )
    parser.add_argument("--luajit", help="Path to luajit executable.")
    parser.add_argument("--fuscript", help="Path to DaVinci Resolve fuscript executable.")
    parser.add_argument(
        "--compiler",
        choices=["auto", "luajit", "fuscript"],
        default="auto",
        help="auto prefers luajit -b, then falls back to Resolve fuscript bytecode.",
    )
    parser.add_argument(
        "--no-copy",
        action="store_true",
        help="Do not copy non-core modules to the output folder.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    modules_dir = Path(args.modules_dir).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    if not modules_dir.is_dir():
        raise SystemExit(f"modules dir does not exist: {modules_dir}")

    luajit = find_luajit(args.luajit, required=args.compiler == "luajit")
    fuscript = find_fuscript(args.fuscript)
    compiler = args.compiler
    if compiler == "auto":
        compiler = "luajit" if luajit else "fuscript"
    if compiler == "fuscript" and not fuscript:
        raise SystemExit("fuscript was not found. Install DaVinci Resolve or pass --fuscript.")
    core_names = set(args.core)

    missing = [name for name in args.core if not (modules_dir / name).is_file()]
    if missing:
        raise SystemExit("core module(s) not found: " + ", ".join(missing))

    if args.no_copy:
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        copy_tree_without_core(modules_dir, out_dir, core_names)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": str(modules_dir),
        "output": str(out_dir),
        "compiler": compiler,
        "luajit": luajit,
        "fuscript": fuscript,
        "compiled": [],
    }

    for name in args.core:
        source_file = modules_dir / name
        output_name = (
            source_file.with_suffix(".ljbc").name
            if args.bytecode_extension == "ljbc"
            else source_file.name
        )
        output_file = out_dir / output_name
        if compiler == "luajit":
            if not luajit:
                raise SystemExit("luajit compiler selected but luajit was not found.")
            compile_module_luajit(luajit, source_file, output_file)
        else:
            if not fuscript:
                raise SystemExit("fuscript compiler selected but fuscript was not found.")
            compile_module_fuscript(fuscript, source_file, output_file)
        manifest["compiled"].append(
            {
                "source": str(source_file),
                "output": str(output_file),
                "require_name": source_file.stem,
            }
        )

    manifest_path = out_dir / "bytecode_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Protected modules written to: {out_dir}")
    print(f"Manifest: {manifest_path}")
    if args.bytecode_extension == "lua":
        print("require() does not need to change because bytecode keeps .lua names.")
    else:
        print("Add ?.ljbc to package.path before require().")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
