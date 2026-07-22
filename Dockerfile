# Pingo AI — образ для Hugging Face Spaces (SDK: docker).
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

# Веса whisper (~150 МБ) кладём в образ на этапе сборки, а не тянем при старте.
# Иначе каждое пробуждение Space после сна = минуты ожидания первого запроса,
# и это ровно те грабли, на которых мы уже стояли локально (DECISIONS §5, п.3).
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base.en', device='cpu', compute_type='int8')"

COPY --chown=user backend/ backend/
COPY --chown=user --from=front /build/dist dist/

# main.py ищет фронт как backend/../dist — раскладка выше это повторяет.
WORKDIR $HOME/app/backend

# 7860 — порт, который HF Spaces ждёт по умолчанию (см. app_port в README.md).
# Без --reload: он роняет запросы в полёте (DECISIONS §5, п.4).
EXPOSE 7860
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
