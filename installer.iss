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
CloseApplications=no
RestartApplications=no
WizardStyle=modern
LicenseFile=DISCLAIMER_CN.txt

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "界面与系统:"
Name: "addtopath"; Description: "将 openGuiclaw 安装目录添加至系统环境变量 (PATH)"; GroupDescription: "界面与系统:"
Name: "alias_og"; Description: "注册终端别名 'og' (方便在命令提示符中直接输入 'og' 启动)"; GroupDescription: "界面与系统:"; Flags: unchecked

Name: "closeprocesses"; Description: "【稳定】强制关闭运行中的本体应用及 Node 进程，防止文件占用"; GroupDescription: "清理重置选项:"
Name: "cleanvenv"; Description: "【重装】删除旧的 Python 依赖缓存池，以便重新下载 (可解依赖冲突)"; GroupDescription: "清理重置选项:"; Flags: unchecked
Name: "clearuserdata"; Description: "【危险】永久删除包含 API 密钥、聊天历史、系统备份在内的全部用户数据"; GroupDescription: "清理重置选项:"; Flags: unchecked

[Files]
; 打包整个发布目录（含启动器 exe + 项目源码）
Source: "dist\openGuiclaw\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\openGuiclaw 本地助理"; Filename: "{app}\openGuiclaw.exe"
Name: "{autodesktop}\openGuiclaw"; Filename: "{app}\openGuiclaw.exe"; Tasks: desktopicon

[Run]
; 安装完成后静默触发首次 venv 初始化（不等待，让用户自己启动）
; 如需安装时自动初始化，可改为 Flags: waituntilterminated
Filename: "{app}\openGuiclaw.exe"; Description: "立即启动 openGuiclaw（初始化环境）"; Flags: postinstall nowait skipifsilent

[Code]
// ─────────────────────────────────────────────────────────────────────────────
// 检测 Edge WebView2 Runtime 是否已安装
// ─────────────────────────────────────────────────────────────────────────────
function IsWebView2Installed(): Boolean;
var
  Version: string;
begin
  Result := RegQueryStringValue(HKLM,
    'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'pv', Version) or
    RegQueryStringValue(HKCU,
    'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'pv', Version);
end;

// ─────────────────────────────────────────────────────────────────────────────
// 卸载旧版本
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
    if Exec(sUnInstallString, '/SILENT /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, iResultCode) then
      Result := iResultCode
    else
      Result := -1;
  end;
end;

procedure KillRelatedProcesses();
var
  ResultCode: Integer;
begin
  // 改为正常窗口运行 PowerShell，防止被杀毒软件判定为恶意后台行为
  Exec('powershell.exe', '-NoProfile -Command "Get-Process openGuiclaw -ErrorAction SilentlyContinue | Stop-Process -Force"', '', SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode);
  Exec('powershell.exe', '-NoProfile -Command "Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force"', '', SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode);
  Exec('powershell.exe', '-NoProfile -Command "Get-Process og -ErrorAction SilentlyContinue | Stop-Process -Force"', '', SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode);
  
  // 兜底：如果有些老系统 PS 不行，再用 taskkill
  Exec('taskkill', '/F /IM openGuiclaw.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec('taskkill', '/F /IM node.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec('taskkill', '/F /IM og.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function InitializeSetup(): boolean;
var
  iResultCode: integer;
begin
  Result := True;

  // 检测 Edge WebView2 Runtime
  if not IsWebView2Installed() then begin
    if MsgBox('未检测到 Microsoft Edge WebView2 Runtime。' + #13#10 + #13#10 +
              'openGuiclaw 需要 WebView2 才能显示界面窗口。' + #13#10 +
              '点击"是"前往微软官网下载安装（推荐），点击"否"跳过继续安装。',
              mbConfirmation, MB_YESNO) = IDYES then begin
      ShellExec('open',
        'https://developer.microsoft.com/zh-cn/microsoft-edge/webview2/',
        '', '', SW_SHOWNORMAL, ewNoWait, iResultCode);
    end;
  end;

  // （取消通过丑陋的 MsgBox 进行打断询问，改为通过下方 Tasks 任务复选框让用户自己选）
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssInstall then
  begin
    // 如果勾选了强制关闭进程（哪怕依靠 CloseApplications=no，我们也双保险再杀一次）
    if WizardIsTaskSelected('closeprocesses') then
    begin
      KillRelatedProcesses();
    end;

    // 清空 Python 环境依赖缓存
    if WizardIsTaskSelected('cleanvenv') then
    begin
      Exec('cmd', '/C rmdir /S /Q "' + ExpandConstant('{userprofile}') + '\.openguiclaw\venv"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;

    // 彻底清除所有用户信息（危险）
    if WizardIsTaskSelected('clearuserdata') then
    begin
      Exec('cmd', '/C rmdir /S /Q "' + ExpandConstant('{userprofile}') + '\.openguiclaw"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
  end;

  if CurStep = ssPostInstall then
  begin
    // 如果勾选了增加终端别名（即在安装目录生成一个 og.bat 指向主程序）
    if WizardIsTaskSelected('alias_og') then
    begin
      SaveStringToFile(ExpandConstant('{app}\og.bat'), '@echo off' + #13#10 + '"%~dp0openGuiclaw.exe" %*', False);
    end;

    if WizardIsTaskSelected('addtopath') then
    begin
      // 正常显示窗口执行，提高杀毒软件兼容性
      Exec('powershell.exe', '-NoProfile -Command "' +
        '$p = [Environment]::GetEnvironmentVariable(''Path'', ''User''); ' +
        '$appDir = ''' + ExpandConstant('{app}') + '''; ' +
        'if ($p -split '';'' -notcontains $appDir) { ' +
        '  [Environment]::SetEnvironmentVariable(''Path'', ($p + '';'' + $appDir).Trim('';''), ''User''); ' +
        '}"', '', SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    KillRelatedProcesses();
  end;

  if CurUninstallStep = usPostUninstall then
  begin
    // 询问是否清除 venv（保留用户数据）
    if MsgBox('是否同时删除 Python 环境缓存 (env / venv)？' + #13#10 +
              '位于: %USERPROFILE%\.openguiclaw\venv' + #13#10 + #13#10 +
              '这可以解决依赖环境损坏的问题。您的配置文件和模型不会被影响。',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      Exec('cmd', '/C rmdir /S /Q "' + ExpandConstant('{userprofile}') + '\.openguiclaw\venv"',
           '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;

    if MsgBox('🚨 危险操作：是否彻底清除所有用户信息？' + #13#10 + #13#10 +
              '这将会永久删除如下处于 %USERPROFILE%\.openguiclaw 的内容：' + #13#10 +
              '- 模型 API Key 及其所有自定义配置' + #13#10 +
              '- AI 会话历史记录与备忘记忆' + #13#10 +
              '- 所有其它用户设置' + #13#10 + #13#10 +
              '注意：点击"是"将不可逆地销毁所有个人数据！',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      Exec('cmd', '/C rmdir /S /Q "' + ExpandConstant('{userprofile}') + '\.openguiclaw"',
           '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;

    // 正常显示窗口执行，从 PATH 中精准移除
    Exec('powershell.exe', '-NoProfile -Command "' +
      '$p = [Environment]::GetEnvironmentVariable(''Path'', ''User''); ' +
      '$appDir = ''' + ExpandConstant('{app}') + '''; ' +
      'if ($p -split '';'' -contains $appDir) { ' +
      '  $np = ($p -split '';'' | Where-Object { $_ -ne $appDir }) -join '';''; ' +
      '  [Environment]::SetEnvironmentVariable(''Path'', $np, ''User''); ' +
      '}"', '', SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode);
  end;
end;
