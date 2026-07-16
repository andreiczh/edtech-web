"""
Спайк голосовой петли (Этап 1): микрофон → STT → LLM → TTS → звук обратно.
Non-streaming, push-to-talk. Цель — «петля живёт» и замер задержки.

Стек (API-путь, без GPU):
  STT — Groq Whisper (free tier, OpenAI-совместимый endpoint)
  LLM — provod.ai (оплата из РФ рублями, OpenAI-совместимый)
  TTS — Windows SAPI через pyttsx3 (спайк); на Этапе 2 меняем на Kokoro/Qwen3-TTS

Открой http://localhost:8000/ — там страница записи микрофона (test.html).
"""

import base64
import os
import time

import pyttsx3
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from openai import OpenAI

load_dotenv()

app = FastAPI(title="Копилот — спайк голосовой петли")
# CORS — чтобы позже можно было дёргать бэкенд с фронта (localhost:5173)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# STT — Groq (OpenAI-совместимый endpoint)
stt_client = OpenAI(
    base_url="https://api.groq.com/openai/v1", api_key=os.environ["GROQ_API_KEY"]
)
# LLM — provod.ai (OpenAI-совместимый)
llm_client = OpenAI(
    base_url=os.environ["PROVOD_BASE_URL"], api_key=os.environ["PROVOD_API_KEY"]
)

SYSTEM_PROMPT = (
    "You are a friendly but strict English tutor for the Russian EGE exam. "
    "Reply in 2-3 short sentences. Gently correct the student's mistakes and keep "
    "the conversation going."
)


def synthesize(text: str, path: str = "reply.wav") -> bytes:
    """TTS через Windows SAPI (спайк). Пробуем выбрать английский голос."""
    engine = pyttsx3.init()
    for v in engine.getProperty("voices"):
        name = (v.name or "").lower()
        if any(k in name for k in ("english", "david", "zira", "mark")):
            engine.setProperty("voice", v.id)
            break
    engine.save_to_file(text, path)
    engine.runAndWait()
    with open(path, "rb") as f:
        return f.read()


@app.get("/")
def index():
    return FileResponse("test.html")


@app.post("/talk")
async def talk(audio: UploadFile = File(...)):
    t0 = time.time()
    data = await audio.read()

    # 1) STT: речь → текст
    transcript = stt_client.audio.transcriptions.create(
        model="whisper-large-v3",
        file=(audio.filename or "speech.webm", data, "audio/webm"),
        language="en",
    )
    user_text = (transcript.text or "").strip()
    t1 = time.time()

    # 2) LLM: «мозг» (короткий ответ — и педагогически верно, и быстрее TTS)
    completion = llm_client.chat.completions.create(
        model=os.environ.get("LLM_MODEL", "gemini-2.5-flash-lite"),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        max_tokens=80,
    )
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
