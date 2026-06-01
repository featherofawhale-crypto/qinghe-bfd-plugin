$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:Path = "C:\Program Files\nodejs;" + $env:Path
$PackageRoot = Get-ChildItem -Path $Root -Directory -Filter "*_Windows" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
$ProjectFfmpeg = if ($PackageRoot) { Join-Path $PackageRoot.FullName "ffmpeg\bin\ffmpeg.exe" } else { "" }

$RequiredPaths = @{
    "DaVinci Resolve" = "C:\Program Files\Blackmagic Design\DaVinci Resolve\Resolve.exe"
    "fuscript" = "C:\Program Files\Blackmagic Design\DaVinci Resolve\fuscript.exe"
    "Resolve Python API" = "C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules\DaVinciResolveScript.py"
    "Project FFmpeg" = $ProjectFfmpeg
    "Installed Edit Script" = Join-Path $env:APPDATA "Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Edit\清何黑帧夹帧检测.lua"
    "Installed Utility Script" = Join-Path $env:APPDATA "Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\清何黑帧夹帧检测.lua"
    "Installed Modules" = Join-Path $env:APPDATA "Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Modules\black_frame_detector"
    "Managed Resolve MCP" = Join-Path $env:LOCALAPPDATA "davinci-resolve-mcp\src\server.py"
}

function Write-Check($name, $ok, $detail) {
    $status = if ($ok) { "OK" } else { "MISSING" }
    Write-Host ("[{0}] {1} {2}" -f $status, $name, $detail)
}

foreach ($entry in $RequiredPaths.GetEnumerator()) {
    Write-Check $entry.Key (Test-Path $entry.Value) $entry.Value
}

$commands = @("git", "py", "node", "npm", "npx")
foreach ($cmd in $commands) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    Write-Check $cmd ($null -ne $found) ($found.Source)
}

py -3 -c "import PySide6; print('[OK] PySide6', PySide6.__version__)"
py -3 -c "import PyInstaller; print('[OK] PyInstaller', PyInstaller.__version__)"

npx --yes davinci-resolve-mcp doctor
