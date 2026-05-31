$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackageRoot = Get-ChildItem -Path $Root -Directory -Filter "*_Windows" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $PackageRoot) { throw "Cannot find package folder ending with _Windows." }

$SourceModules = Join-Path $PackageRoot.FullName "black_frame_detector"
$SourceMain = Get-ChildItem -Path $PackageRoot.FullName -File -Filter "*.lua" |
    Select-Object -First 1
$SourceFfmpeg = Join-Path $PackageRoot.FullName "ffmpeg\bin"

if (-not $SourceMain) { throw "Cannot find main Lua script in package folder." }
if (!(Test-Path $SourceModules)) { throw "Missing module folder: $SourceModules" }

$ScriptsRoot = Join-Path $env:APPDATA "Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts"
$EditDir = Join-Path $ScriptsRoot "Edit"
$ModulesDir = Join-Path $ScriptsRoot "Modules\black_frame_detector"
$BundledFfmpegDir = Join-Path $ModulesDir "ffmpeg\windows"
$BackupRoot = Join-Path $ModulesDir ("backup_" + (Get-Date -Format "yyyyMMdd_HHmmss"))

New-Item -ItemType Directory -Force -Path $EditDir, $ModulesDir, $BundledFfmpegDir | Out-Null

$ExistingMain = Join-Path $EditDir $SourceMain.Name
if (Test-Path $ExistingMain) {
    New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
    Copy-Item $ExistingMain (Join-Path $BackupRoot $SourceMain.Name) -Force
}

Get-ChildItem $ModulesDir -File -Filter "*.lua" -ErrorAction SilentlyContinue | ForEach-Object {
    New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
    Copy-Item $_.FullName (Join-Path $BackupRoot $_.Name) -Force
}

Copy-Item $SourceMain.FullName (Join-Path $EditDir $SourceMain.Name) -Force
Copy-Item (Join-Path $SourceModules "*.lua") $ModulesDir -Force

if (Test-Path $SourceFfmpeg) {
    Copy-Item (Join-Path $SourceFfmpeg "*.exe") $BundledFfmpegDir -Force
}

$RunUi = Join-Path $Root "pyside_ui\run_ui.bat"
if (Test-Path $RunUi) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $linkPath = Join-Path $desktop "Qinghe BFD Control.lnk"
    $wsh = New-Object -ComObject WScript.Shell
    $shortcut = $wsh.CreateShortcut($linkPath)
    $shortcut.TargetPath = $RunUi
    $shortcut.WorkingDirectory = Split-Path $RunUi -Parent
    $shortcut.Description = "Qinghe Black Frame Detector PySide6 Control"
    $shortcut.Save()
}

$pythonCandidates = @()
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) { $pythonCandidates += [pscustomobject]@{ Exe = $py.Source; Arg = "-3" } }
$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) { $pythonCandidates += [pscustomobject]@{ Exe = $python.Source; Arg = "" } }
$fallback = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (Test-Path $fallback) { $pythonCandidates += [pscustomobject]@{ Exe = $fallback; Arg = "" } }

$selectedExe = $null
$selectedArg = ""
foreach ($candidate in $pythonCandidates) {
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
    } catch {}
}

if ($selectedExe) {
    $requirements = Join-Path $Root "pyside_ui\requirements.txt"
    if (Test-Path $requirements) {
        if ($selectedArg) { & $selectedExe $selectedArg -c "import PySide6" *> $null }
        else { & $selectedExe -c "import PySide6" *> $null }
        if ($LASTEXITCODE -ne 0) {
            if ($selectedArg) { & $selectedExe $selectedArg -m pip install -r $requirements }
            else { & $selectedExe -m pip install -r $requirements }
        }
    }

    $builder = Join-Path $Root "tools\lua_bytecode_builder.py"
    $protectedDir = Join-Path $Root "dist\Modules\black_frame_detector"
    if (Test-Path $builder) {
        if ($selectedArg) {
            & $selectedExe $selectedArg $builder --modules-dir $SourceModules --out-dir $protectedDir --core black_frame_analyzer.lua duplicate_detector.lua --compiler auto
        } else {
            & $selectedExe $builder --modules-dir $SourceModules --out-dir $protectedDir --core black_frame_analyzer.lua duplicate_detector.lua --compiler auto
        }
        if ($LASTEXITCODE -eq 0 -and (Test-Path $protectedDir)) {
            Copy-Item (Join-Path $protectedDir "black_frame_analyzer.lua") $ModulesDir -Force
            Copy-Item (Join-Path $protectedDir "duplicate_detector.lua") $ModulesDir -Force
            Copy-Item (Join-Path $protectedDir "bytecode_manifest.json") $ModulesDir -Force
        } else {
            Write-Host "Warning: protected bytecode build failed; source modules remain installed."
        }
    }
}

Write-Host "Installed Resolve script:"
Write-Host "  $EditDir"
Write-Host "Installed modules:"
Write-Host "  $ModulesDir"
Write-Host "Bundled FFmpeg:"
Write-Host "  $BundledFfmpegDir"
if (Test-Path $BackupRoot) {
    Write-Host "Backup:"
    Write-Host "  $BackupRoot"
}
Write-Host "Done. Restart DaVinci Resolve if it is already open."
