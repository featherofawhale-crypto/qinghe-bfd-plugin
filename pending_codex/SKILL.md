---
name: qinghe-bfd-dev
description: Use when modifying, packaging, testing, or reviewing the Qinghe BFD DaVinci Resolve plugin, including Lua detection logic, PySide UI, timeline IO handling, mixed-cut detection, audio-channel checks, text/SRT tooling, release zips, and integrity/watermark protection.
---

# Qinghe BFD Development Skill

Use this skill before changing the Qinghe BFD plugin.

## Start Here

1. Read `CLAUDE.md` for project-wide rules.
2. Read `docs/lua_bytecode_and_pyside_bridge.md` for public architecture and packaging notes.
3. For owner-only acceptance cases, read `private_docs/acceptance_cases.md`. Never package that folder into a public release.
4. Inspect `git status --short` before editing and do not revert user changes.

## Core Invariants

- Timeline FPS, start frame, start timecode, and IO range come from Resolve, not constants.
- All detection modes must report UI results and timeline markers in time order.
- Double-click jump targets must convert through the active timeline start frame/timecode.
- Mixed-cut checks must detect one-frame inserts inside uncut clips.
- Complex mode must not swallow markers/results and must clean temporary cache files.
- Audio checks must distinguish source mapping, timeline item state, and track format.
- Text tools search, jump, replace, and delete the exact selected row/item.

## Release Integrity

When changing protection code, keep it practical and reversible:

- Compare core module hashes against a release manifest at startup.
- If a module does not match, show `非官方构建` and disable core detection unless owner override is explicitly documented.
- Keep bytecode protection and watermark traceability in release packages.
- Do not add destructive traps, resource-wasting behavior, or hidden sabotage.

## Version And Git

For shipped changes, bump the version in all version-bearing files listed in `CLAUDE.md`, run tests, stage, and commit. Leave unrelated untracked files alone.

## Verification Commands

```powershell
py -3 -m compileall pyside_ui
py -3 -m unittest tests.test_pyside_ui
.\install_windows.ps1
.\build_release_windows.ps1
```

After building, inspect the generated zip for:

- bundled Python runtime through PyInstaller output
- `QingheBFDControl.exe`
- bundled `ffmpeg.exe` and `ffprobe.exe`
- protected Lua bytecode files
- `bytecode_manifest.json`
- no `private_docs/`

