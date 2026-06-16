param(
    [string]$Version = "2.0.1-beta.14"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ReleaseName = "QingheBFD_v${Version}_Windows"
$ReleaseRoot = Join-Path $Root "release"
$StageRoot = Join-Path $ReleaseRoot $ReleaseName
$ZipPath = Join-Path $ReleaseRoot ($ReleaseName + ".zip")

function Assert-Path($Path, $Label) {
    if (!(Test-Path $Path)) {
        throw "Missing ${Label}: $Path"
    }
    Write-Host "[OK] $Label"
}

function Assert-NotContains($Path, $Pattern, $Label) {
    $text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    if ($text -match $Pattern) {
        throw "Forbidden external dependency in ${Label}: pattern '$Pattern' found in $Path"
    }
    Write-Host "[OK] $Label does not contain $Pattern"
}

function Invoke-Isolated($Exe, [string[]]$Arguments, $Label, [int[]]$AllowedExitCodes = @(0)) {
    $envBackup = @{
        PATH = $env:PATH
        PYTHONHOME = $env:PYTHONHOME
        PYTHONPATH = $env:PYTHONPATH
        QT_PLUGIN_PATH = $env:QT_PLUGIN_PATH
        QT_QPA_PLATFORM_PLUGIN_PATH = $env:QT_QPA_PLATFORM_PLUGIN_PATH
    }
    try {
        $env:PATH = Split-Path -Parent $Exe
        Remove-Item Env:\PYTHONHOME -ErrorAction SilentlyContinue
        Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue
        Remove-Item Env:\QT_PLUGIN_PATH -ErrorAction SilentlyContinue
        Remove-Item Env:\QT_QPA_PLATFORM_PLUGIN_PATH -ErrorAction SilentlyContinue
        $output = & $Exe @Arguments 2>&1
        if ($LASTEXITCODE -notin $AllowedExitCodes) {
            throw "${Label} failed with exit code ${LASTEXITCODE}: $($output -join "`n")"
        }
        Write-Host "[OK] $Label"
    } finally {
        foreach ($key in $envBackup.Keys) {
            $value = $envBackup[$key]
            if ($null -eq $value) {
                Remove-Item "Env:\$key" -ErrorAction SilentlyContinue
            } else {
                Set-Item "Env:\$key" $value
            }
        }
    }
}

Assert-Path $StageRoot "release folder"
Assert-Path $ZipPath "release zip"
Assert-Path (Join-Path $StageRoot "install_windows.bat") "one-click installer"
$InstallScript = Join-Path $StageRoot "install_windows.ps1"
Assert-Path $InstallScript "installer script"
$PackagedExe = Join-Path $StageRoot "pyside_ui\QingheBFDControl\QingheBFDControl.exe"
Assert-Path $PackagedExe "packaged PySide executable"
Assert-Path (Join-Path $StageRoot "pyside_ui\icon.ico") "UI icon"
$UiInternal = Join-Path $StageRoot "pyside_ui\QingheBFDControl\_internal"
Assert-Path $UiInternal "packaged Python runtime"
$BundledPython = Join-Path $StageRoot "pyside_ui\python_runtime\python.exe"
Assert-Path $BundledPython "bundled bridge Python"

$PluginRoot = Join-Path $StageRoot "QingheBFD_Plugin_Windows"
Assert-Path $PluginRoot "Resolve plugin root"
Assert-Path (Join-Path $PluginRoot "black_frame_detector") "black_frame_detector modules"
Assert-Path (Join-Path $PluginRoot "modules") "legacy modules alias"
$BundledFfmpeg = Join-Path $PluginRoot "ffmpeg\windows\ffmpeg.exe"
$BundledFfprobe = Join-Path $PluginRoot "ffmpeg\windows\ffprobe.exe"
Assert-Path $BundledFfmpeg "bundled ffmpeg"
Assert-Path $BundledFfprobe "bundled ffprobe"

$MainLua = Get-ChildItem -Path $PluginRoot -File -Filter "*.lua" | Select-Object -First 1
if (-not $MainLua) {
    throw "Missing main Lua entry in $PluginRoot"
}
Write-Host "[OK] main Lua entry: $($MainLua.Name)"

Assert-Path (Join-Path $UiInternal "donate") "donation assets"
Assert-Path (Join-Path $UiInternal "templates\caption-bin.drb") "caption template"
Assert-Path (Join-Path $UiInternal "data\font_probe_rules.json") "font probe rules"
Assert-Path (Join-Path $UiInternal "data\font_style_library.json") "font style library"

Assert-NotContains $InstallScript "pip\s+install" "installer script"
Assert-NotContains $InstallScript "Get-Command\s+(py|python)" "installer script"
Assert-NotContains $InstallScript "\.cache\\codex-runtimes" "installer script"
Assert-NotContains $InstallScript "run_ui_hidden\.vbs|run_ui\.bat" "installer script"

Invoke-Isolated $BundledFfmpeg @("-hide_banner", "-version") "bundled ffmpeg starts without PATH"
Invoke-Isolated $BundledFfprobe @("-hide_banner", "-version") "bundled ffprobe starts without PATH"
Invoke-Isolated $BundledPython @("-I", "-S", "-c", "import sys,json,ssl,subprocess; print(json.dumps({'exe':sys.executable,'ok':True}))") "bundled Python stdlib starts isolated"
Invoke-Isolated $PackagedExe @("--resolve-bridge") "packaged PySide exe bridge-worker mode starts" @(0, 2)

$ZipSize = (Get-Item $ZipPath).Length
if ($ZipSize -lt 100MB) {
    throw "Release zip is unexpectedly small: $ZipSize bytes"
}
Write-Host "[OK] release zip size: $([math]::Round($ZipSize / 1MB, 2)) MB"

Write-Host "Windows release verification passed."
