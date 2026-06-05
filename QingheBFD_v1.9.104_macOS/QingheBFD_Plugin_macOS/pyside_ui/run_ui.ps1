$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$candidates = @()

$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
    $candidates += [pscustomobject]@{ Exe = $py.Source; Arg = "-3" }
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    $candidates += [pscustomobject]@{ Exe = $python.Source; Arg = "" }
}

$fallback = "C:\Users\24724\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (Test-Path $fallback) {
    $candidates += [pscustomobject]@{ Exe = $fallback; Arg = "" }
}

$selectedExe = $null
$selectedArg = ""
foreach ($candidate in $candidates) {
    $exe = $candidate.Exe
    $arg = $candidate.Arg
    try {
        if ($arg) { & $exe $arg -c "import sys; print(sys.version)" *> $null }
        else { & $exe -c "import sys; print(sys.version)" *> $null }
        if ($LASTEXITCODE -eq 0) {
            $selectedExe = $exe
            $selectedArg = $arg
            break
        }
    } catch {
    }
}

if (-not $selectedExe) {
    throw "No working Python interpreter was found."
}

if ($selectedArg) { & $selectedExe $selectedArg -c "import PySide6" *> $null }
else { & $selectedExe -c "import PySide6" *> $null }
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PySide6..."
    if ($selectedArg) { & $selectedExe $selectedArg -m pip install -r requirements.txt }
    else { & $selectedExe -m pip install -r requirements.txt }
}

if ($selectedArg) { & $selectedExe $selectedArg app.py }
else { & $selectedExe app.py }
