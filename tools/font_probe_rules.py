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
import html
import json
import os
import re
import shutil
import struct
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
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
    seen: set[str] = set()
    page = start_page
    while len(listings) < limit and page < start_page + max_pages:
        text = decode_html(read_url(LIST_URL.format(page=page)))
        for match in re.finditer(
            r'<a[^>]+href="(?P<href>/font-(?P<id>\d+)\.html)"[^>]+title="(?P<title>[^"]+)"',
            text,
        ):
            font_id = match.group("id")
            if font_id in seen:
                continue
            seen.add(font_id)
            source = html.unescape(match.group("title")).strip()
            listings.append(FontListing(font_id, source, urllib.parse.urljoin("https://www.fonts.net.cn", match.group("href"))))
            if len(listings) >= limit:
                break
        page += 1
    return listings


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


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


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
    sys.path.insert(0, str(PYSIDE_DIR))
    from resolve_bridge import ResolveBridge

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
for name in candidates:
    if name in after:
        accepted = name
        break

textplus_ok = False
textplus_font = ""
textplus_style = ""
textplus_error = ""
if accepted:
    comp = safe(lambda: fusion.NewComp(), None)
    try:
        tool = safe(lambda: comp.AddTool("TextPlus", -32768, -32768), None) if comp else None
        if tool:
            safe(lambda: tool.SetInput("StyledText", "清何字体探针123ABC"), None)
            safe(lambda: tool.SetInput("Font", accepted), None)
            safe(lambda: tool.SetInput("Style", style), None)
            textplus_font = str(safe(lambda: tool.GetInput("Font"), "") or "")
            textplus_style = str(safe(lambda: tool.GetInput("Style"), "") or "")
            textplus_ok = (textplus_font == accepted)
    except Exception as exc:
        textplus_error = str(exc)
    finally:
        safe(lambda: comp.Close(), None)

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
    "addfont_results": addfont_results[:20],
    "needs_rule": bool((not direct_before) and accepted and accepted != source and textplus_ok),
}, ensure_ascii=False))
''' % json.dumps(payload, ensure_ascii=False)
    bridge = ResolveBridge()
    result = bridge._run_resolve_python(code, timeout=45)
    return result or {"ok": False, "error": "resolve-no-json"}


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
        probe = resolve_probe(font.source, ascii_font, metadata) if not args.no_resolve else {"ok": True, "skipped": True}
        rule = None
        if probe.get("needs_rule"):
            rule = build_rule(font, font_file, metadata, probe)
        return {
            "ok": True,
            "font_id": font.font_id,
            "source": font.source,
            "detail_url": font.detail_url,
            "downloaded": True,
            "font_file": font_file.name,
            "metadata": {key: metadata.get(key) for key in ("families", "full_names", "postscript_names", "styles")},
            "probe": probe,
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


def write_rules_from_results(results_path: Path, rules_path: Path) -> int:
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
            key = (str(rule.get("source") or ""), str(rule.get("accepted_candidate") or ""))
            if key in seen:
                continue
            seen.add(key)
            rules.append(rule)
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    rules_path.write_text(json.dumps({"version": 1, "rules": rules}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(rules)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe Chinese font fallback rules for DaVinci Resolve Text+.")
    parser.add_argument("--limit", type=int, default=20, help="Number of font listings to inspect.")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--rules-output", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--resume", action="store_true", help="Skip font IDs already present in the JSONL output.")
    parser.add_argument("--keep-temp", action="store_true", help="Keep downloaded/extracted temporary font files for debugging.")
    parser.add_argument("--no-resolve", action="store_true", help="Only download and parse fonts; skip Resolve/Text+ probing.")
    parser.add_argument("--delay", type=float, default=0.3, help="Delay between downloads.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    done = checkpointed_ids(args.output) if args.resume else set()
    listings = crawl_listings(args.limit, args.start_page)
    processed = 0
    for font in listings:
        if font.font_id in done:
            continue
        result = process_font(font, args)
        append_jsonl(args.output, result)
        processed += 1
        status = "RULE" if result.get("needs_rule") else ("OK" if result.get("ok") else "SKIP")
        print(f"[{processed}/{len(listings)}] {status} {font.font_id} {font.source}", flush=True)
        if args.delay > 0:
            time.sleep(args.delay)
    rule_count = write_rules_from_results(args.output, args.rules_output) if args.output.exists() else 0
    if not args.keep_temp:
        shutil.rmtree(TEMP_ROOT, ignore_errors=True)
    print(json.dumps({"processed": processed, "rules": rule_count, "results": str(args.output), "rules_output": str(args.rules_output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
