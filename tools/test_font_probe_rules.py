#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import struct
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font_probe_rules as probe
import build_font_rule_delivery as delivery


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


def write_rgb_png(path: Path, width: int, height: int, pixels: list[tuple[int, int, int]]) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        payload = kind + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)

    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixels[y * width + x])
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw)))
        + chunk(b"IEND", b"")
    )


class FontProbeRuleTests(unittest.TestCase):
    def test_self_check_keeps_real_mixed_sample_text(self) -> None:
        result = probe.self_check()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["visual_sample_text"], "清何黑帧检测 QH123")

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
                    "non_white_pct": 8.5,
                },
            }
        )
        error_frame = result_record(
            visual={
                "visible": True,
                "pixel_stats": {
                    "tofu_suspect": False,
                    "error_frame_suspect": True,
                    "error_frame_reason": "non-white-background",
                    "glyph_segments": 6,
                    "non_white_pct": 98.0,
                },
            }
        )

        self.assertTrue(probe.is_visual_rule_result(valid))
        self.assertFalse(probe.is_visual_rule_result(no_visual))
        self.assertFalse(probe.is_visual_rule_result(tofu))
        self.assertTrue(probe.is_visual_rule_result(too_few))
        self.assertFalse(probe.is_visual_rule_result(error_frame))

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
                            "non_white_pct": 8.5,
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

    def test_iter_rule_fonts_from_results_only_rechecks_existing_rule_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            results_path = Path(temp) / "results.jsonl"
            records = [
                {"font_id": "1", "source": "A", "detail_url": "https://example.test/a", "rule": {"source": "A"}},
                {"font_id": "2", "source": "B", "rule": None},
                {"font_id": "1", "source": "A duplicate", "rule": {"source": "A duplicate"}},
                {"font_id": "3", "source": "C", "rule": {"source": "C"}},
            ]
            results_path.write_text(
                "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n",
                encoding="utf-8",
            )

            fonts = list(probe.iter_rule_fonts_from_results(results_path))

        self.assertEqual([font.font_id for font in fonts], ["1", "3"])
        self.assertEqual(fonts[0].detail_url, "https://example.test/a")
        self.assertEqual(fonts[1].detail_url, "https://www.fonts.net.cn/font-3.html")

    def test_black_error_overlay_frame_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "font_not_found_like.png"
            pixels = [(0, 0, 0)] * (320 * 180)
            for y in range(150, 156):
                for x in range(60, 260):
                    pixels[y * 320 + x] = (255, 255, 255)
            write_rgb_png(path, 320, 180, pixels)

            stats = probe.png_nonblank_stats(path)

        self.assertTrue(stats["error_frame_suspect"], stats)
        self.assertEqual(stats["error_frame_reason"], "non-white-background")

    def test_visual_profile_uses_mixed_sample_with_script_specific_gate(self) -> None:
        cjk_profile = probe.visual_profile_for_font("段宁毛笔古韵体", {"families": ["DuanNing MaoBi GuYunTI"]})
        latin_profile = probe.visual_profile_for_font("Clean Sans", {"families": ["Clean Sans"]})

        self.assertEqual(cjk_profile["expected_script"], "cjk")
        self.assertEqual(cjk_profile["sample_text"], "清何黑帧检测 QH123")
        self.assertTrue(cjk_profile["require_tofu_check"])
        self.assertEqual(latin_profile["expected_script"], "latin")
        self.assertEqual(latin_profile["sample_text"], "清何黑帧检测 QH123")
        self.assertFalse(latin_profile["require_tofu_check"])

    def test_known_font_not_found_rule_is_blocked(self) -> None:
        rule = {
            "source": "段宁毛笔古韵体",
            "accepted": "DuanNing MaoBi GuYunTI",
            "accepted_candidate": "DuanNing MaoBi GuYunTI|||Regular",
            "style": "Regular",
            "proof": {
                "direct_before": False,
                "textplus_ok": True,
                "visual_ok": True,
                "visible": True,
                "glyph_segments": 6,
                "tofu_suspect": False,
            },
        }

        self.assertIn("Font Not Found", delivery.blocked_rule_reason(rule))
        validation = delivery.validate_basic_rules([rule])
        self.assertEqual(validation["bad_rules"], 1)

    def test_visual_candidate_selection_tries_next_candidate_after_font_not_found_frame(self) -> None:
        calls: list[tuple[str, str]] = []

        def fake_visual_runner(font: str, style: str, _font_path: Path, _args: object, _font_id: str, **_kwargs) -> dict:
            calls.append((font, style))
            if font == "Bad Family":
                return {
                    "ok": True,
                    "visible": False,
                    "pixel_stats": {
                        "error_frame_suspect": True,
                        "error_frame_reason": "font not found",
                        "glyph_segments": 6,
                    },
                }
            return {
                "ok": True,
                "visible": True,
                "font": font,
                "style": style,
                "pixel_stats": {
                    "tofu_suspect": False,
                    "error_frame_suspect": False,
                    "glyph_segments": 6,
                    "non_white_pct": 8.5,
                },
            }

        selected = probe.select_visual_candidate(
            {
                "accepted": "Bad Family",
                "style": "Regular",
                "textplus_candidates": [
                    {"accepted": "Bad Family", "style": "Regular", "textplus_ok": True},
                    {"accepted": "GoodPSName", "style": "Regular", "textplus_ok": True},
                ],
            },
            Path("font.ttf"),
            object(),
            "case",
            profile={
                "expected_script": "cjk",
                "sample_text": "清何黑帧检测 QH123",
                "require_tofu_check": True,
            },
            visual_runner=fake_visual_runner,
        )

        self.assertEqual(selected["accepted"], "GoodPSName")
        self.assertEqual(calls, [("Bad Family", "Regular"), ("GoodPSName", "Regular")])
        self.assertEqual(len(selected["rejected_visual_candidates"]), 1)


if __name__ == "__main__":
    unittest.main()
