$ErrorActionPreference = "Stop"

$ScriptsRoot = Join-Path $env:APPDATA "Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts"
$EditDir = Join-Path $ScriptsRoot "Edit"
$UtilityDir = Join-Path $ScriptsRoot "Utility"
$ModulesDir = Join-Path $ScriptsRoot "Modules\black_frame_detector"
$MainLuaName = (-join ([char[]](0x6e05, 0x4f55, 0x9ed1, 0x5e27, 0x5939, 0x5e27, 0x68c0, 0x6d4b))) + ".lua"

foreach ($path in @(
    (Join-Path $EditDir $MainLuaName),
    (Join-Path $UtilityDir $MainLuaName)
)) {
    if (Test-Path $path) {
        Remove-Item -LiteralPath $path -Force
        Write-Host "Removed: $path"
    }
}

if (Test-Path $ModulesDir) {
    Remove-Item -LiteralPath $ModulesDir -Recurse -Force
    Write-Host "Removed modules: $ModulesDir"
}

$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Qinghe BFD Control.lnk"
if (Test-Path $desktopShortcut) {
    Remove-Item -LiteralPath $desktopShortcut -Force
    Write-Host "Removed legacy desktop shortcut: $desktopShortcut"
}

Write-Host "Qinghe BFD Windows plugin uninstalled. Restart DaVinci Resolve if it is open."
