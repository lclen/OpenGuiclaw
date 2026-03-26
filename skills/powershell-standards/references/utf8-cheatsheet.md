# UTF-8 备忘录

## 最稳的三条

1. 中文文件不要走 PowerShell 默认管道或重定向。
2. 文件读写显式指定 UTF-8。
3. 调 Python 时优先加 `-X utf8`。

## 推荐片段

### 控制台编码兜底

```powershell
[Console]::InputEncoding  = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding           = [System.Text.UTF8Encoding]::new($false)
```

### 读取 UTF-8 文件

```powershell
$utf8 = [System.Text.UTF8Encoding]::new($false)
$text = [System.IO.File]::ReadAllText($Path, $utf8)
```

### 写入 UTF-8 文件

```powershell
$utf8 = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($Path, $Text, $utf8)
```

### 追加 UTF-8 文件

```powershell
$utf8 = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::AppendAllText($Path, $AppendText, $utf8)
```

### Python 读写

```powershell
python -X utf8 -c "from pathlib import Path; print(Path(r'D:\repo\README.md').read_text(encoding='utf-8'))"
```

```powershell
python -X utf8 -c "from pathlib import Path; Path(r'D:\repo\README.md').write_text('中文内容', encoding='utf-8')"
```

## 高风险写法

- `Get-Content ... | python -`
- `... > 中文文件.md`
- `Set-Content` / `Out-File` 直接写 Markdown
- `>>` 直接追加中文
