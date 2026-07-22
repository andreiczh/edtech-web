---
title: Pingo AI
emoji: 🎤
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Голосовой ИИ-тренажёр устного английского под ЕГЭ
---

<!-- Блок выше — служебный заголовок для Hugging Face Spaces: без него Space не
     соберётся. На GitHub он выглядит лишним, но это единственный способ держать
     один README и на GitHub, и на Space. app_port обязан совпадать с портом в
     Dockerfile. -->

# Pingo AI

Голосовой ИИ-тренажёр устного английского под ЕГЭ. Ученик говорит голосом → ИИ отвечает
голосом и разбирает ответ по критериям ФИПИ.

> Репозиторий называется `edtech-copilot-web` — это старое имя того же проекта.

**Главный документ — [`HANDOFF.md`](HANDOFF.md).** Там полная техническая сводка: статус,
архитектура, запуск, грабли, роадмап. История решений — [`docs/DECISIONS.md`](docs/DECISIONS.md).
Правила для AI-агентов — [`CLAUDE.md`](CLAUDE.md).

## Что работает

- ✅ **«Разговор с носителем»** — реальная голосовая петля end-to-end: микрофон → STT → LLM → TTS.
- ✅ **Разбор монолога ЕГЭ (Задание 4)** — `/monologue` + экран практики. Прогнан замером
  22.07.2026: развёрнутый монолог 9/10, нарочно слабый 3/10.
- ✅ **Стриминг ответа** (`/talk_stream`) — бэкенд отдаёт фразы по одной: расшифровка 2.7 c,
  первый звук 4.2 c, весь ответ 6.6 c. Фронтовую часть живым микрофоном ещё не гоняли.
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

Всё делается на одной машине — Windows-ноут (`C:\Users\Lenovo\edtech-copilot-web`).

```powershell
# Windows, полный цикл
cd C:\Users\Lenovo\edtech-copilot-web
git pull --rebase
npm.cmd run build          # обязательно: бэкенд раздаёт dist/
cd backend
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Открыть `http://localhost:8000/`. Проверка — `http://localhost:8000/health`.

Только фронт, с горячей перезагрузкой: `npm run dev` (:5173, проксирует на :8000).

## Публичная ссылка

Хостинг — **Hugging Face Spaces** (Docker). Туннель с ноутбука не вышел: из РФ
`cloudflared` не поднимает соединение с edge, детали в [`docs/DECISIONS.md`](docs/DECISIONS.md) §2.
Пошаговая инструкция по деплою: [`docs/DEPLOY-HF.md`](docs/DEPLOY-HF.md).
Собирается по `Dockerfile` в корне, порт 7860 (`app_port` в заголовке этого файла).

## Структура

| Путь | Что там |
|---|---|
| `backend/main.py` | весь бэкенд: `/talk`, `/talk_stream`, `/monologue`, `/health` |
| `src/useConversation.ts` | машина состояний диалога + запись + стриминг |
| `src/ege/` | экзаменационный флоу и тренажёр |
| `src/ege/MonologuePractice.tsx` | практика монолога с реальным ИИ-разбором |
| `src/components/` | логотип, слайдер режимов, ЛК, круги-визуализатор, кнопка микрофона |
| `docs/DECISIONS.md` | история решений и выстраданные факты |
