# Development Notes And Cautions

Version: 1.9.104

This document records the development and packaging rules for Qinghe BFD.

## Architecture

The tool has three main layers:

- Resolve Lua entry script: `清何黑帧夹帧检测_v1.9.48_Windows/清何黑帧夹帧检测.lua`
- Lua modules: `清何黑帧夹帧检测_v1.9.48_Windows/black_frame_detector`
- PySide control panel: `pyside_ui`

The release installer places files under:

```text
%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Edit
%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Modules\black_frame_detector
```

## Packaged Runtime

The Windows zip includes:

- `QingheBFDControl.exe` plus PyInstaller `_internal` files.
- A bundled Python runtime inside the PyInstaller output.
- PySide6 runtime files inside the PyInstaller output.
- FFmpeg executables copied from the package `ffmpeg/bin` directory.
- Protected Lua bytecode for:
  - `black_frame_analyzer.lua`
  - `duplicate_detector.lua`

Users should not need to install Python, PySide6, PyInstaller, or FFmpeg separately.

## Build Command

Run from the project root:

```powershell
.\build_release_windows.ps1
```

Expected output:

```text
release\QingheBFD_v1.9.104_Windows
release\QingheBFD_v1.9.104_Windows.zip
```

## Install Command

From the extracted release folder:

```powershell
.\install_windows.ps1
```

or double-click:

```text
install_windows.bat
```

## Detection Logic Notes

- Timeline FPS must come from the active Resolve timeline. Do not hard-code 24 fps.
- Timeline start timecode and frame offset must be preserved when jumping, marking, or rendering.
- IO points apply to visual detection and audio detection.
- Complex mode analyzes a rendered timeline cache and should return markers/results to the UI.
- Mixed-cut and one-frame insert detection must handle clips that are not manually cut on the timeline.
- Text features should support SRT/subtitle tracks, Resolve text layers, Text+, search highlighting, jump, replace, and delete.
- Audio checks should distinguish mono mapping, left-only/right-only content, and track format limits.

## Protection And Traceability

- The release embeds the watermark label:

```text
QH-BFD:清何:wm-20260603:v1.9.104
```

- Marker custom data, reports, and debug logs include the watermark where supported.
- Core algorithms are protected with Resolve/fuscript bytecode during release build.
- This protection raises copying cost but is not a guarantee against professional reverse engineering.

## Cautions For Future Development

- Keep edits scoped. Avoid broad rewrites of Resolve API bridge code without tests.
- Do not change user-facing timecode behavior without testing non-01:00:00:00 timelines.
- Do not use destructive git commands to discard user changes.
- Do not run proxy, account, PAT, or cloud automation tools from `tools/windsurf-assistant` as part of this plugin.
- When changing package files, update the version in:
  - `pyside_ui/app.py`
  - `build_release_windows.ps1`
  - `black_frame_detector/config.lua`
  - `清何黑帧夹帧检测.lua`

## Verification Checklist

Run before shipping:

```powershell
py -3 -m compileall pyside_ui
py -3 -m unittest tests.test_pyside_ui
.\install_windows.ps1
.\build_release_windows.ps1
```

Then inspect the generated zip and confirm:

- `install_windows.bat` exists.
- `pyside_ui/QingheBFDControl/QingheBFDControl.exe` exists.
- `QingheBFD_Plugin_Windows/ffmpeg/bin/ffmpeg.exe` exists.
- `QingheBFD_Plugin_Windows/black_frame_detector/bytecode_manifest.json` exists.
