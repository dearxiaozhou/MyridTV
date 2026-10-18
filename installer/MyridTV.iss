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
; 资产主路径：首装页选的目录（不改就是 {app}\assets）。卸载不删，里面的素材归用户。
Name: "{code:GetAssetsDir}"; Flags: uninsneveruninstall

[INI]
; 只在首装页真的改过目录时写下来：安装目录里的 assets_root.ini 是「安装器预设」，
; 设置页里改的路径优先级更高（写进 app_config.json）。值里的非 ASCII 已转成 \uXXXX，文件恒为纯 ASCII。
Filename: "{app}\_internal\data\assets_root.ini"; Section: "assets"; Key: "root"; String: "{code:GetAssetsDirJson}"; Check: AssetsDirIsCustom; Flags: createkeyifdoesntexist

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\MyridTV.exe"; WorkingDir: "{app}"; IconFilename: "{app}\MyridTV.exe"
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\MyridTV.exe"; WorkingDir: "{app}"; IconFilename: "{app}\MyridTV.exe"

[Run]
Filename: "{app}\MyridTV.exe"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
// ---------------------------------------------------------------------------
// 资产目录选择页（首装时可选自定义，不改就用系统自动指定的 {app}\assets）
// ---------------------------------------------------------------------------
var
  AssetsDirPage: TInputDirWizardPage;
  AssetsDefaultApplied: Boolean;
  AssetsLastDefault: String;

function HexDigitChar(N: Integer): Char;
const
  HexTable = '0123456789ABCDEF';
begin
  Result := HexTable[N + 1];
end;

function JsonEscapePath(const S: String): String;
var
  I: Integer;
  C: Integer;
begin
  Result := '';
  for I := 1 to Length(S) do
  begin
    C := Ord(S[I]);
    if C = Ord('\') then
      Result := Result + '\\'
    else if (C < 32) or (C > 126) then
      // 非 ASCII 一律转成 \uXXXX：写进 ini 的文件恒为纯 ASCII，绕开 ANSI/UTF-8 编码差异
      Result := Result + '\u' + HexDigitChar((C shr 12) and 15) + HexDigitChar((C shr 8) and 15)
                + HexDigitChar((C shr 4) and 15) + HexDigitChar(C and 15)
    else
      Result := Result + S[I];
  end;
end;

function TrimTrailingBackslash(const S: String): String;
begin
  Result := Trim(S);
  if (Length(Result) > 3) and (Copy(Result, Length(Result), 1) = '\') then
    Result := Copy(Result, 1, Length(Result) - 1);
end;

procedure InitializeWizard;
begin
  AssetsDirPage := CreateInputDirPage(wpSelectDir,
    '选择资产目录',
    '生成的图片 / 视频 / 音频 / Blender 预演等素材都放在这个目录里。',
    '不改就用下面的默认位置（软件安装目录下的 assets）。装好后也能在设置页里改，卸载不会删这个目录。',
    False, '');
  AssetsDirPage.Add('资产目录：');
  AssetsDirPage.Values[0] := ExpandConstant('{app}\assets');
  AssetsDefaultApplied := False;
  AssetsLastDefault := '';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  DefaultDir: String;
begin
  Result := True;
  // 用户在上一页可能改了安装位置，这里把默认值同步成「新安装位置下的 assets」
  if (CurPageID = wpSelectDir) and (AssetsDirPage <> nil) then
  begin
    DefaultDir := AddBackslash(WizardDirValue) + 'assets';
    if (not AssetsDefaultApplied) or (Trim(AssetsDirPage.Values[0]) = '')
       or (CompareText(TrimTrailingBackslash(AssetsDirPage.Values[0]), AssetsLastDefault) = 0) then
    begin
      AssetsDirPage.Values[0] := DefaultDir;
      AssetsLastDefault := DefaultDir;
      AssetsDefaultApplied := True;
    end;
  end;
end;

function GetAssetsDir: String;
begin
  if (AssetsDirPage = nil) or (Trim(AssetsDirPage.Values[0]) = '') then
    Result := ExpandConstant('{app}\assets')
  else
    Result := TrimTrailingBackslash(AssetsDirPage.Values[0]);
end;

function GetAssetsDirJson: String;
begin
  Result := JsonEscapePath(GetAssetsDir);
end;

function AssetsDirIsCustom: Boolean;
begin
  // 只有真的偏离默认（{app}\assets）才写配置；保持默认就留空 = 系统自动指定
  Result := (AssetsDirPage <> nil) and (Trim(AssetsDirPage.Values[0]) <> '')
            and (CompareText(TrimTrailingBackslash(AssetsDirPage.Values[0]),
                             ExpandConstant('{app}\assets')) <> 0);
end;
