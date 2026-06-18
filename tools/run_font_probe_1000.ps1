param(
    [int]$Limit = 5000,
    [int]$TargetRules = 1000,
    [int]$ResolvePreflightTimeout = 20,
    [string]$Output = "artifacts\font_probe_reports\visual_1000.jsonl",
    [string]$RulesOutput = "artifacts\font_probe_reports\visual_1000_rules.json",
    [switch]$KeepVisualPng
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Title,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host "== $Title =="
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Title failed with exit code $LASTEXITCODE"
    }
}

Invoke-Step "Offline self-check" {
    python tools\font_probe_rules.py --self-check
}

Invoke-Step "Unit tests" {
    python -m unittest tools.test_font_probe_rules
}

Invoke-Step "Resolve/Fusion preflight" {
    python tools\font_probe_rules.py --check-resolve --resolve-preflight-timeout $ResolvePreflightTimeout
}

$argsList = @(
    "tools\font_probe_rules.py",
    "--limit", "$Limit",
    "--resume",
    "--visual",
    "--target-rules", "$TargetRules",
    "--rules-require-visual",
    "--output", $Output,
    "--rules-output", $RulesOutput,
    "--resolve-preflight-timeout", "$ResolvePreflightTimeout"
)

if ($KeepVisualPng) {
    $argsList += "--keep-visual-png"
}

Invoke-Step "Strict visual font probe" {
    python @argsList
}

Invoke-Step "Strict result validation" {
    python tools\font_probe_rules.py --validate-results $Output
}

Write-Host ""
Write-Host "Rules output: $RulesOutput"
