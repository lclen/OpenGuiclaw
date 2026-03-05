[Setup]
AppName=openGuiclaw
AppVersion={#AppVersion}
AppId={{dad829f5-504b-4a54-86fc-ba73006122c8}
DefaultDirName={autopf}\openGuiclaw
DefaultGroupName=openGuiclaw
OutputDir=output
OutputBaseFilename=openGuiclaw_Setup_{#AppVersion}
SetupIconFile=static\favicon.ico
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
DisableWelcomePage=no
; 允许同版本覆盖安装（修复/重装场景）
AllowDowngrade=yes

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "额外图标:"
Name: "addtopath"; Description: "将 openGuiclaw 安装目录添加至用户系统环境变量 (PATH)，用于命令行全局调用"; GroupDescription: "功能辅助:"

[Files]
Source: "dist\openGuiclaw\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\openGuiclaw 本地助理"; Filename: "{app}\openGuiclaw.exe"
Name: "{autodesktop}\openGuiclaw"; Filename: "{app}\openGuiclaw.exe"; Tasks: desktopicon

[Code]
// ─────────────────────────────────────────────────────────────────────────────
// 卸载旧版本：在安装开始前检测注册表中的旧版本并静默卸载
// ─────────────────────────────────────────────────────────────────────────────
function GetUninstallString(): string;
var
  sUnInstPath: string;
  sUnInstallString: string;
begin
  sUnInstPath := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}_is1';
  sUnInstallString := '';
  if not RegQueryStringValue(HKLM, sUnInstPath, 'UninstallString', sUnInstallString) then
    RegQueryStringValue(HKCU, sUnInstPath, 'UninstallString', sUnInstallString);
  Result := sUnInstallString;
end;

function IsUpgrade(): boolean;
begin
  Result := (GetUninstallString() <> '');
end;

function UnInstallOldVersion(): integer;
var
  sUnInstallString: string;
  iResultCode: integer;
begin
  Result := 0;
  sUnInstallString := GetUninstallString();
  if sUnInstallString <> '' then begin
    sUnInstallString := RemoveQuotes(sUnInstallString);
    // /SILENT 静默卸载，/NORESTART 不重启，保留用户数据（data/ 目录）
    if Exec(sUnInstallString, '/SILENT /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, iResultCode) then
      Result := iResultCode
    else
      Result := -1;
  end;
end;

function InitializeSetup(): boolean;
var
  iResultCode: integer;
begin
  Result := True;
  if IsUpgrade() then begin
    if MsgBox('检测到已安装旧版本的 openGuiclaw。'#13#10#13#10
              '点击"是"将先卸载旧版本再安装新版本（您的配置和数据不会被删除）。'#13#10
              '点击"否"将直接覆盖安装。',
              mbConfirmation, MB_YESNO) = IDYES then begin
      iResultCode := UnInstallOldVersion();
      if iResultCode <> 0 then begin
        MsgBox('旧版本卸载失败（错误码: ' + IntToStr(iResultCode) + '）。'#13#10
               '请手动卸载后重试，或点击确定继续强制安装。',
               mbError, MB_OK);
      end;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Paths: string;
begin
  if CurStep = ssInstall then
  begin
    // 开始正式搬运文件前，强行处决可能占用文件的进程
    Exec('taskkill', '/F /IM openGuiclaw.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
  
  if CurStep = ssPostInstall then
  begin
    // 如果客户勾选了写入 PATH 以激活短令调用
    if IsTaskSelected('addtopath') then
    begin
      if RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'PATH', Paths) then
      begin
        if Pos(ExpandConstant('{app}'), Paths) = 0 then
        begin
          Paths := Paths + ';' + ExpandConstant('{app}');
          RegWriteStringValue(HKEY_CURRENT_USER, 'Environment', 'PATH', Paths);
        end;
      end
      else
      begin
        RegWriteStringValue(HKEY_CURRENT_USER, 'Environment', 'PATH', ExpandConstant('{app}'));
      end;
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
  Paths: string;
  AppPath: string;
begin
  if CurUninstallStep = usUninstall then
  begin
    // 完全卸载前也要杀毒进程以免锁定
    Exec('taskkill', '/F /IM openGuiclaw.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
  
  if CurUninstallStep = usPostUninstall then
  begin
    if MsgBox('是否同时清除您的所有配置数据、AI 会话历史以及沙盒全局缓存？'#13#10'(对应将完全静默删除：~/.openGuiclaw)', mbConfirmation, MB_YESNO) = IDYES then
    begin
      DelTree(ExpandConstant('{userprofile}\.openGuiclaw'), True, True, True);
    end;
    
    // 自动寻找并剥离环境变量
    if RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'PATH', Paths) then
    begin
      AppPath := ExpandConstant('{app}');
      StringChangeEx(Paths, AppPath + ';', '', True);
      StringChangeEx(Paths, ';' + AppPath, '', True);
      StringChangeEx(Paths, AppPath, '', True);
      RegWriteStringValue(HKEY_CURRENT_USER, 'Environment', 'PATH', Paths);
    end;
  end;
end;
