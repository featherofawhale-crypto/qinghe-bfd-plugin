#!/usr/bin/env python3
"""
Download temporary Chinese fonts, probe DaVinci Resolve/Fusion font names,
and emit rules only for fonts whose source name fails but a corrected Resolve
Text+ name succeeds.

This tool intentionally uses only Python's standard library plus the local
ResolveBridge module. It does not require fontTools, requests, py launcher,
system ffmpeg, or system Python packages.
"""

from __future__ import annotations

import argparse
import ast
import html
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import tempfile
import urllib.parse
import urllib.request
import zlib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

def find_project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "pyside_ui" / "resolve_bridge.py").exists():
            return parent
    return here.parents[1]


ROOT = find_project_root()
PYSIDE_DIR = ROOT / "pyside_ui"
DEFAULT_OUTPUT = ROOT / "artifacts" / "font_probe_reports" / "font_probe_results.jsonl"
DEFAULT_RULES = ROOT / "artifacts" / "font_probe_reports" / "candidate_font_probe_rules.json"
TEMP_ROOT = Path(os.environ.get("QINGHE_FONT_PROBE_TEMP", r"C:\Temp\qinghe_font_probe_rules"))
LIST_URL = "https://www.fonts.net.cn/fonts-zh-{page}.html"
DETAIL_URL = "https://www.fonts.net.cn/font-{font_id}.html"
DOWNLOAD_URL = "https://www.fonts.net.cn/font-download.html"
USER_AGENT = "Mozilla/5.0 QingheFontProbe/1.0"
STYLE_NAMES = (
    "Regular",
    "Bold",
    "Italic",
    "Medium",
    "Light",
    "Book",
    "Normal",
    "DemiBold",
    "Demibold",
    "ExtraBold",
    "Extrabold",
    "Heavy",
    "Black",
)
VISUAL_SAMPLE_TEXT = "\u6e05 \u4f55 \u9ed1 \u5e27 \u68c0 \u6d4b Qinghe Black Frame 123ABC"
LATIN_VISUAL_SAMPLE_TEXT = VISUAL_SAMPLE_TEXT
RESOLVE_PYTHON_ENV = "QINGHE_RESOLVE_PYTHON"


@dataclass(frozen=True)
class FontListing:
    font_id: str
    source: str
    detail_url: str


def read_url(url: str, *, data: dict[str, str] | None = None, timeout: int = 30, retries: int = 3) -> bytes:
    encoded = None
    if data is not None:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=encoded,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": "https://www.fonts.net.cn/",
        },
    )
    last_exc: Exception | None = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:
            last_exc = exc
            if attempt >= retries:
                break
            time.sleep(0.8 * attempt)
    raise RuntimeError(str(last_exc or "network-error"))


def decode_html(payload: bytes) -> str:
    for encoding in ("utf-8", "gb18030"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", "replace")


def crawl_listings(limit: int, start_page: int = 1, max_pages: int = 200) -> list[FontListing]:
    listings: list[FontListing] = []
    for listing in iter_listings(limit, start_page, max_pages=max_pages):
        listings.append(listing)
    return listings


def iter_listings(limit: int, start_page: int = 1, max_pages: int = 200) -> Iterator[FontListing]:
    seen: set[str] = set()
    page = start_page
    yielded = 0
    while yielded < limit and page < start_page + max_pages:
        try:
            text = decode_html(read_url(LIST_URL.format(page=page), timeout=15, retries=2))
        except Exception as exc:
            print(f"[crawl] SKIP page={page} error={exc}", flush=True)
            page += 1
            continue
        page_count = 0
        for match in re.finditer(
            r'<a[^>]+href="(?P<href>/font-(?P<id>\d+)\.html)"[^>]+title="(?P<title>[^"]+)"',
            text,
        ):
            font_id = match.group("id")
            if font_id in seen:
                continue
            seen.add(font_id)
            source = html.unescape(match.group("title")).strip()
            yield FontListing(font_id, source, urllib.parse.urljoin("https://www.fonts.net.cn", match.group("href")))
            yielded += 1
            page_count += 1
            if yielded >= limit:
                break
        print(f"[crawl] page={page} listings={page_count} total={yielded}", flush=True)
        page += 1


def checkpointed_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    found: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            font_id = str(item.get("font_id") or "")
            if font_id:
                found.add(font_id)
    return found


def iter_rule_fonts_from_results(path: Path) -> Iterator[FontListing]:
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item.get("rule"), dict):
                continue
            font_id = str(item.get("font_id") or "").strip()
            source = str(item.get("source") or item.get("rule", {}).get("source") or "").strip()
            detail_url = str(item.get("detail_url") or "").strip()
            if not font_id or font_id in seen:
                continue
            seen.add(font_id)
            if not detail_url:
                detail_url = DETAIL_URL.format(font_id=font_id)
            yield FontListing(font_id, source, detail_url)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def text_has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", str(text or "")))


def visual_profile_for_font(source: str, metadata: dict[str, Any]) -> dict[str, Any]:
    values = [str(source or "")]
    for group in ("families", "full_names", "postscript_names"):
        raw = metadata.get(group) if isinstance(metadata, dict) else None
        if isinstance(raw, list):
            values.extend(str(item or "") for item in raw)
    expected_script = "cjk" if any(text_has_cjk(value) for value in values) else "latin"
    return {
        "expected_script": expected_script,
        "sample_text": VISUAL_SAMPLE_TEXT,
        "require_tofu_check": expected_script == "cjk",
    }


def download_font_zip(font: FontListing, work_dir: Path) -> Path:
    response = json.loads(decode_html(read_url(DOWNLOAD_URL, data={"id": font.font_id})))
    if not response.get("success"):
        raise RuntimeError(str(response.get("error") or "download-refused"))
    data = response.get("data") or {}
    download_url = str(data.get("url") or data.get("download") or "").strip()
    if not download_url:
        raise RuntimeError("download-url-missing")
    if download_url.startswith("//"):
        download_url = "https:" + download_url
    elif download_url.startswith("/"):
        download_url = urllib.parse.urljoin("https://www.fonts.net.cn", download_url)
    zip_path = work_dir / f"{font.font_id}.zip"
    zip_path.write_bytes(read_url(download_url, timeout=60))
    return zip_path


def extract_font_files(zip_path: Path, extract_dir: Path) -> list[Path]:
    try:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extract_dir)
    except zipfile.BadZipFile as exc:
        raise RuntimeError("bad-zip-response") from exc
    fonts: list[Path] = []
    for path in extract_dir.rglob("*"):
        if path.suffix.lower() in {".ttf", ".otf", ".ttc"} and path.is_file():
            fonts.append(path)
    return sorted(fonts, key=lambda item: item.stat().st_size, reverse=True)


def table_directory(data: bytes, offset: int = 0) -> dict[str, tuple[int, int]]:
    if len(data) < offset + 12:
        return {}
    scaler, num_tables = struct.unpack_from(">I H", data, offset)
    if scaler not in (0x00010000, 0x4F54544F, 0x74727565):
        return {}
    tables: dict[str, tuple[int, int]] = {}
    cursor = offset + 12
    for _ in range(num_tables):
        if len(data) < cursor + 16:
            break
        tag = data[cursor : cursor + 4].decode("latin1", "replace")
        table_offset, table_length = struct.unpack_from(">II", data, cursor + 8)
        tables[tag] = (table_offset + offset, table_length)
        cursor += 16
    return tables


def font_offsets(data: bytes) -> list[int]:
    if len(data) >= 12 and data[:4] == b"ttcf":
        count = struct.unpack_from(">I", data, 8)[0]
        offsets = []
        for idx in range(count):
            cursor = 12 + idx * 4
            if len(data) >= cursor + 4:
                offsets.append(struct.unpack_from(">I", data, cursor)[0])
        return offsets
    return [0]


def decode_name(raw: bytes, platform_id: int, encoding_id: int) -> str:
    encodings = []
    if platform_id in (0, 3):
        encodings.extend(["utf-16-be", "utf-8"])
    elif platform_id == 1:
        encodings.extend(["mac_roman", "utf-8"])
    if encoding_id in (1, 10):
        encodings.insert(0, "utf-16-be")
    encodings.extend(["utf-16-be", "utf-8", "gb18030", "latin1"])
    for encoding in dict.fromkeys(encodings):
        try:
            text = raw.decode(encoding).replace("\x00", "").strip()
        except UnicodeDecodeError:
            continue
        if text:
            return text
    return ""


def parse_font_names(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    families: list[str] = []
    full_names: list[str] = []
    postscript_names: list[str] = []
    styles: list[str] = []
    names_by_id: dict[str, list[str]] = {}
    for offset in font_offsets(data):
        tables = table_directory(data, offset)
        if "name" not in tables:
            continue
        table_offset, table_length = tables["name"]
        table = data[table_offset : table_offset + table_length]
        if len(table) < 6:
            continue
        _format, count, string_offset = struct.unpack_from(">HHH", table, 0)
        for index in range(count):
            cursor = 6 + index * 12
            if len(table) < cursor + 12:
                continue
            platform_id, encoding_id, _language_id, name_id, length, offset_in_strings = struct.unpack_from(">HHHHHH", table, cursor)
            start = string_offset + offset_in_strings
            raw = table[start : start + length]
            value = decode_name(raw, platform_id, encoding_id)
            if not value:
                continue
            bucket = names_by_id.setdefault(str(name_id), [])
            if value not in bucket:
                bucket.append(value)
            if name_id == 1 and value not in families:
                families.append(value)
            elif name_id == 2 and value not in styles:
                styles.append(value)
            elif name_id == 4 and value not in full_names:
                full_names.append(value)
            elif name_id == 6 and value not in postscript_names:
                postscript_names.append(value)
    return {
        "file": path.name,
        "families": families,
        "full_names": full_names,
        "postscript_names": postscript_names,
        "styles": styles or ["Regular"],
        "names_by_id": names_by_id,
    }


def candidate_resolve_pythons() -> list[Path]:
    candidates: list[Path] = []
    override = os.environ.get(RESOLVE_PYTHON_ENV)
    if override:
        candidates.append(Path(override))
    home = Path.home()
    candidates.extend(
        [
            home / "AppData" / "Local" / "Programs" / "Python" / "Python314" / "python.exe",
            home / "AppData" / "Local" / "davinci-resolve-mcp" / "venv" / "Scripts" / "python.exe",
            home / "AppData" / "Roaming" / "uv" / "tools" / "resolve-mcp" / "Scripts" / "python.exe",
            Path(sys.executable),
        ]
    )
    seen: set[Path] = set()
    existing: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        existing.append(resolved)
    return existing


def run_resolve_python(code: str, *, timeout: int = 45) -> dict[str, Any] | None:
    sys.path.insert(0, str(PYSIDE_DIR))
    from resolve_bridge import resolve_python_script

    script = resolve_python_script(code)
    last_error = ""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".py", delete=False) as handle:
        handle.write(script)
        script_path = Path(handle.name)
    try:
        for python_exe in candidate_resolve_pythons():
            try:
                completed = subprocess.run(
                    [str(python_exe), str(script_path)],
                    cwd=str(ROOT),
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=max(5, int(timeout)),
                )
            except subprocess.TimeoutExpired:
                last_error = f"{python_exe}: timeout"
                continue
            except Exception as exc:
                last_error = f"{python_exe}: {exc}"
                continue
            if completed.returncode != 0:
                last_error = f"{python_exe}: exit {completed.returncode} {completed.stderr.strip()}"
                continue
            lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
            for line in reversed(lines):
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict):
                    data.setdefault("_resolve_python", str(python_exe))
                    return data
            last_error = f"{python_exe}: no-json stdout={completed.stdout[-500:]} stderr={completed.stderr[-500:]}"
    finally:
        script_path.unlink(missing_ok=True)
    return {"ok": False, "error": "resolve-python-failed", "detail": last_error}


def read_png_rgb(path: Path) -> tuple[int, int, list[tuple[int, int, int]]]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"not a PNG: {path}")
    offset = 8
    width = height = color_type = bit_depth = None
    payload = bytearray()
    while offset + 8 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack_from(">IIBB", chunk, 0)
        elif chunk_type == b"IDAT":
            payload.extend(chunk)
        elif chunk_type == b"IEND":
            break
    if width is None or height is None or bit_depth not in (8, 16) or color_type not in (2, 6):
        raise ValueError(f"unsupported PNG format: bit_depth={bit_depth} color_type={color_type}")
    channels = 3 if color_type == 2 else 4
    bytes_per_sample = 2 if bit_depth == 16 else 1
    pixel_bytes = channels * bytes_per_sample
    row_bytes = int(width) * pixel_bytes
    raw = zlib.decompress(bytes(payload))
    rows: list[bytes] = []
    cursor = 0
    previous = bytearray(row_bytes)
    for _ in range(int(height)):
        filter_type = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor : cursor + row_bytes])
        cursor += row_bytes
        for index in range(row_bytes):
            left = row[index - pixel_bytes] if index >= pixel_bytes else 0
            up = previous[index]
            up_left = previous[index - pixel_bytes] if index >= pixel_bytes else 0
            if filter_type == 1:
                row[index] = (row[index] + left) & 0xFF
            elif filter_type == 2:
                row[index] = (row[index] + up) & 0xFF
            elif filter_type == 3:
                row[index] = (row[index] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                predictor = left + up - up_left
                pa = abs(predictor - left)
                pb = abs(predictor - up)
                pc = abs(predictor - up_left)
                prior = left if pa <= pb and pa <= pc else (up if pb <= pc else up_left)
                row[index] = (row[index] + prior) & 0xFF
            elif filter_type != 0:
                raise ValueError(f"unsupported PNG filter: {filter_type}")
        rows.append(bytes(row))
        previous = row
    pixels: list[tuple[int, int, int]] = []
    for row in rows:
        for index in range(0, len(row), pixel_bytes):
            if bit_depth == 16:
                pixels.append((row[index], row[index + 2], row[index + 4]))
            else:
                pixels.append((row[index], row[index + 1], row[index + 2]))
    return int(width), int(height), pixels


def png_nonblank_stats(path: Path, *, step: int = 4) -> dict[str, Any]:
    width, height, pixels = read_png_rgb(path)
    sampled = 0
    non_white = 0
    very_dark = 0
    near_white = 0
    for y in range(0, height, max(1, step)):
        base = y * width
        for x in range(0, width, max(1, step)):
            red, green, blue = pixels[base + x]
            lum = int(0.299 * red + 0.587 * green + 0.114 * blue)
            sampled += 1
            if lum >= 245:
                near_white += 1
            if lum < 245:
                non_white += 1
            if lum < 80:
                very_dark += 1
    tofu = cjk_tofu_stats(width, height, pixels)
    near_white_pct = round((100.0 * near_white / sampled) if sampled else 0.0, 4)
    non_white_pct = round((100.0 * non_white / sampled) if sampled else 0.0, 4)
    very_dark_pct = round((100.0 * very_dark / sampled) if sampled else 0.0, 4)
    error_frame_suspect = near_white_pct < 50.0 or non_white_pct > 15.0 or very_dark_pct > 10.0
    error_frame_reason = ""
    if near_white_pct < 50.0:
        error_frame_reason = "non-white-background"
    elif non_white_pct > 15.0:
        error_frame_reason = "too-much-non-white"
    elif very_dark_pct > 10.0:
        error_frame_reason = "too-much-dark-area"
    return {
        "width": width,
        "height": height,
        "samples": sampled,
        "non_white": non_white,
        "near_white": near_white,
        "very_dark": very_dark,
        "near_white_pct": near_white_pct,
        "non_white_pct": non_white_pct,
        "very_dark_pct": very_dark_pct,
        "error_frame_suspect": bool(error_frame_suspect),
        "error_frame_reason": error_frame_reason,
        **tofu,
    }


def cjk_tofu_stats(width: int, height: int, pixels: list[tuple[int, int, int]]) -> dict[str, Any]:
    threshold = 170
    col_counts: list[int] = []
    row_counts = [0] * height
    for x in range(width):
        count = 0
        for y in range(height):
            red, green, blue = pixels[y * width + x]
            lum = int(0.299 * red + 0.587 * green + 0.114 * blue)
            if lum < threshold:
                count += 1
                row_counts[y] += 1
        col_counts.append(count)

    active_rows = [idx for idx, count in enumerate(row_counts) if count > max(3, width * 0.002)]
    if not active_rows:
        return {"glyph_segments": 0, "tofu_suspect": True, "tofu_reason": "no-dark-glyphs"}
    y0, y1 = min(active_rows), max(active_rows)
    min_col = max(3, int((y1 - y0 + 1) * 0.015))
    raw_segments: list[tuple[int, int]] = []
    start: int | None = None
    for idx, count in enumerate(col_counts):
        if count >= min_col and start is None:
            start = idx
        elif count < min_col and start is not None:
            raw_segments.append((start, idx - 1))
            start = None
    if start is not None:
        raw_segments.append((start, width - 1))

    segments: list[tuple[int, int]] = []
    for start, end in raw_segments:
        if end - start < 12:
            continue
        if segments and start - segments[-1][1] < 18:
            segments[-1] = (segments[-1][0], end)
        else:
            segments.append((start, end))
    wide_segments = [(start, end) for start, end in segments if (end - start + 1) > 40]
    if len(wide_segments) < 4:
        return {
            "glyph_segments": len(wide_segments),
            "tofu_suspect": True,
            "tofu_reason": "too-few-cjk-glyph-segments",
        }

    fingerprints: list[str] = []
    hollow_boxes = 0
    for start, end in wide_segments[:8]:
        local_dark: list[tuple[int, int]] = []
        for y in range(y0, y1 + 1):
            for x in range(start, end + 1):
                red, green, blue = pixels[y * width + x]
                lum = int(0.299 * red + 0.587 * green + 0.114 * blue)
                if lum < threshold:
                    local_dark.append((x, y))
        if not local_dark:
            continue
        bx0 = min(x for x, _ in local_dark)
        bx1 = max(x for x, _ in local_dark)
        by0 = min(y for _, y in local_dark)
        by1 = max(y for _, y in local_dark)
        bw = max(1, bx1 - bx0 + 1)
        bh = max(1, by1 - by0 + 1)
        total_dark = len(local_dark)
        inner_dark = 0
        margin_x = max(2, int(bw * 0.25))
        margin_y = max(2, int(bh * 0.25))
        for x, y in local_dark:
            if bx0 + margin_x <= x <= bx1 - margin_x and by0 + margin_y <= y <= by1 - margin_y:
                inner_dark += 1
        dark_density = total_dark / float(bw * bh)
        inner_density = inner_dark / float(max(1, (bw - 2 * margin_x) * (bh - 2 * margin_y)))
        aspect = bw / float(bh)
        if 0.65 <= aspect <= 1.35 and dark_density < 0.28 and inner_density < 0.08:
            hollow_boxes += 1

        bits = []
        for gy in range(16):
            yy0 = by0 + int(gy * bh / 16)
            yy1 = by0 + int((gy + 1) * bh / 16)
            for gx in range(16):
                xx0 = bx0 + int(gx * bw / 16)
                xx1 = bx0 + int((gx + 1) * bw / 16)
                cells = 0
                dark = 0
                for yy in range(yy0, max(yy0 + 1, yy1)):
                    for xx in range(xx0, max(xx0 + 1, xx1)):
                        red, green, blue = pixels[yy * width + xx]
                        lum = int(0.299 * red + 0.587 * green + 0.114 * blue)
                        cells += 1
                        dark += 1 if lum < threshold else 0
                bits.append("1" if dark >= max(1, cells // 5) else "0")
        fingerprints.append("".join(bits))

    max_similarity = 0.0
    for index, left in enumerate(fingerprints):
        for right in fingerprints[index + 1 :]:
            same = sum(1 for a, b in zip(left, right) if a == b)
            max_similarity = max(max_similarity, same / float(max(1, len(left))))
    tofu_suspect = hollow_boxes >= 4 or (len(fingerprints) >= 4 and max_similarity >= 0.94)
    reason = ""
    if hollow_boxes >= 4:
        reason = "hollow-box-glyphs"
    elif len(fingerprints) >= 4 and max_similarity >= 0.94:
        reason = "repeated-identical-glyphs"
    return {
        "glyph_segments": len(wide_segments),
        "hollow_box_segments": hollow_boxes,
        "max_glyph_similarity": round(max_similarity, 4),
        "tofu_suspect": bool(tofu_suspect),
        "tofu_reason": reason,
    }


def candidate_names(source: str, metadata: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for group in ("families", "full_names", "postscript_names"):
        for value in metadata.get(group) or []:
            text = str(value or "").strip()
            if text and text not in values:
                values.append(text)
    source = str(source or "").strip()
    if source and source not in values:
        values.append(source)
    return values


def resolve_probe(source: str, font_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    candidates = candidate_names(source, metadata)
    style = str((metadata.get("styles") or ["Regular"])[0] or "Regular")
    payload = {
        "source": source,
        "font_path": str(font_path),
        "candidates": candidates,
        "style": style,
    }
    code = r'''
import json
import os
import time

PAYLOAD = json.loads(%r)

def safe(callable_obj, default=None):
    try:
        return callable_obj()
    except Exception:
        return default

fusion = dvr_script.scriptapp("Fusion")
manager = fusion.FontManager if fusion else None
if not manager:
    print(json.dumps({"ok": False, "error": "fusion-fontmanager-unavailable"}, ensure_ascii=False))
    raise SystemExit(0)

source = str(PAYLOAD.get("source") or "").strip()
font_path = str(PAYLOAD.get("font_path") or "").strip()
candidates = [str(item or "").strip() for item in (PAYLOAD.get("candidates") or []) if str(item or "").strip()]
style = str(PAYLOAD.get("style") or "Regular").strip() or "Regular"

def font_list():
    value = safe(lambda: manager.GetFontList(), {}) or {}
    return value if isinstance(value, dict) else {}

before = font_list()
direct_before = bool(source and source in before)
addfont_results = []
for name in candidates:
    addfont_results.append({"name": name, "added": bool(safe(lambda n=name: manager.AddFont(font_path, n), False))})
safe(lambda: manager.AddFont(font_path), False)
after = font_list()

accepted = ""
textplus_candidates = []
for name in candidates:
    if name not in after:
        continue

    textplus_ok = False
    textplus_font = ""
    textplus_style = ""
    textplus_error = ""
    comp = safe(lambda: fusion.NewComp(), None)
    try:
        tool = safe(lambda: comp.AddTool("TextPlus", -32768, -32768), None) if comp else None
        if tool:
            safe(lambda: tool.SetInput("StyledText", "清何字体探针123ABC"), None)
            safe(lambda: tool.SetInput("Font", name), None)
            safe(lambda: tool.SetInput("Style", style), None)
            textplus_font = str(safe(lambda: tool.GetInput("Font"), "") or "")
            textplus_style = str(safe(lambda: tool.GetInput("Style"), "") or "")
            textplus_ok = (textplus_font == name)
    except Exception as exc:
        textplus_error = str(exc)
    finally:
        safe(lambda: comp.Close(), None)
    item = {
        "accepted": name,
        "style": style,
        "textplus_ok": bool(textplus_ok),
        "textplus_font": textplus_font,
        "textplus_style": textplus_style,
        "textplus_error": textplus_error,
    }
    textplus_candidates.append(item)
    if not accepted and textplus_ok:
        accepted = name

first = next((item for item in textplus_candidates if item.get("accepted") == accepted), {})
textplus_ok = bool(first.get("textplus_ok"))
textplus_font = str(first.get("textplus_font") or "")
textplus_style = str(first.get("textplus_style") or "")
textplus_error = str(first.get("textplus_error") or "")

print(json.dumps({
    "ok": True,
    "source": source,
    "direct_before": direct_before,
    "accepted": accepted,
    "style": style,
    "textplus_ok": bool(textplus_ok),
    "textplus_font": textplus_font,
    "textplus_style": textplus_style,
    "textplus_error": textplus_error,
    "textplus_candidates": textplus_candidates[:20],
    "addfont_results": addfont_results[:20],
    "needs_rule": bool((not direct_before) and accepted and accepted != source and textplus_ok),
}, ensure_ascii=False))
''' % json.dumps(payload, ensure_ascii=False)
    result = run_resolve_python(code, timeout=45)
    return result or {"ok": False, "error": "resolve-no-json"}


def visual_probe(
    accepted_font: str,
    style: str,
    font_path: Path,
    args: argparse.Namespace,
    font_id: str,
    *,
    sample_text: str = VISUAL_SAMPLE_TEXT,
    expected_script: str = "cjk",
) -> dict[str, Any]:
    if not args.visual:
        return {"ok": True, "skipped": True}
    visual_dir = Path(args.visual_dir)
    visual_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "timeline_index": int(args.timeline_index),
        "track_index": int(args.track_index),
        "item_index": int(args.item_index),
        "tool_name": str(args.tool_name),
        "timecode": str(args.timecode or ""),
        "font": str(accepted_font),
        "font_path": str(font_path),
        "style": str(style or "Regular"),
        "visual_dir": str(visual_dir.resolve()),
        "render_dir": str((TEMP_ROOT / "visual_render").resolve()),
        "prefix": f"font_probe_{font_id}",
        "sample_text": str(sample_text or VISUAL_SAMPLE_TEXT),
        "expected_script": str(expected_script or "cjk"),
    }
    code = r'''
import json
import os
import time

PAYLOAD = json.loads(%r)

def safe(callable_obj, default=None):
    try:
        return callable_obj()
    except Exception:
        return default

resolve = dvr_script.scriptapp("Resolve")
fusion = dvr_script.scriptapp("Fusion")
if not resolve:
    print(json.dumps({"ok": False, "error": "resolve-unavailable"}, ensure_ascii=False))
    raise SystemExit(0)
manager = fusion.FontManager if fusion else None
if manager:
    safe(lambda: manager.AddFont(str(PAYLOAD["font_path"]), str(PAYLOAD["font"])), None)
    safe(lambda: manager.AddFont(str(PAYLOAD["font_path"])), None)
project = resolve.GetProjectManager().GetCurrentProject()
if not project:
    print(json.dumps({"ok": False, "error": "no-project"}, ensure_ascii=False))
    raise SystemExit(0)
timeline = project.GetTimelineByIndex(int(PAYLOAD["timeline_index"])) or project.GetCurrentTimeline()
if not timeline:
    print(json.dumps({"ok": False, "error": "timeline-not-found"}, ensure_ascii=False))
    raise SystemExit(0)
project.SetCurrentTimeline(timeline)
timecode = str(PAYLOAD.get("timecode") or "")
if timecode:
    safe(lambda: timeline.SetCurrentTimecode(timecode), None)
clips = timeline.GetItemListInTrack("video", int(PAYLOAD["track_index"])) or []
item_index = int(PAYLOAD["item_index"])
if item_index < 0 or item_index >= len(clips):
    print(json.dumps({"ok": False, "error": "timeline-item-not-found", "clip_count": len(clips)}, ensure_ascii=False))
    raise SystemExit(0)
clip = clips[item_index]
comp = safe(lambda: clip.GetFusionCompByIndex(1), None)
if not comp:
    print(json.dumps({"ok": False, "error": "fusion-comp-not-found"}, ensure_ascii=False))
    raise SystemExit(0)

for _, old_tool in list((comp.GetToolList(False) or {}).items()):
    attrs = safe(lambda tool=old_tool: tool.GetAttrs(), {}) or {}
    name = str(attrs.get("TOOLS_Name") or "")
    reg = str(attrs.get("TOOLS_RegID") or "")
    if name.startswith("QHProbe") or reg == "Saver":
        safe(lambda tool=old_tool: tool.Delete(), None)
        safe(lambda n=name: comp.DeleteTool(n), None)
        safe(lambda tool=old_tool: comp.DeleteTool(tool), None)

bg = safe(lambda: comp.AddTool("Background", -4, 0), None)
tool = safe(lambda: comp.AddTool("TextPlus", -3, 0), None)
transform = safe(lambda: comp.AddTool("Transform", -2, 0), None)
merge = safe(lambda: comp.AddTool("Merge", -1, 0), None)
if not bg or not tool or not transform or not merge:
    print(json.dumps({"ok": False, "error": "probe-tools-create-failed"}, ensure_ascii=False))
    raise SystemExit(0)

safe(lambda: bg.SetAttrs({"TOOLS_Name": "QHProbeBG"}), None)
safe(lambda: tool.SetAttrs({"TOOLS_Name": "QHProbeText"}), None)
safe(lambda: transform.SetAttrs({"TOOLS_Name": "QHProbeTransform"}), None)
safe(lambda: merge.SetAttrs({"TOOLS_Name": "QHProbeMerge"}), None)
safe(lambda: bg.SetInput("Width", 1920), None)
safe(lambda: bg.SetInput("Height", 1080), None)
for corner in ("TopLeft", "TopRight", "BottomLeft", "BottomRight"):
    safe(lambda c=corner: bg.SetInput(c + "Red", 1), None)
    safe(lambda c=corner: bg.SetInput(c + "Green", 1), None)
    safe(lambda c=corner: bg.SetInput(c + "Blue", 1), None)
    safe(lambda c=corner: bg.SetInput(c + "Alpha", 1), None)

safe(lambda: tool.SetInput("StyledText", str(PAYLOAD["sample_text"])), None)
safe(lambda: tool.SetInput("Font", str(PAYLOAD["font"])), None)
safe(lambda: tool.SetInput("Style", str(PAYLOAD["style"])), None)
safe(lambda: tool.SetInput("Size", 0.14), None)
safe(lambda: tool.SetInput("Center", {1: 0.5, 2: 0.5, 3: 0.0}), None)
safe(lambda: tool.SetInput("Start", 0), None)
safe(lambda: tool.SetInput("End", 1), None)
safe(lambda: tool.SetInput("Enabled1", 1), None)
safe(lambda: tool.SetInput("Opacity1", 1), None)
for name in ("Red1", "Green1", "Blue1", "Red1Clone", "Green1Clone", "Blue1Clone"):
    safe(lambda n=name: tool.SetInput(n, 0), None)
for name in ("Alpha1", "Alpha1Clone"):
    safe(lambda n=name: tool.SetInput(n, 1), None)

safe(lambda: transform.SetInput("Size", 0.58), None)
safe(lambda: transform.ConnectInput("Input", tool.Output), None)
safe(lambda: merge.ConnectInput("Background", bg.Output), None)
safe(lambda: merge.ConnectInput("Foreground", transform.Output), None)
safe(lambda: comp.SetAttrs({"COMPB_Modified": True}), None)

folder = str(PAYLOAD["render_dir"])
prefix = str(PAYLOAD["prefix"])
os.makedirs(folder, exist_ok=True)
path = os.path.join(folder, prefix + ".png")
before_files = set(os.listdir(folder))
for name in os.listdir(folder):
    if name.startswith(prefix) and name.lower().endswith(".png"):
        safe(lambda n=name: os.remove(os.path.join(folder, n)), None)

saver = comp.AddTool("Saver", 2, 2)
safe(lambda: saver.SetAttrs({"TOOLS_Name": "QHProbeSaver"}), None)
safe(lambda: saver.SetInput("Clip", path), None)
safe(lambda: saver.ConnectInput("Input", merge.Output), None)
safe(lambda: comp.SetAttrs({"COMPN_RenderStart": 0, "COMPN_RenderEnd": 0, "COMPN_GlobalStart": 0, "COMPN_GlobalEnd": 119}), None)
render_started = time.time()
export_ok = bool(safe(lambda: comp.Render(), False))
time.sleep(0.2)
actual_path = ""
if os.path.exists(path):
    actual_path = path
else:
    names_after = os.listdir(folder)
    new_matches = [
        os.path.join(folder, name)
        for name in names_after
        if name not in before_files and name.lower().endswith(".png")
    ]
    prefix_matches = [
        os.path.join(folder, name)
        for name in names_after
        if name.startswith(prefix) and name.lower().endswith(".png")
    ]
    recent_matches = [
        os.path.join(folder, name)
        for name in names_after
        if name.lower().endswith(".png") and os.path.getmtime(os.path.join(folder, name)) >= render_started - 1.0
    ]
    matches = new_matches or prefix_matches or recent_matches
    matches.sort(key=lambda item: os.path.getmtime(item), reverse=True)
    if matches:
        actual_path = matches[0]
safe(lambda: comp.DeleteTool(saver), None)
readback_font = str(safe(lambda: tool.GetInput("Font"), "") or "")
readback_style = str(safe(lambda: tool.GetInput("Style"), "") or "")
print(json.dumps({
    "ok": bool(export_ok and actual_path and os.path.exists(actual_path)),
    "export_ok": export_ok,
    "path": actual_path if actual_path and os.path.exists(actual_path) else "",
    "font": readback_font,
    "style": readback_style,
}, ensure_ascii=False))
''' % json.dumps(payload, ensure_ascii=False)
    data = run_resolve_python(code, timeout=90) or {"ok": False, "error": "visual-no-json"}
    image_path = Path(str(data.get("path") or ""))
    if data.get("ok") and image_path.exists():
        report_path = visual_dir / image_path.name
        if image_path.resolve() != report_path.resolve():
            shutil.copy2(image_path, report_path)
            data["render_path"] = str(image_path)
            data["path"] = str(report_path)
            image_path = report_path
        try:
            stats = png_nonblank_stats(image_path)
        except Exception as exc:
            stats = {"error": str(exc)}
        data["pixel_stats"] = stats
        data["expected_script"] = payload["expected_script"]
        data["visible"] = visual_result_is_usable(data, expected_script=payload["expected_script"])
        if not args.keep_visual_png:
            for path in image_path.parent.glob(f"{payload['prefix']}*"):
                if path.suffix.lower() in {".png", ".drx"}:
                    path.unlink(missing_ok=True)
    else:
        data["visible"] = False
    return data


def iter_textplus_candidates(probe: dict[str, Any]) -> list[dict[str, str]]:
    items = probe.get("textplus_candidates")
    candidates: list[dict[str, str]] = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict) or not item.get("textplus_ok"):
                continue
            accepted = str(item.get("accepted") or item.get("font") or "").strip()
            if not accepted:
                continue
            style = str(item.get("style") or probe.get("style") or "Regular").strip() or "Regular"
            candidate = {"accepted": accepted, "style": style}
            if candidate not in candidates:
                candidates.append(candidate)
    accepted = str(probe.get("accepted") or "").strip()
    if accepted:
        fallback = {"accepted": accepted, "style": str(probe.get("style") or "Regular").strip() or "Regular"}
        if fallback not in candidates:
            candidates.insert(0, fallback)
    return candidates


def visual_result_is_usable(visual: dict[str, Any], *, expected_script: str = "cjk") -> bool:
    if not isinstance(visual, dict):
        return False
    if visual.get("skipped"):
        return True
    stats = visual.get("pixel_stats")
    if not isinstance(stats, dict):
        return False
    if stats.get("error_frame_suspect", False) is True:
        return False
    if float(stats.get("non_white_pct", 0.0)) <= 0:
        return False
    if expected_script == "cjk":
        return bool(
            stats.get("tofu_suspect") is False
            and int(stats.get("glyph_segments") or 0) >= 4
        )
    return True


def select_visual_candidate(
    probe: dict[str, Any],
    font_path: Path,
    args: argparse.Namespace,
    font_id: str,
    *,
    profile: dict[str, Any] | None = None,
    visual_runner=visual_probe,
) -> dict[str, Any]:
    profile = profile or {"expected_script": "cjk", "sample_text": VISUAL_SAMPLE_TEXT, "require_tofu_check": True}
    rejected: list[dict[str, Any]] = []
    for candidate in iter_textplus_candidates(probe):
        accepted = candidate["accepted"]
        style = candidate["style"]
        visual = visual_runner(
            accepted,
            style,
            font_path,
            args,
            font_id,
            sample_text=str(profile.get("sample_text") or VISUAL_SAMPLE_TEXT),
            expected_script=str(profile.get("expected_script") or "cjk"),
        )
        if visual_result_is_usable(visual, expected_script=str(profile.get("expected_script") or "cjk")):
            return {
                "accepted": accepted,
                "style": style,
                "visual": visual,
                "rejected_visual_candidates": rejected,
            }
        rejected.append({"accepted": accepted, "style": style, "visual": visual})
    return {
        "accepted": "",
        "style": str(probe.get("style") or "Regular"),
        "visual": {"ok": False, "visible": False, "error": "no-visual-candidate-rendered"},
        "rejected_visual_candidates": rejected,
    }


def build_rule(font: FontListing, font_file: Path, metadata: dict[str, Any], probe: dict[str, Any]) -> dict[str, Any]:
    accepted = str(probe.get("accepted") or "")
    style = str(probe.get("style") or "Regular")
    return {
        "ok": True,
        "source": font.source,
        "accepted": accepted,
        "accepted_candidate": f"{accepted}|||{style}",
        "actual_font": accepted,
        "registered_font_file": font_file.name,
        "registered_font_name": accepted,
        "candidate_attempts": max(1, (probe.get("candidates") or metadata.get("families") or [accepted]).index(accepted) + 1)
        if accepted in (probe.get("candidates") or metadata.get("families") or [accepted])
        else 1,
        "message": "Resolve Text+ 字体探针修复规则",
    }


def process_font(font: FontListing, args: argparse.Namespace) -> dict[str, Any]:
    work_dir = TEMP_ROOT / font.font_id
    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        zip_path = download_font_zip(font, work_dir)
        font_files = extract_font_files(zip_path, work_dir / "extract")
        if not font_files:
            raise RuntimeError("no-font-file")
        font_file = font_files[0]
        ascii_font = work_dir / ("font" + font_file.suffix.lower())
        shutil.copy2(font_file, ascii_font)
        metadata = parse_font_names(ascii_font)
        profile = visual_profile_for_font(font.source, metadata)
        probe = resolve_probe(font.source, ascii_font, metadata) if not args.no_resolve else {"ok": True, "skipped": True}
        visual = {"ok": True, "skipped": True}
        visual_selection: dict[str, Any] | None = None
        if probe.get("needs_rule"):
            visual_selection = select_visual_candidate(probe, ascii_font, args, font.font_id, profile=profile)
            visual = visual_selection["visual"]
            if visual_selection.get("accepted"):
                probe["accepted"] = str(visual_selection.get("accepted") or "")
                probe["style"] = str(visual_selection.get("style") or probe.get("style") or "Regular")
        rule = None
        if probe.get("needs_rule") and visual_result_is_usable(visual):
            rule = build_rule(font, font_file, metadata, probe)
        rejected_visual_candidates = (
            visual_selection.get("rejected_visual_candidates", []) if isinstance(visual_selection, dict) else []
        )
        return {
            "ok": True,
            "font_id": font.font_id,
            "source": font.source,
            "detail_url": font.detail_url,
            "downloaded": True,
            "font_file": font_file.name,
            "metadata": {key: metadata.get(key) for key in ("families", "full_names", "postscript_names", "styles")},
            "visual_profile": profile,
            "probe": probe,
            "visual": visual,
            "rejected_visual_candidates": rejected_visual_candidates,
            "needs_rule": bool(rule),
            "rule": rule,
        }
    except Exception as exc:
        return {
            "ok": False,
            "font_id": font.font_id,
            "source": font.source,
            "detail_url": font.detail_url,
            "error": str(exc),
        }
    finally:
        if not args.keep_temp:
            shutil.rmtree(work_dir, ignore_errors=True)


def is_visual_rule_result(item: dict[str, Any]) -> bool:
    if not item.get("needs_rule") or not isinstance(item.get("rule"), dict):
        return False
    visual = item.get("visual")
    if not isinstance(visual, dict) or visual.get("skipped"):
        return False
    return visual_result_is_usable(visual)


def write_rules_from_results(results_path: Path, rules_path: Path, *, require_visual: bool = False) -> int:
    rules: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    with results_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            rule = item.get("rule")
            if not isinstance(rule, dict):
                continue
            if require_visual and not is_visual_rule_result(item):
                continue
            key = (str(rule.get("source") or ""), str(rule.get("accepted_candidate") or ""))
            if key in seen:
                continue
            seen.add(key)
            rules.append(rule)
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    rules_path.write_text(json.dumps({"version": 1, "rules": rules}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(rules)


def validate_results(results_path: Path) -> dict[str, Any]:
    total = 0
    ok = 0
    rule_records = 0
    visual_valid_rules = 0
    visual_invalid_rules = 0
    skipped: dict[str, int] = {}
    with results_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                skipped["json-decode"] = skipped.get("json-decode", 0) + 1
                continue
            total += 1
            ok += 1 if item.get("ok") else 0
            if item.get("needs_rule"):
                rule_records += 1
                if is_visual_rule_result(item):
                    visual_valid_rules += 1
                else:
                    visual_invalid_rules += 1
                    visual = item.get("visual") if isinstance(item.get("visual"), dict) else {}
                    reason = "no-visual"
                    if isinstance(visual, dict):
                        stats = visual.get("pixel_stats") if isinstance(visual.get("pixel_stats"), dict) else {}
                        reason = str(visual.get("error") or stats.get("tofu_reason") or "visual-not-valid")
                    skipped[reason] = skipped.get(reason, 0) + 1
            elif not item.get("ok"):
                reason = str(item.get("error") or "unknown-error")
                skipped[reason] = skipped.get(reason, 0) + 1
    return {
        "ok": True,
        "results": str(results_path),
        "total_records": total,
        "ok_records": ok,
        "rule_records": rule_records,
        "visual_valid_rules": visual_valid_rules,
        "visual_invalid_rules": visual_invalid_rules,
        "skipped": skipped,
    }


def self_check() -> dict[str, Any]:
    errors: list[str] = []
    if VISUAL_SAMPLE_TEXT != "清 何 黑 帧 检 测 Qinghe Black Frame 123ABC":
        errors.append("visual-sample-text-changed")
    if not any("\u4e00" <= char <= "\u9fff" for char in VISUAL_SAMPLE_TEXT):
        errors.append("visual-sample-text-missing-cjk")
    if not re.search(r"[A-Za-z]", VISUAL_SAMPLE_TEXT):
        errors.append("visual-sample-text-missing-latin")

    source = Path(__file__).read_text(encoding="utf-8")
    try:
        compile(source, str(Path(__file__)), "exec")
    except Exception as exc:
        errors.append(f"module-compile-failed:{exc}")

    embedded_count = 0
    try:
        tree = compile(source, str(Path(__file__)), "exec", flags=ast.PyCF_ONLY_AST)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == "code" for target in node.targets):
                continue
            value = node.value
            if isinstance(value, ast.BinOp) and isinstance(value.left, ast.Constant) and isinstance(value.left.value, str):
                embedded_count += 1
                try:
                    compile(value.left.value % "{}", f"<embedded-resolve-{embedded_count}>", "exec")
                except Exception as exc:
                    errors.append(f"embedded-{embedded_count}-compile-failed:{exc}")
    except Exception as exc:
        errors.append(f"embedded-scan-failed:{exc}")
    if embedded_count < 2:
        errors.append(f"embedded-script-count-too-low:{embedded_count}")

    return {
        "ok": not errors,
        "errors": errors,
        "embedded_scripts": embedded_count,
        "visual_sample_text": VISUAL_SAMPLE_TEXT,
    }


def resolve_preflight(timeout: int = 20) -> dict[str, Any]:
    code = r'''
import json
resolve = dvr_script.scriptapp("Resolve")
fusion = dvr_script.scriptapp("Fusion")
project = None
timeline = None
if resolve:
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject() if pm else None
    timeline = project.GetCurrentTimeline() if project else None
print(json.dumps({
    "resolve": bool(resolve),
    "fusion": bool(fusion),
    "version": resolve.GetVersionString() if resolve else "",
    "project": project.GetName() if project else "",
    "timeline": timeline.GetName() if timeline else "",
}, ensure_ascii=False))
'''
    result = run_resolve_python(code, timeout=max(5, int(timeout)))
    if not isinstance(result, dict):
        return {"ok": False, "error": "resolve-preflight-no-json"}
    result["ok"] = bool(result.get("resolve") and result.get("fusion"))
    if not result["ok"] and not result.get("error"):
        result["error"] = "resolve-or-fusion-unavailable"
    return result


def resolve_scripting_diagnostics(timeout: int = 30) -> dict[str, Any]:
    probe_code = r'''
import json
import os
import sys

base = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
script_api = os.environ.get(
    "RESOLVE_SCRIPT_API",
    os.path.join(base, "Blackmagic Design", "DaVinci Resolve", "Support", "Developer", "Scripting"),
)
module_path = os.path.join(script_api, "Modules")
if os.path.isdir(module_path):
    sys.path.insert(0, module_path)

result = {
    "python": sys.executable,
    "python_version": sys.version.split()[0],
    "script_api": script_api,
    "module_path": module_path,
    "module_path_exists": os.path.isdir(module_path),
    "resolve_script_lib": os.environ.get("RESOLVE_SCRIPT_LIB", ""),
}
try:
    import DaVinciResolveScript as dvr_script
    result["import_ok"] = True
    result["module_file"] = str(getattr(dvr_script, "__file__", ""))
    try:
        resolve = dvr_script.scriptapp("Resolve")
        fusion = dvr_script.scriptapp("Fusion")
        result["resolve"] = bool(resolve)
        result["fusion"] = bool(fusion)
        result["version"] = resolve.GetVersionString() if resolve else ""
    except Exception as exc:
        result["scriptapp_error"] = repr(exc)
except Exception as exc:
    result["import_ok"] = False
    result["import_error"] = repr(exc)
print(json.dumps(result, ensure_ascii=False))
'''
    candidates: list[dict[str, Any]] = []
    for python_exe in candidate_resolve_pythons():
        try:
            completed = subprocess.run(
                [str(python_exe), "-c", probe_code],
                cwd=str(ROOT),
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=max(5, int(timeout)),
            )
        except subprocess.TimeoutExpired:
            candidates.append({"python": str(python_exe), "ok": False, "error": "timeout"})
            continue
        except Exception as exc:
            candidates.append({"python": str(python_exe), "ok": False, "error": str(exc)})
            continue
        parsed: dict[str, Any] = {
            "python": str(python_exe),
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip()[-1000:],
            "stderr": completed.stderr.strip()[-1000:],
        }
        for line in reversed([line.strip() for line in completed.stdout.splitlines() if line.strip()]):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                parsed = value
                parsed["returncode"] = completed.returncode
                if completed.stderr.strip():
                    parsed["stderr"] = completed.stderr.strip()[-1000:]
                break
        parsed["ok"] = bool(parsed.get("resolve") and parsed.get("fusion"))
        candidates.append(parsed)
    ok = any(item.get("ok") for item in candidates)
    remediation = ""
    if not ok:
        remediation = (
            "DaVinciResolveScript imports, but scriptapp returns empty. "
            "Check Resolve Preferences > System > General > External scripting and set it to Local or Network, "
            "then restart Resolve and rerun this command."
        )
    return {"ok": ok, "candidates": candidates, "remediation": remediation}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe Chinese font fallback rules for DaVinci Resolve Text+.")
    parser.add_argument("--self-check", action="store_true", help="Run offline checks for this probe script and exit.")
    parser.add_argument("--validate-results", type=Path, help="Summarize a JSONL probe result file and count strict visual rules.")
    parser.add_argument("--check-resolve", action="store_true", help="Check Resolve/Fusion scripting availability and exit.")
    parser.add_argument("--diagnose-resolve-scripting", action="store_true", help="Print detailed Resolve scripting diagnostics and exit.")
    parser.add_argument("--recheck-results", type=Path, help="Re-download and visually recheck fonts that produced rules in an existing JSONL file.")
    parser.add_argument("--limit", type=int, default=20, help="Number of font listings to inspect.")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--rules-output", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--rules-require-visual", action="store_true", help="Only write rules whose Resolve visual proof passed.")
    parser.add_argument("--target-rules", type=int, default=0, help="Stop after this many strict visual rules are present.")
    parser.add_argument("--resolve-preflight-timeout", type=int, default=20, help="Seconds to wait for the initial Resolve scripting check.")
    parser.add_argument("--skip-resolve-preflight", action="store_true", help="Do not fail fast when Resolve/Fusion scripting is unavailable.")
    parser.add_argument("--resume", action="store_true", help="Skip font IDs already present in the JSONL output.")
    parser.add_argument("--keep-temp", action="store_true", help="Keep downloaded/extracted temporary font files for debugging.")
    parser.add_argument("--visual", action="store_true", help="Require an exported Resolve still to contain visible text before writing a rule.")
    parser.add_argument("--timeline-index", type=int, default=1, help="Resolve timeline index used for visual Text+ probing.")
    parser.add_argument("--track-index", type=int, default=1, help="Video track index of the visual Text+ probe item.")
    parser.add_argument("--item-index", type=int, default=0, help="Zero-based item index of the visual Text+ probe item.")
    parser.add_argument("--tool-name", default="Template", help="Fusion Text+ tool name inside the probe item.")
    parser.add_argument("--timecode", default="", help="Timeline timecode inside the probe item for Gallery still export.")
    parser.add_argument("--visual-dir", type=Path, default=ROOT / "artifacts" / "font_probe_reports" / "visual", help="Temporary still export folder.")
    parser.add_argument("--visual-threshold-pct", type=float, default=0.25, help="Minimum non-white sampled pixels for a visible text pass.")
    parser.add_argument("--keep-visual-png", action="store_true", help="Keep exported still PNG/DRX visual evidence files.")
    parser.add_argument("--no-resolve", action="store_true", help="Only download and parse fonts; skip Resolve/Text+ probing.")
    parser.add_argument("--delay", type=float, default=0.3, help="Delay between downloads.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.self_check:
        result = self_check()
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0 if result.get("ok") else 1
    if args.validate_results:
        result = validate_results(args.validate_results)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0 if result.get("ok") else 1
    if args.check_resolve:
        result = resolve_preflight(args.resolve_preflight_timeout)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0 if result.get("ok") else 1
    if args.diagnose_resolve_scripting:
        result = resolve_scripting_diagnostics(args.resolve_preflight_timeout)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    if not args.no_resolve and not args.skip_resolve_preflight:
        result = resolve_preflight(args.resolve_preflight_timeout)
        if not result.get("ok"):
            print(json.dumps({"ok": False, "stage": "resolve-preflight", **result}, ensure_ascii=True, indent=2))
            return 2
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    done = checkpointed_ids(args.output) if args.resume else set()
    processed = 0
    strict_rule_count = 0
    font_iter = iter_rule_fonts_from_results(args.recheck_results) if args.recheck_results else iter_listings(args.limit, args.start_page)
    for font in font_iter:
        if font.font_id in done:
            continue
        if args.recheck_results and processed >= max(0, int(args.limit)):
            break
        result = process_font(font, args)
        append_jsonl(args.output, result)
        processed += 1
        if args.output.exists() and (args.target_rules > 0 or args.rules_require_visual):
            strict_rule_count = write_rules_from_results(args.output, args.rules_output, require_visual=True)
        status = "RULE" if result.get("needs_rule") else ("OK" if result.get("ok") else "SKIP")
        suffix = f" strict_rules={strict_rule_count}" if args.target_rules > 0 else ""
        print(f"[{processed}] {status} {font.font_id} {font.source}{suffix}", flush=True)
        if args.target_rules > 0 and strict_rule_count >= args.target_rules:
            break
        if args.delay > 0:
            time.sleep(args.delay)
    require_visual_rules = bool(args.rules_require_visual or args.target_rules > 0)
    rule_count = (
        write_rules_from_results(args.output, args.rules_output, require_visual=require_visual_rules)
        if args.output.exists()
        else 0
    )
    if not args.keep_temp:
        shutil.rmtree(TEMP_ROOT, ignore_errors=True)
    print(json.dumps({"processed": processed, "rules": rule_count, "results": str(args.output), "rules_output": str(args.rules_output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
