#define MyAppName "Qinghe BFD"
#ifndef MyAppVersion
#define MyAppVersion "2.0.1-beta.14"
#endif
#ifndef SourceDir
#define SourceDir "release\QingheBFD_v2.0.1-beta.14_Windows"
#endif
#ifndef OutputDir
#define OutputDir "release\installer"
#endif

[Setup]
AppId={{A7393D89-0C20-4BC6-A3F4-2B8B9ED87F41}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Qinghe
DefaultDirName={localappdata}\QingheBFD
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=QingheBFD_v{#MyAppVersion}_Windows_Setup
SetupIconFile={#SourceDir}\pyside_ui\icon.ico
UninstallDisplayIcon={app}\pyside_ui\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile={#SourceDir}\installer_disclaimer.txt

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\install_windows.ps1"""; Flags: runhidden waituntilterminated; StatusMsg: "Installing DaVinci Resolve plugin..."

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\uninstall_windows.ps1"""; Flags: runhidden waituntilterminated
