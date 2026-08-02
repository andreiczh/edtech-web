# Nightly backup of the Pingo AI database (Neon has no backups on free tier).
# ASCII only: Windows PowerShell 5.1 reads .ps1 as CP1251, Cyrillic breaks it.
#
# Usage:
#   .\backup.ps1                 - key from PINGO_ADMIN_KEY env var
#   .\backup.ps1 -Key "..."      - key passed explicitly
#
# Schedule (Task Scheduler, run once):
#   schtasks /Create /SC DAILY /ST 03:30 /TN "PingoBackup" /TR ^
#     "powershell -NoProfile -File C:\Users\Lenovo\edtech-copilot-web\backend\backup.ps1"
#   (env var PINGO_ADMIN_KEY must be set for the user, see docs/MONITORING.md)

param(
    [string]$Key = $env:PINGO_ADMIN_KEY,
    [string]$Url = "https://pingo-ai-dpd9.onrender.com/admin/backup?images=1",
    [string]$Dir = "$env:USERPROFILE\pingo-backups"
)

if (-not $Key) {
    Write-Error "No admin key. Set PINGO_ADMIN_KEY or pass -Key."
    exit 1
}

if (-not (Test-Path $Dir)) { New-Item -ItemType Directory -Force $Dir | Out-Null }

$stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$file = Join-Path $Dir "pingo-$stamp.json"

try {
    Invoke-WebRequest -Uri $Url -Headers @{ "X-Admin-Key" = $Key } `
        -OutFile $file -TimeoutSec 300 -UseBasicParsing
} catch {
    Write-Error "Backup failed: $($_.Exception.Message)"
    exit 1
}

$size = (Get-Item $file).Length
if ($size -lt 100) {
    Write-Error "Backup file suspiciously small ($size bytes) - check the key."
    exit 1
}
Write-Output "OK: $file ($([math]::Round($size/1KB)) KB)"

# Keep the last 14 dumps, drop older ones.
Get-ChildItem $Dir -Filter "pingo-*.json" | Sort-Object Name -Descending |
    Select-Object -Skip 14 | Remove-Item -Force
