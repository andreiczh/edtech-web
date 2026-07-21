# set-key.ps1 - write backend\.env with the Mistral settings and the API key.
# Run:  powershell -ExecutionPolicy Bypass -File backend\set-key.ps1
#
# The key is typed blind at a prompt: it is never echoed to the screen, never
# stored in the command history, and never printed back. There is no place in
# this file to paste it into - that is the point.
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads .ps1 as the
# system ANSI codepage (CP1251 on RU Windows), so Cyrillic would break parsing.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "This rewrites backend\.env for Mistral." -ForegroundColor Cyan
Write-Host "Paste the key at the prompt below - it will NOT be shown on screen." -ForegroundColor Cyan
Write-Host ""

$sec  = Read-Host "Mistral API key" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
$key  = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

if (-not $key -or $key.Length -lt 8) {
    Write-Host "Empty or suspiciously short - nothing was written." -ForegroundColor Red
    Read-Host "Press Enter to close" | Out-Null
    exit 1
}

if (Test-Path ".env") { Copy-Item ".env" ".env.backup" -Force }

$lines = @(
    "LLM_BASE_URL=https://api.mistral.ai/v1",
    "LLM_MODEL=mistral-small-latest",
    ("LLM_API_KEY=" + $key),
    "WHISPER_MODEL=base.en",
    "TTS_VOICE=en-US-AriaNeural"
)
Set-Content -Path ".env" -Value $lines -Encoding ascii
Remove-Variable key, sec, bstr

Write-Host ""
Write-Host "Written: backend\.env  (previous file kept as .env.backup)" -ForegroundColor Green
Write-Host "Key length is not shown on purpose. Verify with /health: llm_key must be True." -ForegroundColor Green
Write-Host "Next: restart the server with run.ps1" -ForegroundColor Green
Read-Host "Press Enter to close" | Out-Null
