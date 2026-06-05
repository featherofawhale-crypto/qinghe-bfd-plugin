from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYSIDE_DIR = ROOT / "QingheBFD_v1.9.104_macOS" / "QingheBFD_Plugin_macOS" / "pyside_ui"
sys.path.insert(0, str(PYSIDE_DIR))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def build_font_candidates(limit: int) -> list[str]:
    from PySide6.QtWidgets import QApplication
    import app as pyside_app

    QApplication.instance() or QApplication([])
    window = pyside_app.MainWindow.__new__(pyside_app.MainWindow)
    window.font_aliases = {}
    window.font_family_styles = {}
    window.available_fonts = []
    pyside_app.MainWindow.load_available_fonts(window)

    candidates: list[str] = []
    for family in window.available_fonts:
        if len(candidates) >= limit:
            break
        styles = list(window.font_family_styles.get(family, [])) or [""]
        for style in styles:
            display_name = f"{family} {style}".strip()
            font_candidates = pyside_app.MainWindow.font_candidates(window, display_name)
            if font_candidates:
                candidate = font_candidates[0]
                if candidate not in candidates:
                    candidates.append(candidate)
            if len(candidates) >= limit:
                break
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="Test whether DaVinci Resolve accepts font candidates on a Text+ layer.")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--timeline-index", type=int, default=0, help="0 means current Resolve timeline.")
    parser.add_argument("--min-pass-rate", type=float, default=80.0)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    from resolve_bridge import ResolveBridge

    candidates = build_font_candidates(max(1, args.limit))
    bridge = ResolveBridge()
    timeline_index = max(0, int(args.timeline_index))
    result = bridge._run_resolve_python(
        rf'''
import json

FONT_CANDIDATES = json.loads({json.dumps(json.dumps(candidates, ensure_ascii=False))})
TIMELINE_INDEX = {timeline_index}
resolve = dvr_script.scriptapp("Resolve")
project_manager = resolve.GetProjectManager() if resolve else None
project = project_manager.GetCurrentProject() if project_manager else None
timeline = None
if project:
    timeline = project.GetTimelineByIndex(TIMELINE_INDEX) if TIMELINE_INDEX > 0 else project.GetCurrentTimeline()

def safe(callable_obj, default=None):
    try:
        return callable_obj()
    except Exception:
        return default

def parse_font_candidate(value):
    text = str(value or "").strip()
    if "|||" in text:
        family, style = text.split("|||", 1)
        return family.strip(), style.strip()
    return text, ""

def find_first_textplus():
    if not timeline:
        return None, "", "", 0, 0
    video_count = int(safe(lambda: timeline.GetTrackCount("video"), 0) or 0)
    for track_index in range(1, video_count + 1):
        clips = safe(lambda ti=track_index: timeline.GetItemListInTrack("video", ti), []) or []
        for item_index, clip in enumerate(clips):
            fusion_count = int(safe(lambda c=clip: c.GetFusionCompCount(), 0) or 0)
            for comp_index in range(1, fusion_count + 1):
                comp = safe(lambda c=clip, ci=comp_index: c.GetFusionCompByIndex(ci))
                tools = safe(lambda c=comp: c.GetToolList(False), {{}}) if comp else {{}}
                iterable = tools.items() if isinstance(tools, dict) else []
                for tool_name, tool in iterable:
                    tool_id = str(safe(lambda t=tool: t.ID, "") or "")
                    font = safe(lambda t=tool: t.GetInput("Font"), None)
                    styled = safe(lambda t=tool: t.GetInput("StyledText"), None)
                    if tool_id == "TextPlus" or font not in (None, "") or styled not in (None, ""):
                        return tool, str(safe(lambda c=clip: c.GetName(), "") or ""), str(tool_name), track_index, item_index
    return None, "", "", 0, 0

tool, clip_name, tool_name, track_index, item_index = find_first_textplus()
if tool is None:
    print(json.dumps({{
        "ok": False,
        "message": "当前时间线没有找到可写 Text+，无法做 Resolve 字体验收。",
        "checked": 0,
        "accepted": 0,
        "failed": 0,
        "failures": [],
    }}, ensure_ascii=False))
    raise SystemExit(0)

original_font = safe(lambda: tool.GetInput("Font"), "")
original_style = safe(lambda: tool.GetInput("Style"), "")
original_text = safe(lambda: tool.GetInput("StyledText"), None)
accepted = 0
failures = []
samples = []
for candidate in FONT_CANDIDATES:
    family, style = parse_font_candidate(candidate)
    before_font = str(safe(lambda: tool.GetInput("Font"), "") or "")
    before_style = str(safe(lambda: tool.GetInput("Style"), "") or "")
    safe(lambda name=family: tool.SetInput("Font", name), None)
    if style:
        safe(lambda value=style: tool.SetInput("Style", value), None)
    if original_text not in (None, ""):
        safe(lambda text=original_text: tool.SetInput("StyledText", text), None)
    after_font = str(safe(lambda: tool.GetInput("Font"), "") or "")
    after_style = str(safe(lambda: tool.GetInput("Style"), "") or "")
    ok = after_font == family or (after_font and after_font != before_font)
    if style:
        ok = ok and (after_style == style or after_style != before_style)
    if ok:
        accepted += 1
        if len(samples) < 20:
            samples.append({{"candidate": candidate, "font": after_font, "style": after_style}})
    else:
        failures.append({{
            "candidate": candidate,
            "before_font": before_font,
            "before_style": before_style,
            "after_font": after_font,
            "after_style": after_style,
        }})

safe(lambda: tool.SetInput("Font", original_font), None)
if original_style not in (None, ""):
    safe(lambda: tool.SetInput("Style", original_style), None)
if original_text not in (None, ""):
    safe(lambda: tool.SetInput("StyledText", original_text), None)

checked = len(FONT_CANDIDATES)
pass_rate = (accepted / checked * 100.0) if checked else 0.0
print(json.dumps({{
    "ok": True,
    "message": "已在当前时间线 Text+ 上完成 Resolve 字体验收，并恢复原字体。",
    "timeline": safe(lambda: timeline.GetName(), ""),
    "clip": clip_name,
    "tool": tool_name,
    "track_index": track_index,
    "item_index": item_index,
    "checked": checked,
    "accepted": accepted,
    "failed": len(failures),
    "pass_rate": round(pass_rate, 2),
    "samples": samples,
    "failures": failures[:50],
}}, ensure_ascii=False))
''',
        timeout=max(60, min(240, args.limit * 2)),
    )
    if not result:
        report = {"ok": False, "message": "Resolve API 未返回结果。", "checked": 0, "accepted": 0, "failed": 0}
    else:
        report = result
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + "\n", encoding="utf-8")
    if not report.get("ok"):
        return 1
    checked = int(report.get("checked", 0) or 0)
    accepted = int(report.get("accepted", 0) or 0)
    pass_rate = (accepted / checked * 100.0) if checked else 0.0
    return 0 if pass_rate >= args.min_pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
