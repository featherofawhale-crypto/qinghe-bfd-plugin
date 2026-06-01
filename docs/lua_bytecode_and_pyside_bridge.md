# Lua bytecode protection and PySide6 bridge

Current Windows plugin version: `1.9.57`.

## LuaJIT bytecode build

Build protected modules:

Windows:

```bat
tools\build_lua_bytecode.bat
```

macOS:

```bash
chmod +x tools/build_lua_bytecode.sh
tools/build_lua_bytecode.sh
```

Manual form:

```bash
python tools/lua_bytecode_builder.py \
  --modules-dir "清何黑帧夹帧检测_v1.9.48_Windows/black_frame_detector" \
  --out-dir "dist/Modules/black_frame_detector" \
  --core black_frame_analyzer.lua duplicate_detector.lua
```

The builder uses `luajit -b` when `luajit` is installed. On this Windows
machine, no standalone `luajit` command was available, so the builder falls
back to DaVinci Resolve's `fuscript.exe` and writes bytecode with
`string.dump(loadfile(...))`. Resolve's bundled Lua runtime produced LuaJIT
bytecode, which was verified by loading the installed protected modules through
`require()`.

The default output keeps the `.lua` filenames. That means existing code can keep:

```lua
local Analyzer = require("black_frame_analyzer")
local DuplicateDetector = require("duplicate_detector")
```

LuaJIT bytecode is loaded by `require()` through `package.path` just like source
Lua when the filename is still `black_frame_analyzer.lua`.

If you build with `--bytecode-extension ljbc`, add this before `require()`:

```lua
package.path = module_dir .. "/?.ljbc;" .. package.path
```

On Windows use `\\?.ljbc;`.

## Compatibility warning

`luajit -b` bytecode must be loaded by a compatible LuaJIT runtime. If Resolve
loads scripts with plain Lua 5.1 instead of LuaJIT, bytecode modules will fail.
Before shipping bytecode-only builds, test inside Resolve on Windows and macOS.

## PySide6 communication design

The stable bridge implemented here is file-based:

1. PySide6 writes a Lua table to `~/.qinghe_bfd/last_params.lua`.
2. `black_frame_detector/py_params_bridge.lua` reads that file.
3. `ui_bridge.lua` checks the bridge before showing UIManager.
4. Your existing Lua detection core receives a normal `params` table.

This avoids a fragile direct Python-to-Lua in-process call. It also keeps the
current Lua algorithm intact while you gradually move UI and orchestration into
Python.

Longer term, the clean architecture is:

```text
pyside_ui/
  app.py                 PySide6 controls and progress UI
  resolve_bridge.py      Resolve Python API connection

black_frame_detector/
  detector_core.lua      pure detection runner, no UI
  py_params_bridge.lua   external params adapter
  ui_bridge.lua          legacy UIManager adapter
```

Both UIManager and PySide6 should call the same detection runner. That is the
point where progress callbacks become clean: the runner accepts `on_progress`
and both UIs render progress in their own way.
