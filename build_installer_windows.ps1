param(
    [string]$Version = "2.0.1-beta.23"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ReleaseName = "QingheBFD_v${Version}_Windows"
$ReleaseRoot = Join-Path $Root "release"
$StageRoot = Join-Path $ReleaseRoot $ReleaseName
$InstallerOut = Join-Path $ReleaseRoot "installer"
$IssPath = Join-Path $Root "installer_windows.iss"

if (!(Test-Path $StageRoot)) {
    throw "Missing release folder. Run build_release_windows.ps1 first: $StageRoot"
}

New-Item -ItemType Directory -Force -Path $InstallerOut | Out-Null

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            $iscc = [pscustomobject]@{ Source = $candidate }
            break
        }
    }
}
if (-not $iscc) {
    throw "Missing Inno Setup compiler ISCC.exe. Install Inno Setup 6 first."
}

& $iscc.Source `
    "/DMyAppVersion=$Version" `
    "/DSourceDir=$StageRoot" `
    "/DOutputDir=$InstallerOut" `
    $IssPath

$InstallerPath = Join-Path $InstallerOut "QingheBFD_v${Version}_Windows_Setup.exe"
if (!(Test-Path $InstallerPath)) {
    throw "Installer was not created: $InstallerPath"
}

Write-Host "Installer:"
Write-Host "  $InstallerPath"
