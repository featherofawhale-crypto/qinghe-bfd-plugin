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

Assert-Path $StageRoot "release folder"
Assert-Path $ZipPath "release zip"
Assert-Path (Join-Path $StageRoot "install_windows.bat") "one-click installer"
Assert-Path (Join-Path $StageRoot "install_windows.ps1") "installer script"
Assert-Path (Join-Path $StageRoot "pyside_ui\QingheBFDControl\QingheBFDControl.exe") "packaged PySide executable"
Assert-Path (Join-Path $StageRoot "pyside_ui\icon.ico") "UI icon"
$UiInternal = Join-Path $StageRoot "pyside_ui\QingheBFDControl\_internal"
Assert-Path $UiInternal "packaged Python runtime"

$PluginRoot = Join-Path $StageRoot "QingheBFD_Plugin_Windows"
Assert-Path $PluginRoot "Resolve plugin root"
Assert-Path (Join-Path $PluginRoot "black_frame_detector") "black_frame_detector modules"
Assert-Path (Join-Path $PluginRoot "modules") "legacy modules alias"
Assert-Path (Join-Path $PluginRoot "ffmpeg\windows\ffmpeg.exe") "bundled ffmpeg"
Assert-Path (Join-Path $PluginRoot "ffmpeg\windows\ffprobe.exe") "bundled ffprobe"

$MainLua = Get-ChildItem -Path $PluginRoot -File -Filter "*.lua" | Select-Object -First 1
if (-not $MainLua) {
    throw "Missing main Lua entry in $PluginRoot"
}
Write-Host "[OK] main Lua entry: $($MainLua.Name)"

Assert-Path (Join-Path $UiInternal "donate") "donation assets"
Assert-Path (Join-Path $UiInternal "templates\caption-bin.drb") "caption template"
Assert-Path (Join-Path $UiInternal "data\font_probe_rules.json") "font probe rules"
Assert-Path (Join-Path $UiInternal "data\font_style_library.json") "font style library"

$ZipSize = (Get-Item $ZipPath).Length
if ($ZipSize -lt 100MB) {
    throw "Release zip is unexpectedly small: $ZipSize bytes"
}
Write-Host "[OK] release zip size: $([math]::Round($ZipSize / 1MB, 2)) MB"

Write-Host "Windows release verification passed."
