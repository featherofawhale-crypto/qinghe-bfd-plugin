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
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\uninstall_windows.ps1"""; Flags: runhidden waituntilterminated; RunOnceId: "QingheBFDPluginCleanup"

[Code]
function ExistingUninstaller(): String;
var
  UninstallPath: String;
begin
  Result := '';
  if RegQueryStringValue(
    HKCU,
    'Software\Microsoft\Windows\CurrentVersion\Uninstall\{A7393D89-0C20-4BC6-A3F4-2B8B9ED87F41}_is1',
    'UninstallString',
    UninstallPath
  ) then begin
    Result := RemoveQuotes(UninstallPath);
  end;

  if (Result = '') and FileExists(ExpandConstant('{localappdata}\QingheBFD\unins000.exe')) then begin
    Result := ExpandConstant('{localappdata}\QingheBFD\unins000.exe');
  end;
end;

function InitializeSetup(): Boolean;
var
  Uninstaller: String;
  Choice: Integer;
  ExitCode: Integer;
begin
  Result := True;
  if WizardSilent() then begin
    Exit;
  end;

  Uninstaller := ExistingUninstaller();
  if Uninstaller = '' then begin
    Exit;
  end;

  Choice := MsgBox(
    '检测到已安装的 Qinghe BFD Windows 版本。' + #13#10 + #13#10 +
    '点击“是”：覆盖安装/更新到当前版本。' + #13#10 +
    '点击“否”：先卸载旧版本，然后退出安装器。' + #13#10 +
    '点击“取消”：不做任何更改。',
    mbConfirmation,
    MB_YESNOCANCEL
  );

  if Choice = IDYES then begin
    Result := True;
  end else if Choice = IDNO then begin
    if not Exec(Uninstaller, '/SILENT', '', SW_SHOW, ewWaitUntilTerminated, ExitCode) then begin
      MsgBox('无法启动旧版本卸载程序：' + Uninstaller, mbError, MB_OK);
    end else begin
      MsgBox('旧版本卸载流程已结束。需要安装新版时，请重新运行本安装包。', mbInformation, MB_OK);
    end;
    Result := False;
  end else begin
    Result := False;
  end;
end;
