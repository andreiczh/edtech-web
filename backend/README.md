# Бэкенд — спайк голосовой петли (Этап 1)

Минимальный бэкенд: `микрофон → STT → LLM → TTS → звук обратно`, push-to-talk,
без стриминга. Цель — убедиться, что петля живёт, и замерить задержку.

Стек (API-путь, GPU не нужна):
- **STT** — Groq Whisper (free tier)
- **LLM** — provod.ai (оплата из РФ рублями)
- **TTS** — Windows SAPI через `pyttsx3` (для спайка; позже → Kokoro/Qwen3-TTS)

## Запуск на Windows (PowerShell)

```powershell
cd backend

# 1) виртуальное окружение
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2) зависимости
pip install -r requirements.txt

# 3) ключи: скопируй .env.example в .env и впиши свои
copy .env.example .env
notepad .env

# 4) запуск
uvicorn main:app --reload --port 8000
```

Открой **http://localhost:8000/** — там страница записи микрофона (`test.html`).
Нажми «Говорить», скажи фразу по-английски, нажми ещё раз. Внизу увидишь задержку
по стадиям (`stt / llm / tts / total`).

## Где взять ключи
- **Groq:** console.groq.com → API Keys (бесплатно).
- **provod.ai:** регистрация → пополнение рублями → API key + base URL + имя модели
  (посмотри точное имя модели в их каталоге, впиши в `LLM_MODEL`).

## Что дальше (Этап 2)
- Завернуть петлю в **Pipecat** (стриминг STT→LLM→TTS + Silero VAD + barge-in), цель <3с.
- Поменять SAPI-TTS на **Kokoro-82M** (CPU, англ., бесплатно) или API-TTS для качества.
- Подключить основной фронт (`../`) к бэкенду по WebSocket.
- Логирование сессий (режим, длительность, реплики, латентность) → SQLite.

## Примечания
- `main.py` отдаёт `test.html` на `/`, поэтому микрофон работает (localhost — secure context).
- `pyttsx3` использует Windows SAPI; голос лучше выбрать английский (David/Zira) — код
  пытается сделать это автоматически.
