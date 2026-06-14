$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:Path = "C:\Program Files\nodejs;" + $env:Path
$PackageRoot = Get-ChildItem -Path $Root -Directory -Filter "*_Windows" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
$ProjectFfmpeg = ""
if ($PackageRoot) {
    foreach ($candidate in @(
        (Join-Path $PackageRoot.FullName "ffmpeg\windows\ffmpeg.exe"),
        (Join-Path $PackageRoot.FullName "ffmpeg\bin\ffmpeg.exe")
    )) {
        if (Test-Path $candidate) {
            $ProjectFfmpeg = $candidate
            break
        }
    }
}
$ProjectFfprobe = if ($ProjectFfmpeg) { $ProjectFfmpeg -replace "ffmpeg\.exe$", "ffprobe.exe" } else { "" }
$PackagedUi = Join-Path $Root "pyside_ui\QingheBFDControl\QingheBFDControl.exe"
$PackagedRuntime = Join-Path $Root "pyside_ui\QingheBFDControl\_internal"
$InstalledEditDir = Join-Path $env:APPDATA "Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Edit"
$MainLuaName = (-join ([char[]](0x6e05, 0x4f55, 0x9ed1, 0x5e27, 0x5939, 0x5e27, 0x68c0, 0x6d4b))) + ".lua"
$InstalledEditScript = Join-Path $InstalledEditDir $MainLuaName

$RequiredPaths = @{
    "DaVinci Resolve" = "C:\Program Files\Blackmagic Design\DaVinci Resolve\Resolve.exe"
    "fuscript" = "C:\Program Files\Blackmagic Design\DaVinci Resolve\fuscript.exe"
    "Resolve Python API" = "C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules\DaVinciResolveScript.py"
    "Project FFmpeg" = $ProjectFfmpeg
    "Project FFprobe" = $ProjectFfprobe
    "Packaged PySide UI" = $PackagedUi
    "Packaged Python Runtime" = $PackagedRuntime
    "Installed Edit Script" = $InstalledEditScript
    "Installed Modules" = Join-Path $env:APPDATA "Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Modules\black_frame_detector"
    "Managed Resolve MCP" = Join-Path $env:LOCALAPPDATA "davinci-resolve-mcp\src\server.py"
}

function Write-Check($name, $ok, $detail) {
    $status = if ($ok) { "OK" } else { "MISSING" }
    Write-Host ("[{0}] {1} {2}" -f $status, $name, $detail)
}

foreach ($entry in $RequiredPaths.GetEnumerator()) {
    $detail = [string]$entry.Value
    $ok = $false
    if ($detail) {
        $ok = Test-Path $detail
    }
    Write-Check $entry.Key $ok $detail
}

$commands = @("git", "py", "node", "npm", "npx")
foreach ($cmd in $commands) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    Write-Check $cmd ($null -ne $found) ($found.Source)
}

$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
    try {
        py -3 -c "import PySide6; print('[OK] PySide6', PySide6.__version__)"
    } catch {
        Write-Host "[MISSING] PySide6"
    }
    try {
        py -3 -c "import PyInstaller; print('[OK] PyInstaller', PyInstaller.__version__)"
    } catch {
        Write-Host "[MISSING] PyInstaller"
    }
} else {
    Write-Host "[SKIP] Python launcher is not required for normal installed users when packaged UI exists."
}

$npx = Get-Command npx -ErrorAction SilentlyContinue
if ($npx -and $env:QINGHE_RUN_MCP_DOCTOR -eq "1") {
    try {
        npx --yes davinci-resolve-mcp doctor
    } catch {
        Write-Host "[WARN] davinci-resolve-mcp doctor failed or is unavailable."
    }
} elseif ($npx) {
    Write-Host "[SKIP] davinci-resolve-mcp doctor is optional; set QINGHE_RUN_MCP_DOCTOR=1 to run it."
} else {
    Write-Host "[SKIP] npx is not required for normal installed users."
}
