$ErrorActionPreference = "Stop"

$Version = "1.9.101"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackageRoot = Get-ChildItem -Path $Root -Directory -Filter "*_Windows" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $PackageRoot) { throw "Cannot find package folder ending with _Windows." }

$SourceModules = Join-Path $PackageRoot.FullName "black_frame_detector"
$SourceMain = Get-ChildItem -Path $PackageRoot.FullName -File -Filter "*.lua" |
    Select-Object -First 1
$SourceFfmpeg = Join-Path $PackageRoot.FullName "ffmpeg"

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
    --paths (Join-Path $Root "pyside_ui") `
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
Copy-Item (Join-Path $Root "check_components.ps1") $StageRoot -Force
Copy-Item (Join-Path $Root "README.md") $StageRoot -Force
Copy-Item (Join-Path $Root "docs") $StageRoot -Recurse -Force
Copy-Item (Join-Path $PyInstallerDist "QingheBFDControl") $StageUi -Recurse -Force

Copy-Item $SourceMain.FullName (Join-Path $StagePlugin $SourceMain.Name) -Force
$StageModules = Join-Path $StagePlugin "black_frame_detector"
New-Item -ItemType Directory -Force -Path $StageModules | Out-Null
Copy-Item (Join-Path $SourceModules "*.lua") $StageModules -Force
Copy-Item (Join-Path $ProtectedDir "black_frame_analyzer.lua") $StageModules -Force
Copy-Item (Join-Path $ProtectedDir "duplicate_detector.lua") $StageModules -Force
Copy-Item (Join-Path $ProtectedDir "bytecode_manifest.json") $StageModules -Force

Get-ChildItem -Path $PackageRoot.FullName -File -Filter "*.txt" -ErrorAction SilentlyContinue |
    Copy-Item -Destination $StagePlugin -Force

$doc = Get-ChildItem -Path $PackageRoot.FullName -File -Filter "*.pdf" -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($doc) {
    Copy-Item $doc.FullName (Join-Path $StagePlugin "QingheBFD_v${Version}_Manual.pdf") -Force
}

if (Test-Path $SourceFfmpeg) {
    New-Item -ItemType Directory -Force -Path (Join-Path $StagePlugin "ffmpeg") | Out-Null
    foreach ($sub in @("bin", "presets")) {
        $src = Join-Path $SourceFfmpeg $sub
        if (Test-Path $src) { Copy-Item $src (Join-Path $StagePlugin "ffmpeg") -Recurse -Force }
    }
    foreach ($name in @("LICENSE", "README.txt")) {
        $src = Join-Path $SourceFfmpeg $name
        if (Test-Path $src) { Copy-Item $src (Join-Path $StagePlugin "ffmpeg") -Force }
    }
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
