# Font Probe Rule Standard

This document defines the strict test standard for Chinese font repair rules in
DaVinci Resolve Text+.

## Valid Rule

A rule counts only when all conditions are true:

1. The source font name does not work directly in Resolve Text+.
2. A corrected Resolve font name is discovered and `Font` readback matches it.
3. Resolve/Fusion renders the sample text to a PNG.
4. The PNG contains visible Chinese glyphs.
5. The PNG is not a tofu-box rendering:
   - `visual.visible` must be `true`.
   - `visual.pixel_stats.tofu_suspect` must be `false`.
   - `visual.pixel_stats.glyph_segments` must be at least `4`.

Fonts that already work without a correction do not count. Paid/commercial-only
download flows are skipped.

## Required Sample Text

The visual sample is:

```text
清 何 黑 帧 检 测
```

The script stores it as Unicode escapes so terminal encoding cannot corrupt it.

## Commands

Offline self-check:

```powershell
python tools\font_probe_rules.py --self-check
python -m unittest tools.test_font_probe_rules
```

Resolve scripting preflight:

```powershell
python tools\font_probe_rules.py --check-resolve --resolve-preflight-timeout 20
```

Strict batch target for 1000 visual rules:

```powershell
python tools\font_probe_rules.py `
  --limit 5000 `
  --resume `
  --visual `
  --target-rules 1000 `
  --rules-require-visual `
  --output artifacts\font_probe_reports\visual_1000.jsonl `
  --rules-output artifacts\font_probe_reports\visual_1000_rules.json `
  --timeline-index 7 `
  --track-index 1 `
  --item-index 5 `
  --timecode 01:00:19:07 `
  --keep-visual-png
```

One-command runner with self-checks, unit tests, Resolve preflight, strict batch,
and final validation:

```powershell
powershell -ExecutionPolicy Bypass -File tools\run_font_probe_1000.ps1 `
  -TimelineIndex 7 `
  -TrackIndex 1 `
  -ItemIndex 5 `
  -Timecode 01:00:19:07 `
  -KeepVisualPng
```

Validate any JSONL result file:

```powershell
python tools\font_probe_rules.py --validate-results artifacts\font_probe_reports\visual_1000.jsonl
```

Completion requires `visual_valid_rules >= 1000` from `--validate-results` and a
rules JSON generated with `--rules-require-visual` or `--target-rules`.

## Current Known Gate

Resolve must be unlocked, in the main application UI, and external scripting
must return both `Resolve` and `Fusion` objects. If the machine is locked or
Resolve is only at Project Manager, `--check-resolve` fails and the batch must
not be counted.
