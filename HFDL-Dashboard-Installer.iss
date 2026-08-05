#define MyAppName "HFDL Operations Dashboard"
#define MyAppVersion "10.6.0-rc1"
#define MyNumericVersion "10.6.0.1"
#define MyAppPublisher "Louis LeMerle, VK2ICW"
#define MyAppExeName "HFDLDashboard.exe"
#define MyAppServerExeName "HFDLDashboardServer.exe"

[Setup]
AppId={{0C559D93-4351-4B16-85C5-7204C8C2AC8B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyNumericVersion}
VersionInfoVersion={#MyNumericVersion}
DefaultDirName={autopf}\HFDL Operations Dashboard
DefaultGroupName=HFDL Operations Dashboard
DisableProgramGroupPage=yes
OutputDir=installer-output
OutputBaseFilename=HFDL-Operations-Dashboard-Setup-v10.6-RC
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=hfdl-dashboard.ico
SetupLogging=yes
LicenseFile=LICENSE
InfoBeforeFile=DISCLAIMER.md
CloseApplications=yes
RestartApplications=no
ChangesEnvironment=no
UsePreviousAppDir=yes
UsePreviousTasks=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Start HFDL Operations Dashboard when I sign in to Windows"; GroupDescription: "Startup:"; Flags: unchecked
Name: "firewalludp"; Description: "Allow inbound UDP 5557 on Private networks"; GroupDescription: "Windows Firewall:"; Flags: unchecked
Name: "launchafter"; Description: "Launch HFDL Operations Dashboard after installation"; GroupDescription: "Finish:"; Flags: checkedonce

[Files]
Source: "dist\HFDL-Dashboard-Windows-v10.6-RC\HFDLDashboard.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\HFDL-Dashboard-Windows-v10.6-RC\HFDLDashboardServer.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\HFDL-Dashboard-Windows-v10.6-RC\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\HFDL-Dashboard-Windows-v10.6-RC\DISCLAIMER.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\HFDL-Dashboard-Windows-v10.6-RC\PRIVACY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\HFDL-Dashboard-Windows-v10.6-RC\SECURITY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\HFDL-Dashboard-Windows-v10.6-RC\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\HFDL-Dashboard-Windows-v10.6-RC\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\HFDL-Dashboard-Windows-v10.6-RC\README-WINDOWS.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\HFDL-Dashboard-Windows-v10.6-RC\VERSION"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\HFDL-Dashboard-Windows-v10.6-RC\hfdl-dashboard.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\HFDL-Dashboard-Windows-v10.6-RC\hfdl-dashboard.png"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\HFDL Operations Dashboard"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Documentation"; Filename: "{app}\README-WINDOWS.md"
Name: "{group}\Uninstall HFDL Operations Dashboard"; Filename: "{uninstallexe}"
Name: "{autodesktop}\HFDL Operations Dashboard"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\HFDL Operations Dashboard"; Filename: "{app}\{#MyAppExeName}"; Tasks: startup

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""HFDL Dashboard UDP"" dir=in action=allow protocol=UDP localport=5557 profile=private program=""{app}\{#MyAppServerExeName}"""; Flags: runhidden waituntilterminated; Tasks: firewalludp
Filename: "{app}\{#MyAppExeName}"; Parameters: "--autostart"; Description: "Launch and start HFDL Operations Dashboard"; Flags: nowait postinstall skipifsilent; Tasks: launchafter

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM HFDLDashboardServer.exe /T /F"; Flags: runhidden waituntilterminated; RunOnceId: "StopHFDLServer"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""HFDL Dashboard UDP"""; Flags: runhidden waituntilterminated; RunOnceId: "RemoveHFDLFirewallRule"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function CmdLineParamExists(const Value: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), Value) = 0 then
    begin
      Result := True;
      Exit;
    end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'),
       '/IM HFDLDashboardServer.exe /T /F',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataPath: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataPath := ExpandConstant('{localappdata}\HFDLDashboard');
    { User data is preserved by default. To remove it, run the uninstaller with /REMOVEUSERDATA. }
    if CmdLineParamExists('/REMOVEUSERDATA') then
      DelTree(DataPath, True, True, True);
  end;
end;
