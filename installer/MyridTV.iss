#define MyAppName "MyridTV"
; 版本号来自仓库 VERSION（由 build-installer.ps1 通过 /D 注入，唯一事实源）；下面两行只是手工编译时的兜底
#ifndef MyAppVersion
#define MyAppVersion "0.0.0"
#endif
#ifndef MyAppDisplayVersion
#define MyAppDisplayVersion "V0.0.0"
#endif
#define MyAppPublisher "MyridTV"
#ifndef MyAppSource
#define MyAppSource AddBackslash(SourcePath) + "build\\MyridTV"
#endif
#ifndef MyOutputDir
  #define MyOutputDir AddBackslash(SourcePath) + "build\\installer"
#endif
#ifndef MyOutputBaseFilename
#define MyOutputBaseFilename "MyridTV-Setup"
#endif

[Setup]
AppId={{D31C0E54-7A26-4F31-A513-2D94A8AF5F51}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppDisplayVersion}
VersionInfoVersion={#MyAppVersion}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoDescription={#MyAppName} Setup
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\MyridTV
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir={#MyOutputDir}
OutputBaseFilename={#MyOutputBaseFilename}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\MyridTV.exe
CloseApplications=yes
CloseApplicationsFilter=MyridTV.exe,MyridTV-Desktop.exe
RestartApplications=no

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#MyAppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\MyridTV.exe"; WorkingDir: "{app}"; IconFilename: "{app}\MyridTV.exe"
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\MyridTV.exe"; WorkingDir: "{app}"; IconFilename: "{app}\MyridTV.exe"

[Run]
Filename: "{app}\MyridTV.exe"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
