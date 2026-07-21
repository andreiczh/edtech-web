# Pingo AI

Голосовой ИИ-тренажёр устного английского под ЕГЭ. Ученик говорит голосом → ИИ отвечает
голосом и разбирает ответ по критериям ФИПИ.

> Репозиторий называется `edtech-copilot-web` — это старое имя того же проекта.

**Главный документ — [`HANDOFF.md`](HANDOFF.md).** Там полная техническая сводка: статус,
архитектура, запуск, грабли, роадмап. История решений — [`docs/DECISIONS.md`](docs/DECISIONS.md).
Правила для AI-агентов — [`CLAUDE.md`](CLAUDE.md).

## Что работает

- ✅ **«Разговор с носителем»** — реальная голосовая петля end-to-end: микрофон → STT → LLM → TTS.
- ✅ **Разбор монолога ЕГЭ (Задание 4)** — эндпоинт `/monologue` + экран практики.
- ⏳ **Стриминг ответа** (`/talk_stream`) — собрано, рантайм на Windows ещё не проверен.
- ⚠️ **Экзаменационная станция** — симуляция с таймерами **без реальной записи**, заглушки.

## Стек

| Узел | Решение | Стоимость |
|---|---|---|
| STT | faster-whisper `base.en` **локально** | $0, без ключа |
| LLM | Mistral `mistral-small-latest` | $0 на free-тарифе |
| TTS | edge-tts `en-US-AriaNeural` | $0, без ключа |
| Бэкенд | FastAPI + uvicorn, раздаёт собранный фронт | — |
| Фронт | React 19 + Vite 6 + TS, обычный CSS, Liquid Glass | — |

Нужен **один** ключ: `LLM_API_KEY` в `backend/.env`.
Всё работает из РФ без VPN — стоп-лист непригодных провайдеров в [`CLAUDE.md`](CLAUDE.md).

## Запуск

Разработка идёт на Маке, запуск и тестирование — на Windows-ноуте.
Пошагово: [`backend/DEPLOY-2-machines.md`](backend/DEPLOY-2-machines.md).

```powershell
# Windows, полный цикл
cd C:\Users\Lenovo\edtech-copilot-web
git pull --rebase
npm.cmd install
npm.cmd run build          # обязательно: бэкенд раздаёт dist/
cd backend
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Открыть `http://localhost:8000/`. Проверка — `http://localhost:8000/health`.

Только фронт, с горячей перезагрузкой: `npm run dev` (:5173, проксирует на :8000).

## Структура

| Путь | Что там |
|---|---|
| `backend/main.py` | весь бэкенд: `/talk`, `/talk_stream`, `/monologue`, `/health` |
| `src/useConversation.ts` | машина состояний диалога + запись + стриминг |
| `src/ege/` | экзаменационный флоу и тренажёр |
| `src/ege/MonologuePractice.tsx` | практика монолога с реальным ИИ-разбором |
| `src/components/` | логотип, слайдер режимов, ЛК, круги-визуализатор, кнопка микрофона |
| `docs/DECISIONS.md` | история решений и выстраданные факты |
