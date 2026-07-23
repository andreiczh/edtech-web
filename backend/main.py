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
import calendar
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import tempfile
import time
from collections import deque
from datetime import date, datetime, timedelta, timezone

# На Windows без Developer Mode huggingface_hub печатает безобидный warning
# про symlinks при каждой загрузке модели — глушим, чтобы не путать с ошибкой.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import aiohttp
import edge_tts
import httpx
from dotenv import load_dotenv
from fastapi import Body, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from faster_whisper import WhisperModel
from openai import AsyncOpenAI, OpenAI

import storage

load_dotenv()

# Убираем системный HTTP-прокси ИЗ НАШЕГО процесса.
#
# На машине разработки стоит VPN-клиент (sing-box/xray), который прописывает
# HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:10809 на всю систему. Библиотеки
# (aiohttp у edge-tts, httpx у openai) это подхватывают, и наши запросы идут
# лишним хопом через локальный прокси, хотя маршрут до провайдеров и так лежит
# через VPN-туннель.
#
# Замерено 22.07.2026, чередующийся A/B по 10 попыток на вариант, edge-tts,
# одна короткая фраза: с прокси медиана 1.26 с (макс 7.82), без прокси
# медиана 0.81 с (макс 6.59). Полсекунды на КАЖДОЙ произнесённой фразе.
#
# Безопасность отключения проверена: и api.mistral.ai, и эндпоинт edge-tts
# отвечают напрямую (0.33 и 0.37 с). Если однажды провайдер окажется доступен
# ТОЛЬКО через прокси — вернуть прежнее поведение переменной KEEP_SYSTEM_PROXY=1.
if not os.environ.get("KEEP_SYSTEM_PROXY"):
    for _var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                 "ALL_PROXY", "all_proxy"):
        os.environ.pop(_var, None)

# Пути, отдающие ПОТОК: их сжимать нельзя, см. GZipExceptStreams ниже.
# Новый потоковый эндпоинт — дописать его путь сюда, иначе стриминг у него
# молча выключится (ответ придёт целиком в самом конце).
# /monologue и /task_feedback тоже здесь: они шлют «сердцебиение» переводами
# строк, а zlib копил бы их в буфере — и смысл сердцебиения пропал бы целиком.
_STREAM_PATHS = {"/talk_stream", "/monologue", "/task_feedback"}


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
    "- USE the conversation history you are given: remember the student's name and the "
    "facts they told you, refer back to them naturally, never ask a question they have "
    "already answered, and never repeat a question you already asked — dig deeper or "
    "change the angle instead.\n"
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
#
# ОТКУДА БЕРЁТСЯ РАСПОЗНАВАНИЕ: "mistral" (по сети) или "local" (faster-whisper).
#
# Замерено 22.07.2026 на этой машине, одно и то же аудио:
#                      реплика ~10 с   монолог ~65 с   совпадение с эталоном
#   Mistral Voxtral        0.54 с          1.22 с              100%
#   локально tiny.en       1.50 с          7-10 с              100%
#   локально base.en       3.20 с         13-17 с              эталон
#
# Дело не только в скорости. faster-whisper — единственная причина, по которой
# бэкенду нужны настоящая память и настоящий процессор. Замерено: с локальными
# моделями процесс держит 332 МБ (пик 449 МБ при загрузке обеих), без них — 99 МБ.
# Бесплатные хостинги дают 512 МБ и 0.1 vCPU, а faster-whisper к тому же почти не
# ускоряется от числа потоков (RTF base.en: 0.275 на одном против 0.193 на четырёх),
# то есть на облачной «десятой доле ядра» он не поедет в принципе. Без него бэкенд —
# тонкая I/O-прослойка, которая влезает куда угодно.
#
# Локальный whisper НЕ выброшен: он остаётся запасным путём, если Mistral не
# ответил, и единственным, если работать без интернета.
STT_PROVIDER = os.environ.get("STT_PROVIDER", "mistral").strip().lower()
STT_REMOTE_MODEL = os.environ.get("STT_REMOTE_MODEL", "voxtral-mini-latest")
# Язык распознавания. Пустая строка = пусть модель определяет сама (не советую,
# см. комментарий в transcribe_remote).
STT_LANGUAGE = os.environ.get("STT_LANGUAGE", "en")

# Откатываться ли на локальный whisper, если Mistral не ответил.
#
# Дома — да: интернет может пропасть, а модель уже скачана.
# На хостинге — НЕТ, и это не перестраховка. Найдено тестом 22.07.2026: на битом
# аудио Mistral отказывает, срабатывает откат, и контейнер на 512 МБ пытается
# поднять модель на 150 МБ. Один такой запрос способен уронить сервис по памяти —
# то есть плохая запись одного ученика выключила бы приложение всем.
STT_FALLBACK_LOCAL = os.environ.get("STT_FALLBACK_LOCAL", "1").strip() not in ("0", "false", "no")

# СИНТЕЗ РЕЧИ: edge-tts основной, Mistral — запасной.
#
# edge-tts быстрее (замер 22.07.2026: медиана 0.42 с против 1.09 с у Mistral) и
# бесплатен, поэтому он основной. Но он использует недокументированный доступ к
# голосам Microsoft, и есть свидетельства, что с IP дата-центров он перестал
# работать. Проверить это можно только с хостинга, а сломалась бы озвучка целиком.
# Поэтому запасной путь заведён заранее и проверен: Mistral отвечает на том же
# ключе, что STT и LLM.
#
# Цена запасного пути — голос. У Mistral для английского только мужские голоса
# ("Paul"), тогда как сейчас звучит женский en-US-AriaNeural. Для тренажёра это
# приемлемо, но заметно, поэтому переключение автоматическое и только при отказе.
# Не давать хостингу усыпить сервис: сами дёргаем свой публичный адрес.
#
# Render на бесплатном тарифе засыпает после 15 минут без ВХОДЯЩИХ запросов и
# просыпается около минуты, показывая заглушку. Первый зашедший друг видит именно
# её. Собственный запрос на свой публичный адрес считается входящим и сон отменяет.
#
# Почему не GitHub Actions: у приватного репозитория 2000 минут в месяц, а пинг
# раз в 10 минут — это 4320 запусков, каждый тарифицируется минимум минутой.
# Не влезает вдвое.
#
# ⚠️ Плата за это — часы работы. У Render 750 инстанс-часов в месяц на аккаунт, а
# в месяце 720-744 часа: круглосуточный пинг съедает ВСЮ квоту без запаса, и при
# перерасходе сервис отключают до следующего месяца. Поэтому пингуем только в окно
# дневной активности (по умолчанию 04:00-20:00 UTC = 07:00-23:00 МСК): 16 часов в
# сутки это ~480 часов в месяц, с запасом. Ночью сервис спит и часы не тратит.
#
# KEEP_AWAKE_URL пуст — механизм выключен (так и надо на localhost).
KEEP_AWAKE_URL = os.environ.get("KEEP_AWAKE_URL", "").strip()
KEEP_AWAKE_FROM_HOUR_UTC = int(os.environ.get("KEEP_AWAKE_FROM_HOUR_UTC", "4"))
KEEP_AWAKE_TO_HOUR_UTC = int(os.environ.get("KEEP_AWAKE_TO_HOUR_UTC", "20"))

TTS_PROVIDER = os.environ.get("TTS_PROVIDER", "edge").strip().lower()
TTS_REMOTE_MODEL = os.environ.get("TTS_REMOTE_MODEL", "voxtral-mini-tts-latest")
TTS_REMOTE_VOICE = os.environ.get("TTS_REMOTE_VOICE", "en_paul_neutral")

# ДВЕ локальные STT-модели, по одной на режим — осознанный размен, не недосмотр.
# Замерено 22.07.2026 на этом ноуте (4 ядра, int8), реплика ~10 с:
#   tiny.en  1.4-2.5 с   base.en  3.2-3.3 с   small.en  7.6-11 с (непригодна)
# Текст при этом совпал с base.en на 100% (реплика) и 98.4% (монолог 65 с).
#
# Почему по-разному в двух режимах:
#   - разговор: ученик ждёт ответа вживую, полторы секунды решают всё, а ошибка
#     в одном слове тут же тонет в диалоге -> tiny.en;
#   - монолог: ждать всё равно секунд десять, зато каждое слово транскрипта
#     превращается в балл ФИПИ и в разбор ошибок -> base.en, точность важнее.
#
# ⚠️ Проверено ТОЛЬКО на синтетической американской речи. Русский школьный акцент
# — тяжёлый случай, и tiny.en может терять отрицания, вопросы и модальные
# (can/can't). Если разговор начнёт «недослышивать» — вернуть base.en одной
# строкой: WHISPER_MODEL_FAST=base.en в backend/.env.
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base.en")
WHISPER_MODEL_FAST = os.environ.get("WHISPER_MODEL_FAST", "tiny.en")
TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-AriaNeural")
# Mistral — дефолт: подтверждённо работает из РФ без VPN и активируется без
# карты. (DeepSeek не начислил бесплатный грант — 402 Insufficient Balance;
# OpenRouter за Cloudflare-блоком РФ — 403.) Свапается через .env, см. .env.example.
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.mistral.ai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "mistral-small-latest")

# Отправлять НАШ трафик мимо VPN, привязав сокеты к физическому интерфейсу.
#
# Зачем. На машине постоянно включён VPN-клиент (sing-box/xray, TUN happ-tun), и
# маршрут по умолчанию ведёт через него. Но Mistral и edge-tts выбирались как раз
# за то, что работают из РФ БЕЗ VPN, — туннель им не нужен, а крюк они оплачивают.
#
# Замерено 22.07.2026, чередующийся A/B (сеть дрейфует по минутам, поэтому только
# чередование, не два блока подряд):
#   LLM, время до первого токена: через VPN медиана 4.76 с (0.57-15.66),
#                                 мимо VPN медиана 0.34 с (0.24-0.52)
#   TTS, короткая фраза:          через VPN медиана 1.71 с (0.58-19.14),
#                                 мимо VPN медиана 0.42 с (0.35-0.57)
# Дело не столько в медиане, сколько в разбросе: мимо туннеля он исчезает совсем.
#
# Выключить VPN целиком нельзя — через него работает сам Claude Code. Привязка
# сокетов трогает ТОЛЬКО наши запросы, остальная система остаётся в туннеле.
#
# Значение — IPv4 физического интерфейса (Wi-Fi / Ethernet), НЕ адрес TUN.
# Посмотреть:  Get-NetIPAddress -AddressFamily IPv4
# Пусто — работаем как раньше, через маршрут по умолчанию.
OUTBOUND_LOCAL_IP = os.environ.get("OUTBOUND_LOCAL_IP", "").strip()


def _usable_local_ip() -> str | None:
    """Адрес ещё существует на машине?

    После смены сети (другой Wi-Fi, новый адрес по DHCP) записанный в .env адрес
    исчезнет, и тогда КАЖДЫЙ исходящий запрос упадёт на bind — сервер выглядел бы
    полностью сломанным из-за строчки в конфиге. Поэтому проверяем на старте и при
    неудаче молча возвращаемся к обычной маршрутизации, громко сказав об этом.
    """
    if not OUTBOUND_LOCAL_IP:
        return None
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((OUTBOUND_LOCAL_IP, 0))
        return OUTBOUND_LOCAL_IP
    except OSError as e:
        print(f"[startup] OUTBOUND_LOCAL_IP={OUTBOUND_LOCAL_IP} больше не существует "
              f"на этой машине ({e}). Работаю через обычный маршрут — это медленнее. "
              f"Посмотри новый адрес: Get-NetIPAddress -AddressFamily IPv4")
        return None
    finally:
        probe.close()


_LOCAL_IP = _usable_local_ip()

# STT-модели грузим лениво и по одному разу на имя (первая загрузка качает веса).
# Держать оба инстанса в памяти дёшево: base.en ~150 МБ, tiny.en ~75 МБ.
_whisper: dict[str, WhisperModel] = {}


def get_whisper(name: str | None = None) -> WhisperModel:
    key = name or WHISPER_MODEL
    if key not in _whisper:
        # int8 на CPU — самый лёгкий режим для ноутбука без GPU.
        _whisper[key] = WhisperModel(key, device="cpu", compute_type="int8")
    return _whisper[key]


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise HTTPException(
            status_code=500,
            detail=f"{name} не задан. Заполни backend/.env (см. .env.example).",
        )
    return val


def transcribe(data: bytes, model: str | None = None) -> str:
    """STT локально через faster-whisper. На вход — байты webm/opus из браузера.

    `model` — какую модель взять. Разговор зовёт быструю, монолог точную,
    объяснение размена см. у WHISPER_MODEL_FAST.
    """
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(data)
        path = f.name
    try:
        segments, _info = get_whisper(model).transcribe(path, language="en", beam_size=1)
        return " ".join(seg.text for seg in segments).strip()
    finally:
        os.unlink(path)


_stt_http: httpx.AsyncClient | None = None


def _stt_client() -> httpx.AsyncClient:
    """Отдельный HTTP-клиент для загрузки аудио в Mistral.

    Почему отдельный, а не общий с LLM. Остальные запросы мы намеренно шлём мимо
    VPN (OUTBOUND_LOCAL_IP) — так вчетверо быстрее. Но ЗАГРУЗКА ФАЙЛА по прямому
    маршруту рвётся: замерено 22.07.2026, три модели подряд, каждая ReadError
    через 15-19 с, тогда как через VPN те же запросы отвечают 200 за 0.5-2.7 с.
    Похоже на тот же DPI, который рубил туннель на крупных загрузках.

    Поэтому здесь local_address НЕ задаём — пусть идёт маршрутом по умолчанию.
    На хостинге никакого VPN нет, и обе ветки совпадут.
    """
    global _stt_http
    if _stt_http is None:
        # Таймаут короткий намеренно. Вечером 22.07.2026 загрузки в Mistral на
        # домашнем канале душились до 17-21 с, но В ИТОГЕ успевали — и запасной
        # локальный whisper не включался никогда: не было ошибки. С жёстким
        # порогом деградация сети превращается в честный откат: подождали
        # STT_TIMEOUT, не вышло — локальная модель разберёт за 1.5-3 с.
        # На Render это не мешает: там загрузка занимает ~0.4 с.
        _stt_http = httpx.AsyncClient(
            timeout=float(os.environ.get("STT_TIMEOUT", "12")), trust_env=False
        )
    return _stt_http


async def transcribe_remote(data: bytes, filename: str = "speech.webm") -> str:
    """STT через Mistral (Voxtral). Возвращает распознанный текст.

    `language` передаём ЯВНО, и это не формальность. Voxtral понимает 13 языков и
    без подсказки определяет его сам — на чистой речи это незаметно, а на русском
    акценте модель уплывает и выдаёт правдоподобную чушь вместо сказанного
    (пользователь поймал это 22.07.2026: «я такого не говорил»). Тренажёр по
    определению англоязычный, гадать язык ему незачем.
    """
    r = await _stt_client().post(
        f"{LLM_BASE_URL.rstrip('/')}/audio/transcriptions",
        headers={"Authorization": f"Bearer {_require('LLM_API_KEY')}"},
        data={"model": STT_REMOTE_MODEL, "language": STT_LANGUAGE},
        files={"file": (filename, data, "audio/webm")},
    )
    if r.status_code != 200:
        raise _RemoteSttError(r.status_code, r.text)
    body = r.json()
    u = body.get("usage") or {}
    _track_usage(stt_req=1, stt_audio_seconds=u.get("prompt_audio_seconds") or 0)
    return (body.get("text") or "").strip()


_storage_ok = False

# ------------------------------------------------------- Входной шлюз API
#
# Тяжёлые эндпоинты (STT+LLM+TTS жгут квоту ключа Mistral) закрыты для
# посторонних: фронт после входа шлёт X-Device = id аккаунта, сервер проверяет,
# что такой аккаунт существует. Любой curl со случайным uuid получает 401.
#
# Скорость: проверка — один SELECT по первичному ключу, и тот кэшируется на
# 10 минут, так что голосовая петля платит за шлюз ноль почти всегда.
#
# Отказ базы = шлюз ОТКРЫТ (fail-open, с криком в лог): назначение шлюза —
# отсечь халявщиков, а не охранять секреты. Уронить занятия всем ученикам
# из-за минутной икоты Neon — хуже, чем пропустить одного постороннего.
#
# REQUIRE_ACCOUNT=0 выключает шлюз (локальная отладка). ADMIN_KEY проходит
# всегда — этим пользуются смоук-тесты.

REQUIRE_ACCOUNT = os.environ.get("REQUIRE_ACCOUNT", "1").strip() not in ("0", "false", "no")

_ACCOUNT_CACHE: dict[str, float] = {}
_ACCOUNT_CACHE_TTL = 600.0


async def _require_account(x_device: str | None, x_admin_key: str | None = None) -> None:
    if not REQUIRE_ACCOUNT:
        return
    admin = os.environ.get("ADMIN_KEY", "")
    if admin and x_admin_key and hmac.compare_digest(x_admin_key, admin):
        return
    if not x_device:
        raise HTTPException(status_code=401, detail="Нужен аккаунт — войди в приложение.")
    now = time.monotonic()
    until = _ACCOUNT_CACHE.get(x_device)
    if until and until > now:
        return
    if not _storage_ok:
        print("[gate] база недоступна — пропускаю без проверки (fail-open)")
        return
    try:
        ok = await asyncio.to_thread(storage.account_exists, x_device)
    except Exception as e:  # noqa: BLE001
        print(f"[gate] проверка аккаунта не удалась ({type(e).__name__}) — fail-open")
        return
    if not ok:
        raise HTTPException(status_code=401, detail="Нужен аккаунт — войди в приложение.")
    # Кэш растёт только от НАСТОЯЩИХ аккаунтов — раздуть память мусорными
    # заголовками нельзя; страховочный сброс на всякий случай.
    if len(_ACCOUNT_CACHE) > 10_000:
        _ACCOUNT_CACHE.clear()
    _ACCOUNT_CACHE[x_device] = now + _ACCOUNT_CACHE_TTL


# Рейт-лимит в памяти процесса. Инстанс один (Render free), распределённый
# лимитер не нужен. Скользящее окно на deque: память O(limit) на ключ,
# словарь подчищается целиком при переполнении — грубо, но ограниченно.
_RATE: dict[str, deque] = {}


def _rate_ok(key: str, limit: int, window_sec: float) -> bool:
    now = time.monotonic()
    dq = _RATE.get(key)
    if dq is None:
        if len(_RATE) > 5_000:
            _RATE.clear()
        dq = deque()
        _RATE[key] = dq
    while dq and now - dq[0] > window_sec:
        dq.popleft()
    if len(dq) >= limit:
        return False
    dq.append(now)
    return True


def _client_ip(request: Request) -> str:
    # Render стоит за прокси: настоящий адрес — первый в X-Forwarded-For.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# --------------------------------------------------- Месячный бюджет Mistral
#
# Месячные квоты ключа в API не видны (только в консоли владельца), поэтому
# потолок ставим СВОЙ, консервативный, и охраняем его так, чтобы обычный ученик
# ничего не заметил:
#   - до 80% бюджета — жизнь как жизнь, никаких ограничений сверх обычных;
#   - дальше лимиты УЖИМАЮТСЯ, а не запрещаются, и только если расход
#     опережает календарь (80% бюджета 29-го числа — не повод никого душить);
#   - жёсткий отказ — только на 100%, и это отказ НАШЕГО потолка, а не ошибка
#     Mistral посреди начатого ответа.
# Считаем запросы LLM: по замеру 23.07.2026 именно они — узкое место, токены
# и близко не выбираются. 0 = бюджет выключен.
MONTHLY_LLM_BUDGET = int(os.environ.get("MONTHLY_LLM_BUDGET", "30000") or 0)

# Счётчик месяца в памяти процесса: инкремент на каждый вызов LLM, изредка
# сверяется с базой (переживает рестарты — Render передеплоивается часто).
_BUDGET = {"month": "", "used": 0, "synced": 0.0}


def _budget_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _month_elapsed_frac() -> float:
    now = datetime.now(timezone.utc)
    days = calendar.monthrange(now.year, now.month)[1]
    return (now.day - 1 + now.hour / 24.0) / days


def _budget_note_llm(n: int) -> None:
    month = _budget_month()
    if _BUDGET["month"] != month:
        _BUDGET.update(month=month, used=0, synced=0.0)
    _BUDGET["used"] += n


def _budget_sync_bg() -> None:
    """Фоновая сверка счётчика с базой: после рестарта память пустая, а месяц —
    нет. Берём максимум из двух: база отстаёт от памяти на fire-and-forget
    записи, память отстаёт от базы после рестарта."""
    if not _storage_ok:
        return

    async def run():
        try:
            month_db = await asyncio.to_thread(storage.month_report)
            db_used = int(month_db.get("llm_req", 0))
            month_now = _budget_month()
            if _BUDGET["month"] == month_now:
                _BUDGET["used"] = max(_BUDGET["used"], db_used)
            else:
                # Свежий процесс (month="") или смена месяца: база — истина.
                # Без этой ветки стартовая сверка молча промахивалась мимо
                # неинициализированного счётчика и used жил нулём до 10 минут.
                _BUDGET.update(month=month_now, used=db_used)
            print(f"[budget] сверка: {_BUDGET['used']}/{MONTHLY_LLM_BUDGET} за {month_now}")
        except Exception as e:  # noqa: BLE001
            print(f"[budget] сверка с базой не удалась ({type(e).__name__})")

    try:
        asyncio.create_task(run())
    except RuntimeError:
        pass


def _budget_state() -> dict:
    """Снимок бюджета для /health и решения о лимитах. mode:
    off / normal / eco (80%+ и опережаем календарь) / low (95%+) / empty."""
    if MONTHLY_LLM_BUDGET <= 0:
        return {"mode": "off"}
    month = _budget_month()
    if _BUDGET["month"] != month:
        _BUDGET.update(month=month, used=0, synced=0.0)
    used, frac = _BUDGET["used"], _BUDGET["used"] / MONTHLY_LLM_BUDGET
    ahead = frac > _month_elapsed_frac()
    mode = "normal"
    if frac >= 1.0:
        mode = "empty"
    elif frac >= 0.95 and ahead:
        mode = "low"
    elif frac >= 0.80 and ahead:
        mode = "eco"
    return {"mode": mode, "used": used, "budget": MONTHLY_LLM_BUDGET,
            "pct": round(frac * 100, 1)}


def _check_voice_rate(identity: str) -> None:
    """Три слоя защиты бюджета Mistral (замер лимитов ключа 23.07.2026:
    LLM 50 запросов/мин на ВСЕХ — это и есть узкое место всей системы).

    1. 20/мин на человека: живой ученик делает 6-10 (реплика = секунды речи +
       ответ), в лимит упрётся только скрипт.
    2. 300/день на человека: усердный ученик делает 100-150 реплик за день;
       кап ловит уведённый аккаунт и зацикленный клиент, не мешая людям.
    3. 45/мин ГЛОБАЛЬНО — ниже провайдерских 50: когда все ученики разом
       упираются в бюджет, они получают наш вежливый 429 «сервис занят», а не
       ошибку Mistral посреди начатого стрима с уже сожжённым STT.

    Поверх — месячный бюджет: при перерасходе лимиты ужимаются (см. _BUDGET),
    полный отказ — только когда месяц выбран целиком.
    """
    per_min, per_day, per_glob = 20, 300, 45
    state = _budget_state()
    if state["mode"] != "off":
        now = time.monotonic()
        if now - _BUDGET["synced"] > 600:
            _BUDGET["synced"] = now
            _budget_sync_bg()
        if state["mode"] == "empty":
            raise HTTPException(
                status_code=429,
                detail="Месячный запас занятий исчерпан — он обновится 1 числа. "
                       "Спасибо, что занимаешься так много!",
            )
        if state["mode"] == "low":
            per_min, per_day, per_glob = 6, 60, 15
        elif state["mode"] == "eco":
            per_min, per_day, per_glob = 10, 150, 30

    if not _rate_ok(f"v:{identity}", per_min, 60.0):
        raise HTTPException(status_code=429, detail="Слишком много запросов подряд — подожди минутку.")
    if not _rate_ok(f"vd:{identity}", per_day, 86_400.0):
        raise HTTPException(
            status_code=429,
            detail="Дневной лимит занятий исчерпан — продолжим завтра. Так мы бережём общий бюджет.",
        )
    if not _rate_ok("v:__global__", per_glob, 60.0):
        raise HTTPException(
            status_code=429,
            detail="Сервис сейчас занят другими учениками — попробуй через минуту.",
        )


async def _load_memory(device: str | None, kind: str | None) -> dict:
    """Выжимки для промпта. Единственное место, где память сидит в горячем пути,
    поэтому жёсткий лимит времени: не успела за секунду — отвечаем без неё.
    Пустой словарь — легальный результат, а не ошибка."""
    if not _storage_ok or not (device or kind):
        return {}
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(storage.get_digests, device, kind), timeout=1.0
        )
    except Exception as e:  # noqa: BLE001
        print(f"[memory] чтение не удалось ({type(e).__name__}: {str(e)[:80]})")
        return {}


def _memory_prompt_block(mem: dict) -> str:
    """Блок памяти для промпта разбора.

    Память — ДОПОЛНЕНИЕ к разбору, не его основа (требование владельца,
    23.07.2026). Это обеспечено дважды: конструкцией (основной промпт с
    критериями всегда идёт первым и целиком, память дописывается в конец, а без
    неё разбор работает так же) и явными правилами ниже — LLM запрещено
    импортировать старые ошибки в текущий ответ и менять балл из-за памяти.
    """
    if not mem:
        return ""
    block = "\n\nBACKGROUND CONTEXT — secondary to everything above:\n"
    if mem.get("user"):
        block += f"- This student's recent profile: {mem['user']}\n"
    if mem.get("global"):
        block += f"- {mem['global']}\n"
    block += (
        "Rules for this context: grade ONLY the current answer by the criteria above. "
        "NEVER list a mistake from memory that is not present in the current answer, "
        "and never change the score because of memory. Use it only to (a) note when a "
        "past mistake is repeated NOW, (b) praise clear improvement over the profile."
    )
    return block


def _track_usage(**metrics) -> None:
    """Свой счётчик расхода Mistral — фоном, мимо критического пути.

    Зачем: лимиты ключа не безлимитные (LLM 50 req/мин и 50k токенов/мин по
    заголовкам API), а месячные квоты видны только в консоли. Считаем сами —
    сводка в /admin/usage и кратко в /health."""
    # Месячный бюджет питается отсюда же — единая точка учёта вызовов LLM.
    # Инкремент в памяти, база не при чём: работает и при упавшем storage.
    if metrics.get("llm_req"):
        _budget_note_llm(int(metrics["llm_req"]))
    if not _storage_ok:
        return

    async def run():
        try:
            await asyncio.to_thread(storage.bump_usage, metrics)
        except Exception as e:  # noqa: BLE001
            print(f"[usage] не записал ({type(e).__name__}: {str(e)[:60]})")

    try:
        asyncio.create_task(run())
    except RuntimeError:
        pass  # вне event loop — в наших путях не случается


def _track_llm(completion) -> None:
    u = getattr(completion, "usage", None)
    if u is not None:
        _track_usage(llm_req=1,
                     llm_prompt_tokens=getattr(u, "prompt_tokens", 0) or 0,
                     llm_completion_tokens=getattr(u, "completion_tokens", 0) or 0)
    else:
        _track_usage(llm_req=1)

def _remember(device: str | None, kind: str, variant: str, feedback: dict,
              duration_sec: int, session_done: bool = False) -> None:
    """Запись итога в память — строго fire-and-forget: ученик ответа не ждёт,
    а упавшая база не должна отнимать у него разбор. Здесь же начисляется XP
    за задание (внутри save_result — там честно видно, повтор это или нет)."""
    if not (_storage_ok and device):
        return

    async def run():
        try:
            await asyncio.to_thread(
                storage.save_result, device, kind, variant,
                int(feedback.get("score") or 0), int(feedback.get("max") or 0),
                duration_sec, feedback.get("errors") or [],
                session_done,
            )
        except Exception as e:  # noqa: BLE001
            print(f"[memory] запись не удалась ({type(e).__name__}: {str(e)[:80]})")

    asyncio.create_task(run())


def _note_reply_bg(device: str | None) -> None:
    """Реплика разговора состоялась — день засчитан, XP начислен (с дневным
    потолком, см. storage.note_reply). Fire-and-forget: разговор эти записи
    не ждёт, а без базы просто не будет стрика — не разговора."""
    if not (_storage_ok and device):
        return

    async def run():
        try:
            await asyncio.to_thread(storage.note_reply, device)
        except Exception as e:  # noqa: BLE001
            print(f"[xp] реплика не записана ({type(e).__name__}: {str(e)[:60]})")

    asyncio.create_task(run())


# ---------------------------------------------------------------- Аккаунты
#
# Регистрация по никнейму и паролю, без почты и восстановления (решение
# владельца, 23.07.2026): никнейм генерируется на фронте из двух английских
# слов, ученику прямо говорят записать пару. Хэш — PBKDF2 из стандартной
# библиотеки: для паролей от аккаунтов без денег и почты этого достаточно,
# а зависимость не добавляется.

def _hash_pw(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120_000)
    return f"{salt}${digest.hex()}"


def _check_pw(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120_000)
        return hmac.compare_digest(digest.hex(), expected)
    except ValueError:
        return False


@app.post("/auth/register")
async def auth_register(request: Request, body: dict = Body(...)):
    # 12 попыток в минуту с одного адреса: живой человек столько не нажмёт,
    # а скрипту, штампующему аккаунты (или перебирающему пароли в login),
    # этого мало.
    if not _rate_ok(f"a:{_client_ip(request)}", 12, 60.0):
        raise HTTPException(status_code=429, detail="Слишком много попыток — подожди минутку.")
    nickname = str(body.get("nickname") or "").strip()
    password = str(body.get("password") or "")
    exam = str(body.get("exam") or "ege")
    # Только английские буквы, без цифр: ник генерируется из двух слов, руками
    # его не вводят (23.07.2026). Фронт это и так не даёт, но API обязан
    # проверять сам — в базу не должно попадать то, что нельзя сгенерировать.
    if not re.fullmatch(r"[A-Za-z]{4,32}", nickname):
        raise HTTPException(
            status_code=422,
            detail="Никнейм — два английских слова без цифр, он генерируется кнопкой.",
        )
    if len(password) < 4:
        raise HTTPException(status_code=422, detail="Пароль — минимум 4 символа.")
    if exam not in ("ege", "other"):
        # ОГЭ фронт не пропускает («soon...»), но сервер обязан проверить сам.
        raise HTTPException(status_code=422, detail="Сейчас доступны ЕГЭ и «другое».")
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна — попробуй чуть позже.")
    try:
        acc_id = await asyncio.to_thread(storage.create_account, nickname, _hash_pw(password), exam)
    except Exception as e:  # noqa: BLE001
        if storage.is_unique_violation(e):
            raise HTTPException(status_code=409, detail="Этот никнейм занят — нажми Change.")
        print(f"[auth] регистрация не удалась: {type(e).__name__}: {str(e)[:120]}")
        raise HTTPException(status_code=503, detail="Не получилось создать аккаунт — попробуй ещё раз.")
    return {"id": acc_id, "nickname": nickname, "exam": exam}


@app.post("/auth/login")
async def auth_login(request: Request, body: dict = Body(...)):
    if not _rate_ok(f"a:{_client_ip(request)}", 12, 60.0):
        raise HTTPException(status_code=429, detail="Слишком много попыток — подожди минутку.")
    nickname = str(body.get("nickname") or "").strip()
    password = str(body.get("password") or "")
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна — попробуй чуть позже.")
    row = await asyncio.to_thread(storage.get_account, nickname)
    if row is None or not _check_pw(password, row[2]):
        # Не различаем «нет такого» и «пароль не тот» — нечего дарить перебору.
        raise HTTPException(status_code=401, detail="Неверный никнейм или пароль.")
    return {"id": row[0], "nickname": row[1], "exam": row[3]}


@app.get("/progress")
async def progress(x_device: str | None = Header(None)):
    """Какие варианты этот ученик уже сдавал — чтобы выдача сессий вычёркивала
    пройденное на любом устройстве, а не только в этом браузере."""
    if not (_storage_ok and x_device):
        return {"solved": []}
    try:
        solved = await asyncio.to_thread(storage.solved_variants, x_device)
    except Exception:  # noqa: BLE001
        solved = []
    return {"solved": solved}


# ------------------------------------------------- Личный кабинет: стрик и XP

# Уровни: порог следующего = 50·L·(L+1) XP суммарно (уровень 1 → 100, 2 → 300,
# 3 → 600, 4 → 1000...). Первые уровни берутся за день-другой — быстрая награда
# новичку, дальше шаг растёт. Имена — экзаменационная легенда до «Examiner».
_LEVEL_NAMES = ["Beginner", "Rookie", "Learner", "Talker", "Speaker",
                "Storyteller", "Debater", "Orator", "Expert", "Examiner"]


def _level_info(xp: int) -> dict:
    level = 1
    while xp >= 50 * level * (level + 1) and level < 99:
        level += 1
    start, nxt = 50 * (level - 1) * level, 50 * level * (level + 1)
    return {
        "level": level,
        "name": _LEVEL_NAMES[min(level - 1, len(_LEVEL_NAMES) - 1)],
        "xp": xp,
        "level_start": start,
        "next_at": nxt,
        "progress": round((xp - start) / (nxt - start), 3),
    }


def _compute_streak(active: set[str], today_str: str) -> dict:
    """Стрик из множества активных дней (московских). Хранится не он, а дни —
    вычисленный стрик невозможно рассинхронизировать.

    Заморозка: ОДНА пропущенная дата на календарную (ISO) неделю не рвёт
    цепочку — сгоревший двадцатидневный стрик это главный момент, где теряют
    учеников. Два пропуска в одну неделю — цепочка рвётся честно. Сегодняшний
    день без занятий цепочку не трогает: его ещё можно закрыть.
    """
    today = date.fromisoformat(today_str)
    # Потраченной считается только заморозка-МОСТ: пропуск, за которым цепочка
    # продолжилась. Обрыв в пустоту до начала цепочки заморозку не ест — иначе
    # новичок с первым днём занятий видел бы «заморозки нет».
    bridged: set[tuple[int, int]] = set()
    pending: list[tuple[int, int]] = []
    streak = 0
    cur = today if today_str in active else today - timedelta(days=1)
    while streak < 3650:
        if cur.isoformat() in active:
            streak += 1
            bridged.update(pending)
            pending.clear()
        else:
            week = cur.isocalendar()[:2]
            if week in bridged or week in pending:
                break
            pending.append(week)
        cur -= timedelta(days=1)
    return {
        "days": streak,
        "active_today": today_str in active,
        "freeze_available": today.isocalendar()[:2] not in bridged,
    }


@app.get("/me/stats")
async def me_stats(x_device: str | None = Header(None),
                   x_admin_key: str | None = Header(None)):
    """Стрик, уровень, XP и неделя столбиками — всё для личного кабинета одним
    запросом. Числа считает сервер из activity_days; фронт только рисует."""
    await _require_account(x_device, x_admin_key)
    if not (_storage_ok and x_device):
        raise HTTPException(status_code=503, detail="Статистика недоступна — база не отвечает.")
    summary = await asyncio.to_thread(storage.activity_summary, x_device)
    active = {d["day"] for d in summary["days"] if d["replies"] + d["tasks"] > 0}
    today = date.fromisoformat(summary["today"])
    by_day = {d["day"]: d for d in summary["days"]}
    week = []
    for i in range(6, -1, -1):
        key = (today - timedelta(days=i)).isoformat()
        d = by_day.get(key)
        week.append({"day": key, "xp": d["xp"] if d else 0,
                     "actions": d["replies"] + d["tasks"] if d else 0})
    return {
        "level": _level_info(summary["xp_total"]),
        "streak": _compute_streak(active, summary["today"]),
        "week": week,
        "totals": {"replies": summary["replies_total"],
                   "tasks": summary["tasks_total"],
                   "xp": summary["xp_total"]},
    }


# --------------------------------------------- Личный кабинет: настройки и ник

def _sanitize_settings(raw: dict) -> dict:
    """Белый список настроек: чужие ключи и дикие значения в базу не попадают.
    Настройки следуют за аккаунтом между устройствами, как и память."""
    out: dict = {}
    if raw.get("theme") in ("dark", "light"):
        out["theme"] = raw["theme"]
    vol = raw.get("volume")
    if isinstance(vol, (int, float)) and not isinstance(vol, bool) and 0 <= vol <= 1:
        out["volume"] = round(float(vol), 2)
    if isinstance(raw.get("show_text"), bool):
        out["show_text"] = raw["show_text"]
    return out


@app.get("/me/settings")
async def me_settings_get(x_device: str | None = Header(None),
                          x_admin_key: str | None = Header(None)):
    await _require_account(x_device, x_admin_key)
    if not (_storage_ok and x_device):
        return {"settings": {}}
    try:
        raw = json.loads(await asyncio.to_thread(storage.get_settings, x_device))
    except Exception:  # noqa: BLE001
        raw = {}
    return {"settings": _sanitize_settings(raw if isinstance(raw, dict) else {})}


@app.post("/me/settings")
async def me_settings_post(body: dict = Body(...),
                           x_device: str | None = Header(None),
                           x_admin_key: str | None = Header(None)):
    await _require_account(x_device, x_admin_key)
    if not x_device:
        raise HTTPException(status_code=401, detail="Нужен аккаунт.")
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна — настройки не сохранились.")
    clean = _sanitize_settings(body if isinstance(body, dict) else {})
    await asyncio.to_thread(storage.save_settings, x_device, json.dumps(clean))
    return {"settings": clean}


@app.post("/me/nickname")
async def me_nickname(request: Request, body: dict = Body(...),
                      x_device: str | None = Header(None),
                      x_admin_key: str | None = Header(None)):
    """Смена ника: имя по-прежнему только генерируется (фронт), сервер проверяет
    те же правила, что при регистрации. Ник — это логин, поэтому под тем же
    рейт-лимитом, что /auth/*."""
    await _require_account(x_device, x_admin_key)
    if not _rate_ok(f"a:{_client_ip(request)}", 12, 60.0):
        raise HTTPException(status_code=429, detail="Слишком много попыток — подожди минутку.")
    if not x_device:
        raise HTTPException(status_code=401, detail="Нужен аккаунт.")
    nickname = str(body.get("nickname") or "").strip()
    if not re.fullmatch(r"[A-Za-z]{4,32}", nickname):
        raise HTTPException(
            status_code=422,
            detail="Никнейм — два английских слова без цифр, он генерируется кнопкой.",
        )
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна — попробуй чуть позже.")
    try:
        ok = await asyncio.to_thread(storage.rename_account, x_device, nickname)
    except Exception as e:  # noqa: BLE001
        if storage.is_unique_violation(e):
            raise HTTPException(status_code=409, detail="Этот никнейм занят — попробуй ещё раз.")
        print(f"[auth] смена ника не удалась: {type(e).__name__}: {str(e)[:120]}")
        raise HTTPException(status_code=503, detail="Не получилось сменить ник — попробуй ещё раз.")
    if not ok:
        raise HTTPException(status_code=401, detail="Аккаунт не найден.")
    return {"id": x_device, "nickname": nickname}


# ------------------------------------------------------------ Банк заданий

ADMIN_KEY = os.environ.get("ADMIN_KEY", "").strip()


def _require_admin(key: str | None) -> None:
    if not ADMIN_KEY:
        raise HTTPException(status_code=503, detail="ADMIN_KEY не задан в окружении сервера.")
    if not key or not hmac.compare_digest(key, ADMIN_KEY):
        raise HTTPException(status_code=401, detail="Неверный админ-ключ.")


@app.get("/tasks")
async def tasks_public():
    """Активные задания из банка. Фронт мешает их со встроенными вариантами;
    если базы нет — отвечаем пустым списком, встроенный банк никуда не девается."""
    if not _storage_ok:
        return {"tasks": []}
    try:
        rows = await asyncio.to_thread(storage.tasks_active)
    except Exception:  # noqa: BLE001
        return {"tasks": []}
    for r in rows:
        try:
            r["payload"] = json.loads(r["payload"])
        except json.JSONDecodeError:
            r["payload"] = {}
    return {"tasks": rows}


@app.post("/admin/tasks")
async def admin_task_add(body: dict = Body(...), x_admin_key: str | None = Header(None)):
    _require_admin(x_admin_key)
    exam = str(body.get("exam") or "ege")
    kind = str(body.get("kind") or "")
    try:
        task_no = int(body.get("task_no") or 0)
    except (TypeError, ValueError):
        task_no = 0
    payload = body.get("payload")
    if exam not in ("ege", "oge", "other"):
        raise HTTPException(status_code=422, detail="Раздел: ege, oge или other.")
    if kind not in ("reading", "dialogue", "interview", "monologue"):
        raise HTTPException(status_code=422, detail="Тип: reading/dialogue/interview/monologue.")
    if not (1 <= task_no <= 99):
        raise HTTPException(status_code=422, detail="Номер задания: от 1 до 99.")
    if not isinstance(payload, dict) or not payload:
        raise HTTPException(status_code=422, detail="payload — объект с полями варианта.")
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна.")
    tid = await asyncio.to_thread(
        storage.task_add, exam, task_no, kind, json.dumps(payload, ensure_ascii=False)
    )
    return {"id": tid}


@app.get("/admin/tasks")
async def admin_task_list(x_admin_key: str | None = Header(None)):
    _require_admin(x_admin_key)
    if not _storage_ok:
        return {"tasks": []}
    rows = await asyncio.to_thread(storage.tasks_all)
    for r in rows:
        try:
            r["payload"] = json.loads(r["payload"])
        except json.JSONDecodeError:
            r["payload"] = {}
    return {"tasks": rows}


@app.post("/admin/tasks/{tid}/toggle")
async def admin_task_toggle(tid: str, x_admin_key: str | None = Header(None)):
    _require_admin(x_admin_key)
    state = await asyncio.to_thread(storage.task_toggle, tid)
    if state is None:
        raise HTTPException(status_code=404, detail="Задание не найдено.")
    return {"active": state}


@app.get("/admin/usage")
async def admin_usage(x_admin_key: str | None = Header(None)):
    """Расход Mistral по дням: свой счётчик вместо консоли, которую видно
    только владельцу. Лимиты ключа для ориентира — из заголовков API
    (замер 23.07.2026)."""
    _require_admin(x_admin_key)
    if not _storage_ok:
        return {"days": {}, "limits": {}}
    days = await asyncio.to_thread(storage.usage_report, 14)
    month = await asyncio.to_thread(storage.month_report)
    return {
        "days": days,
        "month": month,
        "budget": _budget_state(),
        "limits_per_minute": {
            "llm_requests": 50, "llm_tokens": 50_000,
            "stt_requests": 60, "stt_audio_seconds": 3600,
            "tts_input_characters": 12_000,
        },
    }


class SttFailed(Exception):
    """Распознать не удалось — ни основным путём, ни запасным.

    Отдельный тип нужен, чтобы эндпоинты могли показать ученику человеческую
    фразу, а техническую причину написать в лог. До 22.07.2026 наружу улетало
    «STT (faster-whisper) ошибка: [Errno 1094995529] Invalid data found when
    processing input: '/tmp/tmphwai8heq.webm'» — код ffmpeg и путь к временному
    файлу на экране у школьника.

    `user_message` — то, что показываем ученику. Причины разные, и валить всё в
    «запись пустая или повреждена» нельзя: на перегрузке Mistral (429) эта
    фраза заставляла человека перезаписывать нормальный ответ.
    """

    def __init__(self, detail: str, user_message: str | None = None):
        super().__init__(detail)
        self.user_message = user_message or (
            "Не расслышал — запись пустая или слишком короткая. Скажи ещё раз."
        )


class _RemoteSttError(Exception):
    """Ошибка HTTP от Mistral STT — со статусом, чтобы отличать перегрузку (429,
    надо просто повторить) от битого аудио (400, повторять бессмысленно)."""

    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:160]}")
        self.status = status


# Липкий откат распознавания. Провал Mistral (обычно таймаут загрузки на плохой
# сети) не должен стоить STT_TIMEOUT секунд НА КАЖДОЙ реплике — после провала
# следующие 5 минут распознаём сразу локально, а потом молча пробуем Mistral
# снова: деградация сети у пользователя обычно временная.
_stt_degraded_until = 0.0
_STT_DEGRADE_SECONDS = 300.0


async def transcribe_auto(data: bytes, local_model: str | None = None) -> str:
    """Распознавание с запасным путём.

    Основной путь — Mistral: быстрее и не требует ни памяти, ни процессора.
    Запасной — локальный whisper, если он разрешён (см. STT_FALLBACK_LOCAL).
    Понижение уровня печатаем в лог: молчаливая деградация хуже отсутствия.
    """
    global _stt_degraded_until
    remote_allowed = STT_PROVIDER == "mistral" and (
        STT_FALLBACK_LOCAL is False or time.time() >= _stt_degraded_until
    )
    if remote_allowed:
        # Две попытки с короткой паузой: жалоба пользователя «иногда тупит и
        # выдаёт ошибку» — это в основном разовые икоты сети и 429 у Mistral,
        # которые лечатся простым повтором. Повторяем только то, что имеет
        # смысл повторять: 429, 5xx и обрывы соединения; 400 (битое аудио)
        # повторять бессмысленно.
        last: Exception | None = None
        for attempt in (1, 2):
            try:
                return await transcribe_remote(data)
            except Exception as e:  # noqa: BLE001
                last = e
                permanent = isinstance(e, _RemoteSttError) and e.status not in (429,) and e.status < 500
                if attempt == 1 and not permanent:
                    await asyncio.sleep(0.6)
                    continue
                break
        detail = f"{type(last).__name__}: {str(last)[:160]}"
        if not STT_FALLBACK_LOCAL:
            print(f"[stt] Mistral не смог дважды ({detail}), откат выключен")
            overloaded = isinstance(last, _RemoteSttError) and (
                last.status == 429 or last.status >= 500
            )
            raise SttFailed(
                detail,
                "Сервис распознавания перегружен — подожди пару секунд и скажи ещё раз."
                if overloaded or not isinstance(last, _RemoteSttError)
                else None,
            ) from last
        _stt_degraded_until = time.time() + _STT_DEGRADE_SECONDS
        print(f"[stt] Mistral не смог ({detail}) — следующие "
              f"{_STT_DEGRADE_SECONDS:.0f}с распознаю локально")
    try:
        return await asyncio.to_thread(transcribe, data, local_model)
    except Exception as e:  # noqa: BLE001
        raise SttFailed(f"{type(e).__name__}: {str(e)[:160]}") from e


async def synthesize_edge(text: str) -> bytes:
    """TTS через edge-tts (нейро-голоса Microsoft). Возвращает mp3-байты.

    Пишем во ВРЕМЕННЫЙ файл (не в cwd), чтобы не мусорить в рабочей папке.

    Коннектор создаём НА КАЖДЫЙ вызов: edge-tts оборачивает сессию в `async with`
    и закрывает коннектор на выходе, переиспользовать его нельзя.
    """
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        path = f.name
    try:
        connector = aiohttp.TCPConnector(local_addr=(_LOCAL_IP, 0)) if _LOCAL_IP else None
        communicate = edge_tts.Communicate(text, TTS_VOICE, connector=connector)
        await communicate.save(path)
        # edge-tts бесплатный, но метрика нужна: если однажды придётся уйти на
        # платный TTS целиком, объём уже будет известен.
        _track_usage(tts_edge_chars=len(text))
        with open(path, "rb") as fh:
            return fh.read()
    finally:
        if os.path.exists(path):
            os.unlink(path)


async def synthesize_mistral(text: str) -> bytes:
    """TTS через Mistral. Тот же ключ, что у STT и LLM."""
    r = await _stt_client().post(
        f"{LLM_BASE_URL.rstrip('/')}/audio/speech",
        headers={"Authorization": f"Bearer {_require('LLM_API_KEY')}"},
        json={"model": TTS_REMOTE_MODEL, "input": text, "voice": TTS_REMOTE_VOICE},
    )
    if r.status_code != 200:
        raise RuntimeError(f"Mistral TTS вернул {r.status_code}: {r.text[:200]}")
    _track_usage(tts_mistral_chars=len(text))
    return r.content


_tts_degraded = False


async def synthesize(text: str) -> bytes:
    """Синтез с запасным путём: edge-tts, при отказе — Mistral.

    Один отказ переключает на запасной путь до конца жизни процесса: если
    edge-tts недоступен с этого IP (а такое подозревают на хостингах), он не
    станет доступен через фразу, и платить таймаутом на каждой реплике незачем.
    """
    global _tts_degraded
    if TTS_PROVIDER == "mistral" or _tts_degraded:
        return await synthesize_mistral(text)
    try:
        return await synthesize_edge(text)
    except Exception as e:  # noqa: BLE001
        print(f"[tts] edge-tts отказал ({type(e).__name__}: {str(e)[:100]}), "
              f"перехожу на Mistral {TTS_REMOTE_VOICE} до перезапуска")
        _tts_degraded = True
        return await synthesize_mistral(text)


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
            http_client=httpx.Client(
                transport=httpx.HTTPTransport(local_address=_LOCAL_IP),
                timeout=_LLM_TIMEOUT, trust_env=False,
            ),
        )
    return _llm


def async_llm_client() -> AsyncOpenAI:
    # Асинхронный клиент — для стриминга токенов (/talk_stream).
    # Свой транспорт нужен ради local_address: см. OUTBOUND_LOCAL_IP выше.
    # trust_env=False — чтобы системный прокси VPN не подхватился обратно.
    global _async_llm
    if _async_llm is None:
        _async_llm = AsyncOpenAI(
            base_url=LLM_BASE_URL, api_key=_require("LLM_API_KEY"),
            timeout=_LLM_TIMEOUT, max_retries=_LLM_RETRIES,
            http_client=httpx.AsyncClient(
                transport=httpx.AsyncHTTPTransport(local_address=_LOCAL_IP),
                timeout=_LLM_TIMEOUT, trust_env=False,
            ),
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


async def _keep_awake_loop():
    """Раз в 10 минут дёргаем собственный /health, чтобы хостинг не усыпил сервис.

    Ошибки глотаем молча по одной, но считаем подряд идущие: если адрес задан
    неверно, лог не должен превратиться в поток мусора, а знать об этом надо.
    """
    fails = 0
    while True:
        await asyncio.sleep(600)
        hour = time.gmtime().tm_hour
        awake_window = (
            KEEP_AWAKE_FROM_HOUR_UTC <= hour < KEEP_AWAKE_TO_HOUR_UTC
            if KEEP_AWAKE_FROM_HOUR_UTC < KEEP_AWAKE_TO_HOUR_UTC
            # окно через полночь (например 22:00-06:00)
            else hour >= KEEP_AWAKE_FROM_HOUR_UTC or hour < KEEP_AWAKE_TO_HOUR_UTC
        )
        if not awake_window:
            continue
        try:
            async with httpx.AsyncClient(timeout=30, trust_env=False) as cl:
                await cl.get(KEEP_AWAKE_URL.rstrip("/") + "/health")
            if fails:
                print(f"[keep-awake] снова отвечает (было {fails} неудач подряд)")
            fails = 0
        except Exception as e:  # noqa: BLE001
            fails += 1
            if fails in (1, 5, 20):
                print(f"[keep-awake] не достучался до {KEEP_AWAKE_URL} "
                      f"({type(e).__name__}), неудач подряд: {fails}")


@app.on_event("startup")
async def _warmup():
    # Локальные модели греем ТОЛЬКО если распознаём локально. Иначе не грузим их
    # вовсе: в этом и смысл перехода на Mistral — не занимать под whisper ~700 МБ
    # памяти, которых на бесплатном хостинге просто нет. Если Mistral однажды не
    # ответит, модель подгрузится лениво в момент отката (первый раз медленно —
    # это честная цена за то, что в обычном режиме её нет в памяти совсем).
    if STT_PROVIDER == "mistral":
        print(f"[startup] STT: Mistral {STT_REMOTE_MODEL} (локальный whisper — только запасной путь)")
        # Прогреваем СОЕДИНЕНИЕ, а не модель. Замерено 22.07.2026: первые два
        # запроса после старта заняли 7.9 и 15.1 с, дальше стабильно 0.43-0.54 с.
        # Разница — TLS-хендшейк и разогрев маршрута; платить за него должен старт
        # сервера, а не первая реплика ученика.
        try:
            t = time.time()
            await _stt_client().get(
                f"{LLM_BASE_URL.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {os.environ.get('LLM_API_KEY', '')}"},
            )
            print(f"[startup] соединение с Mistral прогрето за {time.time() - t:.1f}с")
        except Exception as e:  # noqa: BLE001
            print(f"[startup] прогрев не удался ({type(e).__name__}) — не страшно, "
                  f"первая реплика просто будет медленнее")
    else:
        for name in dict.fromkeys([WHISPER_MODEL, WHISPER_MODEL_FAST]):
            print(f"[startup] Загружаю faster-whisper:{name} (первый раз качает модель, подожди)...")
            await asyncio.to_thread(get_whisper, name)
        print("[startup] STT-модели готовы.")
    if KEEP_AWAKE_URL:
        asyncio.create_task(_keep_awake_loop())
        print(f"[startup] самопинг раз в 10 мин на {KEEP_AWAKE_URL}, "
              f"окно {KEEP_AWAKE_FROM_HOUR_UTC:02d}:00-{KEEP_AWAKE_TO_HOUR_UTC:02d}:00 UTC")

    # Память об ошибках. Недоступная база НЕ роняет сервер: продукт обязан
    # работать и без памяти, просто без персонализации.
    global _storage_ok
    try:
        await asyncio.to_thread(storage.ensure_schema)
        _storage_ok = True
        print(f"[startup] память включена: {storage.describe()}")
        if not storage.DATABASE_URL:
            print("[startup] ⚠ память в SQLite: на Render диск эфемерный, база "
                  "живёт до ближайшего деплоя. Для постоянной — DATABASE_URL (Neon).")
    except Exception as e:  # noqa: BLE001
        _storage_ok = False
        print(f"[startup] память НЕдоступна ({type(e).__name__}: {e}) — работаю без неё")

    # Месячный бюджет: после рестарта память процесса пустая, а месяц — нет.
    # Сверяемся с базой сразу, не дожидаясь ленивого триггера в _check_voice_rate.
    # Строго ПОСЛЕ включения памяти: _budget_sync_bg без _storage_ok — no-op.
    if MONTHLY_LLM_BUDGET > 0:
        _BUDGET["synced"] = time.monotonic()
        _budget_sync_bg()

    print("[startup] Сервер принимает запросы.")


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
        "stt": (
            f"mistral:{STT_REMOTE_MODEL}"
            + (f" (запасной: faster-whisper {WHISPER_MODEL_FAST}/{WHISPER_MODEL})"
               if STT_FALLBACK_LOCAL else " (без отката, локальный whisper выключен)")
            if STT_PROVIDER == "mistral"
            else f"faster-whisper:{WHISPER_MODEL_FAST} (разговор) / {WHISPER_MODEL} (монолог), local"
        ),
        "tts": f"edge-tts:{TTS_VOICE}",
        "llm_base": LLM_BASE_URL,
        "llm_model": LLM_MODEL,
        "llm_key": bool(os.environ.get("LLM_API_KEY")),
        "memory": storage.describe() if _storage_ok else "выключена",
        # Сводка расхода за сегодня — секретов не содержит, а увидеть «сколько
        # уже сожгли» можно без ключа админки. Полная разбивка — /admin/usage.
        "usage_today": _usage_today(),
        # Месячный бюджет вызовов LLM: mode normal/eco/low/empty (см. _BUDGET).
        "budget_month": _budget_state(),
    }


def _usage_today() -> dict:
    if not _storage_ok:
        return {}
    try:
        report = storage.usage_report(1)
        return next(iter(report.values()), {}) if report else {}
    except Exception:  # noqa: BLE001
        return {}


@app.post("/talk")
async def talk(audio: UploadFile = File(...),
               x_device: str | None = Header(None),
               x_admin_key: str | None = Header(None)):
    await _require_account(x_device, x_admin_key)
    _check_voice_rate(x_device or "admin")
    t0 = time.time()
    data = await audio.read()

    # 1) STT
    try:
        user_text = await transcribe_auto(data)
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
    _track_llm(completion)
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


async def _json_with_heartbeat(work):
    """Отдаём JSON потоком: пока считаем — шлём переводы строк.

    Зачем. Бесплатные туннели и часть прокси рвут запрос, который не отдал ни
    байта за несколько секунд. Замерено 22.07.2026 на serveo: обрыв ровно на
    5.1с, а `/monologue` честно считает 6-15с → через туннель он не работал
    никогда, отдавая 502. `/talk_stream` выживал только потому, что первый чанк
    уходит через ~3с. Здесь мы делаем то же самое искусственно.

    Ведущие переводы строк — валидный JSON, поэтому `res.json()` на фронте
    парсит ответ как раньше, менять разбор не нужно.

    Плата: статус ответа уходит ДО того, как результат посчитан, поэтому ошибка
    больше не может приехать кодом 502 — она приезжает полем `detail` в теле с
    кодом 200. Фронт проверяет и код, и это поле.
    """
    task = asyncio.create_task(work)
    while True:
        done, _ = await asyncio.wait({task}, timeout=2.0)
        if done:
            break
        yield "\n"
    try:
        yield json.dumps(task.result(), ensure_ascii=False)
    except HTTPException as e:
        yield json.dumps({"detail": e.detail}, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        yield json.dumps({"detail": f"Внутренняя ошибка: {e}"}, ensure_ascii=False)


@app.post("/monologue")
async def monologue(audio: UploadFile = File(...),
                    x_device: str | None = Header(None),
                    x_admin_key: str | None = Header(None)):
    """Разбор монолога (ЕГЭ Задание 4): полное аудио → batch STT → ОДИН
    структурный проход LLM → JSON-фидбэк (3 критерия + ошибки). Без TTS —
    разбор текстовый, для экрана результата.

    Отдаётся потоком с «сердцебиением» — см. `_json_with_heartbeat`. Тело ответа
    и его разбор на фронте от этого не меняются.
    """
    await _require_account(x_device, x_admin_key)
    _check_voice_rate(x_device or "admin")
    data = await audio.read()
    return StreamingResponse(
        _json_with_heartbeat(_monologue_work(data)),
        # text/event-stream вместо application/json — намеренно. Тело у нас не SSE,
        # но именно на этот Content-Type прокси (nginx и большинство облачных)
        # отключают буферизацию, а на JSON — нет. Фронт читает сырое тело через
        # body.getReader(), заголовок ему безразличен. Мы уже дважды теряли стриминг
        # на буферизации (gzip, DECISIONS §5 п.7), и на чужом хостинге проверить это
        # заранее нельзя — дешевле подстраховаться заголовком.
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


async def _monologue_work(data: bytes) -> dict:
    t0 = time.time()

    # 1) STT — весь монолог разом. Запасной локальный путь берёт ТОЧНУЮ модель:
    #    здесь каждое слово транскрипта превращается в балл ФИПИ.
    try:
        transcript_text = await transcribe_auto(data)
    except SttFailed as e:
        print(f"[stt] монолог не распознан: {e}")
        raise HTTPException(status_code=502, detail=e.user_message)
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

    _track_llm(completion)
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


# ------------------------------------------------------------------------
# Разбор ЛЮБОГО задания устной части: /task_feedback.
#
# Появился 22.07.2026 по запросу «подключи бэкенд везде, где есть голосовой
# ввод»: до этого ИИ-разбор был только у монолога (№42), а чтение, диалог и
# интервью честно говорили «разбора нет». Один эндпоинт на все типы, различия —
# в промпте; фронт передаёт kind и payload (текст для чтения / пункты вопросов).
#
# Единый формат ответа LLM для 39-41:
#   {"summary": <ru>, "score": N, "max": M, "errors": [{quote, correction,
#    explanation}]}
# Для monologue используется старый промпт с критериями ФИПИ, а score/max
# досчитываются на сервере — фронт везде видит одну и ту же форму.

_FEEDBACK_JSON_SHAPE = (
    'Return ONLY a JSON object (no prose, no markdown) with EXACTLY this shape:\n'
    '{"summary": "<one short sentence in Russian>", "score": <int>, "max": <int>, '
    '"errors": [{"cat": "gram|lex|order|missing|logic", '
    '"quote": "<what the student said, English>", '
    '"correction": "<fixed, English>", "explanation": "<по-русски, кратко>"}]}\n'
    "cat is the error category: gram=grammar, lex=vocabulary, order=word order, "
    "missing=required element absent, logic=meaning. It feeds the student's "
    "long-term mistake profile, so choose it carefully.\n"
    "Up to 6 most important errors. Be honest but encouraging (level A2-B1)."
)


def _feedback_prompt(kind: str, payload: dict) -> str:
    if kind == "reading":
        ref = str(payload.get("referenceText") or "")
        return (
            "You are an examiner for the Russian EGE oral English exam, Task 1 "
            "(reading a short text aloud). You get the REFERENCE text and an AUTOMATIC "
            "TRANSCRIPT of what the student actually said.\n\n"
            "IMPORTANT: a transcript cannot show pronunciation, stress or intonation — "
            "NEVER invent phonetic errors. Judge ONLY what the text shows: skipped, "
            "replaced, added or misread words. In errors, quote = what the student said "
            "(or «пропущено», if a fragment is missing), correction = the fragment as "
            "written in the reference.\n"
            "score: 1 if the text is read completely with at most 2 minor slips, else 0. "
            "max: 1.\n\n" + _FEEDBACK_JSON_SHAPE + f"\n\nREFERENCE TEXT:\n{ref}"
        )
    if kind == "dialogue":
        points = payload.get("points") or []
        ad = str(payload.get("ad") or "")
        pts = "; ".join(str(p) for p in points)
        return (
            "You are an examiner for the Russian EGE oral English exam, Task 2 (four "
            f"direct questions about an advertisement: {ad}). The student had to ask "
            f"four DIRECT questions about: {pts}.\n\n"
            "From the transcript, count how many of these points are covered by a "
            "correctly formed direct question. score = that count, max = 4. In errors "
            "list wrong word order, indirect questions instead of direct ones, and "
            "grammar slips. If a point was not asked about at all, add an error with "
            "quote=«вопрос не задан» and correction = an example of a correct question.\n\n"
            + _FEEDBACK_JSON_SHAPE
        )
    if kind == "interview":
        questions = [str(q) for q in (payload.get("questions") or [])]
        qs = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
        return (
            "You are an examiner for the Russian EGE oral English exam, Task 3 "
            "(interview). The student answered these questions one after another:\n"
            f"{qs}\n\n"
            "The transcript is one continuous recording of all answers. An answer counts "
            "as full if it is relevant and contains at least two sentences. "
            f"score = number of properly answered questions, max = {max(1, len(questions))}. "
            "In errors list grammar and vocabulary mistakes from the transcript.\n\n"
            + _FEEDBACK_JSON_SHAPE
        )
    # monologue — старый проверенный промпт с критериями ФИПИ
    return MONOLOGUE_PROMPT


async def _task_feedback_work(kind: str, payload_raw: str, data: bytes,
                              device: str | None, variant: str,
                              duration_sec: int, session_done: bool = False) -> dict:
    t0 = time.time()
    # Выжимки памяти тянем ПАРАЛЛЕЛЬНО с распознаванием: STT занимает 0.5-2 с,
    # SELECT успевает заведомо раньше — добавка к задержке ровно ноль.
    mem_task = asyncio.create_task(_load_memory(device, kind))
    try:
        transcript_text = await transcribe_auto(data)
    except SttFailed as e:
        print(f"[stt] task_feedback не распознал: {e}")
        raise HTTPException(status_code=502, detail=e.user_message)
    t1 = time.time()
    if not transcript_text:
        raise HTTPException(
            status_code=422, detail="Тишина — ничего не распознали. Запиши ответ ещё раз."
        )

    try:
        payload = json.loads(payload_raw) if payload_raw else {}
    except json.JSONDecodeError:
        payload = {}

    mem = await mem_task
    if mem:
        print(f"[memory] выжимки в промпте разбора: {', '.join(sorted(mem))}")

    client = llm_client()
    try:
        completion = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system",
                     "content": _feedback_prompt(kind, payload) + _memory_prompt_block(mem)},
                    {"role": "user", "content": transcript_text},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=800,
            )
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"LLM ошибка ({LLM_MODEL}): {e}")

    _track_llm(completion)
    raw = (completion.choices[0].message.content or "").strip()
    try:
        feedback = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail=f"LLM вернул не-JSON: {raw[:200]}")

    # Монолог отвечает в формате критериев ФИПИ — доводим до единой формы,
    # чтобы фронт не различал типы заданий.
    if kind == "monologue" and "criteria" in feedback:
        try:
            feedback["score"] = sum(int(c.get("score", 0)) for c in feedback["criteria"])
            feedback["max"] = sum(int(c.get("max", 0)) for c in feedback["criteria"]) or 10
        except (TypeError, ValueError):
            feedback["score"], feedback["max"] = 0, 10

    # В память — после того как ответ готов, мимо критического пути.
    _remember(device, kind, variant, feedback, duration_sec, session_done)

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


@app.post("/task_feedback")
async def task_feedback(
    audio: UploadFile = File(...),
    kind: str = Form(...),
    payload: str = Form("{}"),
    variant: str = Form(""),
    duration: int = Form(0),
    # «1» на последнем варианте серии — бонус XP за доведённую до конца сессию.
    # Флаг клиентский, но цена ему 25 XP под общими рейт-лимитами — воровать тут
    # нечего, а серверу пришлось бы ради него хранить состояние сессий.
    session_done: int = Form(0),
    x_device: str | None = Header(None),
    x_admin_key: str | None = Header(None),
):
    """Разбор ответа на задание устной части (39-42). Отдаётся потоком с
    «сердцебиением» — см. `_json_with_heartbeat`; путь обязан быть в
    `_STREAM_PATHS`, иначе gzip молча похоронит стриминг.

    `X-Device` — id аккаунта (или устройства): по нему и копится профиль
    ошибок, и работает входной шлюз."""
    await _require_account(x_device, x_admin_key)
    _check_voice_rate(x_device or "admin")
    if kind not in {"reading", "dialogue", "interview", "monologue"}:
        raise HTTPException(status_code=422, detail=f"Неизвестный тип задания: {kind}")
    data = await audio.read()
    return StreamingResponse(
        _json_with_heartbeat(
            _task_feedback_work(kind, payload, data, x_device, variant, duration,
                                bool(session_done))
        ),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


def _sanitize_history(raw: str) -> list[dict]:
    """История диалога от клиента — по 10 последних реплик.

    Память диалога НАМЕРЕННО клиентская: живёт в вкладке браузера и приходит с
    каждым запросом. Серверу это даёт ноль состояния и ноль хранения (мы решили
    не хранить транскрипты речи), а истории — естественную смерть вместе со
    вкладкой. Цена — ~400 токенов промпта, около +0.05 с у Mistral.

    Клиенту, впрочем, не верим: максимум 10 реплик, роли только user/assistant,
    каждая обрезается до 300 символов — иначе curl мог бы затолкать в промпт
    роман и оплатить его нашим ключом.
    """
    try:
        items = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    out = []
    for it in items[-10:]:
        if not isinstance(it, dict):
            continue
        role = it.get("role")
        content = str(it.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        out.append({"role": role, "content": content[:300]})
    return out


@app.post("/talk_stream")
async def talk_stream(audio: UploadFile = File(...),
                      history: str = Form("[]"),
                      x_device: str | None = Header(None),
                      x_admin_key: str | None = Header(None)):
    await _require_account(x_device, x_admin_key)
    _check_voice_rate(x_device or "admin")
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
        # Профиль ученика тянем параллельно с распознаванием — добавка ноль.
        # В разговоре используется только личная выжимка, без общей: тьютор
        # исправляет мягко и по чуть-чуть, сводка всех ошибок ему не нужна.
        mem_task = asyncio.create_task(_load_memory(x_device, None))
        # 1) STT (batch, после стопа — Шаг B сделает это стримингом во время речи).
        #    Запасной локальный путь — БЫСТРАЯ модель: в живом разговоре полторы
        #    секунды дороже, чем точность одного слова (см. WHISPER_MODEL_FAST).
        try:
            user_text = await transcribe_auto(data, WHISPER_MODEL_FAST)
        except SttFailed as e:
            # Ученику — человеческая фраза (у разных причин она разная: битая
            # запись vs перегрузка сервиса), техника уходит в лог сервера.
            print(f"[stt] не распознал: {e}")
            yield json.dumps(
                {"done": True, "user": "", "reply": e.user_message,
                 "latency": {"stt": round(time.time() - t0, 2), "first_audio": 0,
                             "total": round(time.time() - t0, 2)}}
            ) + "\n"
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

        # Личная выжимка делает тьютора внимательнее к повторяющимся ошибкам
        # именно этого ученика. Правило «одна короткая поправка за реплику»
        # сохраняется — оно уже в SYSTEM_PROMPT.
        mem = await mem_task
        sys_prompt = SYSTEM_PROMPT
        if mem.get("user"):
            sys_prompt += (
                "\n\nBackground context, secondary to everything above — memory about "
                f"this student: {mem['user']}\n"
                "Use it ONLY if one of these mistakes appears again in the current "
                "utterance — then gently point it out (still at most one short tip). "
                "Never bring up old mistakes on their own, and never let this memory "
                "change the topic of the conversation."
            )
            print("[memory] профиль ученика подключён к разговору")

        # Память ДИАЛОГА: последние реплики сессии между system и текущей фразой.
        # Тьютор помнит, о чём шла речь, и перестаёт отвечать с чистого листа.
        past = _sanitize_history(history)
        if past:
            print(f"[dialog] история: {len(past)} реплик")

        try:
            stream = await client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    *past,
                    {"role": "user", "content": user_text},
                ],
                max_tokens=120,
                stream=True,
            )
            stream_usage = None
            async for chunk in stream:
                # usage приезжает в последнем чанке стрима (если провайдер его
                # шлёт) — запоминаем для счётчика расхода.
                if getattr(chunk, "usage", None) is not None:
                    stream_usage = chunk.usage
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
            # Учёт расхода: точно из usage, а если стрим его не отдал — оценкой
            # по символам (~4 символа на токен): бюджету хватает точности ±20%.
            if stream_usage is not None:
                _track_usage(llm_req=1,
                             llm_prompt_tokens=getattr(stream_usage, "prompt_tokens", 0) or 0,
                             llm_completion_tokens=getattr(stream_usage, "completion_tokens", 0) or 0)
            else:
                approx_prompt = (len(sys_prompt) + sum(len(p["content"]) for p in past)
                                 + len(user_text)) // 4
                _track_usage(llm_req=1, llm_prompt_tokens=approx_prompt,
                             llm_completion_tokens=max(1, len(reply_full) // 4))
        except TtsFailed as e:
            yield json.dumps({"error": f"TTS (edge-tts) ошибка: {e}"}) + "\n"
            return
        except Exception as e:  # noqa: BLE001
            yield json.dumps({"error": f"LLM ошибка ({LLM_MODEL}): {e}"}) + "\n"
            return

        # Реплика состоялась целиком — только теперь она считается занятием
        # (стрик + XP). Оборванные и ошибочные ходы в статистику не попадают.
        _note_reply_bg(x_device)

        t2 = time.time()
        yield json.dumps(
            {"done": True, "user": user_text, "reply": reply_full.strip(),
             "latency": {"stt": round(t1 - t0, 2),
                         "first_audio": round((first_audio_at or t2) - t1, 2),
                         "total": round(t2 - t0, 2)}}
        ) + "\n"

    return StreamingResponse(
        gen(),
        # text/event-stream, а не application/x-ndjson — см. объяснение у /monologue:
        # на этот тип прокси отключают буферизацию, фронту заголовок безразличен.
        media_type="text/event-stream",
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
