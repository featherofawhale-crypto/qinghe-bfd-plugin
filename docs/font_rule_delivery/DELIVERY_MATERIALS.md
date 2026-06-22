# Font Rule Delivery Materials

This document is the complete handoff index for the font-rule delivery work.
Use it together with `AI_HANDOFF.md`.

## 1. Delivery Package

All committed delivery files are under:

`docs/font_rule_delivery/`

### Rule Files

| File | Status | Purpose |
| --- | --- | --- |
| `basic_font_rules.json` | Committed, version 24 | Main per-font mapping rules. Contains 2809 entries. |
| `fallback_probe_rules.json` | Committed, version 24 | General fallback candidate-generation rules. Contains 6 entries. |
| `source_manifest.json` | Committed, version 24 | Records source result files, rule counts, validation counts, and generation metadata. |

### Scripts In The Delivery Package

| File | Status | Purpose |
| --- | --- | --- |
| `font_probe_rules.py` | Committed | Full Resolve/Text+ probe and visual verification script copied from `tools/font_probe_rules.py`. |
| `validate_font_rule_delivery.py` | Committed | Offline validator for delivery JSON rule shape and duplicate keys. |
| `run_strict_font_probe.ps1` | Committed | PowerShell runner template for strict visual probing. |

### Documentation In The Delivery Package

| File | Status | Purpose |
| --- | --- | --- |
| `README.md` | Committed | User-facing delivery summary and basic usage. |
| `AI_HANDOFF.md` | Committed | Operator/AI handoff: current state, warnings, exact commands, and stop conditions. |
| `DELIVERY_MATERIALS.md` | Committed | This complete material index. |
| `delivery_materials_manifest.json` | Committed | Machine-readable material index for another AI. |

## 2. Source/Developer Scripts

These are outside the delivery directory but are part of the handoff.

| File | Status | Purpose |
| --- | --- | --- |
| `tools/font_probe_rules.py` | Committed | Source version of the probe script. Edit this first, then rebuild delivery. |
| `tools/build_font_rule_delivery.py` | Committed | Rebuilds `docs/font_rule_delivery/` from source artifacts. Current delivery version is 24. |
| `tools/test_font_probe_rules.py` | Committed | Unit tests for font visual-rule logic, result validation, and delivery rule validation. |
| `tools/font_probe_rules_spec.md` | Committed | Older technical spec for probe workflow; useful context but less current than this handoff. |
| `tools/run_font_probe_1000.ps1` | Committed | Older 1000-rule runner; useful as reference only. Prefer explicit commands in `AI_HANDOFF.md`. |
| `tools/test_resolve_api_bridge.ps1` | Committed | Resolve API bridge test script, not specific to font rules. |

## 3. Runtime Evidence Artifacts

These files are under `artifacts/font_probe_reports/`. They are not committed, but they are critical current-state evidence.

| File/Folder | Status | Purpose |
| --- | --- | --- |
| `visual_6000.jsonl` | Local artifact | Original source results used to build the 2809 delivery rules. |
| `visual_6000_rules.json` | Local artifact | Original source rules used by the delivery builder. |
| `visual_6000_recheck_v14.jsonl` | Local artifact | Current active strict visual recheck output. At handoff: 2092 visual-valid rules, 0 visual-invalid rules. |
| `visual_6000_recheck_v14_rules.json` | Local artifact | Strict visual rule output generated from the recheck JSONL. At handoff: 2090-2000+ rule entries depending on latest write/validation path; use `--validate-results` as authority. |
| `visual_probe_smoke_v22.jsonl` | Local artifact | One-rule smoke test after removing intrusive render path. |
| `visual_probe_restore_v23.jsonl` | Local artifact | One-rule smoke test proving timeline restore and MediaOut safety after restore fix. |
| `visual/` | Local artifact folder | Exported PNG evidence frames for visual probe runs. |
| `recheck_v14_batch*.log` | Local artifact logs | Historical batch logs. Useful for timeline of progress and network failures. |

Important: `artifacts/` is not the committed delivery package. It is local evidence. Do not delete it unless the user explicitly asks.

## 4. Current Verified Counts

Delivery package validator:

```powershell
python docs\font_rule_delivery\validate_font_rule_delivery.py
```

Expected current output:

```json
{
  "basic_rules": 2809,
  "unique_keys": 2809,
  "fallback_rules": 6,
  "bad_rules": 0,
  "bad_samples": []
}
```

Strict visual recheck validator:

```powershell
python tools\font_probe_rules.py --validate-results artifacts\font_probe_reports\visual_6000_recheck_v14.jsonl
```

Expected current output at handoff:

```json
{
  "ok": true,
  "raw_records": 2308,
  "total_records": 2264,
  "ok_records": 2243,
  "rule_records": 2092,
  "visual_valid_rules": 2092,
  "visual_invalid_rules": 0
}
```

Network skips currently observed:

- WinError 10054: 2 records
- WinError 10053: 19 records

## 5. What Counts As Valid Visual Evidence

A rule is not considered visually proven only because it exists in `basic_font_rules.json`.

A visually proven rule must have all of these:

- Resolve Text+ accepts the candidate font and style.
- Exported visual frame exists.
- Exported frame is not a Resolve error frame.
- Exported frame does not show `Font Not Found`.
- Mixed Chinese/English sample is visible.
- CJK glyphs are not tofu boxes.
- `visual_result_is_usable(...)` returns usable evidence.
- Probe leaves `MediaOut1.Input` connected.
- Probe leaves no `QHProbeSaver`.
- Probe restores the user's original timeline, normally `06234`.

## 6. Known Unsafe Old Behavior Already Fixed

Do not reintroduce these:

- `comp.Render()`
- `QHProbeSaver`
- Deleting generic `Saver` tools
- Leaving Resolve on `QH_FontProbe_Temp`
- Leaving `MediaOut1.Input` empty

Current source scripts should show:

- No `comp.Render()`
- No `QHProbeSaver`
- `ExportCurrentFrameAsStill(...)`
- `restore_context()`

Check with:

```powershell
rg -n "comp\.Render\(|QHProbeSaver|reg == \"Saver\"|ExportCurrentFrameAsStill|restore_context" tools\font_probe_rules.py docs\font_rule_delivery\font_probe_rules.py
```

## 7. Safe Smoke Test

Run this before any future batch:

```powershell
Remove-Item artifacts\font_probe_reports\visual_probe_restore_v23.jsonl,artifacts\font_probe_reports\visual_probe_restore_v23_rules.json -ErrorAction SilentlyContinue
python docs\font_rule_delivery\font_probe_rules.py --recheck-results artifacts\font_probe_reports\visual_6000.jsonl --visual --rules-require-visual --output artifacts\font_probe_reports\visual_probe_restore_v23.jsonl --rules-output artifacts\font_probe_reports\visual_probe_restore_v23_rules.json --timeline-index 7 --track-index 1 --item-index 5 --timecode 01:00:19:07 --keep-visual-png --keep-temp --resolve-preflight-timeout 60 --resume --limit 1 --download-retries 1 --download-retry-base-delay 0.5 --delay 0
python tools\font_probe_rules.py --validate-results artifacts\font_probe_reports\visual_probe_restore_v23.jsonl
```

After smoke, verify Resolve still returns to `06234` and the probe comp still has:

- `MediaOut1.Input -> QHProbeMerge`
- `has_saver: false`

## 8. Safe Batch Command

Only continue if the user explicitly asks to continue testing.

```powershell
python docs\font_rule_delivery\font_probe_rules.py --recheck-results artifacts\font_probe_reports\visual_6000.jsonl --visual --rules-require-visual --output artifacts\font_probe_reports\visual_6000_recheck_v14.jsonl --rules-output artifacts\font_probe_reports\visual_6000_recheck_v14_rules.json --timeline-index 7 --track-index 1 --item-index 5 --timecode 01:00:19:07 --keep-visual-png --keep-temp --resolve-preflight-timeout 60 --resume --limit 50 --download-retries 1 --download-retry-base-delay 0.5 --delay 0.2 --skip-font-id 40722165767 --skip-font-id 31856238106 --skip-font-id 43254106857 --skip-font-id 31844737039
```

Known temporary skip IDs:

- `40722165767`
- `31856238106`
- `43254106857`
- `31844737039`

They are skipped for hangs/stalls, not because they were proven invalid.

## 9. Stop Conditions

Stop immediately if any of these happen:

- User says stop.
- Resolve shows `Render completed`.
- Resolve shows `No frame available for MediaOut1`.
- Resolve shows `Font Not Found`.
- User timeline is not restored to `06234`.
- `visual_invalid_rules` becomes non-zero.
- `QHProbeSaver` appears again.
- `MediaOut1.Input` is empty.

## 10. Git State At Handoff

Last intended handoff commit before this materials index:

- `edfb767 Add font rule handoff notes`

This material index should be committed in a later commit.

Untracked files such as installer files, `ffmpeg/`, `modules/`, and `tools/windsurf-assistant` were present before this handoff and were not touched.
