# run.ps1 — обновить и запустить сервер на Windows одной командой.
# Запуск:  powershell -ExecutionPolicy Bypass -File run.ps1
$ErrorActionPreference = "Stop"

# 1) подтянуть свежий код с GitHub (то, что ты запушил с Мака)
Set-Location "$PSScriptRoot\.."
git pull
Set-Location "$PSScriptRoot"

# 2) окружение
if (-not (Test-Path ".venv")) { py -3.11 -m venv .venv }
.\.venv\Scripts\Activate.ps1
pip install -q -r requirements.txt

# 3) .env
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Создан .env — впиши ключи (GROQ_API_KEY, PROVOD_*), потом запусти снова." -ForegroundColor Yellow
    notepad .env
    exit 1
}

# 4) запуск. --host 0.0.0.0 — чтобы сервер был доступен и для туннеля/локальной сети.
uvicorn main:app --reload --host 0.0.0.0 --port 8000
