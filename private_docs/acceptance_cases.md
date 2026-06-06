# Qinghe BFD Private Acceptance Cases

This file is owner-only. It documents cases that future developers must pass before a release is accepted. Do not copy `private_docs/` into public release zips.

## Timeline And IO

- Active timeline FPS must be read from Resolve for every detection job. Test at 23.976, 24, 25, 29.97, 30, 50, and 60 fps.
- Timeline start timecode may be `00:00:00:00` or `01:00:00:00`; marker placement and jump must stay correct.
- If Resolve has IO points, video detection, audio detection, complex mode, text navigation, and result jumps must stay inside the IO range.
- If no IO points exist, the default detection range is the full active timeline.

## Mixed-Cut And One-Frame Insert

- A single uncut mixed-footage clip can contain multiple shots. The detector must identify internal cuts and compare them with visible timeline boundaries.
- A one-frame inserted shot inside an uncut clip must be detected without requiring the user to cut the clip manually.
- Compound/fusion-style or nested clips must be treated as possible mixed-cut sources when their visible output contains internal cuts.
- Complex mode can confirm the issue, but normal mode should at least flag mixed-cut risk and suggest complex mode when normal scan cannot prove the frame-level result.

## Complex Mode

- Complex mode renders/uses a cache with controlled bitrate and a user-visible cache directory.
- Complex mode returns all detected markers/results to the PySide UI.
- Cache files are deleted after successful completion unless the user selected a keep-cache/debug option.
- Bad-frame detection can depend on complex mode, but enabling that option must prompt or auto-enable complex mode clearly.

## Results And Navigation

- Results are sorted by timeline time.
- Every result row can be double-clicked to jump to the corresponding timeline time.
- Jump conversion must respect timeline start frame and start timecode.
- Empty or stale result rows must not require repeated clicking.

## Audio

- Mono source mapping, left-only content, right-only content, and true stereo are separate outcomes.
- Real stereo clips must not be marked as mono.
- If Resolve API cannot modify the channel mapping, the UI must remove the unsafe correction button or log the exact unsupported API path.
- Mono/problem audio clip color should be visually distinct from common marker colors.

## Text, SRT, And Text+

- Default scan checks SRT/subtitle tracks first.
- Optional scan checks Resolve text layers and Text+.
- Search highlights matching words in each row and shows match count.
- Replace modifies only the selected row/item unless the user explicitly chooses batch replace.
- Deleting text must target the selected row/item and preserve other rows.

## Installation

- One-click install must copy the Lua script to `Scripts/Edit`, modules to `Scripts/Modules/black_frame_detector`, and create/update the PySide shortcut.
- Manual install instructions must explain the same file destinations in plain Chinese.
- Closing DaVinci Resolve should close the launched PySide panel.
