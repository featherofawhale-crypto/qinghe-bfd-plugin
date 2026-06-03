$ErrorActionPreference = "Stop"

$Version = "1.9.105"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackageRoot = Get-ChildItem -Path $Root -Directory -Filter "*_Windows" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
$MacTemplateRoot = Get-ChildItem -Path $Root -Directory |
    Where-Object { Test-Path (Join-Path $_.FullName "ffmpeg\macos\ffmpeg") } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $PackageRoot) { throw "Cannot find current package folder ending with _Windows." }
if (-not $MacTemplateRoot) { throw "Missing extracted macOS template folder containing ffmpeg\macos\ffmpeg." }

$SourceModules = Join-Path $PackageRoot.FullName "black_frame_detector"
$SourceMain = Get-ChildItem -Path $PackageRoot.FullName -File -Filter "*.lua" |
    Select-Object -First 1
$SourceMacFfmpeg = Join-Path $MacTemplateRoot.FullName "ffmpeg"

if (-not $SourceMain) { throw "Cannot find main Lua script in package folder." }
if (!(Test-Path $SourceModules)) { throw "Missing module folder: $SourceModules" }
if (!(Test-Path (Join-Path $SourceMacFfmpeg "macos\ffmpeg"))) {
    throw "Missing bundled macOS FFmpeg from extracted DMG template: $SourceMacFfmpeg"
}

$ReleaseRoot = Join-Path $Root "release"
$ReleaseName = "QingheBFD_v${Version}_macOS"
$StageRoot = Join-Path $ReleaseRoot $ReleaseName
$StagePlugin = Join-Path $StageRoot "QingheBFD_Plugin_macOS"
$StageModules = Join-Path $StagePlugin "modules"
$StageUi = Join-Path $StagePlugin "pyside_ui"

New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null
if (Test-Path $StageRoot) {
    $resolvedStage = (Resolve-Path $StageRoot).Path
    $resolvedRelease = (Resolve-Path $ReleaseRoot).Path
    if (-not $resolvedStage.StartsWith($resolvedRelease)) {
        throw "Refusing to remove path outside release root: $resolvedStage"
    }
    Remove-Item -LiteralPath $StageRoot -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $StageRoot, $StagePlugin, $StageModules, $StageUi | Out-Null

Copy-Item (Join-Path $Root "install_macos.command") $StageRoot -Force
Copy-Item (Join-Path $Root "uninstall_macos.command") $StageRoot -Force
Copy-Item (Join-Path $Root "check_components_macos.sh") $StageRoot -Force
Copy-Item (Join-Path $Root "README.md") $StageRoot -Force
Copy-Item (Join-Path $Root "docs\macos_release.md") $StageRoot -Force

Copy-Item $SourceMain.FullName (Join-Path $StagePlugin $SourceMain.Name) -Force
Copy-Item (Join-Path $SourceModules "*.lua") $StageModules -Force
Copy-Item $SourceMacFfmpeg (Join-Path $StagePlugin "ffmpeg") -Recurse -Force
Copy-Item (Join-Path $Root "pyside_ui\*") $StageUi -Recurse -Force -Exclude "QingheBFDControl", "QingheBFDControl.exe", "*.exe", "__pycache__"

Get-ChildItem -Path $StageRoot -Recurse -Filter "*_com.apple.provenance" -ErrorAction SilentlyContinue |
    Remove-Item -Force

$ZipPath = Join-Path $ReleaseRoot ($ReleaseName + ".zip")
if (Test-Path $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
Compress-Archive -Path (Join-Path $StageRoot "*") -DestinationPath $ZipPath -Force

Write-Host "macOS release folder:"
Write-Host "  $StageRoot"
Write-Host "macOS release zip:"
Write-Host "  $ZipPath"
Write-Host "User entry:"
Write-Host "  $StageRoot\install_macos.command"
Write-Host "Note: Windows can create this macOS zip, but a signed .app/.dmg must be produced on macOS with hdiutil."
