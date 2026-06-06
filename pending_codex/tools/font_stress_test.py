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


def main() -> int:
    parser = argparse.ArgumentParser(description="Stress-test Qinghe BFD font name resolution.")
    parser.add_argument("--min-pass-rate", type=float, default=95.0)
    parser.add_argument("--json", type=Path, default=None, help="Optional report path.")
    parser.add_argument("--sample-limit", type=int, default=40)
    args = parser.parse_args()

    from PySide6.QtGui import QFontDatabase, QFontInfo
    from PySide6.QtWidgets import QApplication
    import app as pyside_app

    QApplication.instance() or QApplication([])
    window = pyside_app.MainWindow.__new__(pyside_app.MainWindow)
    window.font_aliases = {}
    window.font_family_styles = {}
    window.available_fonts = []
    pyside_app.MainWindow.load_available_fonts(window)

    checks: list[dict] = []
    for family in list(window.available_fonts):
        styles = list(window.font_family_styles.get(family, [])) or [""]
        for style in styles:
            display_name = f"{family} {style}".strip()
            candidates = pyside_app.MainWindow.font_candidates(window, display_name)
            first_candidate = candidates[0] if candidates else ""
            if "|||" in first_candidate:
                render_family, render_style = first_candidate.split("|||", 1)
            else:
                render_family = pyside_app.MainWindow.font_system_family(window, first_candidate or family)
                render_style = style

            font = (
                QFontDatabase.font(render_family, render_style, 24)
                if render_style
                else pyside_app.QFont(render_family, 24)
            )
            actual_family = str(QFontInfo(font).family() or "")
            known_names = pyside_app.MainWindow.font_known_names(window, display_name)
            ok = bool(candidates) and actual_family.casefold() in known_names
            checks.append(
                {
                    "ok": ok,
                    "display": display_name,
                    "family": family,
                    "style": style,
                    "first_candidate": first_candidate,
                    "actual_family": actual_family,
                    "candidates": candidates[:8],
                }
            )

    total = len(checks)
    ok_count = sum(1 for check in checks if check["ok"])
    failures = [check for check in checks if not check["ok"]]
    pass_rate = (ok_count / total * 100.0) if total else 0.0
    report = {
        "families": len(window.available_fonts),
        "style_checks": total,
        "ok": ok_count,
        "fail": len(failures),
        "pass_rate": round(pass_rate, 2),
        "chinese_families": sum(
            1 for family in window.available_fonts
            if pyside_app.MainWindow.font_language_tag(family) == "中"
        ),
        "failure_samples": failures[: max(0, args.sample_limit)],
    }

    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + "\n", encoding="utf-8")
    return 0 if pass_rate >= args.min_pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
