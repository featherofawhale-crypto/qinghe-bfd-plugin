from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYSIDE_DIR = ROOT / "QingheBFD_v1.9.104_macOS" / "QingheBFD_Plugin_macOS" / "pyside_ui"
sys.path.insert(0, str(PYSIDE_DIR))


def split_csv_field(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def compact_key(value: str) -> str:
    clean = "".join(ch for ch in str(value or "").casefold() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
    for token in ("regular", "normal", "常规", "标准", "標準"):
        clean = clean.replace(token, "")
    return clean


def parse_fc_list() -> list[dict]:
    output = subprocess.check_output(
        ["fc-list", "--format", "%{family}\t%{style}\t%{fullname}\t%{postscriptname}\t%{file}\n"],
        text=True,
        stderr=subprocess.DEVNULL,
        timeout=30,
    )
    records: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for line in output.splitlines():
        parts = line.split("\t")
        while len(parts) < 5:
            parts.append("")
        families = split_csv_field(parts[0])
        styles = split_csv_field(parts[1]) or [""]
        fullnames = split_csv_field(parts[2])
        postscripts = split_csv_field(parts[3])
        path = parts[4].strip()
        if not path:
            continue
        names = []
        for value in [*families, *fullnames, *postscripts, Path(path).stem]:
            if value and value not in names:
                names.append(value)
        display_names = []
        for value in [*families, *fullnames]:
            if value and value not in display_names:
                display_names.append(value)
        for display in display_names or names:
            if display.startswith("."):
                continue
            for style in styles:
                source = f"{display} {style}".strip() if style and style.lower() not in {"regular", "normal"} and style not in display else display
                if source.startswith("."):
                    continue
                key = (source, style, path)
                if key in seen:
                    continue
                seen.add(key)
                records.append(
                    {
                        "source": source,
                        "style": style,
                        "path": path,
                        "names": names,
                    }
                )
    return records


def build_records(limit: int) -> list[dict]:
    records = parse_fc_list()
    if limit > 0:
        records = records[:limit]
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Explore Resolve/Fusion font acceptance and emit only needed fallback rules.")
    parser.add_argument("--limit", type=int, default=0, help="0 means all font faces from fc-list.")
    parser.add_argument("--timeline-index", type=int, default=0)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--rules-json", type=Path, default=None)
    args = parser.parse_args()

    from resolve_bridge import ResolveBridge

    records = build_records(args.limit)
    bridge = ResolveBridge()
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump(records, handle, ensure_ascii=False)
        records_path = handle.name
    result = bridge._run_resolve_python(
        rf'''
import json
import os

with open({json.dumps(records_path)}, "r", encoding="utf-8") as handle:
    FONT_RECORDS = json.load(handle)
TIMELINE_INDEX = {int(args.timeline_index)}

resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
timeline = project.GetTimelineByIndex(TIMELINE_INDEX) if project and TIMELINE_INDEX > 0 else (project.GetCurrentTimeline() if project else None)

def safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default

def compact_key(value):
    text = str(value or "").casefold()
    keep = []
    for ch in text:
        if ch.isalnum() or "\\u4e00" <= ch <= "\\u9fff":
            keep.append(ch)
    clean = "".join(keep)
    for token in ("regular", "normal", "常规", "标准", "標準"):
        clean = clean.replace(token, "")
    return clean

def fusion_font_index():
    names = set()
    style_map = {{}}
    basename_to_family = {{}}
    try:
        fusion = dvr_script.scriptapp("Fusion")
        manager = fusion.FontManager if fusion else None
        font_list = manager.GetFontList() if manager else {{}}
    except Exception:
        font_list = {{}}
    if isinstance(font_list, dict):
        for family, styles in font_list.items():
            family_text = str(family or "").strip()
            if not family_text:
                continue
            names.add(family_text)
            style_map.setdefault(family_text, set())
            if isinstance(styles, dict):
                for style, path in styles.items():
                    style_text = str(style or "").strip()
                    if style_text:
                        style_map[family_text].add(style_text)
                    basename = os.path.basename(str(path or ""))
                    if basename:
                        basename_to_family.setdefault(basename, family_text)
    return names, style_map, basename_to_family

fusion_names, fusion_styles, basename_to_family = fusion_font_index()

def find_first_textplus():
    if not timeline:
        return None
    video_count = int(safe(lambda: timeline.GetTrackCount("video"), 0) or 0)
    for track_index in range(1, video_count + 1):
        clips = safe(lambda ti=track_index: timeline.GetItemListInTrack("video", ti), []) or []
        for clip in clips:
            fusion_count = int(safe(lambda c=clip: c.GetFusionCompCount(), 0) or 0)
            for comp_index in range(1, fusion_count + 1):
                comp = safe(lambda c=clip, ci=comp_index: c.GetFusionCompByIndex(ci))
                tools = safe(lambda c=comp: c.GetToolList(False), {{}}) if comp else {{}}
                if not isinstance(tools, dict):
                    continue
                for _tool_name, tool in tools.items():
                    tool_id = str(safe(lambda t=tool: t.ID, "") or "")
                    font = safe(lambda t=tool: t.GetInput("Font"), None)
                    styled = safe(lambda t=tool: t.GetInput("StyledText"), None)
                    if tool_id == "TextPlus" or font not in (None, "") or styled not in (None, ""):
                        return tool
    return None

tool = find_first_textplus()
if tool is None:
    print(json.dumps({{"ok": False, "message": "当前时间线没有找到可写 Text+。"}}, ensure_ascii=False))
    raise SystemExit(0)

original_font = safe(lambda: tool.GetInput("Font"), "")
original_style = safe(lambda: tool.GetInput("Style"), "")
original_text = safe(lambda: tool.GetInput("StyledText"), None)

checked = 0
direct_ok = 0
fallback_ok = 0
failed = []
rules = []
samples = []

for record in FONT_RECORDS:
    source = str(record.get("source", "") or "").strip()
    style = str(record.get("style", "") or "").strip()
    path = str(record.get("path", "") or "").strip()
    names = [str(name or "").strip() for name in record.get("names", []) if str(name or "").strip()]
    basename = os.path.basename(path)
    mapped_family = basename_to_family.get(basename, "")
    candidates = []
    for name in names:
        if name in fusion_names:
            if style and fusion_styles.get(name) and style in fusion_styles.get(name, set()):
                candidates.append((name, style, "direct"))
            else:
                candidates.append((name, style, "direct"))
    if mapped_family:
        candidates.append((mapped_family, style, "fallback"))
    for name in names[:6]:
        candidates.append((name, style, "path"))

    deduped = []
    seen = set()
    for family, cand_style, kind in candidates:
        key = (family, cand_style)
        if not family or key in seen:
            continue
        seen.add(key)
        deduped.append((family, cand_style, kind))

    checked += 1
    record_ok = False
    accepted_kind = ""
    accepted_family = ""
    accepted_style = ""
    before_font = str(safe(lambda: tool.GetInput("Font"), "") or "")
    before_style = str(safe(lambda: tool.GetInput("Style"), "") or "")
    for family, cand_style, kind in deduped[:12]:
        safe(lambda f=family: tool.SetInput("Font", f), None)
        if cand_style:
            safe(lambda s=cand_style: tool.SetInput("Style", s), None)
        if original_text not in (None, ""):
            safe(lambda text=original_text: tool.SetInput("StyledText", text), None)
        after_font = str(safe(lambda: tool.GetInput("Font"), "") or "")
        after_style = str(safe(lambda: tool.GetInput("Style"), "") or "")
        font_ok = after_font == family or (after_font and after_font != before_font)
        style_ok = (not cand_style) or after_style == cand_style or after_style != before_style
        if font_ok and style_ok:
            record_ok = True
            accepted_kind = kind
            accepted_family = after_font or family
            accepted_style = after_style or cand_style
            if kind == "direct":
                direct_ok += 1
            else:
                fallback_ok += 1
                rule_source = source
                rule_candidate = family + (("|||" + cand_style) if cand_style else "")
                rules.append({{
                    "ok": True,
                    "source": rule_source,
                    "accepted": source,
                    "accepted_candidate": rule_candidate,
                    "local_accepted_candidate": rule_candidate,
                    "actual_font": accepted_family,
                    "registered_font_file": basename,
                    "registered_font_name": family,
                    "candidate_attempts": len(deduped[:12]),
                    "message": "全量字体探针修复规则",
                }})
            if len(samples) < 80:
                samples.append({{
                    "source": source,
                    "style": style,
                    "kind": kind,
                    "candidate": family + (("|||" + cand_style) if cand_style else ""),
                    "readback": accepted_family,
                    "readback_style": accepted_style,
                }})
            break
    if not record_ok:
        failed.append({{
            "source": source,
            "style": style,
            "path": path,
            "names": names[:12],
            "mapped_family": mapped_family,
            "candidates": [f + (("|||" + s) if s else "") for f, s, _k in deduped[:12]],
        }})

safe(lambda: tool.SetInput("Font", original_font), None)
if original_style not in (None, ""):
    safe(lambda: tool.SetInput("Style", original_style), None)
if original_text not in (None, ""):
    safe(lambda: tool.SetInput("StyledText", original_text), None)

print(json.dumps({{
    "ok": True,
    "checked": checked,
    "direct_ok": direct_ok,
    "fallback_ok": fallback_ok,
    "failed_count": len(failed),
    "failed": failed[:200],
    "rules": rules,
    "samples": samples,
}}, ensure_ascii=False))
''',
        timeout=3600,
    )
    try:
        Path(records_path).unlink(missing_ok=True)
    except Exception:
        pass
    report = result or {"ok": False, "message": "Resolve API 未返回结果。"}
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.rules_json:
        args.rules_json.parent.mkdir(parents=True, exist_ok=True)
        args.rules_json.write_text(
            json.dumps({"version": 1, "rules": report.get("rules", [])}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
