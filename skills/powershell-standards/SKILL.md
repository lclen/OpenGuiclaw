---
name: powershell-standards
description: 编写、审查和执行 PowerShell 命令或脚本时使用，尤其适合处理中文文本、文件读写、编码设置、脚本规范、错误处理和常见命令模式。用户提到 PowerShell、pwsh、乱码、UTF-8、脚本规范、命令重写、Windows 自动化脚本时应优先使用。
---

# PowerShell Standards

用这个 skill 来保证 PowerShell 命令和脚本在仓库里长期可维护，尤其避免中文文本在读写、重定向、管道和外部程序交互时出现乱码。

## 适用场景

- 用户要求编写 PowerShell 命令或 `.ps1` 脚本
- 用户提到中文乱码、UTF-8、编码异常
- 需要用 PowerShell 读写 Markdown、JSON、配置文件或日志
- 需要把一段 shell 命令改写为更稳的 PowerShell
- 需要为仓库补充 PowerShell 使用规范

## 核心原则

### 1. 中文内容默认按 UTF-8 处理

优先规则：

1. 不要让中文文本经过 PowerShell 默认管道或重定向链路
2. 文件读写必须显式指定 UTF-8
3. 调用 Python 时优先加 `-X utf8`
4. 如必须让 PowerShell 参与文本传输，先设置控制台编码

### 2. 避免这些高风险写法

不要默认使用以下方式处理中文文本：

- `Get-Content file.md | python -`
- `python script.py > file.md`
- `Set-Content file.md $text`
- `Out-File file.md`
- `>>` 追加中文 Markdown

这些写法不一定每次都会坏，但很容易在控制台编码、BOM、重定向和外部程序之间丢字或变成乱码。

### 3. 优先这些稳定写法

#### PowerShell 直接文件读写

```powershell
$utf8 = [System.Text.UTF8Encoding]::new($false)
$text = [System.IO.File]::ReadAllText($path, $utf8)
[System.IO.File]::WriteAllText($path, $text, $utf8)
```

#### Python 直接文件读写

```powershell
python -X utf8 -c "from pathlib import Path; print(Path(r'D:\repo\README.md').read_text(encoding='utf-8'))"
```

```powershell
python -X utf8 -c "from pathlib import Path; Path(r'D:\repo\README.md').write_text('中文内容', encoding='utf-8')"
```

#### 控制台编码兜底

```powershell
[Console]::InputEncoding  = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding           = [System.Text.UTF8Encoding]::new($false)
```

> [!IMPORTANT]
> 这只是兜底，不应替代“显式 UTF-8 文件读写”。

## 脚本规范

### 1. 统一脚本头

新建 `.ps1` 时，默认以这个结构起手：

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

[Console]::InputEncoding  = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding           = [System.Text.UTF8Encoding]::new($false)

param(
    [Parameter(Mandatory)]
    [string]$Path
)
```

### 2. 路径和文件

- 优先用 `-LiteralPath`，减少空格、方括号、通配符带来的路径误判
- 目录拼接优先 `Join-Path`
- 判断存在性优先 `Test-Path -LiteralPath`
- 创建目录优先 `New-Item -ItemType Directory -Force`

### 3. 错误处理

- 默认设置 `$ErrorActionPreference = 'Stop'`
- 对关键块使用 `try { ... } catch { ... }`
- 不要依赖沉默失败
- 只在确有必要时使用 `-ErrorAction SilentlyContinue`

### 4. 输出规范

- 给调用方返回数据时，优先 `Write-Output`
- 给用户看提示时，才用 `Write-Host`
- 结构化数据优先输出对象，再按需要 `ConvertTo-Json`
- 不要把日志输出和返回值混在一起

### 5. 命名规范

- 函数名优先用 PowerShell Approved Verbs，如 `Get-`、`Set-`、`New-`、`Remove-`、`Test-`
- 变量名用清晰英文，不用单字母缩写
- 参数名尽量显式，例如 `$ProjectRoot`、`$OutputPath`

## 常见任务推荐写法

### 读取 UTF-8 Markdown

```powershell
$utf8 = [System.Text.UTF8Encoding]::new($false)
$content = [System.IO.File]::ReadAllText('D:\repo\README.md', $utf8)
```

### 写入 UTF-8 Markdown

```powershell
$utf8 = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText('D:\repo\README.md', $content, $utf8)
```

### 追加日志

```powershell
$utf8 = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::AppendAllText('D:\repo\logs\run.log', "`r`n$newLine", $utf8)
```

### 读取和写入 JSON

```powershell
$utf8 = [System.Text.UTF8Encoding]::new($false)
$json = [System.IO.File]::ReadAllText($configPath, $utf8) | ConvertFrom-Json
$json.enabled = $true
[System.IO.File]::WriteAllText(
    $configPath,
    ($json | ConvertTo-Json -Depth 10),
    $utf8
)
```

### 调用外部程序

```powershell
$result = & python -X utf8 .\script.py --input $InputPath
if ($LASTEXITCODE -ne 0) {
    throw "Python script failed with exit code $LASTEXITCODE"
}
```

### 查找文件

```powershell
Get-ChildItem -LiteralPath $ProjectRoot -Recurse -File -Filter *.md
```

### 文本搜索

```powershell
Get-ChildItem -LiteralPath $ProjectRoot -Recurse -File |
    Select-String -Pattern 'project-tracker' -CaseSensitive
```

## 协作规则

当你为用户写 PowerShell 时，按这个顺序决策：

1. 先判断任务是否涉及中文文本、Markdown、JSON、日志或跨程序文本传输
2. 如果涉及，默认切到显式 UTF-8 文件读写方案
3. 如果只是列目录、找文件、启动程序，可直接写普通 PowerShell
4. 如果命令会长期复用，优先整理成带 `param()` 的脚本，而不是一次性命令串

## 审查清单

输出 PowerShell 方案前，快速自检：

- 是否避免了高风险的中文管道或重定向
- 是否显式指定了 UTF-8
- 是否使用了 `Set-StrictMode` 和 `$ErrorActionPreference = 'Stop'`
- 是否把“用户提示”和“程序输出”分开
- 是否使用了更稳的路径写法，如 `-LiteralPath` 和 `Join-Path`
- 是否适合抽成 `.ps1` 而不是一长串单行命令

## 参考资料

- [UTF-8 备忘录](./references/utf8-cheatsheet.md)
- [脚本模板](./references/script-template.ps1)
