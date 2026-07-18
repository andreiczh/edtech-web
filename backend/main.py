"""
Голосовая петля (Этап 2, редизайн на бесплатные и доступные из РФ API):
  микрофон → STT → LLM → TTS → звук обратно. Push-to-talk, замер задержки.

Стек — только бесплатное и доступное из РФ без VPN:
  STT — faster-whisper ЛОКАЛЬНО (офлайн, без ключа, без гео-блока)
  LLM — OpenRouter :free-модели (OpenAI-совместимо, из РФ без VPN, без карты);
        endpoint свапается через .env → можно указать DeepSeek или любой
        другой OpenAI-совместимый провайдер, ничего в коде не меняя.
  TTS — edge-tts (нейро-голоса Microsoft, бесплатно, без ключа, из РФ ок)

Открой http://localhost:8000/ — там страница записи микрофона (test.html).
Сервер стартует даже без LLM-ключа: страница откроется, а /talk скажет, чего нет.
"""

from __future__ import annotations

import asyncio
import base64
import os
import tempfile
import time

# На Windows без Developer Mode huggingface_hub печатает безобидный warning
# про symlinks при каждой загрузке модели — глушим, чтобы не путать с ошибкой.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import edge_tts
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from faster_whisper import WhisperModel
from openai import OpenAI

load_dotenv()

app = FastAPI(title="Копилот — голосовая петля (free stack)")
# CORS — чтобы позже дёргать бэкенд с фронта (localhost:5173).
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
# Сжимаем ответы (JS-бандл ~225 КБ несжатым) — важно за нестабильным туннелем
# (trycloudflare/RF-маршрут): меньше файл — меньше шанс оборваться на середине.
app.add_middleware(GZipMiddleware, minimum_size=500)

SYSTEM_PROMPT = (
    "You are a warm, encouraging native-speaker English tutor helping a Russian "
    "teenager (A2-B1 level) practise SPEAKING for the EGE exam.\n"
    "Rules:\n"
    "- Reply in natural spoken English, 1-3 short sentences. Your reply is read aloud "
    "by a text-to-speech voice, so keep it short and easy to say — no markdown, no "
    "emojis, no lists, no bullet points.\n"
    "- Always finish with one simple follow-up question to keep the conversation going.\n"
    "- Correct only mistakes that break meaning or are clearly wrong. Do it briefly and "
    "kindly (\"You can say ...\"), then move on — do not nitpick every small error.\n"
    "- Match the student's level, speak clearly, and encourage them.\n"
    "- Reply in English only."
)

# Настройки через .env (все с разумными дефолтами).
# base.en — лёгкая англ.-модель: быстрее и легче по памяти, чем small (важно для
# слабого ноута). Точнее/тяжелее по возрастанию: base.en < small.en < small.
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base.en")
TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-AriaNeural")
# Mistral — дефолт: подтверждённо работает из РФ без VPN и активируется без
# карты. (DeepSeek не начислил бесплатный грант — 402 Insufficient Balance;
# OpenRouter за Cloudflare-блоком РФ — 403.) Свапается через .env, см. .env.example.
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.mistral.ai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "mistral-small-latest")

# STT-модель грузим лениво и один раз (первый вызов скачает веса ~150–500 МБ).
_whisper: WhisperModel | None = None


def get_whisper() -> WhisperModel:
    global _whisper
    if _whisper is None:
        # int8 на CPU — самый лёгкий режим для ноутбука без GPU.
        _whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    return _whisper


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise HTTPException(
            status_code=500,
            detail=f"{name} не задан. Заполни backend/.env (см. .env.example).",
        )
    return val


def transcribe(data: bytes) -> str:
    """STT локально через faster-whisper. На вход — байты webm/opus из браузера."""
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(data)
        path = f.name
    try:
        segments, _info = get_whisper().transcribe(path, language="en", beam_size=1)
        return " ".join(seg.text for seg in segments).strip()
    finally:
        os.unlink(path)


async def synthesize(text: str) -> bytes:
    """TTS через edge-tts (нейро-голоса Microsoft). Возвращает mp3-байты.

    Пишем во ВРЕМЕННЫЙ файл (не в cwd), чтобы не мусорить в рабочей папке.
    """
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        path = f.name
    try:
        communicate = edge_tts.Communicate(text, TTS_VOICE)
        await communicate.save(path)
        with open(path, "rb") as fh:
            return fh.read()
    finally:
        if os.path.exists(path):
            os.unlink(path)


def llm_client() -> OpenAI:
    # Ленивое создание — сервер стартует и без ключа.
    return OpenAI(base_url=LLM_BASE_URL, api_key=_require("LLM_API_KEY"))


@app.on_event("startup")
async def _warmup():
    # Прогреваем STT-модель при СТАРТЕ: первая загрузка (~150 МБ) идёт здесь и
    # видна в консоли, а не виснет на первом /talk (иначе соединение рвётся).
    print(f"[startup] Загружаю faster-whisper:{WHISPER_MODEL} (первый раз качает модель, подожди)...")
    await asyncio.to_thread(get_whisper)
    print("[startup] STT-модель готова. Сервер принимает запросы.")


_HERE = os.path.dirname(os.path.abspath(__file__))
_DIST = os.path.join(_HERE, "..", "dist")  # собранный React-фронт (npm run build)


@app.get("/test")
def test_page():
    """Старая проверочная страница (vanilla JS). Основной UI — собранный фронт на /."""
    return FileResponse(os.path.join(_HERE, "test.html"))


@app.get("/health")
def health():
    return {
        "ok": True,
        "stt": f"faster-whisper:{WHISPER_MODEL} (local)",
        "tts": f"edge-tts:{TTS_VOICE}",
        "llm_base": LLM_BASE_URL,
        "llm_model": LLM_MODEL,
        "llm_key": bool(os.environ.get("LLM_API_KEY")),
    }


@app.post("/talk")
async def talk(audio: UploadFile = File(...)):
    t0 = time.time()
    data = await audio.read()

    # 1) STT (локальная CPU-работа → в отдельный поток, чтобы не блокировать сервер)
    try:
        user_text = await asyncio.to_thread(transcribe, data)
    except Exception as e:  # noqa: BLE001 — покажем причину в UI
        raise HTTPException(status_code=502, detail=f"STT (faster-whisper) ошибка: {e}")
    t1 = time.time()

    # Тишина / ничего не распознали — не гоняем LLM+TTS впустую.
    if not user_text:
        return {
            "user": "",
            "ai": "(не расслышал — скажи ещё раз, чуть громче)",
            "audio_b64": "",
            "audio_mime": "audio/mpeg",
            "latency": {"stt": round(t1 - t0, 2), "llm": 0, "tts": 0, "total": round(t1 - t0, 2)},
        }

    # 2) LLM (OpenAI-совместимый вызов; частая причина ошибки — имя модели в LLM_MODEL)
    client = llm_client()
    try:
        completion = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_text},
                ],
                max_tokens=80,
            )
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"LLM ошибка ({LLM_MODEL}): {e}")
    ai_text = (completion.choices[0].message.content or "").strip()
    t2 = time.time()

    # 3) TTS (edge-tts, асинхронно)
    try:
        wav = await synthesize(ai_text)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"TTS (edge-tts) ошибка: {e}")
    t3 = time.time()

    return {
        "user": user_text,
        "ai": ai_text,
        "audio_b64": base64.b64encode(wav).decode(),
        "audio_mime": "audio/mpeg",
        "latency": {
            "stt": round(t1 - t0, 2),
            "llm": round(t2 - t1, 2),
            "tts": round(t3 - t2, 2),
            "total": round(t3 - t0, 2),
        },
    }


# Раздаём собранный React-фронт (../dist) на "/", если он собран (npm run build).
# Так весь UI и API живут на ОДНОМ адресе — одна публичная ссылка через туннель,
# без возни с двумя серверами и CORS. Маршруты /talk, /health, /test заданы ВЫШЕ
# и имеют приоритет над этим mount.
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
else:

    @app.get("/")
    def _need_build():
        # Фронт ещё не собран — покажем проверочную страницу как заглушку.
        return FileResponse(os.path.join(_HERE, "test.html"))
