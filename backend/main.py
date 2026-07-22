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
import socket
import tempfile
import time

# На Windows без Developer Mode huggingface_hub печатает безобидный warning
# про symlinks при каждой загрузке модели — глушим, чтобы не путать с ошибкой.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import aiohttp
import edge_tts
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from faster_whisper import WhisperModel
from openai import AsyncOpenAI, OpenAI

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
# /monologue тоже здесь: он шлёт «сердцебиение» переводами строк, а zlib копил бы
# их в буфере — и смысл сердцебиения пропал бы целиком.
_STREAM_PATHS = {"/talk_stream", "/monologue"}


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
        _stt_http = httpx.AsyncClient(timeout=60.0, trust_env=False)
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
        raise RuntimeError(f"Mistral STT вернул {r.status_code}: {r.text[:200]}")
    return (r.json().get("text") or "").strip()


class SttFailed(Exception):
    """Распознать не удалось — ни основным путём, ни запасным.

    Отдельный тип нужен, чтобы эндпоинты могли показать ученику человеческую
    фразу, а техническую причину написать в лог. До 22.07.2026 наружу улетало
    «STT (faster-whisper) ошибка: [Errno 1094995529] Invalid data found when
    processing input: '/tmp/tmphwai8heq.webm'» — код ffmpeg и путь к временному
    файлу на экране у школьника.
    """


async def transcribe_auto(data: bytes, local_model: str | None = None) -> str:
    """Распознавание с запасным путём.

    Основной путь — Mistral: быстрее и не требует ни памяти, ни процессора.
    Запасной — локальный whisper, если он разрешён (см. STT_FALLBACK_LOCAL).
    Понижение уровня печатаем в лог: молчаливая деградация хуже отсутствия.
    """
    if STT_PROVIDER == "mistral":
        try:
            return await transcribe_remote(data)
        except Exception as e:  # noqa: BLE001
            detail = f"{type(e).__name__}: {str(e)[:160]}"
            if not STT_FALLBACK_LOCAL:
                print(f"[stt] Mistral не смог ({detail}), откат выключен")
                raise SttFailed(detail) from e
            print(f"[stt] Mistral не смог ({detail}), перехожу на локальный whisper")
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
    }


@app.post("/talk")
async def talk(audio: UploadFile = File(...)):
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
async def monologue(audio: UploadFile = File(...)):
    """Разбор монолога (ЕГЭ Задание 4): полное аудио → batch STT → ОДИН
    структурный проход LLM → JSON-фидбэк (3 критерия + ошибки). Без TTS —
    разбор текстовый, для экрана результата.

    Отдаётся потоком с «сердцебиением» — см. `_json_with_heartbeat`. Тело ответа
    и его разбор на фронте от этого не меняются.
    """
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
        raise HTTPException(
            status_code=502,
            detail="Не удалось распознать запись — она пустая или повреждена. Запиши ещё раз.",
        )
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
        # 1) STT (batch, после стопа — Шаг B сделает это стримингом во время речи).
        #    Запасной локальный путь — БЫСТРАЯ модель: в живом разговоре полторы
        #    секунды дороже, чем точность одного слова (см. WHISPER_MODEL_FAST).
        try:
            user_text = await transcribe_auto(data, WHISPER_MODEL_FAST)
        except SttFailed as e:
            # Ученику — человеческая фраза, причина уходит в лог сервера.
            # Чаще всего сюда попадает пустая или слишком короткая запись.
            print(f"[stt] не распознал: {e}")
            yield json.dumps(
                {"done": True, "user": "",
                 "reply": "Не расслышал — запись пустая или слишком короткая. Скажи ещё раз.",
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
