# Qinghe BFD Windows Installer

Version: 2.0.1-beta.14

Qinghe BFD is a DaVinci Resolve black-frame, stuck-frame, mixed-cut, duplicate-frame, corrupt-frame, audio-channel, and timeline-text inspection tool.

## Quick Start

1. Run `QingheBFD_v2.0.1-beta.14_Windows_Setup.exe`.
2. Accept the disclaimer page and finish the installer.
3. Restart DaVinci Resolve if it is already open.
4. Open Resolve menu: `Workspace -> Scripts -> Edit -> 清何黑帧夹帧检测`.
5. Use the plugin from inside DaVinci Resolve. The installer does not create a desktop shortcut.

## Included Components

- DaVinci Resolve Lua entry script.
- Lua modules under `black_frame_detector`.
- Protected bytecode copies of the core detection modules.
- PySide UI packaged by PyInstaller as `QingheBFDControl.exe`.
- Bundled Python runtime inside the PyInstaller app folder.
- Bundled FFmpeg executables under the plugin package.
- Windows setup EXE, installer scripts, uninstaller, and component checker.
- Developer notes and operation cautions under `docs`.

Users do not need to install Python, PySide, or FFmpeg separately when using the setup EXE.

## Requirements

- Windows 10 or later.
- DaVinci Resolve 17 or later.
- DaVinci Resolve scripting enabled.
- A project with an active timeline.

## Important Notes

- The setup EXE installs the plugin into the current user's DaVinci Resolve script folders.
- If Resolve is already open during installation, restart Resolve before testing the script menu.
- Complex mode creates temporary render/cache files and removes them after detection when the flow completes.
- The release contains a watermark string for traceability: `QH-BFD:清何:wm-20260603:v2.0.1-beta.14`.
- Core Lua detection modules are protected as bytecode in the release package.

## Support Files

- `docs/lua_bytecode_and_pyside_bridge.md`: development notes, packaging flow, and cautions.
- `pyside_ui/README.md`: PySide control panel notes.
- `check_components.ps1`: local component diagnostics.
- `uninstall_windows.ps1`: plugin cleanup used by the Windows uninstaller.
