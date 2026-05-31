#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$ROOT/tools/lua_bytecode_builder.py" \
  --modules-dir "$ROOT/清何黑帧夹帧检测_v1.9.48_Windows/black_frame_detector" \
  --out-dir "$ROOT/dist/Modules/black_frame_detector" \
  --core black_frame_analyzer.lua duplicate_detector.lua
