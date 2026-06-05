# Qinghe BFD Developer Notes

You are working on the Qinghe BFD DaVinci Resolve plugin. Address the user as `清何大大` and keep replies concise.

## Product Boundary

This project ships a Windows DaVinci Resolve script plus a PySide control panel for black-frame, stuck-frame, mixed-cut, duplicate-frame, corrupt-frame, audio-channel, IO-range, and timeline-text checks.

Primary roots:

- `清何黑帧夹帧检测_v1.9.48_Windows/`: Resolve Lua script and Lua modules.
- `pyside_ui/`: PySide6 control panel and Resolve bridge.
- `docs/`: public development and packaging notes copied into release zips.
- `private_docs/`: owner-only acceptance cases. Do not copy these into release packages.
- `tests/`: Python regression tests.

## Rules Before Editing

- Do not hard-code timeline FPS. Always use the active Resolve timeline FPS.
- Preserve timeline start timecode and IO points when detecting, marking, jumping, rendering, or listing text.
- IO points apply to video detection, complex mode, audio detection, and text navigation unless a feature explicitly says otherwise.
- Complex mode must return marker/result data to the UI and clean cache files after the run completes.
- Mixed-cut detection must catch one-frame inserts inside uncut mixed footage and compound-style clips, not only manually cut timeline items.
- Audio channel checks must not mark real stereo as mono. If Resolve cannot safely modify mapping, log the exact API limitation and keep the UI honest.
- Text tools must support SRT/subtitle tracks first, then Resolve text layers/Text+. Search highlights matches without filtering rows away.

## Required Version Bump

When changing shipped code or docs, update the same version in:

- `pyside_ui/app.py`
- `build_release_windows.ps1`
- `清何黑帧夹帧检测_v1.9.48_Windows/black_frame_detector/config.lua`
- `清何黑帧夹帧检测_v1.9.48_Windows/清何黑帧夹帧检测.lua`
- public docs that mention the version

Current version: `1.9.103`.

## Packaging

Build the Windows release from the repo root:

```powershell
.\build_release_windows.ps1
```

The zip must include:

- `install_windows.bat`
- `install_windows.ps1`
- `check_components.ps1`
- `QingheBFD_Plugin_Windows`
- `pyside_ui/QingheBFDControl/QingheBFDControl.exe`
- bundled PyInstaller Python runtime
- bundled FFmpeg binaries
- `black_frame_detector/bytecode_manifest.json`

Do not include `private_docs/` in public zips.

## Verification

Run these before claiming the build is ready:

```powershell
py -3 -m compileall pyside_ui
py -3 -m unittest tests.test_pyside_ui
.\install_windows.ps1
.\build_release_windows.ps1
```

For Resolve-facing behavior, verify with an actual Resolve project when possible. Passing local tests alone is not proof that the plugin opened, read a timeline, or placed markers correctly.

