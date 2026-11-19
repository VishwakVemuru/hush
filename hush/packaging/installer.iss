; Inno Setup script for hush-setup.exe. Built by packaging/build.ps1 (needs Inno Setup 6).
#define AppVersion GetEnv("HUSH_VERSION")
#if AppVersion == ""
  #define AppVersion "1.4.0"
#endif

[Setup]
AppId={{6E7C2E61-4C3B-4E7E-9C65-0B1D7E9A5F21}
AppName=hush.
AppVersion={#AppVersion}
AppPublisher=hush.
AppPublisherURL=https://github.com/VishwakVemuru/hush
DefaultDirName={localappdata}\Programs\hush
DefaultGroupName=hush.
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=hush-setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\hush.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Add a desktop shortcut"; Flags: checkedonce
Name: "startup"; Description: "Start hush. with Windows (quietly, in the tray)"; Flags: unchecked

[Files]
Source: "..\dist\hush\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\hush."; Filename: "{app}\hush.exe"
Name: "{autodesktop}\hush."; Filename: "{app}\hush.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "hush"; \
  ValueData: """{app}\hush.exe"" --tray"; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\hush.exe"; Description: "Open hush."; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c taskkill /im hush.exe /f"; Flags: runhidden; RunOnceId: "killhush"
