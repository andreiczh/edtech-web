# backend — FastAPI: API, фронт из `dist/`, бот MAX

`микрофон → STT (Mistral Voxtral) → LLM (Mistral) → TTS (Mistral) → звук обратно`,
плюс разбор заданий 39–42 по шкалам ФИПИ (шкалу считает код, модель отвечает
на вопросы эксперта), споры о балле, статистика, бот и вход через MAX.

Нужен **один** ключ — `LLM_API_KEY` (Mistral): распознавание, разбор и озвучка
идут на нём. Запасные пути без ключа: `STT_PROVIDER=local` (faster-whisper),
`TTS_PROVIDER=edge` (edge-tts). Все переменные — [`.env.example`](.env.example).

## Запуск

Одной командой из корня: `docker compose up --build` (см. корневой README).
Без Docker (Windows):

```powershell
cd C:\Users\Lenovo\edtech-copilot-web
npm.cmd ci
npm.cmd run build
cd backend
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

`npm run build` обязателен после каждого `git pull`: бэкенд раздаёт собранный
`dist/`, которого нет в git. Наличие `dist/` проверяется один раз при старте —
после сборки сервер перезапустить. Без `--reload`: он роняет запросы в полёте.

## Маршруты (58, полное описание — `/openapi.json`, `/docs`)

| Группа | Маршруты | Кому |
|---|---|---|
| Вход | `POST /auth/register`, `/auth/login`, `/auth/max` | всем (регистрация — по коду) |
| Ученик | `GET/POST /me/settings`, `GET /me/stats`, `/me/analytics`, `GET/POST /me/favorites`, `POST /me/nickname`, `GET /progress` | `X-Device` |
| Задания | `GET /tasks`, `POST /task_feedback`, `POST /task_dispute`, `GET /feedback/catalog`, `POST /speak`, `GET /pron/weakest` | `X-Device` (банк и справочник — всем) |
| Разговор | `POST /talk_stream` (NDJSON), `POST /talk_review`, `GET /personas`; `POST /talk` и `/monologue` — прежние, фронт ими не пользуется | `X-Device` |
| MAX | `POST /max/webhook`, `GET /max-check`, `POST /max/probe/*` | вебхук — по секрету из токена |
| Служебные | `GET /health`, `GET /ping`, `GET /img/*` | всем |
| Админка | `/admin/*` (обзор, задания, импорт ФИПИ, коды, споры, корпус, бэкап/восстановление, использование) | `X-Admin-Key` |

Ошибки читаемые: сервер всегда шлёт `detail` (иногда в теле 200 — heartbeat
длинных запросов), фронт показывает его человеку.

## Проверка

- `/health`: `ok`, `llm_key`, `llm_model`, `llm_fallback` (ушёл ли на запасную
  модель), `stt`, `stt_task`, `tts`, `budget_month`, `max_bot`
  (`token_set`, `id_salt_set`, счётчики вебхука).
- Офлайн-тесты: `test_*.py` без `_live` — запускать как скрипты через
  `.venv\Scripts\python.exe`. Живые (`*_live.py`) ходят в Mistral и жгут квоту.

## Грабли

- Секреты в заголовках сравнивать только `_safe_eq`, запись читать только
  `_read_audio`, фон запускать только `_spawn` — см. `CLAUDE.md` здесь же.
- `.env` не создавать Блокнотом: допишет `.txt` и может сохранить в ANSI.
- `.ps1` — только ASCII (PowerShell 5.1 читает их в CP1251).
- На хостинге с 512 МБ `STT_FALLBACK_LOCAL=0`: локальный whisper туда не влезает.

История решений и замеры — [`../docs/DECISIONS.md`](../docs/DECISIONS.md),
правила для агентов — [`CLAUDE.md`](CLAUDE.md).
