# src/ege2 — задания устной части

- `tasks.ts` — банк заданий и прогресс; `selection.ts` — выбор вариантов и
  слияние прогресса.
- `useRecorder.ts`, `audioMime.ts` — запись ответа и формат записи.
- `useCountdown.ts` — отсчёт и таймеры.
- `feedback.ts` — запрос разбора (`POST /task_feedback`).
- `dispute.ts`, `screenshot.ts` — жалоба на балл и снимок экрана к ней.
- `favorites.ts`, `favoritesCore.ts` — избранные задания.
- `askAloud.ts`, `sayWord.ts`, `speakable.ts` — озвучка вопроса и слова
  (`POST /speak`).
- `device.ts` — идентификатор ученика для заголовка `X-Device`.

Файлы `*.test.ts` — тесты соседних модулей.
