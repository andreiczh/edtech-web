# Тестовые данные для проверки API

Речь здесь синтезирована (edge-tts, голос en-US-GuyNeural): микрофон для проверки
не нужен. Тексты, которые звучат в файлах, — в `spoken_texts.json`; задания взяты
из опубликованного банка прода (`GET /tasks`), их id стоят в `variant`.

| Файл | Что это |
|---|---|
| `reading_39.mp3` | чистое чтение текста задания 1 → ожидается балл 1 из 1, ошибок 0 |
| `dialogue_40.mp3` | четыре вопроса к объявлению (задание 2), косвенные — часть не засчитается |
| `interview_41.mp3` | пять одинаковых общих ответов (задание 3) → большинство не засчитано |
| `monologue_42.mp3` | монолог по двум фото (задание 4) → балл около 5–7 из 10 |
| `talk_turn.mp3` | реплика для разговора (`/talk_stream`) |
| `task_feedback_payloads.json` | поля `kind`, `variant`, `payload` для `POST /task_feedback` по каждому типу |
| `register.json` | тело `POST /auth/register` (регистрация открыта, код не нужен; ник должен быть свободен) |
| `talk_review.json` | тело `POST /talk_review` (три реплики ученика с одной ошибкой) |

## Порядок проверки (curl)

```bash
BASE=https://pingo-ai-dpd9.onrender.com
# 1. аккаунт → id в X-Device
ID=$(curl -s -X POST $BASE/auth/register -H 'Content-Type: application/json' -d @register.json | python -c "import sys,json; print(json.load(sys.stdin)['id'])")
# 2. разбор чтения (10–40 с)
curl -s -X POST $BASE/task_feedback -H "X-Device: $ID" -F audio=@reading_39.mp3 -F kind=reading \
  -F "payload=$(python -c "import json; print(json.dumps(json.load(open('task_feedback_payloads.json'))['reading']['payload']))")" -F persona=tutor
# 3. разговор (NDJSON-поток: {text, audio_b64} … {done, user, reply, latency})
curl -s -N -X POST $BASE/talk_stream -H "X-Device: $ID" -F audio=@talk_turn.mp3 -F 'history=[]' -F persona=tutor
# 4. разбор беседы
curl -s -X POST $BASE/talk_review -H "X-Device: $ID" -H 'Content-Type: application/json' -d @talk_review.json
# 5. статистика после работ
curl -s $BASE/me/stats -H "X-Device: $ID"
```

Ожидаемые коды и поля — в [`../../DATA-API.yaml`](../../DATA-API.yaml). Пустая или
слишком короткая запись возвращает 200 с полем `detail` («Не расслышал…»).
