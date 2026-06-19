param(
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
