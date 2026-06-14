#!/usr/bin/env python3
"""Verify a Qinghe release manifest against files on disk."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify release manifest file hashes.")
    parser.add_argument("release_dir", type=Path, help="Directory that contains manifest.json.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    release_dir = args.release_dir.resolve()
    manifest_path = release_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"manifest not found: {manifest_path}")
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failed: list[str] = []
    missing: list[str] = []
    checked = 0
    for rel, info in manifest.get("files", {}).items():
        path = release_dir / rel
        if not path.exists():
            missing.append(rel)
            continue
        checked += 1
        actual = sha256_file(path)
        expected = info.get("sha256")
        if actual != expected:
            failed.append(rel)

    if missing:
        print("Missing files:")
        for rel in missing:
            print(f"  - {rel}")
    if failed:
        print("Hash mismatches:")
        for rel in failed:
            print(f"  - {rel}")
    if missing or failed:
        print(f"FAILED: checked={checked}, missing={len(missing)}, mismatched={len(failed)}")
        return 1

    print(f"OK: checked {checked} files for {manifest.get('product')} {manifest.get('version')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
