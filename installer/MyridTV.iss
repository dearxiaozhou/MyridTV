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
; 不允许记住上次的勾选：每次安装都按默认（不勾＝普通安装，不动数据目录）
UsePreviousTasks=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\MyridTV.exe
CloseApplications=yes
CloseApplicationsFilter=MyridTV.exe,MyridTV-Desktop.exe
RestartApplications=no

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "portable"; Description: "作为独立实例安装（自带数据目录，与其它 MyridTV 安装互不影响）"; GroupDescription: "附加选项："; Flags: unchecked

[Files]
Source: "{#MyAppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; 勾选「独立实例」时才创建空 user_data\：程序看到它就用自带数据目录（便携模式），并自动使用自己的端口。
; 卸载时绝不动这个目录（里面是用户数据）。
Name: "{app}\user_data"; Tasks: portable; Flags: uninsneveruninstall

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\MyridTV.exe"; WorkingDir: "{app}"; IconFilename: "{app}\MyridTV.exe"
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\MyridTV.exe"; WorkingDir: "{app}"; IconFilename: "{app}\MyridTV.exe"

[Run]
Filename: "{app}\MyridTV.exe"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
