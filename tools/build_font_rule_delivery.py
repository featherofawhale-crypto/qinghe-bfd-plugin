#!/usr/bin/env python3
"""
Build a deliverable folder for Qinghe font probe rules.

The output separates two layers:
- basic_font_rules.json: verified per-font mappings from source display names
  to Resolve/Text+ accepted names.
- fallback_probe_rules.json: generalized candidate-generation rules derived from
  the verified probe dataset for cases not covered by direct mappings.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ROOT / "artifacts" / "font_probe_reports" / "visual_1000.jsonl"
DEFAULT_RULES = ROOT / "artifacts" / "font_probe_reports" / "visual_1000_rules.json"
DEFAULT_OUT = ROOT / "docs" / "font_rule_delivery"
DELIVERY_VERSION = 4

BLOCKED_FONT_NOT_FOUND_RULES: dict[tuple[str, str], str] = {
    (
        "段宁毛笔古韵体",
        "DuanNing MaoBi GuYunTI|||Regular",
    ): "Resolve Text+ shows Font Not Found for DuanNing MaoBi GuYunTI Regular in live UI.",
}


def has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", str(text or "")))


def ascii_only(text: str) -> bool:
    value = str(text or "")
    return bool(value) and all(ord(ch) < 128 for ch in value)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def normalize_rule(rule: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    visual = record.get("visual") if isinstance(record.get("visual"), dict) else {}
    stats = visual.get("pixel_stats") if isinstance(visual.get("pixel_stats"), dict) else {}
    probe = record.get("probe") if isinstance(record.get("probe"), dict) else {}
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    source = str(rule.get("source") or "")
    accepted = str(rule.get("accepted") or "")
    accepted_candidate = str(rule.get("accepted_candidate") or "")
    return {
        "type": "basic_mapping",
        "source": source,
        "accepted": accepted,
        "accepted_candidate": accepted_candidate,
        "actual_font": str(rule.get("actual_font") or accepted),
        "style": str(probe.get("style") or "Regular"),
        "registered_font_file": str(rule.get("registered_font_file") or ""),
        "registered_font_name": str(rule.get("registered_font_name") or accepted),
        "candidate_attempts": int(rule.get("candidate_attempts") or 0),
        "proof": {
            "direct_before": bool(probe.get("direct_before")),
            "textplus_ok": bool(probe.get("textplus_ok")),
            "textplus_font": str(probe.get("textplus_font") or ""),
            "visual_ok": bool(visual.get("ok")),
            "visible": bool(visual.get("visible")),
            "glyph_segments": int(stats.get("glyph_segments") or 0),
            "tofu_suspect": bool(stats.get("tofu_suspect")),
            "error_frame_suspect": bool(stats.get("error_frame_suspect", False)),
            "error_frame_reason": str(stats.get("error_frame_reason") or ""),
            "near_white_pct": float(stats.get("near_white_pct", 100.0)),
            "non_white_pct": float(stats.get("non_white_pct", 0.0)),
            "very_dark_pct": float(stats.get("very_dark_pct", 0.0)),
        },
        "metadata": {
            "families": metadata.get("families") if isinstance(metadata.get("families"), list) else [],
            "full_names": metadata.get("full_names") if isinstance(metadata.get("full_names"), list) else [],
            "postscript_names": metadata.get("postscript_names") if isinstance(metadata.get("postscript_names"), list) else [],
            "styles": metadata.get("styles") if isinstance(metadata.get("styles"), list) else [],
        },
    }


def blocked_rule_reason(rule: dict[str, Any]) -> str:
    source = str(rule.get("source") or "")
    accepted_candidate = str(rule.get("accepted_candidate") or "")
    accepted = str(rule.get("accepted") or "")
    style = str(rule.get("style") or "Regular")
    candidates = [
        (source, accepted_candidate),
        (source, f"{accepted}|||{style}"),
    ]
    for key in candidates:
        reason = BLOCKED_FONT_NOT_FOUND_RULES.get(key)
        if reason:
            return reason
    return ""


def classify_mapping(rule: dict[str, Any]) -> str:
    source = str(rule.get("source") or "")
    accepted = str(rule.get("accepted") or "")
    metadata = rule.get("metadata") if isinstance(rule.get("metadata"), dict) else {}
    families = [str(value) for value in metadata.get("families", [])]
    full_names = [str(value) for value in metadata.get("full_names", [])]
    postscript_names = [str(value) for value in metadata.get("postscript_names", [])]
    if accepted in postscript_names:
        return "postscript_name"
    if accepted in families and ascii_only(accepted):
        return "ascii_family_name"
    if accepted in full_names and ascii_only(accepted):
        return "ascii_full_name"
    if has_cjk(source) and ascii_only(accepted):
        return "cjk_source_to_ascii_resolve_name"
    if "|||" in str(rule.get("accepted_candidate") or ""):
        return "packed_family_style"
    return "other"


def build_fallback_rules(basic_rules: list[dict[str, Any]]) -> dict[str, Any]:
    classes = Counter(classify_mapping(rule) for rule in basic_rules)
    source_cjk = sum(has_cjk(str(rule.get("source") or "")) for rule in basic_rules)
    accepted_ascii = sum(ascii_only(str(rule.get("accepted") or "")) for rule in basic_rules)
    return {
        "version": DELIVERY_VERSION,
        "purpose": "Fallback probe rules for fonts not covered by exact basic mappings.",
        "summary": {
            "sample_rules": len(basic_rules),
            "source_has_cjk": source_cjk,
            "accepted_ascii_only": accepted_ascii,
            "pattern_counts": dict(classes),
        },
        "rules": [
            {
                "id": "F001_exact_mapping_first",
                "priority": 10,
                "when": "The selected font source matches a basic mapping source key.",
                "generate_candidates": ["accepted_candidate", "accepted"],
                "success_gate": "Resolve Text+ SetInput('Font') succeeds and GetInput('Font') reads back the accepted family.",
            },
            {
                "id": "F010_postscript_name_after_cjk_failure",
                "priority": 20,
                "when": "The source name contains CJK and direct Resolve/Fusion lookup fails.",
                "generate_candidates": [
                    "font name table nameID=6 PostScript name",
                    "ASCII family name",
                    "ASCII full name without style suffix",
                ],
                "evidence": f"{classes.get('postscript_name', 0)} verified mappings accepted a PostScript name.",
                "success_gate": "Text+ readback font equals candidate and visual render has >=4 glyph segments with tofu_suspect=false.",
            },
            {
                "id": "F020_ascii_family_from_fontmanager",
                "priority": 30,
                "when": "FontManager.AddFont(path, name) succeeds but the CJK display name is not listed as an available family.",
                "generate_candidates": [
                    "FontManager family resolved from the font file basename",
                    "first ASCII family returned by the font name table",
                    "first ASCII full name returned by the font name table",
                ],
                "evidence": f"{classes.get('ascii_family_name', 0)} verified mappings accepted an ASCII family name.",
                "success_gate": "Fusion FontManager reports candidate available or Text+ readback changes from previous font.",
            },
            {
                "id": "F030_pack_family_style",
                "priority": 40,
                "when": "The selected font name includes a style suffix or the font metadata exposes styles.",
                "generate_candidates": [
                    "family|||metadata style",
                    "PostScript family|||Regular",
                    "ASCII family|||Regular",
                    "ASCII full name|||Regular",
                ],
                "success_gate": "Text+ Font and Style readback match the packed candidate.",
            },
            {
                "id": "F040_register_file_backed_candidate",
                "priority": 50,
                "when": "A local font file path is known but no generated name is in the current Fusion font list.",
                "generate_candidates": [
                    "candidate|||style|||font_file_path",
                    "FontManager.AddFont(font_file_path, candidate)",
                    "FontManager.AddFont(font_file_path)",
                ],
                "success_gate": "AddFont returns true, then Text+ accepts the resolved FontManager family.",
            },
            {
                "id": "F090_reject_direct_success_as_rule",
                "priority": 90,
                "when": "The original source name already works directly.",
                "action": "Do not count it as a repair rule.",
                "success_gate": "direct_before must be false and accepted must differ from source for rule counting.",
            },
        ],
    }


def validate_basic_rules(basic_rules: list[dict[str, Any]]) -> dict[str, Any]:
    bad: list[dict[str, Any]] = []
    keys: set[tuple[str, str]] = set()
    for index, rule in enumerate(basic_rules):
        key = (str(rule.get("source") or ""), str(rule.get("accepted_candidate") or ""))
        keys.add(key)
        proof = rule.get("proof") if isinstance(rule.get("proof"), dict) else {}
        block_reason = blocked_rule_reason(rule)
        if (
            block_reason
            or "font not found" in str(proof.get("error_frame_reason") or "").lower()
            or proof.get("direct_before") is True
            or not proof.get("textplus_ok")
            or not proof.get("visual_ok")
            or not proof.get("visible")
            or proof.get("tofu_suspect") is True
            or proof.get("error_frame_suspect") is True
            or float(proof.get("near_white_pct", 100.0)) < 50.0
            or float(proof.get("non_white_pct", 0.0)) > 15.0
            or float(proof.get("very_dark_pct", 0.0)) > 10.0
            or int(proof.get("glyph_segments") or 0) < 4
            or str(rule.get("source") or "") == str(rule.get("accepted") or "")
        ):
            bad.append(
                {
                    "index": index,
                    "source": rule.get("source"),
                    "accepted": rule.get("accepted"),
                    "block_reason": block_reason,
                    "proof": proof,
                }
            )
    return {
        "rules": len(basic_rules),
        "unique_keys": len(keys),
        "bad_rules": len(bad),
        "bad_samples": bad[:10],
    }


def write_text(path: Path, text: str) -> None:
    path.write_text(text.replace("\r\n", "\n"), encoding="utf-8")


def build_readme(out_dir: Path, basic_count: int, validation: dict[str, Any]) -> str:
    return f"""# 清何字体探针规则交付包

本目录是 DaVinci Resolve Text+ 字体切换的两层规则交付包。

## 两层规则

1. `basic_font_rules.json`
   - 基础字体映射规则。
   - 每条都是“原字体名直接失败”后，找到 Resolve/Text+ 真正接受的字体名。
   - 只有同时通过 Text+ 读回和 PNG 中文可视化验证，才会进入这里。

2. `fallback_probe_rules.json`
   - 兜底探测规则。
   - 当基础映射库没有命中时，用这些泛化规则继续生成候选名。
   - 这些规则来自已验证样本的归纳：PostScript 名、ASCII family、family/style 打包、FontManager 注册等。

## 当前验证结果

- 基础映射条数：`{basic_count}`
- 去重映射键：`{validation.get("unique_keys")}`
- 失败规则：`{validation.get("bad_rules")}`

## 规则成立标准

一条基础映射规则必须全部满足：

- `direct_before=false`
- `accepted != source`，不能把原本可直接切换的字体算作规则
- Resolve Text+ 接受修正候选名，并且读回匹配
- 渲染 PNG 可见真实中文
- `tofu_suspect=false`
- `error_frame_suspect=false`锛屼笉鑳芥槸 Resolve 鐨?`Font Not Found` 绛夐粦搴曢敊璇彁绀哄抚
- 鐢婚潰蹇呴』淇濇寔鐧藉簳瀛楀舰锛歯ear_white_pct>=50銆乶on_white_pct<=15銆乿ery_dark_pct<=10
- `glyph_segments>=4`

## 文件说明

- `basic_font_rules.json`：基础映射规则。
- `fallback_probe_rules.json`：兜底探测规则。
- `validate_font_rule_delivery.py`：验证本目录规则是否满足标准。
- `run_strict_font_probe.ps1`：继续采集严格视觉规则的脚本。
- `font_probe_rules.py`：完整测试脚本副本。
- `source_manifest.json`：生成来源和统计信息。
"""


def build_validator_script() -> str:
    return r'''#!/usr/bin/env python3
import json
from pathlib import Path

root = Path(__file__).resolve().parent
basic = json.loads((root / "basic_font_rules.json").read_text(encoding="utf-8"))
fallback = json.loads((root / "fallback_probe_rules.json").read_text(encoding="utf-8"))
rules = basic.get("rules", [])
blocked = {
    ("段宁毛笔古韵体", "DuanNing MaoBi GuYunTI|||Regular"): "Resolve Text+ shows Font Not Found for DuanNing MaoBi GuYunTI Regular in live UI.",
}
bad = []
keys = set()
for index, rule in enumerate(rules):
    key = (str(rule.get("source") or ""), str(rule.get("accepted_candidate") or ""))
    keys.add(key)
    proof = rule.get("proof") if isinstance(rule.get("proof"), dict) else {}
    block_reason = blocked.get(key, "")
    if (
        block_reason
        or "font not found" in str(proof.get("error_frame_reason") or "").lower()
        or proof.get("direct_before") is True
        or not proof.get("textplus_ok")
        or not proof.get("visual_ok")
        or not proof.get("visible")
        or proof.get("tofu_suspect") is True
        or proof.get("error_frame_suspect") is True
        or float(proof.get("near_white_pct", 100.0)) < 50.0
        or float(proof.get("non_white_pct", 0.0)) > 15.0
        or float(proof.get("very_dark_pct", 0.0)) > 10.0
        or int(proof.get("glyph_segments") or 0) < 4
        or str(rule.get("source") or "") == str(rule.get("accepted") or "")
    ):
        bad.append({"index": index, "source": rule.get("source"), "accepted": rule.get("accepted"), "block_reason": block_reason})
result = {
    "basic_rules": len(rules),
    "unique_keys": len(keys),
    "fallback_rules": len(fallback.get("rules", [])),
    "bad_rules": len(bad),
    "bad_samples": bad[:10],
}
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if not bad and len(rules) == len(keys) and fallback.get("rules") else 1)
'''


def build_probe_runner() -> str:
    return r'''param(
    [int]$TargetRules = 6000,
    [int]$Limit = 20000,
    [int]$StartPage = 1,
    [int]$TimelineIndex = 7,
    [int]$TrackIndex = 1,
    [int]$ItemIndex = 5,
    [string]$Timecode = "01:00:19:07",
    [string]$Output = "artifacts\font_probe_reports\visual_6000.jsonl",
    [string]$RulesOutput = "artifacts\font_probe_reports\visual_6000_rules.json"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

python tools\font_probe_rules.py `
  --limit $Limit `
  --start-page $StartPage `
  --resume `
  --visual `
  --target-rules $TargetRules `
  --rules-require-visual `
  --output $Output `
  --rules-output $RulesOutput `
  --timeline-index $TimelineIndex `
  --track-index $TrackIndex `
  --item-index $ItemIndex `
  --timecode $Timecode `
  --resolve-preflight-timeout 20 `
  --keep-visual-png

python tools\font_probe_rules.py --validate-results $Output
'''


def build_delivery(results_path: Path, rules_path: Path, out_dir: Path) -> dict[str, Any]:
    records = load_jsonl(results_path)
    source_rules = load_json(rules_path).get("rules", [])
    record_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        rule = record.get("rule") if isinstance(record.get("rule"), dict) else None
        if not rule:
            continue
        key = (str(rule.get("source") or ""), str(rule.get("accepted_candidate") or ""))
        record_by_key[key] = record

    basic_rules: list[dict[str, Any]] = []
    blocked_rules: list[dict[str, str]] = []
    for rule in source_rules:
        if not isinstance(rule, dict):
            continue
        key = (str(rule.get("source") or ""), str(rule.get("accepted_candidate") or ""))
        record = record_by_key.get(key)
        if not record:
            continue
        normalized = normalize_rule(rule, record)
        block_reason = blocked_rule_reason(normalized)
        if block_reason:
            blocked_rules.append(
                {
                    "source": str(normalized.get("source") or ""),
                    "accepted_candidate": str(normalized.get("accepted_candidate") or ""),
                    "reason": block_reason,
                }
            )
            continue
        basic_rules.append(normalized)

    validation = validate_basic_rules(basic_rules)
    fallback = build_fallback_rules(basic_rules)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": DELIVERY_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rules": basic_rules,
    }
    write_text(out_dir / "basic_font_rules.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    write_text(out_dir / "fallback_probe_rules.json", json.dumps(fallback, ensure_ascii=False, indent=2) + "\n")
    write_text(out_dir / "README.md", build_readme(out_dir, len(basic_rules), validation))
    write_text(out_dir / "validate_font_rule_delivery.py", build_validator_script())
    write_text(out_dir / "run_strict_font_probe.ps1", build_probe_runner())
    manifest = {
        "version": DELIVERY_VERSION,
        "generated_at": payload["generated_at"],
        "source_results": str(results_path),
        "source_rules": str(rules_path),
        "basic_rule_count": len(basic_rules),
        "fallback_rule_count": len(fallback["rules"]),
        "blocked_rule_count": len(blocked_rules),
        "blocked_rules": blocked_rules,
        "validation": validation,
    }
    write_text(out_dir / "source_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    source_script = ROOT / "tools" / "font_probe_rules.py"
    if source_script.exists():
        shutil.copy2(source_script, out_dir / "font_probe_rules.py")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Qinghe font rule delivery folder.")
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    manifest = build_delivery(args.results, args.rules, args.out)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if manifest["validation"]["bad_rules"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
