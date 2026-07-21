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
        Write-Host "Fix the error above before starting the server." -ForegroundColor Red
        exit 1
    }
}

# 1) pull the latest code pushed from the Mac
Set-Location $root
Write-Host "[1/4] git pull" -ForegroundColor Cyan
git pull --rebase
Assert-Ok "git pull"

# 2) frontend deps + build. The backend serves ../dist, which is NOT in git,
#    so skipping this means serving a stale UI. npm.cmd (not npm) bypasses the
#    PowerShell shim blocked by ExecutionPolicy.
Write-Host "[2/4] npm install + build" -ForegroundColor Cyan
npm.cmd install
Assert-Ok "npm install"
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
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
