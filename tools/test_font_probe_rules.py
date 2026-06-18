#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font_probe_rules as probe


def result_record(*, visual: dict | None, needs_rule: bool = True) -> dict:
    return {
        "ok": True,
        "needs_rule": needs_rule,
        "rule": {
            "source": "测试字体",
            "accepted_candidate": "Fixed Font|||Regular",
        }
        if needs_rule
        else None,
        "visual": visual,
    }


class FontProbeRuleTests(unittest.TestCase):
    def test_self_check_keeps_real_cjk_sample_text(self) -> None:
        result = probe.self_check()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["visual_sample_text"], "清 何 黑 帧 检 测")

    def test_visual_rule_requires_real_visible_non_tofu_glyphs(self) -> None:
        valid = result_record(
            visual={
                "visible": True,
                "pixel_stats": {
                    "tofu_suspect": False,
                    "glyph_segments": 6,
                    "non_white_pct": 8.5,
                },
            }
        )
        no_visual = result_record(visual={"skipped": True})
        tofu = result_record(
            visual={
                "visible": True,
                "pixel_stats": {
                    "tofu_suspect": True,
                    "tofu_reason": "hollow-box-glyphs",
                    "glyph_segments": 6,
                },
            }
        )
        too_few = result_record(
            visual={
                "visible": True,
                "pixel_stats": {
                    "tofu_suspect": False,
                    "glyph_segments": 2,
                },
            }
        )

        self.assertTrue(probe.is_visual_rule_result(valid))
        self.assertFalse(probe.is_visual_rule_result(no_visual))
        self.assertFalse(probe.is_visual_rule_result(tofu))
        self.assertFalse(probe.is_visual_rule_result(too_few))

    def test_rules_output_can_require_visual_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            results_path = Path(temp) / "results.jsonl"
            rules_path = Path(temp) / "rules.json"
            records = [
                result_record(visual={"skipped": True}),
                result_record(
                    visual={
                        "visible": True,
                        "pixel_stats": {
                            "tofu_suspect": False,
                            "glyph_segments": 6,
                        },
                    }
                ),
            ]
            results_path.write_text(
                "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n",
                encoding="utf-8",
            )

            count = probe.write_rules_from_results(results_path, rules_path, require_visual=True)
            rules = json.loads(rules_path.read_text(encoding="utf-8"))

        self.assertEqual(count, 1)
        self.assertEqual(len(rules["rules"]), 1)


if __name__ == "__main__":
    unittest.main()
