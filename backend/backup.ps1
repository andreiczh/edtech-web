# Nightly backup of the Pingo AI database (Neon has no backups on free tier).
# ASCII only: Windows PowerShell 5.1 reads .ps1 as CP1251, Cyrillic breaks it.
#
# Usage:
#   .\backup.ps1                 - key from PINGO_ADMIN_KEY env var
#   .\backup.ps1 -Key "..."      - key passed explicitly
#   .\backup.ps1 -Url "http://127.0.0.1:8000/admin/backup?images=1"   - test run
#
# Schedule (Task Scheduler, run once):
#   schtasks /Create /SC DAILY /ST 03:30 /TN "PingoBackup" /TR ^
#     "powershell -NoProfile -File C:\Users\Lenovo\edtech-copilot-web\backend\backup.ps1"
#   (env var PINGO_ADMIN_KEY must be set for the user, see docs/MONITORING.md)
#
# WHY THE CHECKS BELOW ARE NOT OPTIONAL. A scheduled task fails silently: nobody
# watches its exit code, and a backup that has been saving 200-byte error pages
# for a month is worse than no backup - it looks like protection while being
# none. So every run is appended to backup.log, and a dump is not accepted until
# it parses as JSON and actually contains rows.

param(
    [string]$Key = $env:PINGO_ADMIN_KEY,
    [string]$Url = "https://pingo-ai-dpd9.onrender.com/admin/backup?images=1",
    [string]$Dir = "$env:USERPROFILE\pingo-backups"
)

if (-not (Test-Path $Dir)) { New-Item -ItemType Directory -Force $Dir | Out-Null }
$log = Join-Path $Dir "backup.log"

function Write-Log($text) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $text
    Add-Content -Path $log -Value $line -Encoding utf8
    Write-Output $line
}

if (-not $Key) {
    Write-Log "FAILED: no admin key. Set PINGO_ADMIN_KEY or pass -Key."
    exit 1
}

$stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$file = Join-Path $Dir "pingo-$stamp.json"

try {
    Invoke-WebRequest -Uri $Url -Headers @{ "X-Admin-Key" = $Key } `
        -OutFile $file -TimeoutSec 300 -UseBasicParsing
} catch {
    Write-Log "FAILED: request error - $($_.Exception.Message)"
    exit 1
}

$size = (Get-Item $file).Length
if ($size -lt 100) {
    Write-Log "FAILED: file is $size bytes - wrong key or wrong URL."
    Remove-Item $file -Force
    exit 1
}

# A wrong key answers with a JSON error page, and that page is well over 100
# bytes. The only honest check is to open the dump and count what is inside.
try {
    $dump = Get-Content $file -Raw -Encoding utf8 | ConvertFrom-Json
} catch {
    Write-Log "FAILED: file is not valid JSON - $($_.Exception.Message)"
    Remove-Item $file -Force
    exit 1
}

# The dump is {created_at, storage, tables: {...}}. Older dumps had the tables
# at the top level, so both shapes are accepted.
$tables = $dump
if ($dump.PSObject.Properties.Name -contains "tables") { $tables = $dump.tables }

$counts = @()
$rows = 0
foreach ($table in @("accounts", "results", "mistakes", "disputes", "tasks")) {
    $n = 0
    if (($tables.PSObject.Properties.Name -contains $table) -and $tables.$table) {
        $n = @($tables.$table).Count
    }
    $rows += $n
    $counts += "$table=$n"
}
if ($rows -eq 0) {
    Write-Log "FAILED: dump has no rows at all - check the key."
    Remove-Item $file -Force
    exit 1
}

Write-Log ("OK: {0} ({1} KB) {2}" -f (Split-Path $file -Leaf),
    [math]::Round($size / 1KB), ($counts -join " "))

# Keep the last 14 dumps, drop older ones.
Get-ChildItem $Dir -Filter "pingo-*.json" | Sort-Object Name -Descending |
    Select-Object -Skip 14 | Remove-Item -Force

# Explicit success code. Without it PowerShell leaves $LASTEXITCODE from
# whatever ran before, and Task Scheduler shows a green run as failed - which
# is how a working backup gets "fixed" until it stops working.
exit 0
