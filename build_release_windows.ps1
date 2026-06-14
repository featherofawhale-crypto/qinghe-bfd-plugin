$ErrorActionPreference = "Stop"

$Version = "2.0.1-beta.14"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackageRoot = Get-ChildItem -Path $Root -Directory -Filter "*_Windows" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $PackageRoot) { throw "Cannot find package folder ending with _Windows." }

$SourceModules = Join-Path $PackageRoot.FullName "black_frame_detector"
if (!(Test-Path $SourceModules)) {
    $SourceModules = Join-Path $PackageRoot.FullName "modules"
}
$SourceMain = Get-ChildItem -Path $PackageRoot.FullName -File -Filter "*.lua" |
    Select-Object -First 1
$SourceFfmpeg = Join-Path $PackageRoot.FullName "ffmpeg"
$FallbackFfmpegBin = Join-Path $Root "ffmpeg\bin"

if (-not $SourceMain) { throw "Cannot find main Lua script in package folder." }
if (!(Test-Path $SourceModules)) { throw "Missing module folder: $SourceModules" }

$BuildRoot = Join-Path $Root "build\windows"
$PyInstallerDist = Join-Path $BuildRoot "pyinstaller-dist"
$PyInstallerWork = Join-Path $BuildRoot "pyinstaller-work"
$ProtectedDir = Join-Path $Root "dist\Modules\black_frame_detector"
$ReleaseRoot = Join-Path $Root "release"
$ReleaseName = "QingheBFD_v${Version}_Windows"
$StageRoot = Join-Path $ReleaseRoot $ReleaseName
$StagePlugin = Join-Path $StageRoot "QingheBFD_Plugin_Windows"
$StageUi = Join-Path $StageRoot "pyside_ui"

New-Item -ItemType Directory -Force -Path $BuildRoot, $ReleaseRoot | Out-Null

if (Test-Path $StageRoot) {
    $resolvedStage = (Resolve-Path $StageRoot).Path
    $resolvedRelease = (Resolve-Path $ReleaseRoot).Path
    if (-not $resolvedStage.StartsWith($resolvedRelease)) {
        throw "Refusing to remove path outside release root: $resolvedStage"
    }
    Remove-Item -LiteralPath $StageRoot -Recurse -Force
}

py -3 -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) {
    py -3 -m pip install pyinstaller
}

py -3 -m pip install -r (Join-Path $Root "pyside_ui\requirements.txt")

py -3 -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name QingheBFDControl `
    --icon (Join-Path $Root "pyside_ui\icon.ico") `
    --paths (Join-Path $Root "pyside_ui") `
    --add-data "$(Join-Path $Root "pyside_ui\icon.svg");." `
    --add-data "$(Join-Path $Root "pyside_ui\icon.ico");." `
    --add-data "$(Join-Path $Root "pyside_ui\donate");donate" `
    --add-data "$(Join-Path $Root "pyside_ui\templates");templates" `
    --add-data "$(Join-Path $Root "pyside_ui\data");data" `
    --distpath $PyInstallerDist `
    --workpath $PyInstallerWork `
    (Join-Path $Root "pyside_ui\app.py")

py -3 (Join-Path $Root "tools\lua_bytecode_builder.py") `
    --modules-dir $SourceModules `
    --out-dir $ProtectedDir `
    --core black_frame_analyzer.lua duplicate_detector.lua `
    --compiler auto

New-Item -ItemType Directory -Force -Path $StageRoot, $StagePlugin, $StageUi | Out-Null
Copy-Item (Join-Path $Root "install_windows.ps1") $StageRoot -Force
Copy-Item (Join-Path $Root "install_windows.bat") $StageRoot -Force
Copy-Item (Join-Path $Root "uninstall_windows.ps1") $StageRoot -Force
Copy-Item (Join-Path $Root "check_components.ps1") $StageRoot -Force
Copy-Item (Join-Path $Root "README.md") $StageRoot -Force
Copy-Item (Join-Path $Root "docs") $StageRoot -Recurse -Force
Copy-Item (Join-Path $PyInstallerDist "QingheBFDControl") $StageUi -Recurse -Force
Copy-Item (Join-Path $Root "pyside_ui\icon.ico") $StageUi -Force
Copy-Item (Join-Path $Root "pyside_ui\icon.svg") $StageUi -Force

Copy-Item $SourceMain.FullName (Join-Path $StagePlugin $SourceMain.Name) -Force
$StageModules = Join-Path $StagePlugin "black_frame_detector"
New-Item -ItemType Directory -Force -Path $StageModules | Out-Null
Copy-Item (Join-Path $SourceModules "*.lua") $StageModules -Force
Copy-Item (Join-Path $ProtectedDir "black_frame_analyzer.lua") $StageModules -Force
Copy-Item (Join-Path $ProtectedDir "duplicate_detector.lua") $StageModules -Force
Copy-Item (Join-Path $ProtectedDir "bytecode_manifest.json") $StageModules -Force
$StageModulesAlias = Join-Path $StagePlugin "modules"
New-Item -ItemType Directory -Force -Path $StageModulesAlias | Out-Null
Copy-Item (Join-Path $StageModules "*") $StageModulesAlias -Recurse -Force

Get-ChildItem -Path $PackageRoot.FullName -File -Filter "*.txt" -ErrorAction SilentlyContinue |
    Copy-Item -Destination $StagePlugin -Force

$doc = Get-ChildItem -Path $PackageRoot.FullName -File -Filter "*.pdf" -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($doc) {
    Copy-Item $doc.FullName (Join-Path $StagePlugin "QingheBFD_v${Version}_Manual.pdf") -Force
}

$StageFfmpeg = Join-Path $StagePlugin "ffmpeg\windows"
New-Item -ItemType Directory -Force -Path $StageFfmpeg | Out-Null
$SourceFfmpegWindows = Join-Path $SourceFfmpeg "windows"
$SourceFfmpegBin = Join-Path $SourceFfmpeg "bin"
$DiscoveredFfmpegBins = Get-ChildItem -Path $Root -Recurse -File -Filter "ffmpeg.exe" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notlike (Join-Path $BuildRoot "*") -and $_.FullName -notlike (Join-Path $StageRoot "*") } |
    ForEach-Object { $_.DirectoryName } |
    Sort-Object -Unique
$FfmpegBin = $null
foreach ($candidate in @($SourceFfmpegWindows, $SourceFfmpegBin, $FallbackFfmpegBin) + $DiscoveredFfmpegBins) {
    if ($candidate -and (Test-Path (Join-Path $candidate "ffmpeg.exe")) -and (Test-Path (Join-Path $candidate "ffprobe.exe"))) {
        $FfmpegBin = $candidate
        break
    }
}
if (-not $FfmpegBin) {
    throw "Missing bundled Windows FFmpeg: expected ffmpeg.exe and ffprobe.exe in package ffmpeg\windows, package ffmpeg\bin, root ffmpeg\bin, or fallback package."
}
Copy-Item (Join-Path $FfmpegBin "ffmpeg.exe") $StageFfmpeg -Force
Copy-Item (Join-Path $FfmpegBin "ffprobe.exe") $StageFfmpeg -Force
if (Test-Path (Join-Path $FfmpegBin "ffplay.exe")) {
    Copy-Item (Join-Path $FfmpegBin "ffplay.exe") $StageFfmpeg -Force
}
foreach ($name in @("LICENSE", "README.txt")) {
    $src = Join-Path $SourceFfmpeg $name
    if (!(Test-Path $src)) { $src = Join-Path (Split-Path $FfmpegBin -Parent) $name }
    if (Test-Path $src) { Copy-Item $src (Join-Path (Split-Path $StageFfmpeg -Parent) $name) -Force }
}
$srcPresets = Join-Path $SourceFfmpeg "presets"
if (!(Test-Path $srcPresets)) { $srcPresets = Join-Path (Split-Path $FfmpegBin -Parent) "presets" }
if (Test-Path $srcPresets) {
    Copy-Item $srcPresets (Split-Path $StageFfmpeg -Parent) -Recurse -Force
}

$ZipPath = Join-Path $ReleaseRoot ($ReleaseName + ".zip")
if (Test-Path $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
Compress-Archive -Path (Join-Path $StageRoot "*") -DestinationPath $ZipPath -Force

Write-Host "Release folder:"
Write-Host "  $StageRoot"
Write-Host "Release zip:"
Write-Host "  $ZipPath"
Write-Host "User entry:"
Write-Host "  $StageRoot\install_windows.bat"
