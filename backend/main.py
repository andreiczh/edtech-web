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
import json
import os
import re
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
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from faster_whisper import WhisperModel
from openai import AsyncOpenAI, OpenAI

load_dotenv()

# Пути, отдающие ПОТОК: их сжимать нельзя, см. GZipExceptStreams ниже.
# Новый потоковый эндпоинт — дописать его путь сюда, иначе стриминг у него
# молча выключится (ответ придёт целиком в самом конце).
_STREAM_PATHS = {"/talk_stream"}


class GZipExceptStreams:
    """GZip для всего, КРОМЕ потоковых ответов.

    Грабли (замерено на Windows-ноуте 22.07.2026): GZipMiddleware ломает
    стриминг насмерть. zlib копит вход во внутреннем буфере и отдаёт сжатый
    блок только когда его наберётся достаточно, а base64-mp3 почти не
    сжимается — поэтому чанки висят в буфере до конца ответа. Итог: браузер
    получал ВЕСЬ NDJSON разом в момент `total`, то есть Шаг A (стриминг
    ответа) не давал ничего вообще.

    Контрольный опыт, один и тот же запрос:
      с gzip:     расшифровка и первый звук пришли на 4.84с (= total 4.82с);
      identity:   расшифровка на 2.72с, первый звук на 3.99с — как задумано.

    `X-Accel-Buffering: no` на StreamingResponse от этого не спасает: он про
    буферизацию в nginx, а тут буфер внутри нашего же процесса.
    """

    def __init__(self, app, **kwargs):
        self._plain = app
        self._gzipped = GZipMiddleware(app, **kwargs)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") in _STREAM_PATHS:
            await self._plain(scope, receive, send)
        else:
            await self._gzipped(scope, receive, send)


app = FastAPI(title="Копилот — голосовая петля (free stack)")
# CORS — чтобы позже дёргать бэкенд с фронта (localhost:5173).
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
# Сжимаем ответы (JS-бандл ~225 КБ несжатым) — важно за нестабильным туннелем
# (trycloudflare/RF-маршрут): меньше файл — меньше шанс оборваться на середине.
app.add_middleware(GZipExceptStreams, minimum_size=500)

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

# Промпт-ревьюер устного ЕГЭ, Задание 4 (монолог, голосовое сообщение другу).
# Критерии ФИПИ (10 баллов): коммуникативная задача (4) + организация (3) +
# языковое оформление (3). ВАЖНО: на вход — авто-транскрипт, поэтому произношение
# оценить НЕЛЬЗЯ (в тексте его нет) → фонетические ошибки не выдумываем.
#
# ВАЖНО-2 (баг, найден замером 22.07.2026): промпт требовал сравнения двух фото,
# а экран честно просит «говори на свободную тему — картинок пока нет». Из-за
# этого связный монолог на 65с получал 0+0+0 и вердикт «нет сравнения двух фото»,
# а разбор ошибок не делался вовсе. Промпт согласован с тем, что просит экран.
# Когда появятся материалы (2 фото + план) — передавать сюда текст задания
# и вернуть проверку по аспектам плана.
MONOLOGUE_PROMPT = (
    "You are an examiner for the Russian EGE oral English exam, Task 4: a ~2-minute "
    "monologue recorded as a voice message to a friend. You receive an AUTOMATIC "
    "TRANSCRIPT of the student's spoken answer.\n\n"
    "THE APP HAS NO PHOTO MATERIALS YET, so the student was asked to speak on a topic "
    "of their own choice in the Task 4 format. NEVER demand a comparison of two photos "
    "and NEVER give zeros because the answer does not describe pictures — grade the "
    "monologue the student was actually asked to produce.\n\n"
    "Grade it by the 3 official criteria (10 points total):\n"
    "1) key=\"task\" — Решение коммуникативной задачи (max 4): is the chosen topic "
    "really developed (not a few generic phrases), volume ~12-15 phrases, does the "
    "student stay on one topic.\n"
    "2) key=\"organization\" — Организация высказывания (max 3): opening + conclusion, "
    "linking words (firstly, however, in conclusion), logical structure.\n"
    "3) key=\"language\" — Языковое оформление (max 3): lexical and grammatical accuracy "
    "and range.\n\n"
    "IMPORTANT: the input is a TEXT transcript — you CANNOT judge pronunciation or word "
    "stress from it, so NEVER invent phonetic errors. Judge only what the text shows.\n\n"
    "Return ONLY a JSON object (no prose, no markdown) with EXACTLY this shape:\n"
    "{\n"
    '  "summary": "<one short sentence in Russian: overall verdict>",\n'
    '  "criteria": [\n'
    '    {"key":"task","name":"Решение коммуникативной задачи","score":<0-4>,"max":4,"comment":"<по-русски, кратко>"},\n'
    '    {"key":"organization","name":"Организация высказывания","score":<0-3>,"max":3,"comment":"<по-русски, кратко>"},\n'
    '    {"key":"language","name":"Языковое оформление","score":<0-3>,"max":3,"comment":"<по-русски, кратко>"}\n'
    "  ],\n"
    '  "errors": [\n'
    '    {"cat":"gram|lex|logic","quote":"<exact words from the answer, English>","correction":"<fixed, English>","explanation":"<по-русски, почему>"}\n'
    "  ]\n"
    "}\n\n"
    "Rules: comments and explanations in Russian; quote and correction in English. "
    "Be honest but encouraging (level A2-B1). List up to 6 most important errors "
    "(cat is only gram/lex/logic — never phon). Zeros are only for an empty answer or "
    "a few unrelated words; any real monologue must be graded on its merits, and the "
    "errors list must be filled in even when the scores are low."
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


# Клиенты создаём ОДИН раз на процесс, а не на каждый запрос: иначе каждый вызов
# платит новый TLS-хендшейк (а из РФ это заметная часть задержки голосовой петли).
# Ленивая инициализация — сервер должен стартовать и без ключа.
# Таймауты заданы явно: дефолт SDK (600с на чтение, 2 ретрая) при обрыве сети
# превращает сбой в многоминутное зависание, которое выглядит как «всё сломалось».
_llm: OpenAI | None = None
_async_llm: AsyncOpenAI | None = None
_LLM_TIMEOUT = 30.0
_LLM_RETRIES = 1


def llm_client() -> OpenAI:
    global _llm
    if _llm is None:
        _llm = OpenAI(
            base_url=LLM_BASE_URL, api_key=_require("LLM_API_KEY"),
            timeout=_LLM_TIMEOUT, max_retries=_LLM_RETRIES,
        )
    return _llm


def async_llm_client() -> AsyncOpenAI:
    # Асинхронный клиент — для стриминга токенов (/talk_stream).
    global _async_llm
    if _async_llm is None:
        _async_llm = AsyncOpenAI(
            base_url=LLM_BASE_URL, api_key=_require("LLM_API_KEY"),
            timeout=_LLM_TIMEOUT, max_retries=_LLM_RETRIES,
        )
    return _async_llm


class TtsFailed(Exception):
    """Сбой синтеза речи. Отдельный тип, чтобы не сваливать его в «LLM ошибка»:
    в /talk_stream синтез идёт внутри того же try, что и стриминг LLM, и без
    разделения падение edge-tts рапортуется как проблема с моделью Mistral —
    пользователь идёт перевыпускать ключ вместо того, чтобы чинить TTS."""


# Граница предложения: точка/!/?/… (возможно несколько) + пробел/конец.
_SENTENCE_END = re.compile(r"[.!?…]+(?=\s|$)")


def _split_sentence(buf: str) -> tuple[str, str]:
    """Отрезает первое законченное предложение из буфера.
    Возвращает (предложение | '', остаток)."""
    m = _SENTENCE_END.search(buf)
    if not m:
        return "", buf
    end = m.end()
    return buf[:end].strip(), buf[end:].lstrip()


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


@app.post("/monologue")
async def monologue(audio: UploadFile = File(...)):
    """Разбор монолога (ЕГЭ Задание 4): полное аудио → batch STT → ОДИН
    структурный проход LLM → JSON-фидбэк (3 критерия + ошибки). Без TTS —
    разбор текстовый, для экрана результата. Фаза 1 (baseline, без стриминга).
    """
    t0 = time.time()
    data = await audio.read()

    # 1) STT — весь монолог разом (Фаза 2 сделает это стримингом во время речи).
    try:
        transcript_text = await asyncio.to_thread(transcribe, data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"STT (faster-whisper) ошибка: {e}")
    t1 = time.time()

    if not transcript_text:
        raise HTTPException(
            status_code=422, detail="Тишина — ничего не распознали. Запиши монолог ещё раз."
        )

    # 2) LLM — один структурный проход, ответ строго JSON.
    client = llm_client()
    try:
        completion = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": MONOLOGUE_PROMPT},
                    {"role": "user", "content": transcript_text},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=800,
            )
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"LLM ошибка ({LLM_MODEL}): {e}")

    raw = (completion.choices[0].message.content or "").strip()
    try:
        feedback = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail=f"LLM вернул не-JSON: {raw[:200]}")
    t2 = time.time()

    return {
        "transcript": transcript_text,
        "feedback": feedback,
        "latency": {
            "stt": round(t1 - t0, 2),
            "llm": round(t2 - t1, 2),
            "total": round(t2 - t0, 2),
        },
    }


@app.post("/talk_stream")
async def talk_stream(audio: UploadFile = File(...)):
    """Разговор со СТРИМИНГОМ ответа (Шаг A к <2с бесшовности).

    Тот же push-to-talk на входе, но ответ течёт пофразно: LLM токенами →
    режем на предложения → каждое сразу озвучиваем (edge-tts) и отдаём чанком
    NDJSON `{text, audio_b64}`. Фронт играет их подряд — первый звук идёт,
    пока генерится остальное. Финальный чанк: `{done, user, reply, latency}`,
    где latency.first_audio = время до первого озвученного предложения.
    """
    data = await audio.read()

    async def gen():
        t0 = time.time()
        # 1) STT (batch, после стопа — Шаг B сделает это стримингом во время речи)
        try:
            user_text = await asyncio.to_thread(transcribe, data)
        except Exception as e:  # noqa: BLE001
            yield json.dumps({"error": f"STT (faster-whisper) ошибка: {e}"}) + "\n"
            return
        t1 = time.time()
        if not user_text:
            yield json.dumps(
                {"done": True, "user": "", "reply": "(не расслышал — скажи ещё раз)",
                 "latency": {"stt": round(t1 - t0, 2), "first_audio": 0, "total": round(t1 - t0, 2)}}
            ) + "\n"
            return

        # Расшифровку отдаём сразу — фронт покажет «Ты сказал…», пока стримится ответ.
        yield json.dumps({"user": user_text}) + "\n"

        # 2) LLM стримингом → 3) пофразный TTS
        client = async_llm_client()
        reply_full = ""
        buf = ""
        first_audio_at = None

        async def emit(sentence: str):
            nonlocal first_audio_at
            try:
                wav = await synthesize(sentence)
            except Exception as e:  # noqa: BLE001
                raise TtsFailed(str(e)) from e
            if first_audio_at is None:
                first_audio_at = time.time()
            return json.dumps({"text": sentence, "audio_b64": base64.b64encode(wav).decode()}) + "\n"

        try:
            stream = await client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_text},
                ],
                max_tokens=120,
                stream=True,
            )
            async for chunk in stream:
                delta = (chunk.choices[0].delta.content or "") if chunk.choices else ""
                if not delta:
                    continue
                buf += delta
                reply_full += delta
                # выгружаем все законченные предложения из буфера
                while True:
                    sentence, buf = _split_sentence(buf)
                    if not sentence:
                        break
                    yield await emit(sentence)
            # хвост (последнее предложение без завершающего пробела)
            tail = buf.strip()
            if tail:
                yield await emit(tail)
        except TtsFailed as e:
            yield json.dumps({"error": f"TTS (edge-tts) ошибка: {e}"}) + "\n"
            return
        except Exception as e:  # noqa: BLE001
            yield json.dumps({"error": f"LLM ошибка ({LLM_MODEL}): {e}"}) + "\n"
            return

        t2 = time.time()
        yield json.dumps(
            {"done": True, "user": user_text, "reply": reply_full.strip(),
             "latency": {"stt": round(t1 - t0, 2),
                         "first_audio": round((first_audio_at or t2) - t1, 2),
                         "total": round(t2 - t0, 2)}}
        ) + "\n"

    return StreamingResponse(
        gen(),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


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
