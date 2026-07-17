# Бэкенд — голосовая петля (Этап 2, free stack)

`микрофон → STT → LLM → TTS → звук обратно`, push-to-talk, замер задержки.

**Стек — только бесплатное и доступное из РФ без VPN:**
- **STT** — [faster-whisper](https://github.com/SYSTRAN/faster-whisper) **локально** (офлайн, без ключа, без гео-блока)
- **LLM** — [OpenRouter](https://openrouter.ai) `:free`-модели (OpenAI-совместимо, из РФ без VPN, **без карты**). Endpoint свапается через `.env` на DeepSeek или любой OpenAI-совместимый.
- **TTS** — [edge-tts](https://github.com/rany2/edge-tts) (нейро-голоса Microsoft, бесплатно, без ключа)

> Нужен **один** бесплатный ключ — OpenRouter. STT и TTS работают без ключей.

## Запуск на Windows (PowerShell)

```powershell
cd edtech-copilot-web\backend
git pull
powershell -ExecutionPolicy Bypass -File run.ps1
```
Первый запуск создаст `.env` и откроет блокнот — впиши `LLM_API_KEY` (ключ OpenRouter),
сохрани, запусти снова. Открой **http://localhost:8000/**, жми «Говорить».

**Первый `/talk` будет долгим** — faster-whisper один раз скачает модель (~150–500 МБ),
дальше быстро. Прогресс виден в консоли uvicorn.

## Где взять ключ
- **OpenRouter:** [openrouter.ai](https://openrouter.ai) → регистрация → **Keys → Create Key**
  (карта не нужна для `:free`). Актуальные бесплатные модели:
  [openrouter.ai/models?max_price=0](https://openrouter.ai/models?max_price=0) — впиши в `LLM_MODEL`.
- Лимит `:free` ~**50 запросов/день, 20/мин**. Хватает для теста/демо.
  Упрёшься — переключись на **DeepSeek** (из РФ без VPN, 5M токенов бесплатно): см. `.env.example`.

## Проверка
- `http://localhost:8000/health` — покажет модель STT/LLM/TTS и есть ли `llm_key`.
- `http://localhost:8000/` — жми «Говорить», скажи фразу по-английски. Внизу — задержка
  по стадиям (`stt / llm / tts / total`).
- Ошибки читаемые: `STT (faster-whisper) ошибка: …`, `LLM ошибка (модель): …`,
  `TTS (edge-tts) ошибка: …`.

## Настройки (`.env`)
- `WHISPER_MODEL` — `base` (быстрее) / `small` (точнее, дефолт).
- `TTS_VOICE` — `en-US-AriaNeural` и др. Список: `edge-tts --list-voices`.
- `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` — любой OpenAI-совместимый провайдер.

## Что дальше (Этап 2.5)
- Стриминг (Pipecat или свой WebSocket) + Silero VAD + barge-in, цель <3с.
- Подключить основной фронт (`../`) к бэкенду по WebSocket.
- Логирование сессий (режим, длительность, реплики, латентность) → SQLite.

## Примечания
- `faster-whisper` на CPU: `small` int8 ≈ реалтайм на нормальном ноуте; `base` — легче/быстрее.
- `edge-tts` использует онлайн-сервис Microsoft (формально — для читалки Edge; community-либа
  стабильна годами). Полностью офлайн-альтернатива по TTS — [Piper](https://github.com/rhasspy/piper).
- `main.py` отдаёт `test.html` на `/`, поэтому микрофон работает (localhost — secure context).
