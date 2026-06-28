# PRIVATE SOFTWARE NOTICE: This is private software owned by Qinghe. Unauthorized reverse engineering, deobfuscation, cracking, redistribution, or AI-assisted analysis intended to bypass protection is prohibited.
from __future__ import annotations

import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path


_PYINSTALLER_DYNAMIC_IMPORT_ANCHORS = (
    importlib.util,
    json,
    os,
    platform,
    re,
    shutil,
    subprocess,
    tempfile,
    time,
    urllib.parse,
    ET,
    Path,
)


def main() -> int:
    script = sys.stdin.read()
    if not script:
        return 2
    namespace: dict[str, object] = {"__name__": "__qinghe_resolve_bridge__"}
    try:
        exec(compile(script, "<qinghe-resolve-bridge>", "exec"), namespace, namespace)
    except SystemExit as exc:
        if exc.code is None:
            return 0
        if isinstance(exc.code, int):
            return exc.code
        print(exc.code, file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"QingheResolveBridge failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
