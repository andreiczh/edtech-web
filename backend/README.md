# backend — голосовая петля (FastAPI)

`микрофон → STT → LLM → TTS → звук обратно`. Плюс разбор монолога ЕГЭ.

**Стек — всё бесплатное и доступное из РФ без VPN:**
- **STT** — [faster-whisper](https://github.com/SYSTRAN/faster-whisper) **локально**,
  модель `base.en` (офлайн, без ключа, без гео-блока)
- **LLM** — **Mistral** (`api.mistral.ai/v1`, `mistral-small-latest`). Свапается через `.env`
  на любой OpenAI-совместимый эндпоинт, но рабочий вариант из РФ ровно один — см. `.env.example`.
- **TTS** — [edge-tts](https://github.com/rany2/edge-tts) (нейро-голоса Microsoft, без ключа)

> Нужен **один** ключ — Mistral (`LLM_API_KEY`). STT и TTS работают без ключей.

## Запуск на Windows

```powershell
cd C:\Users\Lenovo\edtech-copilot-web
git pull --rebase
npm.cmd run build
cd backend
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Или одной командой: `powershell -ExecutionPolicy Bypass -File run.ps1` — он делает
то же самое, включая пересборку фронта.

**`npm run build` обязателен после каждого `git pull`** — бэкенд раздаёт собранный `dist/`,
которого нет в git. Без сборки увидишь старый интерфейс или отладочную страницу.

**Первый старт долгий** — faster-whisper один раз качает модель (~150 МБ) без индикатора
прогресса. Ждать строку `Uvicorn running on http://127.0.0.1:8000`.

## Эндпоинты

| Метод | Путь | Что делает |
|---|---|---|
| GET | `/` | раздаёт собранный фронт (`../dist`); если его нет — `test.html` |
| GET | `/health` | какой STT/LLM/TTS поднят, есть ли ключ (значение не печатается) |
| GET | `/test` | отладочная страница, показывает задержку по стадиям |
| POST | `/talk` | non-streaming разговор: аудио → STT → LLM → TTS → JSON |
| POST | `/talk_stream` | стриминг ответа: пофразный TTS, NDJSON-чанки. Фронт ходит сюда |
| POST | `/monologue` | разбор монолога ЕГЭ Задание 4 по критериям ФИПИ (4+3+3=10) |

## Проверка

- `http://localhost:8000/health` — ожидаем `"llm_key": true`,
  `"llm_model": "mistral-small-latest"`.
- `http://localhost:8000/` — приложение. Если открылась отладочная страница,
  значит `dist/` не собран.
- Ошибки читаемые и показывают причину: `STT (faster-whisper) ошибка: …`,
  `LLM ошибка (модель): …`, `TTS (edge-tts) ошибка: …`.

## Настройки (`.env`)

Все с рабочими дефолтами прямо в коде (`main.py:103–109`), `.env` нужен только ради ключа.

| Переменная | Дефолт |
|---|---|
| `LLM_API_KEY` | — (обязательна) |
| `LLM_BASE_URL` | `https://api.mistral.ai/v1` |
| `LLM_MODEL` | `mistral-small-latest` |
| `WHISPER_MODEL` | `base.en` |
| `TTS_VOICE` | `en-US-AvaMultilingualNeural` |

## Грабли

- Запускать **без `--reload`** — он роняет запросы в полёте.
- После `npm run build` бэкенд надо **перезапустить**: наличие `dist/` проверяется
  один раз при импорте модуля.
- `.ps1` — только ASCII (PowerShell 5.1 читает их в CP1251).
- `.env` не создавать Блокнотом: допишет `.txt` и может сохранить в ANSI.
- Конкурентные транскрипции сериализуются — модель whisper одна и на CPU.
  Для одного пользователя не заметно, под пилот надо перемерять.

## Что дальше

Роадмап — в [`../HANDOFF.md`](../HANDOFF.md) §9. Ближайшее: память диалога,
логирование сессий → SQLite, замер конкурентности.
