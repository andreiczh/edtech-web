"""
Спайк голосовой петли (Этап 1): микрофон → STT → LLM → TTS → звук обратно.
Non-streaming, push-to-talk. Цель — «петля живёт» и замер задержки.

Стек (API-путь, без GPU):
  STT — Groq Whisper (free tier, OpenAI-совместимый endpoint)
  LLM — provod.ai (оплата из РФ рублями, OpenAI-совместимый)
  TTS — Windows SAPI / macOS через pyttsx3 (спайк); позже — Kokoro/Qwen3-TTS

Открой http://localhost:8000/ — там страница записи микрофона (test.html).
Сервер стартует даже без ключей: страница откроется, а /talk скажет, чего не хватает.
"""

import base64
import os
import subprocess
import sys
import time

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from openai import OpenAI

load_dotenv()

app = FastAPI(title="Копилот — спайк голосовой петли")
# CORS — чтобы позже можно было дёргать бэкенд с фронта (localhost:5173)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

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


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise HTTPException(
            status_code=500,
            detail=f"{name} не задан. Заполни backend/.env (см. .env.example).",
        )
    return val


def synthesize(text: str, path: str = "reply.wav") -> bytes:
    """TTS в ОТДЕЛЬНОМ процессе (tts_worker.py).

    Прямой вызов pyttsx3 в долгоживущем сервере падает на 2-м запросе
    («run loop already started»). Подпроцесс на каждый синтез это лечит.
    """
    worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_worker.py")
    proc = subprocess.run(
        [sys.executable, worker, path],
        input=text,
        text=True,
        capture_output=True,
        timeout=60,
    )
    if proc.returncode != 0 or not os.path.exists(path):
        raise HTTPException(
            status_code=500,
            detail=f"TTS не удался: {proc.stderr.strip() or 'нет вывода воркера'}",
        )
    with open(path, "rb") as f:
        return f.read()


@app.get("/")
def index():
    return FileResponse("test.html")


@app.get("/health")
def health():
    return {
        "ok": True,
        "groq_key": bool(os.environ.get("GROQ_API_KEY")),
        "provod_key": bool(os.environ.get("PROVOD_API_KEY")),
        "provod_url": bool(os.environ.get("PROVOD_BASE_URL")),
    }


@app.post("/talk")
async def talk(audio: UploadFile = File(...)):
    # Клиенты создаём здесь (лениво), чтобы сервер стартовал и без ключей
    stt_client = OpenAI(
        base_url="https://api.groq.com/openai/v1", api_key=_require("GROQ_API_KEY")
    )
    llm_client = OpenAI(
        base_url=_require("PROVOD_BASE_URL"), api_key=_require("PROVOD_API_KEY")
    )

    t0 = time.time()
    data = await audio.read()

    # 1) STT: речь → текст
    try:
        transcript = stt_client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=(audio.filename or "speech.webm", data, "audio/webm"),
            language="en",
        )
    except Exception as e:  # noqa: BLE001 — покажем причину в UI (ключ/сеть/лимит)
        raise HTTPException(status_code=502, detail=f"STT (Groq) ошибка: {e}")
    user_text = (transcript.text or "").strip()
    t1 = time.time()

    # Тишина / STT ничего не расслышал — не гоняем LLM+TTS впустую.
    if not user_text:
        return {
            "user": "",
            "ai": "(не расслышал — скажи ещё раз, чуть громче)",
            "audio_b64": "",
            "latency": {"stt": round(t1 - t0, 2), "llm": 0, "tts": 0, "total": round(t1 - t0, 2)},
        }

    # 2) LLM: «мозг» (короткий ответ — и педагогически верно, и быстрее TTS)
    try:
        completion = llm_client.chat.completions.create(
            model=os.environ.get("LLM_MODEL", "gemini-2.5-flash-lite"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            max_tokens=80,
        )
    except Exception as e:  # noqa: BLE001 — частая причина: неверное имя модели в LLM_MODEL
        raise HTTPException(status_code=502, detail=f"LLM (provod.ai) ошибка: {e}")
    ai_text = (completion.choices[0].message.content or "").strip()
    t2 = time.time()

    # 3) TTS: текст → речь
    wav = synthesize(ai_text)
    t3 = time.time()

    return {
        "user": user_text,
        "ai": ai_text,
        "audio_b64": base64.b64encode(wav).decode(),
        "latency": {
            "stt": round(t1 - t0, 2),
            "llm": round(t2 - t1, 2),
            "tts": round(t3 - t2, 2),
            "total": round(t3 - t0, 2),
        },
    }
