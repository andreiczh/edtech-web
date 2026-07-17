# run.ps1 - update and start the backend server on Windows in one command.
# Run:  powershell -ExecutionPolicy Bypass -File run.ps1
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads .ps1 as the
# system ANSI codepage (CP1251 on RU Windows), so Cyrillic / em-dashes here
# would break the parser.
$ErrorActionPreference = "Stop"

# 1) pull the latest code from GitHub (what was pushed from the Mac)
Set-Location "$PSScriptRoot\.."
git pull
Set-Location "$PSScriptRoot"

# 2) python environment
if (-not (Test-Path ".venv")) { py -3.11 -m venv .venv }
.\.venv\Scripts\Activate.ps1
pip install -q -r requirements.txt

# 3) .env with API keys
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env - fill in your keys (GROQ_API_KEY, PROVOD_*), then run this again." -ForegroundColor Yellow
    notepad .env
    exit 1
}

# 4) start. No --reload: it restarts the server on file writes and drops
#    in-flight requests. On the FIRST start the STT model downloads (~150 MB) -
#    wait for the line "Uvicorn running on http://0.0.0.0:8000" before using it.
Write-Host "Starting server. On first run it downloads the STT model - wait for 'Uvicorn running'." -ForegroundColor Cyan
uvicorn main:app --host 0.0.0.0 --port 8000
