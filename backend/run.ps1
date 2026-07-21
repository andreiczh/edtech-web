# run.ps1 - update, rebuild and start the server on Windows in one command.
# Run:  powershell -ExecutionPolicy Bypass -File run.ps1
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads .ps1 as the
# system ANSI codepage (CP1251 on RU Windows), so Cyrillic / em-dashes here
# would break the parser.
#
# NOTE: $ErrorActionPreference does NOT react to exit codes of native programs
# (git.exe, npm.cmd, pip.exe), so every step checks $LASTEXITCODE by hand.
# Without that a failed "git pull" is skipped silently and the server starts
# on stale code.

$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\.."

function Assert-Ok($step) {
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "FAILED: $step (exit code $LASTEXITCODE)." -ForegroundColor Red
        Write-Host "Read the error above. Common cases:" -ForegroundColor Yellow
        Write-Host "  'unstaged changes'  -> run: git stash" -ForegroundColor Yellow
        Write-Host "  'unmerged files'    -> run: git rebase --abort, then ask the Mac agent" -ForegroundColor Yellow
        Write-Host "  'SSL' / 'unable to access' -> network problem. Turn the VPN OFF:" -ForegroundColor Yellow
        Write-Host "     this project does not need it, and it can break git and the API." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Server NOT started. Press Enter to close." -ForegroundColor Red
        Read-Host | Out-Null
        exit 1
    }
}

# Port check first: VPN / proxy clients (v2rayN, clash, ...) open local
# listeners, and if one took :8000 uvicorn dies on bind with WinError 10048
# at the very last step - after several minutes of pulling and building.
$busy = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    $owner = (Get-Process -Id $busy[0].OwningProcess -ErrorAction SilentlyContinue).ProcessName
    Write-Host "Port 8000 is already taken by '$owner' (pid $($busy[0].OwningProcess))." -ForegroundColor Red
    Write-Host "If that is an old server of ours - close its window and run this again." -ForegroundColor Yellow
    Write-Host "If it is a VPN / proxy client - change its local port or stop it." -ForegroundColor Yellow
    Read-Host "Press Enter to close" | Out-Null
    exit 1
}

# 1) pull the latest code pushed from the Mac.
#    --autostash: local edits are set aside and put back automatically instead
#    of blocking the pull. Note it also makes git return 0 even if putting them
#    back conflicts - so the working tree is still expected to stay clean.
Set-Location $root
Write-Host "[1/4] git pull" -ForegroundColor Cyan
git pull --rebase --autostash
Assert-Ok "git pull"

# 2) frontend deps + build. The backend serves ../dist, which is NOT in git,
#    so skipping the build means serving a stale UI. npm.cmd (not npm) bypasses
#    the PowerShell shim blocked by ExecutionPolicy.
#
#    "npm ci", NOT "npm install": install rewrites package-lock.json on Windows
#    (it drops the macOS-only optional binaries of rollup/esbuild that the Mac
#    recorded), which then blocks every future "git pull" with "unstaged
#    changes". "npm ci" installs strictly from the lock file and never writes
#    to it. Run it only when the lock file is newer than node_modules -
#    dependencies change rarely, and a full reinstall on every server start
#    would cost a minute for nothing.
Write-Host "[2/4] frontend deps + build" -ForegroundColor Cyan
$needDeps = $true
$nm = Join-Path $root "node_modules"
if (Test-Path $nm) {
    $lockTime = (Get-Item (Join-Path $root "package-lock.json")).LastWriteTime
    if ((Get-Item $nm).LastWriteTime -ge $lockTime) { $needDeps = $false }
}
if ($needDeps) {
    Write-Host "      dependencies changed - running npm ci" -ForegroundColor Cyan
    npm.cmd ci
    Assert-Ok "npm ci"
} else {
    Write-Host "      dependencies unchanged - skipping install" -ForegroundColor DarkGray
}
npm.cmd run build
Assert-Ok "npm run build"

# 3) python environment
Set-Location $PSScriptRoot
Write-Host "[3/4] python env" -ForegroundColor Cyan
if (-not (Test-Path ".venv")) {
    py -3.11 -m venv .venv
    Assert-Ok "create venv"
}
.\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
Assert-Ok "pip install"

# 4) .env with the single API key (Mistral)
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ""
    Write-Host "Created .env from the template." -ForegroundColor Yellow
    Write-Host "Put your Mistral key into LLM_API_KEY, save, close Notepad," -ForegroundColor Yellow
    Write-Host "then run this script again." -ForegroundColor Yellow
    Start-Process notepad ".env" -Wait
    exit 1
}

# 5) start. No --reload: it restarts on file writes and drops in-flight
#    requests. On the FIRST start the STT model downloads (~150 MB) with no
#    progress bar - wait for the "Uvicorn running" line before using the app.
Write-Host "[4/4] starting server" -ForegroundColor Cyan
Write-Host "First run downloads the STT model - wait for 'Uvicorn running'." -ForegroundColor Cyan
Write-Host ""
Write-Host "DO NOT press Ctrl+C in this window just to copy text - it STOPS the server." -ForegroundColor Yellow
Write-Host "To copy: select with the mouse, then press Enter (or Ctrl+Shift+C)." -ForegroundColor Yellow
Write-Host ""

# Run uvicorn DIRECTLY in the foreground. Do not pipe it and do not use "2>&1":
# uvicorn logs to stderr, and redirecting a native command's stderr makes
# PowerShell wrap every log line into an error record - which, together with
# $ErrorActionPreference = "Stop" above, kills the script on the very first
# "INFO: Started server process" line. Learned the hard way; do not "improve".
$ErrorActionPreference = "Continue"
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
