# PySide6 UI bridge

Current Windows plugin version: `1.9.57`.

This folder contains an external PySide6 control panel for the DaVinci Resolve
black-frame detector.

## Run

```bash
python -m pip install -r pyside_ui/requirements.txt
python pyside_ui/app.py
```

On Windows, the one-click installer also creates a desktop shortcut to
`pyside_ui/run_ui.bat`.

## Flow

1. The PySide6 UI connects to the Resolve Python API when Resolve is running.
2. The UI lists timelines and writes selected parameters to:

   `~/.qinghe_bfd/last_params.lua`

3. The Lua module `py_params_bridge.lua` reads that file.
4. `ui_bridge.lua` checks the external parameter file before showing the old
   UIManager panel. If external parameters exist, the old UI is skipped.

This keeps your current Lua algorithm intact while allowing a modern external
UI to control it.

## Important

DaVinci Resolve external scripting must be enabled in Resolve preferences for
full Python API access. If automatic Lua triggering fails, start the detection
from Resolve's Workspace > Scripts menu after pressing Start in this UI.
