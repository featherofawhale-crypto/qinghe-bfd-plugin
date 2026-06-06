# PySide Control Panel

Version: 2.0.01-测试版

The PySide control panel is the Windows UI companion for the Resolve Lua script.

## Release Behavior

In the Windows zip, this app is packaged by PyInstaller:

```text
pyside_ui/QingheBFDControl/QingheBFDControl.exe
```

The PyInstaller folder includes the Python runtime, PySide6, and required support libraries. End users do not need to install Python.

## Development Run

For development only:

```powershell
py -3 -m pip install -r pyside_ui\requirements.txt
py -3 pyside_ui\app.py
```

## Important UI Notes

- The window should remain single-instance.
- The UI should close when DaVinci Resolve exits.
- Timeline FPS must be read from Resolve and reflected in frame thresholds.
- IO point reads must handle timelines whose start timecode is not `01:00:00:00`.
- Text search should highlight matched words while preserving row visibility.
- Detection results should be time-sorted and double-clickable for timeline jump.

## Diagnostics

Logs are written through the Resolve/Lua side and PySide bridge progress files. When packaging issues appear, check:

- `bfd_debug.log` under the user home directory.
- PyInstaller output under `build/windows`.
- Installed UI path recorded in `ui_launcher_path.txt`.
