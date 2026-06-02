# Qinghe BFD Windows Package

Version: 1.9.102

Qinghe BFD is a DaVinci Resolve black-frame, stuck-frame, mixed-cut, duplicate-frame, corrupt-frame, audio-channel, and timeline-text inspection tool.

## Quick Start

1. Extract the Windows zip to a normal local folder.
2. Double-click `install_windows.bat`.
3. Restart DaVinci Resolve if it is already open.
4. Open Resolve menu: `Workspace -> Scripts -> Edit -> 清何黑帧夹帧检测`.
5. Use the generated desktop shortcut `Qinghe BFD Control` for the PySide control panel.

## Included Components

- DaVinci Resolve Lua entry script.
- Lua modules under `black_frame_detector`.
- Protected bytecode copies of the core detection modules.
- PySide UI packaged by PyInstaller as `QingheBFDControl.exe`.
- bundled Python runtime inside the PyInstaller app folder.
- Bundled FFmpeg executables under the plugin package.
- Windows installer scripts and component checker.
- Developer notes and operation cautions under `docs`.

Users do not need to install Python or PySide separately when using the release zip.

## Requirements

- Windows 10 or later.
- DaVinci Resolve 17 or later.
- DaVinci Resolve scripting enabled.
- A project with an active timeline.

## Important Notes

- The zip is designed for local installation. Do not run the plugin from inside the compressed archive.
- If Resolve is already open during installation, restart Resolve before testing the script menu.
- Complex mode creates temporary render/cache files and removes them after detection when the flow completes.
- The release contains a watermark string for traceability: `QH-BFD:清何:wm-20260603:v1.9.102`.
- Core Lua detection modules are protected as bytecode in the release package.

## Support Files

- `docs/lua_bytecode_and_pyside_bridge.md`: development notes, packaging flow, and cautions.
- `pyside_ui/README.md`: PySide control panel notes.
- `check_components.ps1`: local component diagnostics.
