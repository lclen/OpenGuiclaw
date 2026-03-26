Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

[Console]::InputEncoding  = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding           = [System.Text.UTF8Encoding]::new($false)

param(
    [Parameter(Mandatory)]
    [string]$InputPath,

    [string]$OutputPath
)

$utf8 = [System.Text.UTF8Encoding]::new($false)

try {
    $content = [System.IO.File]::ReadAllText($InputPath, $utf8)

    if ($OutputPath) {
        [System.IO.File]::WriteAllText($OutputPath, $content, $utf8)
        Write-Output $OutputPath
    } else {
        Write-Output $content
    }
} catch {
    throw "PowerShell script failed: $($_.Exception.Message)"
}
