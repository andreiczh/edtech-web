# GoSpeak — один образ для любого Docker-хостинга (Render, compose, HF Spaces).
#
# Один контейнер = весь продукт: FastAPI отдаёт и API, и собранный React-фронт,
# поэтому публичная ссылка одна и CORS никого не волнует.
#
# Почему вообще хостинг, а не туннель с ноутбука: 22.07.2026 три попытки поднять
# cloudflared с машины в РФ упёрлись в TLS-обрыв до edge (порт 7844), а трафик к
# нему шёл через VPN-клиент с непрозрачными правилами. Подробности —
# docs/DECISIONS.md §2.

# ---------- 1) сборка фронта ----------
# Сборка идёт под Linux, а package-lock.json писался на Mac. Проверено перед
# написанием этого файла: в локе есть и @rollup/rollup-linux-x64-gnu, и
# @esbuild/linux-x64, поэтому "npm ci" здесь не развалится. Если после смены
# зависимостей сборка упадёт на "Cannot find module @rollup/rollup-linux-*" —
# значит лок пересобрали без linux-биналов, и чинить надо лок, а не Dockerfile.
FROM node:22-bookworm-slim AS front
WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
# public/ обязателен: vite кладёт его содержимое в корень сборки. Без этой
# строки прод собирался БЕЗ шрифтов и маскотов — локально всё работало, а на
# Render файлы молча пропадали (найдено смоук-тестом 23.07.2026).
COPY public ./public
RUN npm run build

# ---------- 2) рантайм ----------
FROM python:3.11-slim

# HF Spaces запускает контейнер от uid 1000, а не от root. Без своего пользователя
# и своего HOME кеш huggingface окажется в неписуемой директории, и faster-whisper
# упадёт при загрузке весов.
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR $HOME/app

COPY --chown=user backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r backend/requirements.txt

USER user

# Веса whisper в образ НЕ кладём (снято 26.09.2026): распознавание идёт через
# Mistral (STT_PROVIDER=mistral, на Render ещё и STT_FALLBACK_LOCAL=0), а 150 МБ
# весов удлиняли сборку — сдача хакатона требует сборку не дольше 5 минут.
# Локальный whisper остаётся запасным путём: при STT_PROVIDER=local веса
# скачаются при первом запросе (DECISIONS §6.47).

COPY --chown=user backend/ backend/
COPY --chown=user --from=front /build/dist dist/

# main.py ищет фронт как backend/../dist — раскладка выше это повторяет.
WORKDIR $HOME/app/backend

# Порт берём из переменной PORT, а если её нет — 7860.
#
# Так один и тот же образ разворачивается где угодно, а не только на Hugging Face:
# HF ждёт фиксированный порт (7860, см. app_port в README.md) и переменную не
# передаёт, а Render, Koyeb, Cloud Run, Railway и почти все остальные наоборот —
# назначают порт сами через PORT и требуют слушать именно его. Зашитый 7860 сделал
# бы образ пригодным ровно для одной площадки.
#
# Форма CMD — shell (не exec), иначе ${PORT} не раскроется, uvicorn получит
# строку "${PORT}" и упадёт на старте.
# Без --reload: он роняет запросы в полёте (DECISIONS §5, п.4).
EXPOSE 7860
CMD python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860}
