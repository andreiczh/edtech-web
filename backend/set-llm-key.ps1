# set-llm-key.ps1 - replace ONLY the LLM_API_KEY line in backend\.env.
# Every other line (bot token, admin key, database url, salts) stays as it is.
# The old set-key.ps1 rewrites the whole file - do not use it after 29.09.2026.
#
# Run (new PowerShell window opens in C:\Users\Lenovo):
#   powershell -ExecutionPolicy Bypass -File C:\Users\Lenovo\edtech-copilot-web\backend\set-llm-key.ps1
#
# The key is typed blind: not shown on screen, not stored in history, never
# printed back. Paste into the prompt with a RIGHT mouse click.
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads .ps1 as the
# system ANSI codepage (CP1251 on RU Windows), so Cyrillic would break parsing.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "Replaces LLM_API_KEY in backend\.env. Other lines are kept." -ForegroundColor Cyan
Write-Host "Paste the key with a RIGHT mouse click, then press Enter. It will NOT be shown." -ForegroundColor Cyan
Write-Host ""

$sec  = Read-Host "API key" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
$key  = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
if ($key) { $key = $key.Trim() }

if (-not $key -or $key.Length -lt 8) {
    Write-Host "Empty or suspiciously short - nothing was changed." -ForegroundColor Red
    Read-Host "Press Enter to close" | Out-Null
    exit 1
}

$path  = Join-Path $PSScriptRoot ".env"
$lines = @()
if (Test-Path $path) {
    Copy-Item $path (Join-Path $PSScriptRoot ".env.backup") -Force
    $lines = @(Get-Content $path -Encoding UTF8 | Where-Object { $_ -notmatch '^\s*LLM_API_KEY\s*=' })
}
$kept   = $lines.Count
$lines += ("LLM_API_KEY=" + $key)
$utf8   = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($path, [string[]]$lines, $utf8)
Remove-Variable key, sec, bstr

Write-Host ""
Write-Host ("Done. Key saved, " + $kept + " other lines kept. Old file: backend\.env.backup") -ForegroundColor Green
Write-Host "Now tell Claude in the chat: key is in .env" -ForegroundColor Green
Read-Host "Press Enter to close" | Out-Null
