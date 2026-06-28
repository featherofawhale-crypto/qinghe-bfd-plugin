[CmdletBinding()]
param(
    [string]$Version = "2.0.1-beta.23",
    [string]$SourcePluginRoot = ""
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($SourcePluginRoot -and (Test-Path $SourcePluginRoot)) {
    $PackageRoot = Get-Item -LiteralPath $SourcePluginRoot
} else {
    $PackageRoot = Get-Item -LiteralPath $Root
}

if (-not $PackageRoot) { throw "Cannot resolve package source root." }

$SourceModules = Join-Path $PackageRoot.FullName "black_frame_detector"
if (!(Test-Path $SourceModules)) {
    $SourceModules = Join-Path $PackageRoot.FullName "modules"
}
$SourceUi = Join-Path $Root "pyside_ui"
$SourceMain = Get-ChildItem -Path $PackageRoot.FullName -File -Filter "*.lua" |
    Select-Object -First 1
$SourceFfmpeg = Join-Path $PackageRoot.FullName "ffmpeg"
$FallbackFfmpegBin = Join-Path $Root "ffmpeg\bin"

if (-not $SourceMain) { throw "Cannot find main Lua script in package folder." }
if (!(Test-Path $SourceModules)) { throw "Missing module folder: $SourceModules" }
if (!(Test-Path $SourceUi)) { throw "Missing pyside_ui folder: $SourceUi" }

$BuildRoot = Join-Path $Root "build\windows"
$PyInstallerDist = Join-Path $BuildRoot "pyinstaller-dist"
$PyInstallerWork = Join-Path $BuildRoot "pyinstaller-work"
$ProtectedDir = Join-Path $Root "dist\Modules\black_frame_detector"
$ReleaseRoot = Join-Path $Root "release"
$ReleaseName = "QingheBFD_v${Version}_Windows"
$StageRoot = Join-Path $ReleaseRoot $ReleaseName
$StagePlugin = Join-Path $StageRoot "QingheBFD_Plugin_Windows"
$StageUi = Join-Path $StageRoot "pyside_ui"

function Resolve-PythonCommand {
    if ($env:QINGHE_PYTHON) {
        if (!(Test-Path $env:QINGHE_PYTHON)) {
            throw "QINGHE_PYTHON points to a missing file: $env:QINGHE_PYTHON"
        }
        return @{
            Exe = $env:QINGHE_PYTHON
            Args = @()
            Label = $env:QINGHE_PYTHON
        }
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{
            Exe = $py.Source
            Args = @("-3")
            Label = "py -3"
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{
            Exe = $python.Source
            Args = @()
            Label = $python.Source
        }
    }

    throw "Python was not found. Install Python or set QINGHE_PYTHON to python.exe."
}

$PythonCommand = Resolve-PythonCommand
Write-Host "Using Python: $($PythonCommand.Label)"

function Invoke-Python {
    param([string[]]$Arguments)
    & $PythonCommand.Exe @($PythonCommand.Args) @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed: $($PythonCommand.Label) $($Arguments -join ' ')"
    }
}

function Invoke-PythonCapture {
    param([string[]]$Arguments)
    $output = & $PythonCommand.Exe @($PythonCommand.Args) @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed: $($PythonCommand.Label) $($Arguments -join ' ')"
    }
    return $output
}

New-Item -ItemType Directory -Force -Path $BuildRoot, $ReleaseRoot | Out-Null

if (Test-Path $StageRoot) {
    $resolvedStage = (Resolve-Path $StageRoot).Path
    $resolvedRelease = (Resolve-Path $ReleaseRoot).Path
    if (-not $resolvedStage.StartsWith($resolvedRelease)) {
        throw "Refusing to remove path outside release root: $resolvedStage"
    }
    try {
        Remove-Item -LiteralPath $StageRoot -Recurse -Force
    } catch {
        $emptyDir = Join-Path $BuildRoot "empty-dir-for-clean"
        if (Test-Path $emptyDir) {
            Remove-Item -LiteralPath $emptyDir -Recurse -Force
        }
        New-Item -ItemType Directory -Force -Path $emptyDir | Out-Null
        robocopy $emptyDir $StageRoot /MIR | Out-Host
        if ($LASTEXITCODE -gt 7) {
            throw "Failed to clear stale release folder: $StageRoot"
        }
        Remove-Item -LiteralPath $StageRoot -Recurse -Force
    }
}

& $PythonCommand.Exe @($PythonCommand.Args) -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) {
    Invoke-Python -Arguments @("-m", "pip", "install", "pyinstaller")
}

Invoke-Python -Arguments @("-m", "pip", "install", "-r", (Join-Path $SourceUi "requirements.txt"))

$BuildPythonInfo = Invoke-PythonCapture -Arguments @(
    "-c",
    "import sys, PyInstaller, PySide6; from PySide6 import QtCore; print(f'python={sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} exe={sys.executable}'); print(f'pyinstaller={PyInstaller.__version__}'); print(f'pyside6={PySide6.__version__} qt={QtCore.qVersion()}')"
)
$BuildPythonInfo | ForEach-Object { Write-Host $_ }
$BuildPythonExe = (Invoke-PythonCapture -Arguments @("-c", "import sys; print(sys.executable)"))[0]
if (!(Test-Path $BuildPythonExe)) {
    throw "Cannot resolve real Python executable from $($PythonCommand.Label): $BuildPythonExe"
}

$pyinstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onedir",
    "--windowed",
    "--name", "QingheBFDControl",
    "--icon", (Join-Path $Root "pyside_ui\icon.ico"),
    "--paths", $SourceUi,
    "--add-data", "$(Join-Path $SourceUi "icon.svg");.",
    "--add-data", "$(Join-Path $Root "pyside_ui\icon.ico");.",
    "--add-data", "$(Join-Path $SourceUi "donate");donate",
    "--add-data", "$(Join-Path $SourceUi "templates");templates",
    "--add-data", "$(Join-Path $SourceUi "data");data",
    "--add-data", "$(Join-Path $SourceUi "bpm_worker.py");.",
    "--add-data", "$(Join-Path $SourceUi "bridge_worker.py");.",
    "--distpath", $PyInstallerDist,
    "--workpath", $PyInstallerWork,
    (Join-Path $SourceUi "app.py")
)
Invoke-Python -Arguments $pyinstallerArgs

$BundledQtCore = Join-Path $PyInstallerDist "QingheBFDControl\_internal\PySide6\Qt6Core.dll"
if (!(Test-Path $BundledQtCore)) {
    throw "Packaged PySide6/Qt runtime is missing from PyInstaller output: $BundledQtCore"
}

$bytecodeArgs = @(
    (Join-Path $Root "tools\lua_bytecode_builder.py"),
    "--modules-dir", $SourceModules,
    "--out-dir", $ProtectedDir,
    "--core", "black_frame_analyzer.lua", "duplicate_detector.lua",
    "--compiler", "auto"
)
Invoke-Python -Arguments $bytecodeArgs

New-Item -ItemType Directory -Force -Path $StageRoot, $StagePlugin, $StageUi | Out-Null
Copy-Item (Join-Path $Root "install_windows.ps1") $StageRoot -Force
Copy-Item (Join-Path $Root "install_windows.bat") $StageRoot -Force
Copy-Item (Join-Path $Root "uninstall_windows.ps1") $StageRoot -Force
Copy-Item (Join-Path $Root "check_components.ps1") $StageRoot -Force
Copy-Item (Join-Path $Root "installer_disclaimer.txt") $StageRoot -Force
Copy-Item (Join-Path $Root "README.md") $StageRoot -Force
Copy-Item (Join-Path $Root "docs") $StageRoot -Recurse -Force
New-Item -ItemType Directory -Force -Path (Join-Path $StageRoot "tools") | Out-Null
Copy-Item (Join-Path $Root "tools\test_resolve_api_bridge.ps1") (Join-Path $StageRoot "tools") -Force
Copy-Item (Join-Path $PyInstallerDist "QingheBFDControl") $StageUi -Recurse -Force
Copy-Item (Join-Path $Root "pyside_ui\icon.ico") $StageUi -Force
Copy-Item (Join-Path $Root "pyside_ui\icon.svg") $StageUi -Force
Copy-Item (Join-Path $SourceUi "data") $StageUi -Recurse -Force
Copy-Item (Join-Path $SourceUi "templates") $StageUi -Recurse -Force
$PythonRuntimeSource = Split-Path -Parent $BuildPythonExe
$StagePythonRuntime = Join-Path $StageUi "python_runtime"
if (Test-Path $StagePythonRuntime) {
    Remove-Item -LiteralPath $StagePythonRuntime -Recurse -Force
}
robocopy $PythonRuntimeSource $StagePythonRuntime /E `
    /XD "__pycache__" "Scripts" "Doc" "include" "libs" "site-packages" `
        (Join-Path $PythonRuntimeSource "Lib\site-packages") `
        (Join-Path $PythonRuntimeSource "Lib\test") `
        (Join-Path $PythonRuntimeSource "Lib\idlelib") `
    /XF "*.pyc" "*.pyo" | Out-Host
if ($LASTEXITCODE -gt 7) {
    throw "Failed to copy bundled Python runtime from $PythonRuntimeSource"
}
if (!(Test-Path (Join-Path $StagePythonRuntime "python.exe"))) {
    throw "Bundled Python runtime is missing python.exe"
}

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
