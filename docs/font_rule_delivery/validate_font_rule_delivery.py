#!/usr/bin/env python3
import json
from pathlib import Path

root = Path(__file__).resolve().parent
basic = json.loads((root / "basic_font_rules.json").read_text(encoding="utf-8"))
fallback = json.loads((root / "fallback_probe_rules.json").read_text(encoding="utf-8"))
rules = basic.get("rules", [])
bad = []
keys = set()
for index, rule in enumerate(rules):
    key = (str(rule.get("source") or ""), str(rule.get("accepted_candidate") or ""))
    keys.add(key)
    proof = rule.get("proof") if isinstance(rule.get("proof"), dict) else {}
    if (
        proof.get("direct_before") is True
        or not proof.get("textplus_ok")
        or not proof.get("visual_ok")
        or not proof.get("visible")
        or proof.get("tofu_suspect") is True
        or int(proof.get("glyph_segments") or 0) < 4
        or str(rule.get("source") or "") == str(rule.get("accepted") or "")
    ):
        bad.append({"index": index, "source": rule.get("source"), "accepted": rule.get("accepted")})
result = {
    "basic_rules": len(rules),
    "unique_keys": len(keys),
    "fallback_rules": len(fallback.get("rules", [])),
    "bad_rules": len(bad),
    "bad_samples": bad[:10],
}
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if not bad and len(rules) == len(keys) and fallback.get("rules") else 1)
