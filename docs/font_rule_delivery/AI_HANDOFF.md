# Font Rule Delivery Handoff

This handoff is for the next AI/operator. Do not continue bulk testing until the safety checks below are understood.

## Current Status

- Project root: `C:\Users\24724\Documents\清何黑帧检测ui优化和加密`
- Delivery package directory: `docs/font_rule_delivery`
- Current delivery version: `23`
- Last relevant commits:
  - `7a50b96 Make font probe timeline restore robust`
  - `ebd5639 Restore Resolve context after font probes`
  - `e5a0929 Avoid intrusive font probe rendering`
  - `1df05b4 Protect verified font rule checkpoints`
- No `font_probe_rules.py` process was running at handoff.

## Verified Counts At Handoff

Command:

```powershell
python tools\font_probe_rules.py --validate-results artifacts\font_probe_reports\visual_6000_recheck_v14.jsonl
```

Latest result:

```json
{
  "ok": true,
  "raw_records": 2308,
  "total_records": 2264,
  "ok_records": 2243,
  "rule_records": 2092,
  "visual_valid_rules": 2092,
  "visual_invalid_rules": 0,
  "skipped": {
    "<urlopen error [WinError 10054] 远程主机强迫关闭了一个现有的连接。>": 2,
    "<urlopen error [WinError 10053] 你的主机中的软件中止了一个已建立的连接。>": 19
  }
}
```

Delivery package validation:

```powershell
python docs\font_rule_delivery\validate_font_rule_delivery.py
```

Latest result:

```json
{
  "basic_rules": 2809,
  "unique_keys": 2809,
  "fallback_rules": 6,
  "bad_rules": 0,
  "bad_samples": []
}
```

Important distinction:

- `docs/font_rule_delivery/basic_font_rules.json` contains 2809 rule entries from the delivery source.
- `artifacts/font_probe_reports/visual_6000_recheck_v14.jsonl` has 2092 currently rechecked Resolve Text+ visual-valid rules.
- The full objective is not complete until all required rules are verified with reliable Resolve Text+ visual evidence, or an explicit reduced scope is accepted by the user.

## Key Files

- Main probe script: `tools/font_probe_rules.py`
- Delivery copy of probe script: `docs/font_rule_delivery/font_probe_rules.py`
- Delivery builder: `tools/build_font_rule_delivery.py`
- Delivery validator: `docs/font_rule_delivery/validate_font_rule_delivery.py`
- Basic rules: `docs/font_rule_delivery/basic_font_rules.json`
- Fallback rules: `docs/font_rule_delivery/fallback_probe_rules.json`
- Source manifest: `docs/font_rule_delivery/source_manifest.json`
- Main original rules/results source:
  - `artifacts/font_probe_reports/visual_6000.jsonl`
  - `artifacts/font_probe_reports/visual_6000_rules.json`
- Current recheck output:
  - `artifacts/font_probe_reports/visual_6000_recheck_v14.jsonl`
  - `artifacts/font_probe_reports/visual_6000_recheck_v14_rules.json`
- Smoke outputs:
  - `artifacts/font_probe_reports/visual_probe_smoke_v22.jsonl`
  - `artifacts/font_probe_reports/visual_probe_restore_v23.jsonl`

Artifacts under `artifacts/` are not committed.

## Resolve Test Environment

Known timeline setup:

- User working timeline: `06234`
- Probe timeline: `QH_FontProbe_Temp`
- Probe target used during testing:
  - `--timeline-index 7`
  - `--track-index 1`
  - `--item-index 5`
  - `--timecode 01:00:19:07`

The old probe implementation damaged the Resolve viewer state by using Fusion `comp.Render()` and a `Saver`. That has been fixed.

Current safety expectations:

- `tools/font_probe_rules.py` and `docs/font_rule_delivery/font_probe_rules.py` must not contain `comp.Render()`.
- Probe should use `project.ExportCurrentFrameAsStill(...)`.
- Probe must not create or leave `QHProbeSaver`.
- Probe must reconnect/keep `MediaOut1.Input -> QHProbeMerge`.
- After each run, Resolve should return to the original timeline, normally `06234`.

Last confirmed safety check after fixes:

```json
{
  "current_timeline": "06234",
  "target_timeline": "QH_FontProbe_Temp",
  "mediaout_input": "QHProbeMerge",
  "has_saver": false,
  "tool_count": 6
}
```

## Critical Warnings

Do not claim "all 2809 are visually verified" based only on `basic_font_rules.json`.

The user explicitly caught these issues:

- `Font Not Found` can appear even when Text+ accepts a font name.
- Chinese tofu/box glyphs are invalid for CJK font verification.
- The visible Resolve viewer state matters; script JSON alone is not enough.
- The old test polluted the Resolve UI and left `MediaOut1` disconnected.

Therefore a valid rule needs all of this evidence:

- Text+ accepts the mapped `Font` and `Style`.
- Exported/current visual frame is not a Resolve error frame.
- Mixed Chinese/English sample renders visibly.
- CJK glyphs are not tofu boxes.
- No `Font Not Found` frame.
- Probe restores the user's original timeline.
- Probe leaves no Saver or broken MediaOut.

## Commands Used For Safe Verification

One-rule smoke test, separate output, does not touch main results:

```powershell
Remove-Item artifacts\font_probe_reports\visual_probe_restore_v23.jsonl,artifacts\font_probe_reports\visual_probe_restore_v23_rules.json -ErrorAction SilentlyContinue
python docs\font_rule_delivery\font_probe_rules.py --recheck-results artifacts\font_probe_reports\visual_6000.jsonl --visual --rules-require-visual --output artifacts\font_probe_reports\visual_probe_restore_v23.jsonl --rules-output artifacts\font_probe_reports\visual_probe_restore_v23_rules.json --timeline-index 7 --track-index 1 --item-index 5 --timecode 01:00:19:07 --keep-visual-png --keep-temp --resolve-preflight-timeout 60 --resume --limit 1 --download-retries 1 --download-retry-base-delay 0.5 --delay 0
python tools\font_probe_rules.py --validate-results artifacts\font_probe_reports\visual_probe_restore_v23.jsonl
```

Main small-batch recheck command used after safety fix:

```powershell
python docs\font_rule_delivery\font_probe_rules.py --recheck-results artifacts\font_probe_reports\visual_6000.jsonl --visual --rules-require-visual --output artifacts\font_probe_reports\visual_6000_recheck_v14.jsonl --rules-output artifacts\font_probe_reports\visual_6000_recheck_v14_rules.json --timeline-index 7 --track-index 1 --item-index 5 --timecode 01:00:19:07 --keep-visual-png --keep-temp --resolve-preflight-timeout 60 --resume --limit 80 --download-retries 1 --download-retry-base-delay 0.5 --delay 0.2 --skip-font-id 40722165767 --skip-font-id 31856238106 --skip-font-id 43254106857 --skip-font-id 31844737039
```

Known temporarily skipped font IDs:

- `40722165767`
- `31856238106`
- `43254106857`
- `31844737039`

They were skipped to keep the main queue moving after hangs or repeated stalls. They are not proven invalid.

## What To Do Next

Recommended next AI workflow:

1. Do not run bulk tests immediately.
2. Confirm no probe process is running:

   ```powershell
   Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*font_probe_rules.py*' }
   ```

3. Confirm code still has no intrusive render path:

   ```powershell
   rg -n "comp\.Render\(|QHProbeSaver|reg == \"Saver\"|ExportCurrentFrameAsStill|restore_context" tools\font_probe_rules.py docs\font_rule_delivery\font_probe_rules.py
   ```

4. Run only a 1-rule smoke test first.
5. Verify current timeline restored to `06234`.
6. Verify probe comp has `MediaOut1.Input -> QHProbeMerge` and no Saver.
7. Only then continue small batches, preferably 50-100 at a time.
8. After each batch, run:

   ```powershell
   python tools\font_probe_rules.py --validate-results artifacts\font_probe_reports\visual_6000_recheck_v14.jsonl
   ```

9. Stop immediately if Resolve UI shows `No frame available for MediaOut1`, `Render completed`, `Font Not Found`, or user timeline is not restored.

## Git / Worktree Notes

Tracked code/docs were clean after the last handoff commit except unrelated untracked files already present in the workspace.

Known untracked items include installer/provenance files, `ffmpeg/`, `modules/`, and `tools/windsurf-assistant`. Do not delete or revert them unless the user explicitly asks.

## Current User Preference

The user explicitly said to stop testing and provide handoff. Do not resume testing unless the user asks.
