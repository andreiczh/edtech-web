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
import io
import json
import os
import re
import secrets
import socket
import tempfile
import threading
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
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from faster_whisper import WhisperModel
from openai import AsyncOpenAI, OpenAI

import audio_check
import ege_prompts
import ege_scoring
import disputes
import fipi_import
import speak_check
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

# Собеседники (голос + характер) вынесены в personas.py — это чистые данные
# без зависимостей от main; здесь только импорт.
from personas import (  # noqa: E402 — после настройки окружения, как и прочие
    DEFAULT_EMOTION,
    DEFAULT_PERSONA,
    MAX_HEAT,
    PERSONAS,
    SYSTEM_PROMPT,
    emotion_of,
    heat_block,
    heat_level,
    persona_of,
    reply_tokens,
)

# Ход свободной беседы: лестница глубины, считается арифметикой из длины
# разговора. Банк заготовленных тем убран 04.08.2026 — тему выбирает человек.
import dialogue  # noqa: E402

# Разбор беседы: промпт, проверка цитат и форма ответа. Сети не касается.
import talk_review  # noqa: E402

# Промпт-ревьюер устного ЕГЭ, Задание 4 (монолог, голосовое сообщение другу).
# Разбор устной части живёт в двух соседних модулях:
#   ege_prompts.py — правила проверки из методички ФИПИ 2026, по которым модель
#                    выносит суждения эксперта (раскрыт аспект / принят вопрос);
#   ege_scoring.py — официальные шкалы, по которым из этих суждений считается балл.
# Модель баллов не ставит: пока ставила, оценка гуляла между запусками и не
# сходилась с образцами проверки. Запасной текст задания для старого /monologue,
# где формулировки от фронта не приходит.

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
# ("Paul"), тогда как сейчас звучит женский en-US-AvaMultilingualNeural. Для тренажёра это
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

# Кто озвучивает. По умолчанию mistral (решение владельца 04.08.2026 по
# прослушиванию: живая интонация оказалась важнее трёх разных тембров).
# Откат к трём голосам — TTS_PROVIDER=edge, ничего больше менять не нужно.
# Разбор компромисса — в synthesize().
TTS_PROVIDER = os.environ.get("TTS_PROVIDER", "mistral").strip().lower()
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
# Голос разговора. Ava — поколение Multilingual (2024+), заметно живее старой
# Aria и вдобавок быстрее: один и тот же текст 7.8с против 9.4с (замер 02.08.2026).
# Меняется переменной TTS_VOICE, список — `edge_tts.list_voices()`.
TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-AvaMultilingualNeural")
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

# Сколько живёт ПРОСТАИВАЮЩЕЕ соединение в пуле.
#
# Умолчание httpx — 5 секунд, и это тихо съедало весь прогрев. В разговоре между
# репликами проходит 10-60 с (человек слушает ответ и думает), значит к моменту
# следующей реплики пул пуст, и каждый запрос заново платит TCP + TLS. Прогрев
# на старте (см. _warmup) грел соединение, которое умирало через пять секунд и
# до первого же ученика не доживало.
#
# 300 с покрывают паузу между репликами с запасом. Дальше соединение всё равно
# закроет уже СЕРВЕР Mistral — поэтому его мало держать, его надо трогать:
# см. _keep_pools_warm.
_KEEPALIVE = httpx.Limits(max_keepalive_connections=8, max_connections=32,
                          keepalive_expiry=300.0)
# Как часто дёргать соединение, чтобы оно не закрылось со стороны сервера или
# NAT. 50 с — меньше типичного idle-таймаута (60 с) и в 3500 раз реже, чем
# лимит запросов; /models не тарифицируется и токенов не тратит.
_POOL_PING_EVERY = 50.0


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
            timeout=float(os.environ.get("STT_TIMEOUT", "12")), trust_env=False,
            limits=_KEEPALIVE,
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
# Состояние фоновой переподключалки — наружу в /health. Пока поле знало одно
# слово «выключена», отличить мёртвую базу от сборки БЕЗ повтора было нельзя:
# 26.08.2026 на это ушло десять минут гаданий по проду. Наружу отдаём тип
# ошибки и счётчик — ни хоста, ни пароля, ни строки подключения в них нет.
_STORAGE_RETRY: dict = {"attempts": 0, "error": "", "next_at": 0.0}

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

# Коды доступа на РЕГИСТРАЦИЮ (03.08.2026, хвост №1 из CLAUDE.md: открытая
# ссылка жгла бы квоту ключа любому прохожему). Логика fail-closed НАМЕРЕННО:
# нет кодов в окружении — регистрация закрыта, а не открыта. Забытая
# переменная должна закрывать дверь, а не распахивать её. Уже созданных
# аккаунтов это не касается: вход и занятия работают как работали.
#
# Формат: INVITE_CODES="код1,код2" — несколько кодов, чтобы разным группам
# (друзья, класс, репетитор) можно было выдать свой и отзывать по одному.
# Сравнение — hmac.compare_digest, как у ADMIN_KEY.
INVITE_CODES = frozenset(
    c.strip() for c in os.environ.get("INVITE_CODES", "").split(",") if c.strip()
)


def _invite_env_ok(code: str) -> bool:
    """Код из переменной окружения — «первый ключ» для холодного старта.
    Сравнение по всем кодам БЕЗ раннего выхода: время ответа не должно
    подсказывать перебором, похож ли код на настоящий."""
    ok = False
    for c in INVITE_CODES:
        if hmac.compare_digest(code, c):
            ok = True
    return ok


async def _check_invite(code: str) -> None:
    """Код доступа: сначала база (управляется из админки), потом переменная.

    Порядок такой намеренно. Коды в базе — рабочий инструмент владельца:
    выдал классу, исчерпал лимит, отключил один — всё без похода в панель
    Render и без редеплоя. Переменная INVITE_CODES осталась ровно для одного
    случая: база ещё пуста, и надо впустить первого человека, который заведёт
    остальные коды.

    Fail-closed сохраняется: нет ни кодов в базе, ни переменной — регистрация
    закрыта. Забытая настройка закрывает дверь, а не распахивает.
    """
    db_ok = False
    if _storage_ok and code:
        try:
            db_ok = await asyncio.to_thread(storage.invite_check, code)
        except Exception as e:  # noqa: BLE001
            print(f"[invite] база не ответила ({type(e).__name__}) — проверяю только переменную")
    if db_ok:
        await asyncio.to_thread(storage.invite_use, code)
        return
    if _invite_env_ok(code):
        return
    # Различать «кодов нет вовсе» и «код неверный» полезно ВЛАДЕЛЬЦУ, а не
    # постороннему: первое видно в /health, наружу — одна и та же фраза.
    has_any = bool(INVITE_CODES)
    if not has_any and _storage_ok:
        try:
            has_any = await asyncio.to_thread(storage.invites_count) > 0
        except Exception:  # noqa: BLE001
            pass
    if not has_any:
        raise HTTPException(
            status_code=503,
            detail="Регистрация пока закрыта. Напиши тому, кто дал ссылку.",
        )
    raise HTTPException(
        status_code=403,
        detail="Неверный код доступа. Спроси код у того, кто поделился ссылкой.",
    )

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


# Алерты владельцу вынесены в alerts.py — блок без зависимостей на main.
import alerts  # noqa: E402
import delivery  # noqa: E402
from alerts import note_failure, notify_owner  # noqa: E402


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
    # Переход в режим экономии/стопа — событие для владельца: продукт начал
    # душить учеников лимитами, и об этом лучше узнать из телеграма, чем от них.
    if mode != _BUDGET.get("alerted_mode"):
        _BUDGET["alerted_mode"] = mode
        if mode in ("eco", "low", "empty"):
            notify_owner(f"budget:{mode}",
                         f"Бюджет LLM: режим {mode}, израсходовано {used}/"
                         f"{MONTHLY_LLM_BUDGET} ({round(frac * 100)}%).")
    return {"mode": mode, "used": used, "budget": MONTHLY_LLM_BUDGET,
            "pct": round(frac * 100, 1)}


def _check_voice_rate(identity: str) -> None:
    """Три слоя защиты бюджета Mistral (замер лимитов ключа 23.07.2026:
    LLM 50 запросов/мин на ВСЕХ — это и есть узкое место всей системы).

    1. 20/мин на человека: живой ученик делает 6-10 (реплика = секунды речи +
       ответ), в лимит упрётся только скрипт.
    2. 300/день на человека: усердный ученик делает 100-150 реплик за день;
       кап ловит уведённый аккаунт и зацикленный клиент, не мешая людям.
    3. 25/мин ГЛОБАЛЬНО. Раньше стояло 45 — «чуть ниже провайдерских 50
       запросов в минуту». Но узкое место у ключа не запросы, а ТОКЕНЫ: их
       50000 в минуту, и одна реплика в разгаре беседы стоит ~1800 (замерено
       04.08.2026 по заголовку x-ratelimit-tokens-query-cost, после того как
       в промпт приехали план беседы и более глубокая история). 50000/1800 —
       это 27 реплик в минуту, а не 50. Лимит 45 стал декоративным: до него
       не доходило, зато Mistral начал бы отдавать 429 посреди начатого
       стрима, с уже сожжённым распознаванием.

       Цена вопроса честная: одновременно говорить смогут ~12-15 учеников.
       Поднять потолок можно двумя способами — платный тариф или более
       короткая история (см. _HISTORY_TURNS); ужать историю обратно можно за
       минуту, но именно она чинила «собеседник не помнит, о чём говорили».

    Поверх — месячный бюджет: при перерасходе лимиты ужимаются (см. _BUDGET),
    полный отказ — только когда месяц выбран целиком.
    """
    per_min, per_day, per_glob = 20, 300, 25
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
            per_min, per_day, per_glob = 6, 60, 10
        elif state["mode"] == "eco":
            per_min, per_day, per_glob = 10, 150, 18

    if not _rate_ok(f"v:{identity}", per_min, 60.0):
        raise HTTPException(status_code=429, detail="Слишком много запросов подряд — подожди минутку.")
    if not _voice_day_ok(identity, per_day):
        raise HTTPException(
            status_code=429,
            detail="Дневной лимит занятий исчерпан — продолжим завтра. Так мы бережём общий бюджет.",
        )
    if not _rate_ok("v:__global__", per_glob, 60.0):
        raise HTTPException(
            status_code=429,
            detail="Сервис сейчас занят другими учениками — попробуй через минуту.",
        )


# Дневной счётчик — ЕДИНСТВЕННЫЙ лимит, которому нельзя жить только в памяти:
# деплой у нас = каждый git push, и раньше он выдавал всем свежие 300 запросов
# в день. Теперь: память для скорости (проверка без похода в базу), запись
# фоном в voice_daily, прогрев на старте. Минутные окна остаются в памяти
# осознанно — их сброс рестартом безвреден.
#
# Заодно лимит стал КАЛЕНДАРНЫМ (московский день), а не скользящими 24 часами:
# фраза «продолжим завтра» теперь означает именно завтра, а не «через сутки
# после первой реплики».
_VOICE_DAY: dict = {"day": "", "counts": {}}


def _voice_day_ok(identity: str, per_day: int) -> bool:
    day = storage.msk_day()
    if _VOICE_DAY["day"] != day:  # полночь по МСК — счётчики с нуля
        _VOICE_DAY.update(day=day, counts={})
    counts = _VOICE_DAY["counts"]
    used = counts.get(identity, 0)
    if used >= per_day:
        return False
    counts[identity] = used + 1
    if len(counts) > 10_000:  # страховка от мусорных identity, как в _RATE
        counts.clear()
        counts[identity] = used + 1
    if _storage_ok:
        threading.Thread(target=_voice_bump_safe, args=(identity, day),
                         daemon=True).start()
    return True


def _voice_bump_safe(identity: str, day: str) -> None:
    try:
        storage.voice_bump(identity, day)
    except Exception as e:  # noqa: BLE001 — счётчик не важнее занятия
        print(f"[rate] запись дневного счётчика не удалась ({type(e).__name__})")


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

    def write() -> None:
        try:
            storage.bump_usage(metrics)
        except Exception as e:  # noqa: BLE001
            print(f"[usage] не записал ({type(e).__name__}: {str(e)[:60]})")

    # Зовут и из обработчика запроса (есть цикл событий), и из ФОНОВОГО ПОТОКА
    # — оттуда сбор произношения пишет свой замер. Раньше здесь безусловно
    # создавалась корутина, и во втором случае она отправлялась в мусор с
    # предупреждением «coroutine was never awaited», а метрика молча терялась.
    # Наличие цикла проверяем ДО создания корутины, иначе она уже создана.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        write()          # в потоке блокировать некого — пишем прямо
        return

    async def run():
        await asyncio.to_thread(write)

    asyncio.create_task(run())


def _track_latency(stage: str, seconds: float) -> None:
    """Скорость этапа — СУММОЙ миллисекунд и СЧЁТЧИКОМ, а не «последним
    значением»: среднее потом считается точно (sum/n) по всем запросам, без
    выборок и потерь. Пишется тем же фоновым путём, что и остальной расход."""
    ms = int(seconds * 1000)
    if ms <= 0:
        return
    _track_usage(**{f"lat_{stage}_ms": ms, f"lat_{stage}_n": 1})


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
    # Код доступа проверяется ПЕРВЫМ, до валидации полей: не-приглашённому
    # незачем знать, какие у нас правила на ники и пароли.
    await _check_invite(str(body.get("invite") or "").strip())
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
    # 8 символов, а не 4 (03.08.2026). Ник у нас генерируется из закрытого
    # списка ~2500 комбинаций, то есть он ПУБЛИЧНО угадываем — вся защита
    # аккаунта держится на пароле. Четырёхсимвольный перебирается за минуты
    # даже под лимитом 12 попыток/мин с IP. Уже созданные аккаунты не трогаем:
    # проверка стоит только на регистрации, вход работает как раньше.
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="Пароль — минимум 8 символов.")
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
        "best": _best_streak(active),
    }


def _best_streak(active: set[str]) -> int:
    """Длиннейшая серия за всю историю — с теми же правилами заморозки:
    один пропуск на ISO-неделю мостится, второй рвёт. Считается проходом по
    датам от старых к новым; объём — сотни дней, скорость не вопрос."""
    if not active:
        return 0
    days = sorted(date.fromisoformat(d) for d in active)
    best = cur_len = 1
    used_weeks: set[tuple[int, int]] = set()
    prev = days[0]
    for d in days[1:]:
        gap = (d - prev).days
        if gap == 1:
            cur_len += 1
        elif gap == 2:
            wk = (prev + timedelta(days=1)).isocalendar()[:2]
            if wk in used_weeks:
                cur_len = 1
                used_weeks = set()
            else:
                used_weeks.add(wk)
                cur_len += 1
        else:
            cur_len = 1
            used_weeks = set()
        best = max(best, cur_len)
        prev = d
    return best


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
    horizon = (today - timedelta(days=62)).isoformat()
    return {
        "level": _level_info(summary["xp_total"]),
        "streak": _compute_streak(active, summary["today"]),
        "week": week,
        "today": summary["today"],
        "active_days": sorted(d for d in active if d >= horizon),
        "totals": {"replies": summary["replies_total"],
                   "tasks": summary["tasks_total"],
                   "xp": summary["xp_total"]},
    }


# --------------------------------------------- Личный кабинет: настройки и ник

def _sanitize_settings(raw: dict) -> dict:
    """Белый список настроек: чужие ключи и дикие значения в базу не попадают.
    Настройки следуют за аккаунтом между устройствами, как и память."""
    out: dict = {}
    if raw.get("theme") in ("dark", "light", "auto"):
        out["theme"] = raw["theme"]
    vol = raw.get("volume")
    if isinstance(vol, (int, float)) and not isinstance(vol, bool) and 0 <= vol <= 1:
        out["volume"] = round(float(vol), 2)
    if isinstance(raw.get("show_text"), bool):
        out["show_text"] = raw["show_text"]
    # Согласие на хранение голоса в корпусе. Отдельный флаг, а не общее
    # «согласен со всем»: ученик должен мочь передумать в любой момент, и
    # снятие галочки обязано немедленно останавливать сбор (проверяется при
    # КАЖДОЙ записи, а не кэшируется).
    if isinstance(raw.get("corpus_consent"), bool):
        out["corpus_consent"] = raw["corpus_consent"]
    # Персона проверяется по реестру, а не принимается на веру: в базе должен
    # лежать только тот id, который сервер умеет озвучить.
    if raw.get("persona") in PERSONAS:
        out["persona"] = raw["persona"]
    return out


@app.get("/personas")
async def personas_list():
    """Каталог собеседников для экрана настроек.

    Открыт без аккаунта намеренно: это витрина, а не действие — ни расхода
    квоты, ни персональных данных здесь нет. Промпты характеров наружу НЕ
    отдаём, клиенту нужны только id, имя и описание.
    """
    return {
        "default": DEFAULT_PERSONA,
        "personas": [
            {"id": pid, "label": p["label"], "description": p["description"],
             "voice": p["voice"], "theme": p["theme"], "quit": p["quit"],
             # Отдаём признак «взрослой» персоны и текст предупреждения:
             # фронт обязан спросить подтверждение ДО первого включения.
             "adult": bool(p.get("adult")), "warning": p.get("warning", "")}
            for pid, p in PERSONAS.items()
        ],
    }


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


@app.get("/me/analytics")
async def me_analytics(x_device: str | None = Header(None),
                       x_admin_key: str | None = Header(None)):
    """Аналитика ученика: динамика балла по типам заданий и профиль ошибок.

    Считается из уже записываемых results/mistakes — ученик видит, куда
    движется его балл и какие ошибки он таскает за собой из работы в работу.
    Это же сырьё для решения «что решать дальше»."""
    await _require_account(x_device, x_admin_key)
    if not (_storage_ok and x_device):
        return {"kinds": {}, "history": [], "mistakes": {"total": 0, "by_cat": [], "repeats": []}}
    try:
        return await asyncio.to_thread(storage.analytics_summary, x_device)
    except Exception as e:  # noqa: BLE001
        print(f"[analytics] не собралась ({type(e).__name__}) — отдаю пустую")
        return {"kinds": {}, "history": [], "mistakes": {"total": 0, "by_cat": [], "repeats": []}}


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


# ------------------------------------------------- Копилка несогласий с ИИ

@app.get("/feedback/catalog")
async def feedback_catalog():
    """Список причин для формы жалобы — ОДИН на фронт и на сервер.

    Открыт без аккаунта: это словарь, а не данные. Разъехавшиеся списки дали бы
    жалобы с кодом, который сервер молча выбросит, и потеря нашлась бы через
    месяц по дыре в статистике."""
    return disputes.catalog()


@app.post("/task_dispute")
async def task_dispute(request: Request, body: dict = Body(...),
                       x_device: str | None = Header(None),
                       x_admin_key: str | None = Header(None)):
    """«Не согласен» — с экрана разбора, из разбора беседы и из разговора.

    Единственный путь, которым речь ученика попадает в базу, — по явному
    нажатию: человек сам отдаёт свой ответ на пересмотр (см. DDL disputes).
    Вместе с ним сохраняется обстановка: текст задания, соседние реплики,
    снимок разбора. Спорные разборы + вердикты владельца = растущий
    калибровочный набор.

    Проверка полноты живёт в disputes.normalize, а не здесь: её же гоняют
    тесты, и обойти её через сырой запрос мимо формы нельзя.
    """
    await _require_account(x_device, x_admin_key)
    # Щедрый лимит: жалоба — редкое действие, а вот заскриптованный спам мог бы
    # налить в базу гигабайты транскриптов.
    if not _rate_ok(f"d:{_client_ip(request)}", 6, 60.0):
        raise HTTPException(status_code=429, detail="Слишком часто — подожди минутку.")
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна — попробуй позже.")
    data, err = disputes.normalize(body if isinstance(body, dict) else {})
    if data is None:
        raise HTTPException(status_code=422, detail=err)
    shot = data.pop("shot", None)
    did = await asyncio.to_thread(storage.dispute_add, x_device or "admin", data)
    # Снимок пишем ПОСЛЕ жалобы и отдельно: если картинка не ляжет, объяснение
    # ученика всё равно сохранится. Обратный порядок терял бы главное ради
    # второстепенного.
    if shot:
        try:
            await asyncio.to_thread(storage.shot_add, did, shot["mime"],
                                    shot["data"], shot["bytes"])
        except Exception as e:  # noqa: BLE001
            print(f"[dispute] снимок не сохранился ({type(e).__name__}) — "
                  f"жалоба {did} осталась без картинки")
    print(f"[dispute] {data['kind']}/{data['target']} — {data['reason']}"
          f" (балл {data['score']}/{data['max_score']}, просят {data['claim_score']}"
          f"{', со снимком' if shot else ''})")
    return {"ok": True, "id": did}


@app.get("/admin/disputes")
async def admin_disputes(status: str | None = None,
                         x_admin_key: str | None = Header(None)):
    """Копилка для владельца: жалобы целиком и разрезы по типам и причинам."""
    _require_admin(x_admin_key)
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна.")
    items = await asyncio.to_thread(storage.disputes_list, status, 200)
    stats = await asyncio.to_thread(storage.disputes_stats)
    # Снимки — только ПРИЗНАКОМ (id и размер), сами картинки приезжают по
    # отдельной ручке, когда владелец откроет карточку. Иначе список из ста
    # жалоб весил бы десятки мегабайт ради превью, которых в списке нет.
    shots = await asyncio.to_thread(
        storage.shots_for, [str(d.get("id")) for d in items])
    for d in items:
        d["shots"] = shots.get(str(d.get("id")), [])
    return {"stats": stats, "disputes": items, "catalog": disputes.catalog(),
            "verdicts": disputes.VERDICTS}


@app.get("/admin/shot/{shot_id}")
async def admin_shot(shot_id: str, key: str | None = None,
                     x_admin_key: str | None = Header(None)):
    """Снимок экрана из жалобы — ТОЛЬКО владельцу.

    Ключ принимаем и заголовком, и параметром: тег <img> заголовки слать не
    умеет, а показывать картинку в админке надо. Параметр не страшнее
    заголовка — админка и так открывается по ключу, и он уже лежит в
    sessionStorage браузера владельца.

    Content-Disposition: inline с фиксированным именем и nosniff — снимок
    прислал посторонний, и браузер не должен угадывать, что это такое.
    """
    _require_admin(x_admin_key or key)
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна.")
    row = await asyncio.to_thread(storage.shot_get, shot_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Снимка нет.")
    mime, data_b64 = row
    try:
        blob = base64.b64decode(data_b64)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="Снимок повреждён.")
    return Response(content=blob, media_type=mime, headers={
        "Content-Disposition": 'inline; filename="screenshot"',
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=600",
    })


@app.get("/pron/weakest")
async def pron_weakest(variant: str = "", x_device: str | None = Header(None),
                       x_admin_key: str | None = Header(None)):
    """«Переслушай эти слова» — единственное, что фонемный замер показывает ученику.

    Отдельной ручкой, а не в ответе разбора, и это осознанно: замер идёт фоном
    и стоит ~19 секунд на бесплатном Render, а ученик ждёт балл 2-6 секунд.
    Прибавить замер к ожиданию значило бы испортить главное ради добавочного.
    Экран забирает слова, когда они появятся, и дорисовывает блок.

    НА БАЛЛ ЭТО НЕ ВЛИЯЕТ и влиять не будет, пока не появятся записи, размеченные
    человеком: распределение говорит, где звук слабее, но не говорит, ошибка это
    или акцент. Совет «переслушай» безвреден при любом ответе, снятый балл — нет.
    """
    await _require_account(x_device, x_admin_key)
    # ВЫКЛЮЧЕНО по умолчанию с 20.08.2026. Причина — замер на СЕМИ записях
    # живой речи участников ЕГЭ с вердиктами экспертов (fipi_audio.py):
    # показатель GOP не разделяет работы, которым эксперт поставил 1 и 0.
    # Работа с ОДНОЙ ошибкой эксперта получила 8 меток, работа с ШЕСТЬЮ — три;
    # абсолютная медиана вероятности у классов тоже перекрывается (0.961-0.981
    # против 0.956-0.973). Показывать ученику список слов, не связанный с тем,
    # что слышит человек, — это ровно выдуманная точность, которая в проекте
    # запрещена. Вернём, когда фонемная ступень (CTC) сможет назвать САМ звук.
    if not (PRON_SHOW and _storage_ok and x_device and variant):
        return {"words": []}
    words = await asyncio.to_thread(storage.pron_weakest, x_device, variant)
    return {"words": words, "note": "на балл не влияет"}


@app.get("/admin/disputes/{did}/pron")
async def admin_dispute_pron(did: str, x_admin_key: str | None = Header(None)):
    """Арбитр спора о чтении: что слышал ЗВУК в том самом прогоне.

    Жалоба «записали не то, что я сказал» — спор чтеца с распознавалкой, и
    текстом он не решается: текст и есть предмет спора. Замер произношения
    того же прогона отвечает фактом: насколько звук подтверждает каждое
    слово эталона. Первый такой арбитраж (goldfish, 16.08.2026: p_norm
    1.008 при нулях настоящих провалов — ученик был прав) делался руками
    через сырую выгрузку; теперь владельцу это одна кнопка в карточке.
    """
    _require_admin(x_admin_key)
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна.")
    brief = await asyncio.to_thread(storage.dispute_brief, did)
    if brief is None:
        raise HTTPException(status_code=404, detail="Жалобы с таким id нет.")
    words = await asyncio.to_thread(
        storage.pron_run_near, brief["student_id"], brief["variant"],
        brief["created_at"])
    return {"kind": brief["kind"], "variant": brief["variant"],
            "run_at": words[0]["run_at"] if words else None,
            "model": words[0]["model"] if words else None,
            "words": [{k: w[k] for k in ("word", "ord", "p_norm", "dur",
                                          "method", "spoken")}
                      for w in words]}


@app.get("/admin/corpus")
async def admin_corpus(limit: int = 50, offset: int = 0, kind: str = "",
                       unverified: int = 0,
                       x_admin_key: str | None = Header(None)):
    """Корпус голоса: что собрано и как система это разметила.

    Звук сюда НЕ едет — он тяжёлый, а листать надо быстро. За самой записью
    ходят отдельно, /admin/corpus/{id}/audio.
    """
    _require_admin(x_admin_key)
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна.")
    stats = await asyncio.to_thread(storage.corpus_stats)
    items = await asyncio.to_thread(storage.corpus_list, min(500, max(1, limit)),
                                    kind, bool(unverified), max(0, offset))
    return {
        "stats": stats,
        "items": items,
        "collecting": CORPUS_COLLECT and not _corpus_full,
        "limits": {"max_mb": CORPUS_MAX_MB, "per_student": CORPUS_PER_STUDENT,
                   "per_student_kind": CORPUS_PER_STUDENT_KIND},
    }


@app.get("/admin/corpus/{cid}/audio")
async def admin_corpus_audio(cid: str, x_admin_key: str | None = Header(None),
                             key: str = ""):
    """Сама запись — послушать в админке или выгрузить на ноут.

    Ключ принимается и заголовком, и параметром: тег <audio> заголовки слать
    не умеет, а слушать записи владельцу нужно прямо в браузере.
    """
    _require_admin(x_admin_key or key or None)
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна.")
    got = await asyncio.to_thread(storage.corpus_audio, cid)
    if not got:
        raise HTTPException(status_code=404, detail="Записи нет.")
    audio, mime = got
    return Response(content=audio, media_type=mime,
                    headers={"Cache-Control": "private, max-age=3600"})


@app.post("/admin/corpus/{cid}/verify")
async def admin_corpus_verify(cid: str, body: dict = Body(...),
                              x_admin_key: str | None = Header(None)):
    """Вердикт владельца поверх автоматической разметки.

    Именно он превращает запись в строку сетки точности: до него у нас есть
    только мнение системы о себе самой.
    """
    _require_admin(x_admin_key)
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна.")
    verdict = str(body.get("verdict") or "").strip()
    if not verdict:
        raise HTTPException(status_code=400, detail="Пустой вердикт.")
    ok = await asyncio.to_thread(storage.corpus_verify, cid, verdict)
    if not ok:
        raise HTTPException(status_code=404, detail="Записи нет.")
    return {"ok": True}


@app.delete("/admin/corpus/{cid}")
async def admin_corpus_delete(cid: str, x_admin_key: str | None = Header(None)):
    """Удалить запись. Нужна не для порядка, а для отзыва согласия: ученик
    вправе передумать, и тогда его голос обязан исчезнуть."""
    _require_admin(x_admin_key)
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна.")
    ok = await asyncio.to_thread(storage.corpus_delete, cid)
    return {"ok": ok}


@app.get("/admin/pronunciation")
async def admin_pronunciation(raw: int = 0,
                              x_admin_key: str | None = Header(None)):
    """Копилка замеров произношения: распределение показателя на живой речи.

    Ради этого экрана всё и собирается. Порог «это ошибка произношения» нельзя
    взять из головы: на синтезированной речи он один, на школьнике с акцентом
    другой. Здесь видно, какой он НА САМОМ ДЕЛЕ и сколько слов попадёт под
    каждый вариант порога.
    """
    _require_admin(x_admin_key)
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна.")
    if raw:
        # Сырые строки для разбора порога снаружи: голоса тут нет и не было,
        # только слова заданий и числа при них.
        return {"samples": await asyncio.to_thread(storage.pron_raw, 20000)}
    stats = await asyncio.to_thread(storage.pron_stats)
    return {"stats": stats, "collecting": PRON_COLLECT and not _pron_disabled,
            "model": os.environ.get("GOP_MODEL", "base.en"),
            "done_this_process": _pron_done}


@app.post("/admin/disputes/{did}")
async def admin_dispute_resolve(did: str, body: dict = Body(...),
                                x_admin_key: str | None = Header(None)):
    """Вердикт владельца по жалобе — разметка золотого набора одной кнопкой.

    Именно этой ручки не хватало, чтобы копилка стала калибровочным набором:
    без вердикта человека спорный разбор остаётся просто жалобой.
    """
    _require_admin(x_admin_key)
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна.")
    data, err = disputes.resolution(body if isinstance(body, dict) else {})
    if data is None:
        raise HTTPException(status_code=422, detail=err)
    ok = await asyncio.to_thread(
        storage.dispute_resolve, did, data["status"], data["verdict"],
        data["verdict_score"], data["verdict_note"])
    if not ok:
        raise HTTPException(status_code=404, detail="Жалобы с таким id нет.")
    return {"ok": True, "id": did, **data}


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


# ------------------------------------------------------------------------
# Картинки к заданиям 40 и 42 — через наш домен.
#
# Заглушки лежат на images.unsplash.com, а он из РФ без VPN недоступен:
# 29.07.2026 замерено с ноутбука владельца — DNS отвечает, TLS-хендшейк виснет
# по таймауту, ни одна из 14 картинок не грузится. Ученик без VPN видел бы
# задание «опиши две фотографии» без фотографий. Render до Unsplash достаёт,
# поэтому картинку тянет сервер и отдаёт со своего адреса — заодно у фронта
# не остаётся ни одного внешнего домена.
_IMG_CACHE: dict[str, tuple[bytes, str]] = {}
_IMG_CACHE_LIMIT = 48
_IMG_ID_RE = re.compile(r"^photo-[0-9A-Za-z_-]{6,40}$")


# ------------------------------------------------------------------------
# Импорт заданий из открытого банка ФИПИ.
#
# Почему ФИПИ, а не «РЕШУ ЕГЭ», и на каких условиях — см. шапку fipi_import.py
# и docs/DECISIONS.md §6.4. Здесь только механика: долгая работа (обход банка,
# скачивание картинок, распознавание) не влезает в один HTTP-запрос, поэтому
# импорт запускается фоновой задачей, а прогресс виден отдельной ручкой.

# Картинки и тексты в банке лежат КАРТИНКАМИ, их читает модель со зрением.
# Отдельная от разговорной: mistral-small на фотографиях врёт (проверено —
# женщину на тренажёре описала как «женщину со смартфоном у лестницы»), а
# неверное описание хуже отсутствующего: разбор начнёт ловить фактические
# ошибки там, где ученик прав.
FIPI_VISION_MODEL = os.environ.get("FIPI_VISION_MODEL", "mistral-medium-latest")

_FIPI_JOB: dict = {"state": "idle", "found": 0, "added": 0, "skipped": 0,
                   "images": 0, "errors": [], "started": "", "finished": ""}


def _fipi_store_image(cl, url: str) -> str | None:
    """Скачать картинку задания и положить к себе. Возвращает id или None."""
    try:
        data, mime = fipi_import.download_image(cl, url)
    except Exception as e:  # noqa: BLE001
        _FIPI_JOB["errors"].append(f"картинка {url[-40:]}: {type(e).__name__}")
        return None
    img_id = hashlib.sha1(url.encode()).hexdigest()[:20]
    storage.image_put(img_id, mime, base64.b64encode(data).decode(), fipi_import.SOURCE)
    _FIPI_JOB["images"] += 1
    return img_id


def _fipi_import_job(pages: int, pagesize: int, limit: int) -> None:
    """Сам импорт. Крутится в отдельном потоке: сеть и распознавание блокируют."""
    job = _FIPI_JOB
    job.update(state="running", found=0, added=0, skipped=0, images=0, errors=[],
               started=datetime.now(timezone.utc).isoformat(), finished="")
    vision = llm_client()
    try:
        with fipi_import.client() as cl:
            items = fipi_import.crawl(cl, pages=pages, pagesize=pagesize, pause=1.5)
            job["found"] = len(items)
            for item in items:
                if limit and job["added"] >= limit:
                    break
                # Дешёвая проверка ПЕРЕД дорогой работой: скачивать картинки и
                # звать зрение ради задания, которое уже в базе, — чистая трата
                # лимитов и времени.
                if storage.task_exists(fipi_import.SOURCE, item["fipi_id"]):
                    job["skipped"] += 1
                    continue
                try:
                    payload = _fipi_payload(cl, vision, item)
                except Exception as e:  # noqa: BLE001
                    job["errors"].append(f"{item['fipi_id']}: {type(e).__name__}: {str(e)[:80]}")
                    continue
                if payload is None:
                    job["skipped"] += 1
                    continue
                # Пауза между заданиями: импорт упирается не в наш процессор, а
                # в лимиты модели, и торопиться тут некуда — это разовая работа.
                time.sleep(0.5)
                tid = storage.task_add_imported(
                    "ege", item["task_no"], item["kind"],
                    json.dumps(payload, ensure_ascii=False),
                    fipi_import.SOURCE, item["fipi_id"])
                if tid:
                    job["added"] += 1
                else:
                    job["skipped"] += 1  # уже импортировали раньше
    except Exception as e:  # noqa: BLE001
        job["errors"].append(f"импорт оборвался: {type(e).__name__}: {str(e)[:120]}")
    job.update(state="done", finished=datetime.now(timezone.utc).isoformat())
    print(f"[fipi] импорт завершён: найдено {job['found']}, добавлено {job['added']}, "
          f"пропущено {job['skipped']}, картинок {job['images']}, ошибок {len(job['errors'])}")


def _fipi_payload(cl, vision, item: dict) -> dict | None:
    """Задание из банка → payload варианта в том виде, в каком его ждёт фронт.

    None означает «брать нечего»: например, у чтения не распозналась картинка
    с текстом, а без эталона задание 39 бесполезно.
    """
    kind = item["kind"]
    brief = item["brief"]
    if kind == "reading":
        if not item["images"]:
            return None
        data, mime = fipi_import.download_image(cl, item["images"][0])
        text = fipi_import.read_text_from_image(vision, FIPI_VISION_MODEL, data, mime)
        # Осмысленный текст для чтения — это несколько предложений, а не обрывок.
        if len(text) < 120:
            return None
        return {"brief": brief, "readText": text}

    if kind == "dialogue":
        img_id = _fipi_store_image(cl, item["images"][0]) if item["images"] else None
        return {
            "brief": brief,
            "imageCaption": item.get("ad") or "",
            "steps": [f"Question {i + 1}: {p}" for i, p in enumerate(item.get("points", []))],
            "images": [f"/img/task/{img_id}"] if img_id else [],
        }

    # monologue: две фотографии, и к каждой — описание того, что на ней реально
    # изображено. Без описаний разбор не поймает фактические ошибки: фотографий
    # он не видит.
    ids, facts = [], []
    for url in item["images"][:2]:
        try:
            data, mime = fipi_import.download_image(cl, url)
        except Exception:  # noqa: BLE001
            continue
        img_id = hashlib.sha1(url.encode()).hexdigest()[:20]
        storage.image_put(img_id, mime, base64.b64encode(data).decode(), fipi_import.SOURCE)
        _FIPI_JOB["images"] += 1
        ids.append(f"/img/task/{img_id}")
        facts.append(fipi_import.photo_fact(vision, FIPI_VISION_MODEL, data, mime))
    if len(ids) != 2:
        return None
    return {"brief": brief, "imageCaption": item.get("topic") or "",
            "images": ids, "photoFacts": facts}


@app.post("/admin/fipi/import")
async def admin_fipi_import(body: dict = Body(default={}),
                            x_admin_key: str | None = Header(None)):
    """Запустить импорт. Возвращается сразу — следить за ходом через /admin/fipi/status."""
    _require_admin(x_admin_key)
    if _FIPI_JOB["state"] == "running":
        raise HTTPException(status_code=409, detail="Импорт уже идёт.")
    pages = max(1, min(int(body.get("pages") or 25), 40))
    # Потолок 500, а не 100: с фильтром qkind=ILI_STD_FULL вся устная часть
    # (377 заданий) приезжает ОДНОЙ страницей, и это один запрос вместо
    # двадцати пяти. Сервер ФИПИ 300 и 500 принимает без урезания.
    pagesize = max(10, min(int(body.get("pagesize") or 500), 500))
    limit = max(0, int(body.get("limit") or 0))
    asyncio.create_task(asyncio.to_thread(_fipi_import_job, pages, pagesize, limit))
    return {"started": True, "pages": pages, "pagesize": pagesize, "limit": limit}


@app.get("/admin/fipi/status")
async def admin_fipi_status(x_admin_key: str | None = Header(None)):
    _require_admin(x_admin_key)
    job = dict(_FIPI_JOB)
    job["errors"] = job["errors"][:10]
    return job


@app.post("/admin/fipi/purge")
async def admin_fipi_purge(x_admin_key: str | None = Header(None)):
    """Убрать всё импортированное. Существует ровно на случай, если
    правообладатель попросит удалить материалы: одна кнопка, а не чистка базы руками."""
    _require_admin(x_admin_key)
    removed = await asyncio.to_thread(storage.tasks_purge_source, fipi_import.SOURCE)
    return {"removed": removed}


@app.get("/img/task/{img_id}")
async def stored_task_image(img_id: str):
    """Картинка задания из нашей базы. Ученик не должен зависеть от доступности
    чужого сервера, а чужой сервер — получать наш трафик."""
    if not re.fullmatch(r"[0-9a-f]{8,40}", img_id):
        raise HTTPException(status_code=404, detail="Нет такой картинки")
    row = await asyncio.to_thread(storage.image_get, img_id)
    if not row:
        raise HTTPException(status_code=404, detail="Нет такой картинки")
    mime, data_b64 = row
    return Response(content=base64.b64decode(data_b64), media_type=mime,
                    headers={"Cache-Control": "public, max-age=604800"})


@app.get("/img/{photo_id}")
async def task_image(photo_id: str, w: int = 900, q: int = 70):
    """Прокси одной картинки задания. Пускаем только id формата Unsplash —
    открытым проксёром для всего интернета сервис становиться не должен."""
    if not _IMG_ID_RE.match(photo_id):
        raise HTTPException(status_code=404, detail="Нет такой картинки")
    w, q = max(200, min(int(w), 1600)), max(30, min(int(q), 90))
    key = f"{photo_id}?w={w}&q={q}"

    cached = _IMG_CACHE.get(key)
    if cached is None:
        url = f"https://images.unsplash.com/{photo_id}?w={w}&q={q}&auto=format&fit=crop"
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as cl:
                r = await cl.get(url)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502,
                                detail=f"Картинка не загрузилась: {type(e).__name__}")
        ctype = r.headers.get("content-type", "")
        if r.status_code != 200 or not ctype.startswith("image/"):
            raise HTTPException(status_code=502, detail=f"Источник ответил {r.status_code}")
        cached = (r.content, ctype)
        if len(_IMG_CACHE) >= _IMG_CACHE_LIMIT:
            _IMG_CACHE.pop(next(iter(_IMG_CACHE)))
        _IMG_CACHE[key] = cached

    body, ctype = cached
    return Response(content=body, media_type=ctype,
                    headers={"Cache-Control": "public, max-age=604800"})


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
        # Замечания к черновику: считаются детерминированно (слова, поля), НЕ
        # моделью — инструмент отбраковки сам ошибаться не должен. Пустой
        # список не значит «хорошо», он значит «заметных дефектов нет»:
        # решение всё равно за человеком, флаги лишь сортируют очередь.
        r["problems"] = fipi_import.draft_problems(r["kind"], r["payload"])
    return {"tasks": rows}


@app.post("/admin/tasks/{tid}/toggle")
async def admin_task_toggle(tid: str, x_admin_key: str | None = Header(None)):
    _require_admin(x_admin_key)
    state = await asyncio.to_thread(storage.task_toggle, tid)
    if state is None:
        raise HTTPException(status_code=404, detail="Задание не найдено.")
    return {"active": state}


def _registration_state() -> str:
    """Открыта ли регистрация — видно без админ-ключа, но БЕЗ самих кодов."""
    db = 0
    if _storage_ok:
        _health_db_refresh()
        db = max(0, _HEALTH_DB["invites"])
    if db > 0:
        return f"по кодам ({db} в базе)"
    if INVITE_CODES:
        return f"по кодам ({len(INVITE_CODES)} из переменной, заведи в админке)"
    return "ЗАКРЫТА: заведи код в админке или задай INVITE_CODES"


@app.post("/admin/test_alert")
async def admin_test_alert(x_admin_key: str | None = Header(None)):
    """Проверка канала алертов одной кнопкой.

    Без неё владелец узнавал бы, что Telegram настроен неверно, ровно в тот
    момент, когда что-то упало, — то есть когда алерт уже не придёт.
    Кулдаун обходим намеренно: это ручная проверка, а не событие.
    """
    _require_admin(x_admin_key)
    if not (alerts.TG_TOKEN and alerts.TG_CHAT):
        raise HTTPException(
            status_code=503,
            detail="Telegram не настроен: задай TELEGRAM_BOT_TOKEN и "
                   "TELEGRAM_CHAT_ID в переменных Render (docs/MONITORING.md).",
        )
    ok, detail = await asyncio.to_thread(alerts.send_now,
                                         "Проверка связи. Если видишь это "
                                         "сообщение — алерты настроены верно.")
    if not ok:
        raise HTTPException(status_code=502, detail=f"Телеграм не принял: {detail}")
    return {"sent": True}


@app.get("/admin/overview")
async def admin_overview(x_admin_key: str | None = Header(None)):
    """Сводка о работе системы: люди, расход, скорости, результаты.

    Правила точности (это витрина владельца, ей верят на слово):
      - все числа из БАЗЫ одним снимком (storage.overview) — не из памяти
        процесса, которую обнуляет каждый деплой;
      - расход месяца считается из тех же строк usage_daily, из которых
        бюджет делает свою сверку, — расхождений «сводка говорит одно,
        бюджет другое» не бывает по построению;
      - производные (на юзера, в день, прогноз) считаются ЗДЕСЬ и только
        делением проверенных чисел; при пустом делителе поле = None, и
        фронт пишет «нет данных», а не ноль.

    Прогноз остатка — экстраполяция среднего дневного расхода по дням,
    В КОТОРЫЕ был трафик (тихие дни не размывают среднее). Это оценка
    «если пользоваться как сейчас», а не обещание.
    """
    _require_admin(x_admin_key)
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна.")
    month = _budget_month()          # 'YYYY-MM' UTC — тот же ключ, что у бюджета
    data = await asyncio.to_thread(storage.overview, month, storage.msk_day())

    used = data["llm_requests"]
    budget = MONTHLY_LLM_BUDGET
    remaining = max(0, budget - used) if budget > 0 else None
    days = data["days_with_traffic"]
    active = data["users"]["active_month"]

    per_day = round(used / days, 1) if days else None
    per_user = round(used / active, 1) if active else None
    days_left = (round(remaining / per_day)
                 if (remaining is not None and per_day) else None)

    data["budget"] = {
        "limit": budget if budget > 0 else None,
        "used": used,
        "remaining": remaining,
        "pct": round(100.0 * used / budget, 1) if budget > 0 else None,
        "per_day_avg": per_day,
        "per_active_user_avg": per_user,
        "days_left_estimate": days_left,
        "mode": _budget_state().get("mode"),
    }
    return data


@app.get("/admin/telegram")
async def admin_telegram(x_admin_key: str | None = Header(None)):
    """Состояние настройки алертов + подсказка chat_id.

    Показывает, ЧТО уже задано (не значения), и ищет chat_id по сообщениям
    боту. Токен наружу не отдаём никогда — только факт «задан».
    """
    _require_admin(x_admin_key)
    state = {
        "token_set": bool(alerts.TG_TOKEN),
        "chat_set": bool(alerts.TG_CHAT),
        "ready": bool(alerts.TG_TOKEN and alerts.TG_CHAT),
    }
    if state["token_set"] and not state["chat_set"]:
        ok, detail = await asyncio.to_thread(alerts.discover_chat_id)
        state["chat_id_hint"] = detail if ok else None
        state["hint_error"] = None if ok else detail
    return state


@app.get("/admin/invites")
async def admin_invites(x_admin_key: str | None = Header(None)):
    _require_admin(x_admin_key)
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна.")
    return {"invites": await asyncio.to_thread(storage.invites_list)}


@app.post("/admin/invites")
async def admin_invite_add(body: dict = Body(...),
                           x_admin_key: str | None = Header(None)):
    """Новый код. Пустой code — сервер придумает сам: так короче и безопаснее,
    чем «qwerty», который владелец сочинит второпях."""
    _require_admin(x_admin_key)
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна.")
    code = str(body.get("code") or "").strip()
    if not code:
        alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
        code = "".join(secrets.choice(alphabet) for _ in range(8))
    if not re.fullmatch(r"[A-Za-z0-9\-_]{4,64}", code):
        raise HTTPException(status_code=422,
                            detail="Код: 4-64 символа, латиница, цифры, дефис.")
    try:
        max_uses = max(0, int(body.get("max_uses") or 0))
    except (TypeError, ValueError):
        max_uses = 0
    ok = await asyncio.to_thread(storage.invite_add, code,
                                 str(body.get("note") or "").strip()[:120], max_uses)
    if not ok:
        raise HTTPException(status_code=409, detail="Такой код уже есть.")
    _HEALTH_DB["at"] = 0.0  # число кодов в /health обновится сразу
    return {"code": code, "max_uses": max_uses}


@app.post("/admin/invites/{code}/toggle")
async def admin_invite_toggle(code: str, body: dict = Body(default={}),
                              x_admin_key: str | None = Header(None)):
    _require_admin(x_admin_key)
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна.")
    active = bool(body.get("active"))
    if not await asyncio.to_thread(storage.invite_set_active, code, active):
        raise HTTPException(status_code=404, detail="Код не найден.")
    _HEALTH_DB["at"] = 0.0  # число кодов в /health обновится сразу
    return {"code": code, "active": active}


@app.get("/admin/backup")
async def admin_backup(images: int = 0,
                       x_admin_key: str | None = Header(None)):
    """Полный дамп базы одним JSON — стратегия бэкапа для Neon free (там
    своих бэкапов нет). Качается по расписанию на ноут владельца:
    backend/backup.ps1 + Планировщик задач Windows (docs/MONITORING.md).
    images=1 добавляет картинки заданий (+несколько МБ, меняются редко)."""
    _require_admin(x_admin_key)
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна.")
    data = await asyncio.to_thread(storage.dump_all, bool(images))
    # Отмечаем ФАКТ выгрузки. Скрипт на ноуте может тихо перестать работать —
    # задача отключилась, ноут спал, файл скрипта пропал с диска (наблюдалось
    # 05.08.2026), — и снаружи это ничем не отличается от «всё хорошо».
    # Сервер знает точно, когда его последний раз забирали, и показывает это
    # в сводке; пропущенные сутки видно сразу.
    rows = sum(len(v) for v in data.values())
    try:
        await asyncio.to_thread(storage.meta_set, "last_backup", f"{rows} строк")
    except Exception as e:  # noqa: BLE001 — отметка не должна ломать сам бэкап
        print(f"[backup] отметка о выгрузке не записалась ({type(e).__name__})")
    return {"created_at": datetime.now(timezone.utc).isoformat(),
            "storage": storage.describe(), "tables": data}


@app.post("/admin/restore")
async def admin_restore(body: dict = Body(...),
                        force: int = 0, replace: int = 0,
                        x_admin_key: str | None = Header(None)):
    """Заливка JSON-бэкапа в ПУСТУЮ базу (см. storage.restore_all).

    Появился 27.08.2026, когда Neon поставил проект на паузу за квоту и
    единственной копией данных остался ночной дамп на ноуте владельца.
    Запуск с ноута: .\.venv\Scripts\python.exe restore.py"""
    _require_admin(x_admin_key)
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна.")
    tables = body.get("tables") or {}
    if not tables:
        raise HTTPException(status_code=400, detail="В теле нет tables — это не бэкап.")
    try:
        counts = await asyncio.to_thread(storage.restore_all, tables,
                                         bool(force), bool(replace))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    _HEALTH_DB["at"] = 0.0  # число кодов и расход в /health пересчитаются
    return {"restored": counts, "rows": sum(counts.values())}


@app.post("/admin/reset_password")
async def admin_reset_password(body: dict = Body(...),
                               x_admin_key: str | None = Header(None)):
    """«Забыл пароль» при аккаунтах без почты и телефона: сброс делает
    владелец руками — он один знает своих учеников в лицо и может проверить,
    что просит настоящий хозяин ника. Новый пароль генерирует СЕРВЕР
    (не админ): случайный, читаемый, показывается один раз в ответе."""
    _require_admin(x_admin_key)
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна.")
    nickname = str(body.get("nickname") or "").strip()
    if not nickname:
        raise HTTPException(status_code=422, detail="Нужен ник.")
    # Без похожих символов (l/1, O/0): пароль диктуют голосом или пишут от руки.
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    new_password = "".join(secrets.choice(alphabet) for _ in range(10))
    ok = await asyncio.to_thread(storage.reset_password, nickname, _hash_pw(new_password))
    if not ok:
        raise HTTPException(status_code=404, detail=f"Ник «{nickname}» не найден.")
    return {"nickname": nickname, "password": new_password}


@app.post("/admin/tasks/publish_clean")
async def admin_publish_clean(body: dict = Body(default={}),
                              x_admin_key: str | None = Header(None)):
    """Опубликовать разом все черновики БЕЗ замечаний.

    Проверять глазами 90 черновиков нереально, а публиковать вслепую нельзя.
    Компромисс: массово уходят только те, у кого детерминированные проверки
    не нашли дефектов; всё с замечаниями остаётся человеку. dry_run=1 сначала
    показывает, что будет опубликовано, — публикация задним числом заметна
    ученикам, поэтому «посмотреть» отделено от «сделать».
    """
    _require_admin(x_admin_key)
    if not _storage_ok:
        raise HTTPException(status_code=503, detail="База недоступна.")
    rows = await asyncio.to_thread(storage.tasks_all)
    clean, flagged = [], 0
    for r in rows:
        if r["active"]:
            continue
        try:
            payload = json.loads(r["payload"])
        except (json.JSONDecodeError, TypeError):
            flagged += 1
            continue
        if fipi_import.draft_problems(r["kind"], payload):
            flagged += 1
        else:
            clean.append(r["id"])
    if body.get("dry_run"):
        return {"would_publish": len(clean), "left_for_review": flagged}
    for tid in clean:
        await asyncio.to_thread(storage.task_toggle, tid)
    print(f"[admin] опубликовано пачкой: {len(clean)}, оставлено на разбор: {flagged}")
    return {"published": len(clean), "left_for_review": flagged}


@app.delete("/admin/tasks/{tid}")
async def admin_task_delete(tid: str, x_admin_key: str | None = Header(None)):
    """Удаление задания насовсем — для бракованных черновиков импорта
    (кривой OCR, картинка не о том). Выключение (toggle) — для «отложить»."""
    _require_admin(x_admin_key)
    ok = await asyncio.to_thread(storage.task_delete, tid)
    if not ok:
        raise HTTPException(status_code=404, detail="Задание не найдено.")
    return {"deleted": tid}


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


# Точное распознавание для ОЦЕНИВАЕМЫХ заданий (39-42).
#
# У двух режимов приложения требования к распознаванию противоположны:
#   разговор — ученик ждёт ответа вживую, каждая доля секунды видна;
#   разбор задания — ученик только что говорил минуту-две и ждёт разбора,
#   лишняя секунда незаметна, зато КАЖДОЕ слово превращается в балл ФИПИ.
# Поэтому модель распознавания у них может быть разной: пусто = та же, что в
# разговоре (voxtral-mini), иначе — чат-модель Voxtral (24B), которой аудио
# отдаётся как вложение. Любой сбой откатывается на обычный путь.
STT_TASK_MODEL = os.environ.get("STT_TASK_MODEL", "").strip()

# Правило «переписывай дословно» здесь не вежливость, а требование продукта:
# разбор считает ошибки ученика, и «услужливо» исправленная грамматика
# превращается в похвалу за текст, которого ученик не говорил.
_VERBATIM_STT = (
    "Transcribe the audio into English text word for word. The speaker is a Russian "
    "teenager practising for an English exam: expect a strong Russian accent, hesitation "
    "and grammatical mistakes. Reproduce EXACTLY what is said and keep every grammatical "
    "error unchanged — never correct, improve, complete or add anything. If a fragment is "
    "unintelligible, omit it rather than guess. Output only the transcription itself."
)

def _to_wav16k(data: bytes) -> bytes:
    """webm/opus из браузера → WAV 16 кГц моно.

    Нужно потому, что чат-модель Voxtral принимает ТОЛЬКО mp3 и wav (проверено
    29.07.2026: на webm приходит 400 «Failed to load audio file»), а MediaRecorder
    в браузере отдаёт webm/opus и другого формата не умеет.

    Формат именно WAV, а не mp3: кодирование mp3 из того же куска занимает втрое
    больше процессора (2.54 с против 0.71 с на 87 секундах речи), а процессор —
    самый дефицитный ресурс на бесплатном Render. Данных получается больше, но
    канал Render→Mistral это переживает, в отличие от 0.1 CPU.
    16 кГц моно — то, с чем работают все модели распознавания; больше не нужно.
    """
    import av  # noqa: PLC0415 — тяжёлый импорт нужен только на этом пути

    src = av.open(io.BytesIO(data))
    buf = io.BytesIO()
    dst = av.open(buf, "w", format="wav")
    stream = dst.add_stream("pcm_s16le", rate=16000)
    stream.layout = "mono"
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    try:
        for frame in src.decode(audio=0):
            for f in resampler.resample(frame):
                f.pts = None
                for packet in stream.encode(f):
                    dst.mux(packet)
        for packet in stream.encode(None):
            dst.mux(packet)
    finally:
        dst.close()
        src.close()
    return buf.getvalue()


# Что чат-модель принимает как есть. Всё остальное перекодируем в WAV.
_CHAT_AUDIO_OK = {".mp3": "mp3", ".wav": "wav"}


async def transcribe_chat(data: bytes, model: str, filename: str = "speech.webm") -> str:
    """Распознавание чат-моделью Voxtral: аудио уходит вложением в /chat/completions."""
    fmt = _CHAT_AUDIO_OK.get(os.path.splitext(filename)[1].lower())
    if fmt is None:
        t0 = time.time()
        data = await asyncio.to_thread(_to_wav16k, data)
        print(f"[stt] перекодировал в wav за {time.time() - t0:.2f}с "
              f"({len(data) // 1024} КБ)")
        fmt = "wav"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "input_audio", "input_audio": {
                "data": base64.b64encode(data).decode(), "format": fmt}},
            {"type": "text", "text": _VERBATIM_STT},
        ]}],
        "temperature": 0.0,
        "max_tokens": 1200,
    }
    # Таймаут свой: общий STT_TIMEOUT (12 с) заточен под быстрый путь разговора,
    # а тут двухминутный монолог обрабатывает модель в восемь раз крупнее.
    r = await _stt_client().post(
        f"{LLM_BASE_URL.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {_require('LLM_API_KEY')}"},
        json=payload,
        timeout=float(os.environ.get("STT_TASK_TIMEOUT", "40")),
    )
    if r.status_code != 200:
        raise _RemoteSttError(r.status_code, r.text)
    body = r.json()
    u = body.get("usage") or {}
    # Это обращение к чат-модели, а не к эндпоинту транскрипции: считаем его и
    # как STT (для статистики), и как запрос LLM — иначе месячный бюджет будет
    # видеть половину расхода.
    _track_usage(stt_req=1,
                 llm_req=1,
                 llm_prompt_tokens=u.get("prompt_tokens", 0) or 0,
                 llm_completion_tokens=u.get("completion_tokens", 0) or 0)
    _budget_note_llm(1)
    return (body["choices"][0]["message"]["content"] or "").strip()


# Осечки точного пути — видны в /health. Молчаливый откат опаснее отсутствия
# отката: система выглядит работающей, а работает на запасной модели и занижает
# баллы. Счётчик здесь не для красоты: сначала я хранил только ПОСЛЕДНЮЮ ошибку,
# её затирал следующий успешный запрос, и провал на webm (чат-модель принимает
# только mp3/wav) прятался за успехом на mp3. Счётчик так не обманешь.
_stt_task_last_error: str = ""
_stt_task_fallbacks: int = 0
_stt_task_ok: int = 0


async def transcribe_for_task(data: bytes, filename: str = "speech.webm") -> str:
    """Распознавание для оцениваемых заданий: точная модель, если она задана.

    Откат обязателен и молчаливым быть не должен: разбор без распознавания —
    это ноль пользы ученику, поэтому при любой осечке точного пути идём
    обычным, но пишем об этом и в лог, и в /health.
    """
    global _stt_task_last_error, _stt_task_fallbacks, _stt_task_ok
    if not STT_TASK_MODEL:
        return await transcribe_auto(data)
    try:
        text = await transcribe_chat(data, STT_TASK_MODEL, filename)
        _stt_task_ok += 1
        return text
    except Exception as e:  # noqa: BLE001
        detail = f"{type(e).__name__}: {str(e)[:200]}"
        _stt_task_last_error = detail
        _stt_task_fallbacks += 1
        print(f"[stt] точная модель {STT_TASK_MODEL} не смогла ({detail}) — откат на обычную")
        return await transcribe_auto(data)


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


async def synthesize_edge(text: str, voice: str | None = None) -> bytes:
    """TTS через edge-tts (нейро-голоса Microsoft). Возвращает mp3-байты.

    Пишем во ВРЕМЕННЫЙ файл (не в cwd), чтобы не мусорить в рабочей папке.

    Коннектор создаём НА КАЖДЫЙ вызов: edge-tts оборачивает сессию в `async with`
    и закрывает коннектор на выходе, переиспользовать его нельзя.
    """
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        path = f.name
    try:
        connector = aiohttp.TCPConnector(local_addr=(_LOCAL_IP, 0)) if _LOCAL_IP else None
        communicate = edge_tts.Communicate(text, voice or TTS_VOICE, connector=connector)
        await communicate.save(path)
        # edge-tts бесплатный, но метрика нужна: если однажды придётся уйти на
        # платный TTS целиком, объём уже будет известен.
        _track_usage(tts_edge_chars=len(text))
        with open(path, "rb") as fh:
            return fh.read()
    finally:
        if os.path.exists(path):
            os.unlink(path)


async def synthesize_mistral(text: str, voice: str | None = None) -> bytes:
    """TTS через Mistral. Тот же ключ, что у STT и LLM.

    Ответ приходит НЕ аудио-байтами, а JSON `{"audio_data": "<base64 mp3>"}` —
    в отличие от привычного OpenAI-совместимого `/audio/speech`. Проверено
    04.08.2026: до этого мы отдавали браузеру сам JSON под видом mp3, и
    запасной путь озвучки был мёртв целиком. Заметить это было нельзя, пока
    edge-tts работает: путь включается только после его отказа, а тогда
    `_tts_degraded` защёлкивается до перезапуска — то есть ученики остались бы
    вообще без голоса, а в телеграме лежало бы благополучное «перешёл на
    запасной». Ровно та же ловушка, что с `/talk_stream` и `/monologue`:
    «собралось» не значит «работает».

    Сырые байты на входе тоже принимаем — если провайдер однажды переедет на
    обычный ответ, озвучка не сломается второй раз.
    """
    r = await _stt_client().post(
        f"{LLM_BASE_URL.rstrip('/')}/audio/speech",
        headers={"Authorization": f"Bearer {_require('LLM_API_KEY')}"},
        json={"model": TTS_REMOTE_MODEL, "input": text,
              "voice": voice or TTS_REMOTE_VOICE},
    )
    if r.status_code != 200:
        raise RuntimeError(f"Mistral TTS вернул {r.status_code}: {r.text[:200]}")
    _track_usage(tts_mistral_chars=len(text))
    body = r.content
    if body[:1] != b"{":
        return body
    try:
        audio = json.loads(body).get("audio_data")
        if not audio:
            raise ValueError("в ответе нет audio_data")
        return base64.b64decode(audio)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Mistral TTS отдал непонятный ответ: {str(e)[:120]}") from e


_tts_degraded = False
# Обратный откат: отказ Mistral (обычно 429 — минутное ведро в 12000 знаков)
# переводит озвучку на edge-tts на время остывания, потом пробуем Mistral
# снова. Именно ОСТЫВАНИЕ, а не защёлка до перезапуска: минутный лимит
# проходит сам, и терять эмоции голоса до деплоя из-за одного 429 незачем.
# Защёлка осталась только у edge: его отказ значит «точка не пускает с этого
# IP», и через минуту это не меняется. До 16.08.2026 обратного отката не было
# вовсе: Mistral стал первичным ещё 04.08, и его сбой оставлял ученика без
# голоса при живом edge-tts рядом.
_TTS_COOLDOWN_SEC = float(os.environ.get("TTS_COOLDOWN_SEC", "120"))
_tts_mistral_down_until = 0.0
_tts_fallbacks = 0
_tts_last_error = ""


async def synthesize(text: str, who: dict | None = None) -> bytes:
    """Синтез голосом выбранной персоны.

    Провайдера задаёт `TTS_PROVIDER`, и это НЕ равнозначные варианты — у каждого
    своя цена (замерено 04.08.2026):

      mistral — эмоция зашита в голос (cheerful, angry, confident и ещё
        четыре), интонация живее, и синтез берёт сразу весь кусок. Но диктор
        ОДИН, мужской: персоны различаются только эмоцией. Медленнее и растёт
        с длиной — 30 знаков 0.65 с, 230 знаков 2.02 с. Своё ведро лимитов:
        12000 входных знаков в минуту, с токенами LLM не пересекается.

      edge — три РАЗНЫХ голоса (Ava, Andrew, Brian) и почти постоянная
        скорость: 0.46 с на короткой фразе, 0.59 с на длинной. Но эмоции нет
        совсем: стили Microsoft бесплатная точка отвергает наглухо.

    Выбор владельца по прослушиванию — mistral: живая интонация оказалась
    важнее трёх тембров. Вернуться к трём голосам — одна переменная окружения.

    Запасной путь остаётся прежним: отказ edge-tts переключает на Mistral до
    конца жизни процесса. Один отказ означает, что edge-tts недоступен с этого
    IP, — через фразу он доступен не станет, и платить таймаутом на каждой
    реплике незачем.
    """
    global _tts_degraded, _tts_mistral_down_until, _tts_fallbacks, _tts_last_error
    who = who or persona_of(None)
    if TTS_PROVIDER == "mistral" or _tts_degraded:
        if time.time() >= _tts_mistral_down_until:
            try:
                return await synthesize_mistral(text, emotion_of(who))
            except Exception as e:  # noqa: BLE001
                _tts_fallbacks += 1
                _tts_last_error = f"{type(e).__name__}: {str(e)[:100]}"
                _tts_mistral_down_until = time.time() + _TTS_COOLDOWN_SEC
                print(f"[tts] Mistral отказал ({_tts_last_error}) — "
                      f"{_TTS_COOLDOWN_SEC:.0f} с озвучивает edge-tts")
                notify_owner("tts:mistral_down",
                             "Mistral TTS отказал — озвучка временно на "
                             f"edge-tts (без эмоций). Осечка: {_tts_last_error}")
        # Пока Mistral остывает — edge-tts. Голос другой, но он ЕСТЬ; тишина
        # хуже смены тембра. Если и edge мёртв (сюда же ведёт путь с защёлкой
        # _tts_degraded), исключение уйдёт наверх — честнее, чем зациклиться.
        return await synthesize_edge(text, who.get("voice"))
    try:
        return await synthesize_edge(text, who.get("voice"))
    except Exception as e:  # noqa: BLE001
        print(f"[tts] edge-tts отказал ({type(e).__name__}: {str(e)[:100]}), "
              f"перехожу на Mistral до перезапуска")
        # Деградация TTS — событие: голоса персон пропали до перезапуска.
        notify_owner("tts:degraded",
                     f"edge-tts отказал ({type(e).__name__}) — озвучка ушла на "
                     "запасной Mistral (один диктор) до перезапуска процесса.")
        _tts_degraded = True
        return await synthesize_mistral(text, emotion_of(who))


# Клиенты создаём ОДИН раз на процесс, а не на каждый запрос: иначе каждый вызов
# платит новый TLS-хендшейк (а из РФ это заметная часть задержки голосовой петли).
# Ленивая инициализация — сервер должен стартовать и без ключа.
# Таймауты заданы явно: дефолт SDK (600с на чтение, 2 ретрая) при обрыве сети
# превращает сбой в многоминутное зависание, которое выглядит как «всё сломалось».
_llm: OpenAI | None = None
_async_llm: AsyncOpenAI | None = None
_llm_http: httpx.AsyncClient | None = None
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
                limits=_KEEPALIVE,
            ),
        )
    return _llm


def llm_http_client() -> httpx.AsyncClient:
    """HTTP-пул под стриминг LLM. Держим ССЫЛКУ на него отдельно от SDK: пул
    надо не только настроить, но и периодически трогать (_keep_pools_warm),
    а достучаться до внутреннего клиента SDK нельзя, не полагаясь на его
    приватные поля."""
    global _llm_http
    if _llm_http is None:
        # Свой транспорт нужен ради local_address: см. OUTBOUND_LOCAL_IP выше.
        # trust_env=False — чтобы системный прокси VPN не подхватился обратно.
        _llm_http = httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(local_address=_LOCAL_IP),
            timeout=_LLM_TIMEOUT, trust_env=False, limits=_KEEPALIVE,
        )
    return _llm_http


def async_llm_client() -> AsyncOpenAI:
    # Асинхронный клиент — для стриминга токенов (/talk_stream).
    global _async_llm
    if _async_llm is None:
        _async_llm = AsyncOpenAI(
            base_url=LLM_BASE_URL, api_key=_require("LLM_API_KEY"),
            timeout=_LLM_TIMEOUT, max_retries=_LLM_RETRIES,
            http_client=llm_http_client(),
        )
    return _async_llm


async def _ping_pool(client: httpx.AsyncClient) -> bool:
    """Дёрнуть соединение, чтобы оно осталось живым. /models не тарифицируется
    и токенов не тратит — это самый дешёвый способ сказать «я ещё здесь»."""
    try:
        r = await client.get(
            f"{LLM_BASE_URL.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {os.environ.get('LLM_API_KEY', '')}"},
            timeout=8.0,
        )
        return r.status_code < 500
    except Exception:  # noqa: BLE001 — прогрев не обязан удаваться
        return False


async def _check_llm_route() -> bool:
    """Проверить, что выбранный маршрут к модели ЖИВОЙ, и откатиться, если нет.

    Зачем. `OUTBOUND_LOCAL_IP` уводит запросы мимо VPN, и когда-то это было
    вчетверо быстрее. Но маршрут задаётся один раз в .env, а сеть меняется: с
    другим туннелем (или без него) прямой путь начинает резаться DPI —
    рукопожатие проходит за 34 мс, а сам запрос умирает по таймауту. Замерено
    05.08.2026 на этой машине: STT и TTS напрямую отваливались с ReadTimeout,
    хотя адрес в .env был совершенно правильный.

    Проверка `_usable_local_ip` этого не ловит: она спрашивает «существует ли
    адрес», а не «доходят ли по нему запросы». Без ответа на второй вопрос
    сервер тихо работает вчетверо медленнее, и понять это можно только замером.
    """
    global _llm_http, _async_llm
    if await _ping_pool(llm_http_client()):
        return True
    if not _LOCAL_IP:
        return False
    print(f"[startup] маршрут мимо VPN (OUTBOUND_LOCAL_IP={_LOCAL_IP}) не отвечает — "
          f"перехожу на обычный маршрут")
    try:
        await _llm_http.aclose()  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass
    _llm_http = httpx.AsyncClient(timeout=_LLM_TIMEOUT, trust_env=False, limits=_KEEPALIVE)
    _async_llm = None  # пересоберётся на новом пуле при первом обращении
    return await _ping_pool(_llm_http)


async def _keep_pools_warm() -> None:
    """Держать соединения с Mistral живыми, пока сервер работает.

    Зачем фоновая задача, а не только прогрев на старте: соединение закрывает
    не наш пул, а вторая сторона (idle-таймаут сервера, NAT). Прогретое на
    старте соединение до первого ученика не доживает, и пауза перед его первым
    ответом складывается из трёх рукопожатий подряд — распознавание, модель,
    озвучка. Цена задачи: два GET в минуту без токенов; выигрыш — рукопожатия
    уходят из горячего пути КАЖДОЙ реплики, и качество при этом не трогается
    вовсе.
    """
    alive = True
    while True:
        await asyncio.sleep(_POOL_PING_EVERY)
        ok = await _ping_pool(_stt_client())
        if _llm_http is not None:
            ok = await _ping_pool(_llm_http) and ok
        # Печатаем только СМЕНУ состояния: строка раз в минуту в логе — шум,
        # в котором тонет всё остальное.
        if ok != alive:
            alive = ok
            print("[warm] соединения с Mistral " + ("снова живы" if ok else
                  "не отвечают на прогрев — первая реплика будет медленнее"))


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


# Минимальная длина ПЕРВОГО озвучиваемого куска. Не эстетика — арифметика.
#
# Реплика режется на два куска: голова уходит в синтез сразу (чтобы звук пошёл
# быстро), остальное — ОДНИМ куском (чтобы у голоса была сквозная интонация, а
# не по нейтральной фразе за раз; ровно это и слышно в примере C).
#
# Голова обязана ЗВУЧАТЬ дольше, чем синтезируется хвост, иначе в середине
# реплики появится дыра. Замер Mistral TTS 04.08.2026: синтез ≈ 0.5 с + 0.0065 с
# на знак, звучание ≈ 0.047 с на знак. Для хвоста в 150-200 знаков синтез
# занимает 1.5-1.8 с, значит голова должна звучать хотя бы столько же:
# 1.8 / 0.047 ≈ 40 знаков. Берём 70 с запасом на медленную сеть.
#
# Сверху это ограничено скоростью самой модели (~200 знаков/с), то есть ожидание
# 70 знаков стоит около 0.35 с к паузе до первого звука — на порядок меньше, чем
# сам синтез.
_HEAD_MIN_CHARS = 70


def _take_head(buf: str) -> tuple[str, str]:
    """Первый кусок для озвучки: целые предложения, пока не наберётся _HEAD_MIN_CHARS.

    Возвращает ('', buf) пока набирать нечего — обрывать предложение на середине
    нельзя, интонация конца фразы у синтеза берётся из знака препинания.
    """
    head, rest = "", buf
    while len(head) < _HEAD_MIN_CHARS:
        sentence, tail = _split_sentence(rest)
        if not sentence:
            return "", buf  # законченных предложений не хватило — ждём ещё
        head = f"{head} {sentence}".strip() if head else sentence
        rest = tail
    return head, rest


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
                # Именно /ping: он не трогает базу. Пинг в /health будил Neon
                # каждые 10 минут, и 100 бесплатных CU-часов сгорели за 26
                # дней (26.08.2026, проект встал на паузу до конца месяца).
                await cl.get(KEEP_AWAKE_URL.rstrip("/") + "/ping")
            if fails:
                print(f"[keep-awake] снова отвечает (было {fails} неудач подряд)")
            fails = 0
        except Exception as e:  # noqa: BLE001
            fails += 1
            if fails in (1, 5, 20):
                print(f"[keep-awake] не достучался до {KEEP_AWAKE_URL} "
                      f"({type(e).__name__}), неудач подряд: {fails}")


async def _storage_reconnect(first_delay: float = 30.0) -> None:
    """База не ответила на старте — пробуем фоном, пока не оживёт.

    Neon умеет засыпать, и если буст деплоя совпал со сном, одноразовая
    проверка выключала память до СЛЕДУЮЩЕГО деплоя: кабинет, статистика и
    календарь отдавали 503, хотя база просыпалась через минуту (видели
    вживую 26.08.2026). Пауза растёт вдвое до десяти минут — мёртвую базу
    долбить незачем, а проснувшуюся подхватим быстро.
    """
    global _storage_ok
    delay = first_delay
    while not _storage_ok:
        _STORAGE_RETRY["next_at"] = time.monotonic() + delay
        await asyncio.sleep(delay)
        try:
            await asyncio.to_thread(storage.ensure_schema)
        except Exception as e:  # noqa: BLE001
            print(f"[storage] база всё ещё недоступна ({type(e).__name__}: {e})")
            delay = min(delay * 2, 600.0)
            _STORAGE_RETRY.update(attempts=_STORAGE_RETRY["attempts"] + 1,
                                  error=type(e).__name__)
            continue
        _storage_ok = True
        print(f"[storage] база ожила — память включена: {storage.describe()}")
        # Последний алерт владельцу был «Память: ВЫКЛЮЧЕНА» — без этой строки
        # он так и висел бы ложью до следующего деплоя.
        notify_owner("storage", "База ожила после неудачного старта — память снова включена.")
        # Всё, что старт делает ПОСЛЕ включения памяти, — здесь тоже:
        # иначе дневные лимиты и месячный бюджет останутся пустыми до рестарта.
        try:
            day = storage.msk_day()
            counts = await asyncio.to_thread(storage.voice_counts, day)
            # Слияние по максимуму, НЕ замена (отличие от старта): за простой
            # память копила реплики, которых в базе нет, — замена словаря
            # откатила бы дневной лимит назад.
            if _VOICE_DAY.get("day") == day:
                for k, v in (_VOICE_DAY.get("counts") or {}).items():
                    counts[k] = max(counts.get(k, 0), v)
            _VOICE_DAY.update(day=day, counts=counts)
            if counts:
                print(f"[storage] дневные лимиты восстановлены: {len(counts)} учеников")
        except Exception as e:  # noqa: BLE001
            print(f"[storage] счётчики дня не поднялись ({type(e).__name__}) — с нуля")
        if MONTHLY_LLM_BUDGET > 0:
            _BUDGET["synced"] = time.monotonic()
            _budget_sync_bg()


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
        t = time.time()
        # Греем ОБА пула: распознавание с озвучкой ходят одним клиентом, модель —
        # другим (у него свой маршрут). Раньше грелся только первый, и первый же
        # запрос к модели всё равно платил рукопожатие.
        ok = await _ping_pool(_stt_client())
        if os.environ.get("LLM_API_KEY"):
            ok = await _check_llm_route() and ok
        print(f"[startup] соединения с Mistral прогреты за {time.time() - t:.1f}с"
              if ok else "[startup] прогрев не удался — первая реплика будет медленнее")
        # И держим их тёплыми: прогрев со сроком жизни в пять секунд бесполезен.
        asyncio.create_task(_keep_pools_warm())
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
            # Без эмодзи намеренно: Windows-консоль в cp1251 роняла print с «⚠»
            # UnicodeEncodeError-ом, а print стоит в try — и «неудачный вывод
            # предупреждения» превращался в «память выключена целиком».
            print("[startup] (!) память в SQLite: на Render диск эфемерный, база "
                  "живёт до ближайшего деплоя. Для постоянной — DATABASE_URL (Neon).")
    except Exception as e:  # noqa: BLE001
        _storage_ok = False
        print(f"[startup] память НЕдоступна ({type(e).__name__}: {e}) — работаю без неё")
        # Не навсегда: фоном пробуем снова, пока база не ответит.
        asyncio.create_task(_storage_reconnect())

    # Дневные лимиты переживают деплой: поднимаем сегодняшние счётчики из базы.
    if _storage_ok:
        try:
            day = storage.msk_day()
            counts = await asyncio.to_thread(storage.voice_counts, day)
            _VOICE_DAY.update(day=day, counts=counts)
            if counts:
                print(f"[startup] дневные лимиты восстановлены: {len(counts)} учеников")
        except Exception as e:  # noqa: BLE001
            print(f"[startup] счётчики дня не поднялись ({type(e).__name__}) — с нуля")

    # Месячный бюджет: после рестарта память процесса пустая, а месяц — нет.
    # Сверяемся с базой сразу, не дожидаясь ленивого триггера в _check_voice_rate.
    # Строго ПОСЛЕ включения памяти: _budget_sync_bg без _storage_ok — no-op.
    if MONTHLY_LLM_BUDGET > 0:
        _BUDGET["synced"] = time.monotonic()
        _budget_sync_bg()

    print("[startup] Сервер принимает запросы.")
    # Старт процесса = деплой или рестарт после падения — владельцу видно оба.
    notify_owner("startup", "Сервер запустился (деплой или рестарт). "
                            f"Память: {storage.describe() if _storage_ok else 'ВЫКЛЮЧЕНА'}.")


_HERE = os.path.dirname(os.path.abspath(__file__))
_DIST = os.path.join(_HERE, "..", "dist")  # собранный React-фронт (npm run build)


@app.get("/test")
def test_page():
    """Старая проверочная страница (vanilla JS). Основной UI — собранный фронт на /."""
    return FileResponse(os.path.join(_HERE, "test.html"))


def _tts_health() -> str:
    """Чем озвучиваем НА САМОМ ДЕЛЕ и не ушли ли на запасной.

    Поле уже один раз врало: было захардкожено строкой «edge-tts», хотя с
    04.08.2026 первичный провайдер — Mistral (поймано 16.08.2026 сверкой с
    ненулевым usage_today.tts_mistral_chars). Та же ловушка, из-за которой у
    STT завели счётчик откатов: откат обязан быть ГРОМКИМ, иначе система
    выглядит рабочей вслепую.
    """
    if TTS_PROVIDER == "mistral" or _tts_degraded:
        s = (f"mistral:{TTS_REMOTE_MODEL} (эмоция в голосе, диктор один)"
             if TTS_PROVIDER == "mistral" else
             f"mistral:{TTS_REMOTE_MODEL} — ЗАПАСНОЙ, edge-tts отказал")
        if _tts_fallbacks:
            s += (f"; откатов на edge {_tts_fallbacks}"
                  + (" (сейчас остывает, говорит edge)"
                     if time.time() < _tts_mistral_down_until else "")
                  + f"; последняя осечка — {_tts_last_error}")
        return s
    return f"edge-tts:{TTS_VOICE}"


@app.get("/ping")
def ping():
    """Пульс для keep-awake и внешних мониторов: ноль обращений к базе.

    Держит бодрым только САМ сервис (Render). База должна засыпать, когда
    учеников нет, — иначе Neon сжигает месячную квоту compute-часов фоном.
    """
    return {"ok": True}


# Поля /health, требующие базы, живут в часовом кэше: диагностику человек
# открывает изредка, и ради неё можно разбудить Neon раз в час, но не каждые
# десять минут фоновым пингом (так сгорела квота августа-2026).
_HEALTH_DB = {"at": 0.0, "usage": {}, "invites": -1}
_HEALTH_DB_TTL = 3600.0


def _health_db_refresh() -> None:
    if not _storage_ok:
        return
    now = time.monotonic()
    if _HEALTH_DB["at"] and now - _HEALTH_DB["at"] < _HEALTH_DB_TTL:
        return
    _HEALTH_DB["at"] = now
    try:
        report = storage.usage_report(1)
        _HEALTH_DB["usage"] = next(iter(report.values()), {}) if report else {}
    except Exception:  # noqa: BLE001
        pass
    try:
        _HEALTH_DB["invites"] = storage.invites_count()
    except Exception:  # noqa: BLE001
        pass


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
        # Распознавание для оцениваемых заданий: какая модель и не сорвалась ли
        # она в откат. Без этого поля откат молчит, и система выглядит рабочей,
        # хотя точный путь мёртв (ровно так и было поймано 29.07.2026).
        "stt_task": (f"{STT_TASK_MODEL}: точным путём {_stt_task_ok}, "
                     f"откатов {_stt_task_fallbacks}"
                     + (f"; последняя осечка — {_stt_task_last_error}"
                        if _stt_task_last_error else "")
                     if STT_TASK_MODEL else "та же, что в разговоре"),
        "tts": _tts_health(),
        "llm_base": LLM_BASE_URL,
        "llm_model": LLM_MODEL,
        "llm_key": bool(os.environ.get("LLM_API_KEY")),
        "memory": _storage_health(),
        # Показываем ТОЛЬКО число кодов, не сами коды. «закрыта» здесь — не
        # ошибка, а сигнал владельцу: задай INVITE_CODES в панели Render.
        "registration": _registration_state(),
        # Сводка расхода за сегодня — секретов не содержит, а увидеть «сколько
        # уже сожгли» можно без ключа админки. Полная разбивка — /admin/usage.
        "usage_today": _usage_today(),
        # Месячный бюджет вызовов LLM: mode normal/eco/low/empty (см. _BUDGET).
        "budget_month": _budget_state(),
    }


def _storage_health() -> str:
    """Что с памятью и жив ли фоновый повтор — одной строкой.

    Три разных состояния раньше выглядели одинаково («выключена»): база мертва
    надолго, база вот-вот подхватится повтором, сервер крутит сборку вообще без
    повтора. Владельцу они требуют РАЗНЫХ действий, поэтому и ответы разные.
    """
    if _storage_ok:
        return storage.describe()
    if not _STORAGE_RETRY["next_at"]:
        # Повтор не запущен: либо старт прошёл удачно и база отвалилась позже,
        # либо это сборка до 26.08.2026, где повтора не было вовсе.
        return "выключена (фоновый повтор не запущен)"
    left = max(0, round(_STORAGE_RETRY["next_at"] - time.monotonic()))
    if not _STORAGE_RETRY["attempts"]:
        return f"выключена, первая попытка через {left}с"
    return (f"выключена: попыток подряд {_STORAGE_RETRY['attempts']}, "
            f"последняя ошибка {_STORAGE_RETRY['error']}, следующая через {left}с")


def _usage_today() -> dict:
    if not _storage_ok:
        return {}
    _health_db_refresh()
    return _HEALTH_DB["usage"]


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
        transcript_text = await transcribe_for_task(data)
    except SttFailed as e:
        print(f"[stt] монолог не распознан: {e}")
        raise HTTPException(status_code=502, detail=e.user_message)
    t1 = time.time()

    if not transcript_text:
        raise HTTPException(
            status_code=422, detail="Тишина — ничего не распознали. Запиши монолог ещё раз."
        )

    # 2) LLM — один структурный проход, ответ строго JSON. Правила и шкала те же,
    #    что у /task_feedback: этот эндпоинт остался для старых клиентов и
    #    смоук-тестов, расходиться в оценке они не должны.
    client = llm_client()
    prompt, ctx = _feedback_prompt("monologue", {}, transcript_text)
    try:
        completion = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": transcript_text},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=2000,
            )
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"LLM ошибка ({LLM_MODEL}): {e}")

    _track_llm(completion)
    raw = (completion.choices[0].message.content or "").strip()
    observations = _loads_forgiving(raw)
    if observations is None:
        raise HTTPException(status_code=502, detail=f"LLM вернул не-JSON: {raw[:200]}")
    feedback = _score_feedback("monologue", observations, ctx)
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

# Оценивание вынесено в scoring.py — чистые функции без сети и базы.
from scoring import (  # noqa: E402
    FALLBACK_MONOLOGUE_BRIEF,
    _errors_from,
    _feedback_prompt,
    _loads_forgiving,
    _score_feedback,
)


async def _recheck_disputed(kind: str, observations: dict, ctx: dict,
                            transcript: str, persona: str, client) -> dict:
    """Спорные вердикты диалога/интервью — на повторную, точечную проверку.

    Что считается спорным (список расширен 05.08.2026):
      * пункт, который первый проход сам пометил borderline;
      * вердикт БЕЗ внятного обоснования — и незачёт, и зачёт. Раньше
        проверялся только незачёт, но незаслуженный балл так же неправомерен,
        как незаслуженный ноль, а «правомерное оценивание» — про обе стороны;
      * цитата, которой нет в расшифровке, и подозрительно короткий зачтённый
        ответ — их метит ege_scoring.flag_suspicious до этого вызова.

    Ограничения по скорости — сознательные (требование владельца: не замедлять):
    один дополнительный вызов на работу, максимум 3 пункта, только 40/41.
    Любой сбой второго прохода оставляет вердикты первого — хуже не становится.
    """
    if kind not in ("dialogue", "interview"):
        return observations
    key = "questions" if kind == "dialogue" else "answers"
    items = [it for it in (observations.get(key) or []) if isinstance(it, dict)]
    points = [str(p) for p in (ctx.get("points" if kind == "dialogue" else "questions") or [])]

    disputed = []
    for i, it in enumerate(items):
        if i >= len(points):
            continue
        reason = str(it.get("reason") or "").strip()
        # Вес спорности: чем выше, тем нужнее второй взгляд. Нужен, потому что
        # пересматриваем максимум три пункта — и выбирать надо худшие.
        weight = 0
        if it.get("quote_missing"):
            weight = 3  # процитировано несказанное — самое опасное
        elif it.get("too_short"):
            weight = 2  # балл за обрывок фразы
        elif it.get("borderline"):
            weight = 2
        elif len(reason) < 8:
            weight = 1  # вердикт без обоснования, в любую сторону
        if weight:
            disputed.append({"n": i + 1, "point": points[i], "weight": weight,
                             "accepted": bool(it.get("accepted")), "reason": reason})
    if not disputed:
        return observations
    # Раньше здесь стоял выход «спорных больше трёх — не проверяем вовсе»: чем
    # хуже была работа, тем меньше её проверяли. Теперь берём три САМЫХ спорных,
    # порядок пунктов сохраняем — цена та же, один вызов.
    if len(disputed) > 3:
        disputed = sorted(disputed, key=lambda d: -d["weight"])[:3]
        disputed.sort(key=lambda d: d["n"])

    task_text = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(points))
    prompt = ege_prompts.recheck_prompt(kind, disputed, task_text, transcript, persona)
    try:
        completion = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "system", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0,  # см. объяснение у первого прохода
                max_tokens=400,
            )
        )
        _track_llm(completion)
        verdicts = (_loads_forgiving((completion.choices[0].message.content or "").strip())
                    or {}).get("items") or []
    except Exception as e:  # noqa: BLE001
        print(f"[recheck] второй проход не удался ({type(e).__name__}) — оставляю первый")
        return observations

    flips = 0
    for v in verdicts:
        if not isinstance(v, dict):
            continue
        try:
            idx = int(v.get("n") or 0) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(items):
            new_ok = bool(v.get("accepted"))
            if new_ok != bool(items[idx].get("accepted")):
                flips += 1
            items[idx]["accepted"] = new_ok
            reason = str(v.get("reason") or "").strip()
            if reason:
                items[idx]["reason"] = reason
    print(f"[recheck] спорных пунктов: {len(disputed)}, вердикт изменён у {flips}")
    return observations


# Второй взгляд на спорные аспекты монолога. ПО УМОЛЧАНИЮ ВЫКЛЮЧЕН — так решил
# замер, а не вкус (05.08.2026, шесть работ ФИПИ, по три прогона на ветку):
#
#   в пределах ±1 балла   3.0/6  ->  3.7/6
#   точное совпадение     2.0/6  ->  1.3/6
#   средняя ошибка       11.0    -> 10.67 балла  <- решающее число
#
# Средняя ошибка не изменилась: второй проход не судит точнее, он судит ДОБРЕЕ.
# Одна и та же правка (аспект 1 «неполно» -> «раскрыт») спасла работу, которой
# эксперты дали 4, и испортила ту, которой дали 0. Платить за это лишним вызовом
# и парой секунд ожидания ученика незачем.
#
# Код оставлен и покрыт тестами намеренно: включается одной переменной, и
# вернуться к нему стоит, когда золотой набор вырастет с шести работ до
# нескольких десятков (копилка жалоб, docs/DECISIONS.md §6.7). На шести работах
# разница в 0.3 балла средней ошибки — это шум, а не вывод.
MONOLOGUE_RECHECK = os.environ.get("MONOLOGUE_RECHECK", "0").strip() not in ("0", "false", "no")


async def _recheck_aspects(kind: str, observations: dict, ctx: dict,
                           transcript: str, persona: str, client) -> dict:
    """Спорные аспекты монолога — на повторную, точечную проверку.

    Отличие от `_recheck_disputed` не в механике, а в том, ЧТО спорно. У
    диалога спорен вердикт по вопросу; здесь — аспект, который первый проход
    зачёл наполовину или подтвердил цитатой, которой в речи нет (отбор —
    ege_scoring.doubtful_aspects).

    Цена: один вызов на работу и только когда спорное есть. Любой сбой
    оставляет вердикты первого прохода — хуже не становится.
    """
    if kind != "monologue" or not MONOLOGUE_RECHECK:
        return observations
    numbers = ege_scoring.doubtful_aspects(observations, transcript)
    if not numbers:
        return observations
    first = {}
    for c in (observations.get("aspects") or []):
        if isinstance(c, dict):
            try:
                first[int(c.get("n") or 0)] = c
            except (TypeError, ValueError):
                continue
    prompt = ege_prompts.aspect_recheck_prompt(
        numbers, str(ctx.get("brief") or ""), ctx.get("facts") or [], first, persona)
    try:
        completion = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "system", "content": prompt},
                          {"role": "user", "content": transcript}],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=700,
            )
        )
        _track_llm(completion)
        data = _loads_forgiving((completion.choices[0].message.content or "").strip()) or {}
    except Exception as e:  # noqa: BLE001
        print(f"[recheck] второй взгляд на аспекты не удался ({type(e).__name__}) — "
              f"остаются вердикты первого прохода")
        return observations
    changed = ege_scoring.merge_aspect_recheck(observations, data.get("aspects"))
    print(f"[recheck] аспекты {numbers}: изменено признаков {changed}")
    return observations


# Сбор замеров произношения. Включается переменной; по умолчанию ВКЛЮЧЁН,
# потому что без живой речи порог не подобрать, а ученику это ничего не стоит:
# считается фоном, после того как разбор уже уехал.
PRON_COLLECT = os.environ.get("PRON_COLLECT", "1").strip() not in ("0", "false", "no")
# Потолок времени на одну запись. Дальше замер бросается: копилка не стоит
# того, чтобы занимать процессор на слабой машине дольше этого.
PRON_BUDGET_SEC = float(os.environ.get("PRON_BUDGET_SEC", "90"))
# Короче этого замерять нечего: на трёх словах нормировка бессмысленна.
PRON_MIN_WORDS = int(os.environ.get("PRON_MIN_WORDS", "6"))
# Разговор идёт десятками реплик за сессию, и мерить КАЖДУЮ на 0.1 vCPU
# нельзя — процессор нужен живым запросам. Берём каждую N-ю.
PRON_TALK_EVERY = int(os.environ.get("PRON_TALK_EVERY", "4"))
# Показывать ли ученику слабые слова. Ноль — потому что показатель не
# предсказывает вердикт эксперта (проверено на живой речи 20.08.2026,
# см. /pron/weakest). Сбор при этом продолжается: числа копятся, а
# показывать их станет чем, когда появится фонемная ступень.
PRON_SHOW = os.environ.get("PRON_SHOW", "0").strip() not in ("0", "false", "no")

# ------------------------------------------------------------ КОРПУС ГОЛОСА
# Здесь хранится САМА ЗАПИСЬ, поэтому правил больше, чем у любой другой части.
#
# Зачем вообще. Всё, что мы пытались построить вокруг произношения и точности
# оценивания, упиралось в одно: живых работ с разметкой нет, а купить их негде
# (§6.28). Корпус решает это единственным честным способом — накапливая
# настоящие ответы настоящих учеников вместе с тем, что система о них решила.
#
# Три предохранителя, каждый обязателен:
#   1. СОГЛАСИЕ. Без corpus_consent=1 в настройках ученика не пишется ничего.
#      Это не вежливость: голос — персональные данные, а среди учеников есть
#      несовершеннолетние.
#   2. ПОТОЛОК МЕСТА. Neon free — 0.5 ГБ на весь проект вместе с заданиями и
#      картинками. Дойдя до CORPUS_MAX_MB, сбор молча останавливается, а не
#      роняет базу, из которой живёт вся система.
#   3. КВОТА НА УЧЕНИКА. Один активный не должен занять корпус собой: нужна
#      РАЗНАЯ речь, а не много одинаковой.
CORPUS_COLLECT = os.environ.get("CORPUS_COLLECT", "1").strip() not in ("0", "false", "no")
CORPUS_MAX_MB = float(os.environ.get("CORPUS_MAX_MB", "150"))
CORPUS_PER_STUDENT = int(os.environ.get("CORPUS_PER_STUDENT", "40"))
CORPUS_PER_STUDENT_KIND = int(os.environ.get("CORPUS_PER_STUDENT_KIND", "15"))
# Запись длиннее этого в корпус не берём: минута речи — это уже полный ответ,
# а всё сверх обычно означает, что ученик забыл остановить запись.
CORPUS_MAX_SEC = float(os.environ.get("CORPUS_MAX_SEC", "180"))
_corpus_full = False

_pron_talk_seen = 0
# Считаем СТРОГО ПО ОДНОЙ записи за раз. На 0.1 vCPU (Render) параллельный
# разбор двух чтений отнял бы процессор у живых запросов остальных учеников.
_pron_gate = threading.Semaphore(1)
_pron_disabled = False
_pron_done = 0


def _mime_of(filename: str) -> str:
    """Тип записи по расширению: браузеры шлют webm/ogg, iOS — mp4/m4a."""
    ext = os.path.splitext(filename or "")[1].lower()
    return {".webm": "audio/webm", ".ogg": "audio/ogg", ".mp3": "audio/mpeg",
            ".wav": "audio/wav", ".m4a": "audio/mp4",
            ".mp4": "audio/mp4"}.get(ext, "audio/webm")


def _collect_corpus_bg(device: str | None, kind: str, variant: str,
                       data: bytes, mime: str, duration: float,
                       transcript: str, reference: str, feedback: dict,
                       audio_info: dict | None = None) -> None:
    """Положить работу в корпус вместе с автоматической разметкой.

    Всё, что система уже решила об этом ответе, кладётся рядом со звуком:
    расшифровка, балл по шкале ФИПИ, разбор по критериям, ошибки с цитатами,
    осмотр звука. Ручная проверка (verified) добавляется владельцем поверх.
    Так одна и та же запись годится и как обучающий пример, и как строка сетки
    точности: видно, что ответил ученик, что решила система и где она неправа.

    Молчит и не мешает: любая беда внутри — это отсутствие ещё одной записи в
    корпусе, а не сломанный разбор у ученика.
    """
    global _corpus_full
    if not (CORPUS_COLLECT and _storage_ok and device and data) or _corpus_full:
        return
    if duration and duration > CORPUS_MAX_SEC:
        return

    def work() -> None:
        global _corpus_full
        try:
            # СОГЛАСИЕ — первое, что проверяется, и проверяется по базе, а не
            # по тому, что прислал клиент.
            try:
                settings = json.loads(storage.get_settings(device) or "{}")
            except Exception:  # noqa: BLE001 — битые настройки = нет согласия
                settings = {}
            if not settings.get("corpus_consent"):
                return
            if storage.corpus_bytes_total() >= CORPUS_MAX_MB * 1048576:
                if not _corpus_full:
                    _corpus_full = True
                    print(f"[corpus] потолок {CORPUS_MAX_MB:.0f} МБ достигнут — "
                          "сбор остановлен до перезапуска")
                    notify_owner("corpus", f"Корпус голоса дошёл до "
                                           f"{CORPUS_MAX_MB:.0f} МБ, сбор остановлен.")
                return
            if storage.corpus_count_for(device) >= CORPUS_PER_STUDENT:
                return
            if storage.corpus_count_for(device, kind) >= CORPUS_PER_STUDENT_KIND:
                return

            labels = _corpus_labels(kind, feedback, audio_info)
            cid = storage.corpus_add(
                device, kind, variant, data, mime, duration, transcript,
                reference, labels.pop("_score", None), labels.pop("_max", None),
                labels)
            print(f"[corpus] {kind} {len(data) // 1024} КБ, разметка "
                  f"{labels.get('summary', '')} -> {cid[:8]}")
        except Exception as e:  # noqa: BLE001 — сбор корпуса не критичен
            print(f"[corpus] не записалось ({type(e).__name__}: {str(e)[:90]})")

    threading.Thread(target=work, daemon=True, name="corpus").start()


def _corpus_labels(kind: str, feedback: dict, audio_info: dict | None) -> dict:
    """Автоматическая разметка одной работы — то, ради чего корпус и нужен.

    Складываем ровно то, что система уже посчитала: балл, критерии, ошибки с
    цитатами, замер подачи, осмотр звука. Ничего не досчитываем заново — это
    снимок ФАКТИЧЕСКОГО решения системы на этой записи, и именно с ним потом
    сравнивается вердикт человека.
    """
    fb = feedback or {}
    score = fb.get("score")
    max_score = fb.get("max_score")
    criteria = {}
    for c in fb.get("criteria") or []:
        if isinstance(c, dict) and c.get("key"):
            criteria[str(c["key"])] = {"score": c.get("score"),
                                       "max": c.get("max")}
    errors = [{"cat": e.get("cat"), "quote": e.get("quote"),
               "correction": e.get("correction")}
              for e in (fb.get("errors") or [])[:20] if isinstance(e, dict)]
    out = {
        "_score": score,
        "_max": max_score,
        "kind": kind,
        "criteria": criteria,
        "errors": errors,
        "errors_n": len(fb.get("errors") or []),
        "summary": (f"{score}/{max_score}" if score is not None else "без балла"),
        "model": LLM_MODEL,
        "stt": STT_TASK_MODEL or STT_REMOTE_MODEL,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }
    if fb.get("delivery"):
        out["delivery"] = {k: v for k, v in fb["delivery"].items()
                           if k in ("wpm", "pauses", "finished", "seconds")}
    if fb.get("diff"):
        out["diff"] = {k: v for k, v in fb["diff"].items()
                       if k in ("substitutions", "omissions", "tail_missing")}
    if audio_info:
        out["audio"] = {k: audio_info.get(k) for k in
                        ("seconds", "loud_frames", "reason") if k in audio_info}
    return out


def _collect_pron_bg(device: str | None, kind: str, variant: str, data: bytes,
                     ext: str, reference: str, method: str = "forced",
                     transcript: str = "") -> None:
    """Замерить произношение и сложить числа в копилку. Ничего не возвращает.

    ДВА СПОСОБА, и путать их нельзя (подробности — storage.pron_stats):
      forced — эталон известен заранее (чтение вслух). Настоящий GOP;
      cross  — эталона нет, сверяем с тем, что услышал ДРУГОЙ распознаватель
               (Mistral). Системы разные, так что это не замкнутый круг, но и
               не то же самое: показатель значит «два распознавателя не
               сошлись», а не «звук не похож на нужное слово».

    Всё, что здесь может пойти не так, обязано остаться внутри: ученик свой
    разбор уже получил, и падение фоновой калибровки не имеет права его
    касаться.
    """
    global _pron_disabled, _pron_done
    if not (PRON_COLLECT and _storage_ok and reference and device) or _pron_disabled:
        return
    # Слишком короткая реплика ничего не даёт распределению, а процессор ест.
    if len(reference.split()) < PRON_MIN_WORDS:
        return

    def work() -> None:
        global _pron_disabled, _pron_done
        # Не ждём очереди: если процессор уже занят другим замером, эту запись
        # просто пропускаем. Копилка наполнится со следующей.
        if not _pron_gate.acquire(blocking=False):
            print("[pron] замер пропущен: процессор занят предыдущим")
            return
        try:
            import gop
            pcm = audio_check.to_pcm(data, ext)
            if pcm is None:
                return
            t0 = time.time()
            res = gop.score(pcm, reference, budget_sec=PRON_BUDGET_SEC)
            spent = time.time() - t0
            if not res.get("ok"):
                print(f"[pron] замер не удался: {res.get('reason')}")
                return
            words = res["words"]
            if method == "forced" and transcript:
                # Слова, которые ученик и не пытался читать, — не произношение.
                # Помечаем их по расшифровке; в распределение порога они не
                # пойдут (storage.pron_stats), но останутся в базе: по ним
                # видно, ЧТО именно было пропущено, и их же можно поднять при
                # разборе жалобы «записали не то».
                unspoken = gop.mark_spoken(words, transcript)
                if unspoken:
                    print(f"[pron] {unspoken} слов эталона не прозвучали — "
                          "в распределение не пойдут")
            else:
                for w in words:
                    w["spoken"] = 1
            # Слова короче трёх букв (in, is, do) выравнивание держит плохо —
            # на проде они заняли весь верх слабых у cross. Поводом придраться
            # к ученику они не станут никогда, так что и копить их незачем.
            words = [w for w in words
                     if sum(ch.isalpha() for ch in str(w.get("word") or "")) >= 3]
            n = storage.pron_add(device, kind, variant, words,
                                 res.get("model", ""), method)
            _pron_done += 1
            print(f"[pron] {kind}/{method}: {n} слов за {spent:.1f} с "
                  f"(покрыто {res['covered']}/{res['of']}, медиана {res['median']})")
            _track_latency("pron_gop", spent)
            # Громкий отказ вместо тихого тормоза: если на этой машине замер
            # съедает больше отведённого, выключаемся до перезапуска и говорим
            # об этом. Иначе фоновая задача незаметно душила бы весь сервис.
            if spent > PRON_BUDGET_SEC:
                _pron_disabled = True
                print(f"[pron] {spent:.0f} с на запись — это дороже отведённого "
                      f"{PRON_BUDGET_SEC:.0f} с. Сбор выключен до перезапуска.")
        except Exception as e:  # noqa: BLE001 — фоновая калибровка не критична
            print(f"[pron] сбор сорвался ({type(e).__name__}: {str(e)[:90]})")
        finally:
            _pron_gate.release()

    threading.Thread(target=work, daemon=True, name="pron-collect").start()


async def _task_feedback_work(kind: str, payload_raw: str, data: bytes,
                              device: str | None, variant: str,
                              duration_sec: int, session_done: bool = False,
                              filename: str = "speech.webm",
                              persona: str = "") -> dict:
    t0 = time.time()

    # Осмотр САМОГО ЗВУКА до распознавания. Тишину нельзя отдавать в Voxtral:
    # он не умеет отвечать «там ничего нет» и сочиняет текст — на шести
    # секундах тишины выдал 960 слов чужого монолога (замер 05.08.2026).
    # Ученику при этом приписывалось несказанное. Дешевле и честнее не
    # спрашивать: заодно экономятся вызов STT и вызов LLM.
    sound = await asyncio.to_thread(
        audio_check.inspect, data, os.path.splitext(filename)[1].lower())
    quiet = audio_check.silence_reason(sound)
    if quiet is not None:
        print(f"[audio] запись отклонена без распознавания: {sound}")
        raise HTTPException(status_code=422, detail=quiet)

    # Выжимки памяти тянем ПАРАЛЛЕЛЬНО с распознаванием: STT занимает 0.5-2 с,
    # SELECT успевает заведомо раньше — добавка к задержке ровно ноль.
    mem_task = asyncio.create_task(_load_memory(device, kind))
    try:
        transcript_text = await transcribe_for_task(data, filename)
    except SttFailed as e:
        print(f"[stt] task_feedback не распознал: {e}")
        note_failure("stt", str(e))
        raise HTTPException(status_code=502, detail=e.user_message)
    t1 = time.time()
    _track_latency("task_stt", t1 - t0)
    if not transcript_text:
        raise HTTPException(
            status_code=422, detail="Тишина — ничего не распознали. Запиши ответ ещё раз."
        )

    # Говорил долго, а слов пришло всего ничего — это провал РАСПОЗНАВАНИЯ, а не
    # ученика. Ставить ноль за «слишком короткий ответ» здесь было бы ложным
    # обвинением: тестировщик поймал ровно это («пишет, я прочитал только
    # 2 слова, хотя фактически прочитал предложение»).
    if audio_check.recognition_failed(sound, transcript_text):
        mem_task.cancel()
        print(f"[audio] распознавание не справилось: {sound}, "
              f"слов {len(transcript_text.split())}")
        note_failure("stt", "мало слов на длинной записи")
        raise HTTPException(
            status_code=502,
            detail=(f"Не удалось разобрать запись: ты говорил "
                    f"{int(sound.get('seconds') or 0)} секунд, а распознать "
                    "удалось лишь пару слов. Это сбой распознавания, а не твой "
                    "ответ — запиши ещё раз, ближе к микрофону."),
        )

    try:
        payload = json.loads(payload_raw) if payload_raw else {}
    except json.JSONDecodeError:
        payload = {}

    # Санитарный шлюз: мусор («пара абстрактных слов», фраза по кругу) получает
    # честный ноль сразу, без траты вызова LLM и 3-5 секунд ожидания.
    gate_reason = ege_scoring.sanity_gate(kind, transcript_text)
    if gate_reason is not None:
        mem_task.cancel()  # выжимки памяти не понадобятся — не бросаем задачу
        print(f"[gate] разбор не запускался: {gate_reason[:80]}")
        feedback = {
            "summary": f"Оценка 0. {gate_reason.capitalize()}.",
            "score": 0, "max": ege_scoring.MAX_SCORE.get(kind, 1), "errors": [],
        }
        _remember(device, kind, variant, feedback, duration_sec, session_done)
        return {
            "transcript": transcript_text,
            "feedback": feedback,
            "latency": {"stt": round(t1 - t0, 2), "llm": 0.0,
                        "total": round(time.time() - t0, 2)},
        }

    mem = await mem_task
    if mem:
        print(f"[memory] выжимки в промпте разбора: {', '.join(sorted(mem))}")

    prompt, ctx = _feedback_prompt(kind, payload, transcript_text, persona)
    client = llm_client()

    # Чтение вслух: ПАРАЛЛЕЛЬНО с разбором меряем подачу (темп и паузы по
    # пословным таймкодам). Параллельно — чтобы замер на процессоре не
    # прибавлялся к ожиданию ученика. Выключен по умолчанию, см. delivery.py.
    delivery_task = None
    if kind == "reading" and delivery.DELIVERY_ANALYSIS:
        delivery_task = asyncio.create_task(
            asyncio.to_thread(delivery.measure, data,
                              os.path.splitext(filename)[1].lower() or ".mp3"))

    try:
        completion = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": prompt + _memory_prompt_block(mem)},
                    {"role": "user", "content": transcript_text},
                ],
                response_format={"type": "json_object"},
                # Ноль, а не 0.2 (05.08.2026). Выигрыш здесь не в точности —
                # средняя сходимость с экспертами почти не меняется, — а в
                # ВОСПРОИЗВОДИМОСТИ: один и тот же ответ обязан получать один и
                # тот же балл. Замер на шести работах ФИПИ по три прогона:
                # при 0.2 разброс «в пределах ±1» был 2-4 из шести, при нуле
                # сузился до 3-4. Проверяющий, который сегодня ставит 4, а
                # завтра 6 за ту же работу, несправедлив независимо от среднего.
                temperature=0.0,
                # Монологу нужно место: четыре аспекта плюс полный список ошибок,
                # по числу которых считается балл за язык.
                max_tokens=2000 if kind == "monologue" else 900,
            )
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"LLM ошибка ({LLM_MODEL}): {e}")

    _track_llm(completion)
    raw = (completion.choices[0].message.content or "").strip()
    observations = _loads_forgiving(raw)
    if observations is None:
        raise HTTPException(status_code=502, detail=f"LLM вернул не-JSON: {raw[:200]}")

    # ОБРЫВ РАЗБОРА. Модель обязана вернуть пункт на каждый вопрос задания:
    # балл — сумма зачтённых, поэтому недостающий пункт молча становится нулём,
    # и ученик с пятью верными ответами видит 1 из 5 и слово «неправильно».
    # Строгость и обрыв на экране неразличимы, поэтому недобор — это НАША
    # ошибка, а не его: даём модели второй заход, и только он решает исход.
    expected_items = len(ctx.get("points" if kind == "dialogue" else "questions") or [])
    if ege_scoring.missing_items(kind, observations, expected_items):
        lack = ege_scoring.missing_items(kind, observations, expected_items)
        print(f"[{kind}] разбор оборвался: не хватает {lack} пунктов из "
              f"{expected_items} — переспрашиваю модель")
        try:
            retry = await asyncio.to_thread(
                lambda: client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[
                        {"role": "system", "content": prompt + _memory_prompt_block(mem)},
                        {"role": "user", "content": transcript_text},
                        {"role": "assistant", "content": raw[:1500]},
                        {"role": "user", "content":
                         f"Разбор неполный: пунктов должно быть РОВНО "
                         f"{expected_items}, по одному на каждый пункт задания, "
                         f"даже если ответа на какой-то из них в записи нет. "
                         f"Верни JSON целиком заново."},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.0,
                    max_tokens=900,
                )
            )
            _track_llm(retry)
            again = _loads_forgiving((retry.choices[0].message.content or "").strip())
            if again is not None and ege_scoring.missing_items(
                    kind, again, expected_items) < lack:
                observations = again
                print(f"[{kind}] второй заход вернул разбор целиком")
        except Exception as e:  # noqa: BLE001 — второй заход не обязан удаться
            print(f"[{kind}] второй заход не удался ({type(e).__name__})")

        # Не помогло — честный отказ вместо выдуманного низкого балла. Ученик
        # переспросит разбор; ложная двойка стоит доверия ко всей проверке.
        if ege_scoring.missing_items(kind, observations, expected_items):
            raise HTTPException(
                status_code=502,
                detail="Разбор оборвался на середине — балл не выставляем, "
                       "чтобы не занизить его случайно. Нажми «Повторить разбор».")

    # Механическая сверка улик ДО второго прохода: приписана ли ученику фраза,
    # которой он не говорил, и не засчитан ли обрывок вместо ответа. Ничего не
    # решает — только помечает пункты, чтобы старший эксперт посмотрел именно
    # на них. Без сети и без вызова модели (05.08.2026).
    suspicious = ege_scoring.flag_suspicious(kind, observations, transcript_text)
    if suspicious:
        print(f"[verify] улики не сошлись — {'; '.join(suspicious)}")

    # Второй взгляд на спорные пункты — аналог третьей проверки из методички.
    # Запускается ТОЛЬКО когда первый проход сам сомневается, поэтому у
    # обычной работы задержка не растёт вовсе.
    observations = await _recheck_disputed(kind, observations, ctx,
                                           transcript_text, persona, client)
    # У монолога спорны не вердикты по вопросам, а аспекты — свой отбор и свой
    # промпт, но та же цена: один вызов и только когда есть что пересматривать.
    observations = await _recheck_aspects(kind, observations, ctx,
                                          transcript_text, persona, client)

    # Балл считает шкала ФИПИ, а не модель, — см. ege_scoring.py.
    feedback = _score_feedback(kind, observations, ctx)

    # Подача — ДОПОЛНЕНИЕ к разбору, на балл не влияет. «Дочитано ли» берём из
    # детерминированной сверки с эталоном, а не из аудио: код это знает точно.
    if delivery_task is not None:
        measured = await delivery_task
        if measured:
            diff = ctx.get("diff") or {}
            finished = diff.get("tail_missing", 0) <= 2
            feedback["delivery"] = {
                **measured,
                "finished": finished,
                "comment": delivery.comment(measured, finished),
            }

    # В память — после того как ответ готов, мимо критического пути.
    _remember(device, kind, variant, feedback, duration_sec, session_done)

    # Корпус голоса: сама запись + всё, что система о ней решила. Только с
    # согласия ученика и только фоном (см. _collect_corpus_bg).
    _collect_corpus_bg(device, kind, variant, data,
                       _mime_of(filename), float(duration_sec or 0),
                       transcript_text, str((ctx or {}).get("reference") or ""),
                       feedback)

    # Замер произношения — ТОЛЬКО в копилку калибровки и ТОЛЬКО фоном.
    # Ученику сейчас не показывается ничего: порога, отделяющего ошибку от
    # акцента, ещё нет, и придумать его вместо того, чтобы измерить, значило
    # бы повторить старую ошибку с выдуманной точностью.
    if kind == "reading":
        _collect_pron_bg(device, kind, variant, data,
                         os.path.splitext(filename)[1].lower() or ".mp3",
                         str((ctx or {}).get("reference") or ""), method="forced",
                         transcript=transcript_text)
    else:
        # У 40, 41 и 42 эталона НЕТ: ученик говорит своими словами. Сверяем
        # звук с расшифровкой Mistral — это другой, более слабый показатель,
        # и в копилке он лежит отдельно.
        _collect_pron_bg(device, kind, variant, data,
                         os.path.splitext(filename)[1].lower() or ".mp3",
                         transcript_text, method="cross")

    t2 = time.time()
    _track_latency("task_llm", t2 - t1)
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
    # Собеседник: меняет строгость спорных решений и голос разбора, не шкалу.
    persona: str = Form(""),
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
                                bool(session_done), audio.filename or "speech.webm",
                                persona)
        ),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


# Глубина памяти диалога. Было 10 реплик по 300 символов — пять обменов, и
# длинный ответ ученика резался на полуслове: собеседник не помнил, о чём
# говорили три минуты назад, и переспрашивал уже отвеченное.
#
# Стало 16 реплик (восемь обменов), но с УБЫВАЮЩЕЙ подробностью: последние
# шесть едут целиком, что старше — сжато до сути. Так сделано после замера
# (04.08.2026): 16 реплик по 500 символов подняли цену одной реплики с ~950 до
# 1846 токенов, а лимит ключа — 50000 токенов в минуту. То есть потолок
# системы падал с ~50 до 26 реплик в минуту ради подробностей десятиминутной
# давности, которые собеседнику нужны только как «о чём вообще шла речь».
#
# Ограничитель здесь именно ТОКЕНЫ, не бюджет: месячный бюджет считает ЗАПРОСЫ,
# и длина истории на него не влияет вовсе.
_HISTORY_TURNS = 16
_HISTORY_CHARS = 500
# Сколько последних реплик сохраняют полную длину. Шесть — три обмена: ровно
# то, на что собеседник отвечает содержательно.
_HISTORY_FULL = 6
_HISTORY_CHARS_OLD = 200


def _sanitize_history(raw: str, turns: int = _HISTORY_TURNS,
                      chars: int = _HISTORY_CHARS,
                      full: int = _HISTORY_FULL,
                      chars_old: int = _HISTORY_CHARS_OLD) -> list[dict]:
    """История диалога от клиента — последние реплики сессии.

    Память диалога НАМЕРЕННО клиентская: живёт в вкладке браузера и приходит с
    каждым запросом. Серверу это даёт ноль состояния и ноль хранения (мы решили
    не хранить транскрипты речи), а истории — естественную смерть вместе со
    вкладкой.

    Клиенту, впрочем, не верим: лимит реплик, роли только user/assistant,
    каждая обрезается по длине — иначе curl мог бы затолкать в промпт роман и
    оплатить его нашим ключом.
    """
    try:
        items = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    out = []
    for it in items[-turns:]:
        if not isinstance(it, dict):
            continue
        role = it.get("role")
        content = str(it.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        out.append({"role": role, "content": content})
    # Обрезка — ПОСЛЕ отбора и по расстоянию от конца: свежее целиком, старое
    # сжато. Считать позицию до фильтрации нельзя — мусорные записи сдвинули бы
    # границу и обрезали бы свежую реплику как древнюю.
    for i, m in enumerate(out):
        limit = chars if i >= len(out) - full else chars_old
        m["content"] = m["content"][:limit]
    return out


@app.post("/talk_stream")
async def talk_stream(audio: UploadFile = File(...),
                      history: str = Form("[]"),
                      persona: str = Form(""),
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
    who = persona_of(persona)

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
            note_failure("stt", str(e))
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

        _track_latency("conv_stt", t1 - t0)
        # Расшифровку отдаём сразу — фронт покажет «Ты сказал…», пока стримится ответ.
        yield json.dumps({"user": user_text}) + "\n"

        # 2) LLM стримингом → 3) пофразный TTS
        client = async_llm_client()
        reply_full = ""
        buf = ""
        first_audio_at = None
        # Ушло ли ученику хоть одно ОЗВУЧЕННОЕ предложение. Именно это, а не
        # «пришёл ли хоть один токен», решает, можно ли повторить запрос:
        # токены, не сложившиеся в предложение, до ученика не доехали и
        # проиграться дважды не могут.
        emitted = False

        async def emit(sentence: str):
            nonlocal first_audio_at, emitted
            t_tts = time.time()
            try:
                wav = await synthesize(sentence, who)
            except Exception as e:  # noqa: BLE001
                raise TtsFailed(str(e)) from e
            if first_audio_at is None:
                first_audio_at = time.time()
                # Синтез ПЕРВОГО куска — самая крупная доля паузы (замер
                # 05.08.2026: ~1.3 из 2.9 с). Меряем отдельно: без разложения
                # по этапам любое «ускорение» будет угадыванием.
                _track_latency("conv_tts", first_audio_at - t_tts)
            emitted = True
            return json.dumps({"text": sentence, "audio_b64": base64.b64encode(wav).decode()}) + "\n"

        # Личная выжимка делает тьютора внимательнее к повторяющимся ошибкам
        # именно этого ученика. Правило «одна короткая поправка за реплику»
        # сохраняется — оно уже в SYSTEM_PROMPT.
        mem = await mem_task
        # Характер персоны дописывается ПОСЛЕ базовых правил: правила формата
        # (без markdown, вопрос в конце) и ремесло собеседника должны пережить
        # любой характер, иначе сломается озвучка или сам разговор.
        sys_prompt = SYSTEM_PROMPT + (f"\n\n{who['prompt']}" if who.get("prompt") else "")

        # Память ДИАЛОГА: последние реплики сессии между system и текущей фразой.
        # Тьютор помнит, о чём шла речь, и перестаёт отвечать с чистого листа.
        past = _sanitize_history(history)
        if past:
            print(f"[dialog] история: {len(past)} реплик")

        # Ход беседы: чья это тема, как читать собеседника и на какой глубине
        # сейчас разговор. Глубина считается ЗДЕСЬ, из длины истории — без
        # отдельного вопроса к модели «насколько мы углубились»: это был бы
        # второй запрос на каждую реплику, то есть удвоение расхода ради
        # арифметики. Идёт до блока памяти: это рабочая инструкция, а память
        # объявлена «вторичной ко всему выше» и не должна перебивать её собой.
        exchanges = len(past) // 2
        sys_prompt += "\n" + dialogue.flow_block(exchanges)
        # Обучающий ход — раз в несколько обменов, такт считает СЕРВЕР
        # (запрос владельца 16.08.2026: «не только просто болтать»).
        teach = dialogue.teach_block(exchanges)
        if teach:
            sys_prompt += teach
        print(f"[dialog] обмен {exchanges + 1}, "
              f"ступень {dialogue.rung_index(exchanges) + 1}"
              + (", обучающий ход" if teach else ""))

        # Градус противостояния — только у жёсткой персоны. Считается по мату в
        # репликах ученика, включая текущую: ответ на брань должен прийти
        # СРАЗУ, а не со следующего хода.
        said = [m["content"] for m in past if m["role"] == "user"] + [user_text]
        heat = heat_block(who, said)
        if heat:
            sys_prompt += heat
            print(f"[dialog] градус {heat_level(said)}/{MAX_HEAT}")

        if mem.get("user"):
            sys_prompt += (
                "\n\nBackground context, secondary to everything above — memory about "
                f"this student: {mem['user']}\n"
                "Use it ONLY if one of these mistakes appears again in the current "
                "utterance — then gently point it out (still at most one short tip). "
                "Never bring up old mistakes on their own, and never let this memory "
                "change the topic of the conversation.\n"
                # Поймано живым прогоном 04.08.2026: собеседник превратил выжимку
                # в выдуманное воспоминание — «I remember you said you like watching
                # films with subtitles», чего ученик не говорил никогда. Выдуманная
                # общая память хуже её отсутствия: человек перестаёт верить всему
                # остальному, что помнит собеседник.
                "This memory is NOT part of your conversation and the student never "
                "told you any of it. Never say 'I remember you said', never quote it "
                "back, never treat it as something that happened between you. The "
                "only things the student has told you are in the messages above."
            )
            print("[memory] профиль ученика подключён к разговору")

        # Память ПРОШЛОЙ БЕСЕДЫ — правило противоположное профилю ошибок:
        # это действительно было между вами (выжимка вашего же прошлого
        # разговора, записана его разбором), и сослаться на неё — то, что
        # делает собеседника человеком, а не автоответчиком. Но тема
        # сегодняшнего разговора всё равно принадлежит ученику.
        if mem.get("talk") and not past:
            # Только в ПЕРВОЙ реплике сессии: дальше жива собственная история
            # разговора, и прошлое уже не нужно — токены дороже ностальгии.
            sys_prompt += (
                "\n\nYOUR LAST CONVERSATION with this student, one line from "
                f"your previous session together: {mem['talk']}\n"
                "This DID happen between you two. If they open with just a "
                "greeting or no subject of their own, FOLLOW UP on it — one "
                "concrete question ('how did that match go?') beats inventing "
                "a fresh observation: it shows you remember them. The moment "
                "they bring anything up, today's topic is theirs — drop the "
                "past and never drag them back to it."
            )
            print("[memory] прошлый разговор подключён")

        # Ретрай LLM (03.08.2026): на домашнем канале 2 запроса из 5 рвались с
        # пустой ошибкой, и ученик молча терял свой ход. Повторяем ТОЛЬКО пока
        # ученику не уехало ни одного ОЗВУЧЕННОГО предложения: после первого
        # повтор проиграл бы начало ответа дважды — тогда честнее отдать ошибку.
        #
        # Условие уточнено 04.08.2026 после сквозного прогона: раньше повтор
        # запрещался, как только приходил первый ТОКЕН. Обрыв в середине
        # генерации (канал рвал соединение через 30 с, обычное дело из РФ)
        # оставлял огрызок фразы, который не сложился в предложение и до
        # ученика не доехал, — но повтор уже считался небезопасным, и человек
        # получал «LLM ошибка» на ровном месте. Ловилось стабильно, на второй
        # реплике каждого прогона.
        _LLM_ATTEMPTS = 3
        for attempt in range(_LLM_ATTEMPTS):
            try:
                # Повтор начинает ответ с чистого листа: недописанный огрызок
                # прошлой попытки иначе склеился бы с новым текстом.
                if attempt:
                    reply_full, buf = "", ""
                stream = await client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        *past,
                        {"role": "user", "content": user_text},
                    ],
                    max_tokens=reply_tokens(who),
                    stream=True,
                )
                stream_usage = None
                head_done = False
                t_ask = time.time()
                async for chunk in stream:
                    # usage приезжает в последнем чанке стрима (если провайдер
                    # его шлёт) — запоминаем для счётчика расхода.
                    if getattr(chunk, "usage", None) is not None:
                        stream_usage = chunk.usage
                    delta = (chunk.choices[0].delta.content or "") if chunk.choices else ""
                    if not delta:
                        continue
                    if not reply_full:
                        # Ожидание первого токена: сеть + очередь + префилл
                        # промпта. Отделено от генерации намеренно — лечатся
                        # они разным, и путать их значит чинить не то.
                        _track_latency("conv_ttft", time.time() - t_ask)
                    buf += delta
                    reply_full += delta
                    if not head_done:
                        head, rest = _take_head(buf)
                        if head:
                            buf = rest
                            head_done = True
                            yield await emit(head)
                # ХВОСТ — одним куском, а не по предложениям: в этом вся суть
                # правки (см. _take_head). Пока голова звучит, хвост успевает
                # синтезироваться, и стык остаётся незаметным.
                tail = buf.strip()
                if tail:
                    yield await emit(tail)
                # Учёт расхода: точно из usage, а если стрим его не отдал —
                # оценкой по символам (~4 на токен): бюджету хватает ±20%.
                if stream_usage is not None:
                    _track_usage(llm_req=1,
                                 llm_prompt_tokens=getattr(stream_usage, "prompt_tokens", 0) or 0,
                                 llm_completion_tokens=getattr(stream_usage, "completion_tokens", 0) or 0)
                else:
                    approx_prompt = (len(sys_prompt) + sum(len(p["content"]) for p in past)
                                     + len(user_text)) // 4
                    _track_usage(llm_req=1, llm_prompt_tokens=approx_prompt,
                                 llm_completion_tokens=max(1, len(reply_full) // 4))
                break  # ответ дошёл целиком
            except TtsFailed as e:
                # У TTS свой запасной путь (edge -> Mistral); если не спас и он,
                # повтор LLM не поможет — часть ответа уже могла прозвучать.
                yield json.dumps({"error": f"TTS (edge-tts) ошибка: {e}"}) + "\n"
                return
            except Exception as e:  # noqa: BLE001
                can_retry = not emitted and attempt + 1 < _LLM_ATTEMPTS
                print(f"[llm] стрим сорвался (попытка {attempt + 1}/{_LLM_ATTEMPTS}, "
                      f"{type(e).__name__}: {str(e)[:80]}) — "
                      + ("повторяю" if can_retry else "отдаю ошибку"))
                if not can_retry:
                    note_failure("llm", f"{type(e).__name__}: {str(e)[:80]}")
                    yield json.dumps({"error": f"LLM ошибка ({LLM_MODEL}): {e}"}) + "\n"
                    return
                await asyncio.sleep(1.0 * (attempt + 1))

        # Реплика состоялась целиком — только теперь она считается занятием
        # (стрик + XP). Оборванные и ошибочные ходы в статистику не попадают.
        _note_reply_bg(x_device)

        # Замер произношения в разговоре — КАЖДАЯ N-я реплика, а не все.
        # Реплик за сессию десятки, и мерить каждую на 0.1 vCPU значило бы
        # отнимать процессор у живых ответов. Эталона тут нет вовсе, поэтому
        # способ «cross»: сверяем звук с тем, что услышал Mistral.
        global _pron_talk_seen
        _pron_talk_seen += 1
        if PRON_TALK_EVERY > 0 and _pron_talk_seen % PRON_TALK_EVERY == 0:
            _collect_pron_bg(x_device, "talk", "", data, ".webm",
                             user_text, method="cross")

        # Корпус берёт реплику разговора по своим правилам, а не по расписанию
        # замера произношения: у него другие потолки (место, квота на ученика),
        # и привязывать их друг к другу значит терять записи без причины.
        _collect_corpus_bg(x_device, "talk", "", data, "audio/webm",
                           float(len(data) / 16000.0), user_text, "", {})

        t2 = time.time()
        _track_latency("conv_answer", (first_audio_at or t2) - t0)
        # first_audio — ОТ ПРИХОДА ЗАПРОСА, а не от конца распознавания.
        # Старая метрика (от t1) показывала красивые 0.9с там, где ученик ждал
        # 2.3с, и по ней принимались решения о скорости. Сеть и загрузка файла
        # сюда всё равно не входят — это честный минимум ожидания, что виден
        # серверу; фронт больше не складывает её со stt.
        yield json.dumps(
            {"done": True, "user": user_text, "reply": reply_full.strip(),
             "latency": {"stt": round(t1 - t0, 2),
                         "first_audio": round((first_audio_at or t2) - t0, 2),
                         "total": round(t2 - t0, 2)}}
        ) + "\n"

    return StreamingResponse(
        gen(),
        # text/event-stream, а не application/x-ndjson — см. объяснение у /monologue:
        # на этот тип прокси отключают буферизацию, фронту заголовок безразличен.
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


# Серверный вариант задания фронт зовёт «39-x<8 знаков uuid>», встроенный —
# «39-1». Ловим только первый: у второго текста на сервере нет.
_REMOTE_VARIANT_RE = re.compile(r"^\d{2}-x([0-9a-fA-F]{6,32})$")


async def _check_word_against_task(text: str, variant: str) -> None:
    """Слово обязано быть в тексте задания — если этот текст у нас есть.

    Три исхода, и молчаливый пропуск среди них законный:
      * вариант серверный и слово в его эталоне — тихо пропускаем;
      * вариант серверный, а слова в эталоне нет — 422, озвучивать нечего;
      * вариант встроенный или база молчит — ПРОПУСКАЕМ, сверять не с чем.

    Третий случай — честная граница, а не дыра, оставленная по лени: текст
    встроенных вариантов живёт только в коде фронта, дублировать его на
    сервере ради этой проверки дороже, чем она стоит. От свободного синтеза
    там защищает форма запроса (`speak_check.word_problem`).
    """
    m = _REMOTE_VARIANT_RE.match(str(variant or "").strip())
    if not m or not _storage_ok:
        return
    try:
        task = await asyncio.to_thread(storage.task_active_by_prefix, m.group(1))
    except Exception as e:  # noqa: BLE001
        # База отвалилась — это НЕ повод обвинять ученика в подлоге.
        print(f"[speak] сверка с эталоном не удалась ({type(e).__name__}) — пропускаю")
        return
    if not task or task.get("kind") != "reading":
        return
    try:
        payload = json.loads(task.get("payload") or "{}")
    except (json.JSONDecodeError, TypeError):
        return
    reference = str(payload.get("readText") or "")
    missing = speak_check.missing_from(text, reference)
    if missing:
        print(f"[speak] слово вне эталона задания {task['id'][:8]}: {missing}")
        raise HTTPException(
            status_code=422,
            detail="Этого слова нет в тексте задания — озвучиваю только его слова.")


@app.post("/speak")
async def speak(request: Request, body: dict = Body(...),
                x_device: str | None = Header(None),
                x_admin_key: str | None = Header(None)):
    """Озвучить готовый текст. Два режима, и у них разные правила.

    **Вопросы интервью (№41), режим по умолчанию.** По формату ЕГЭ вопросы
    интервьюера ЗВУЧАТ, а не показываются: экзаменуемый воспринимает их на
    слух. Мы показывали их текстом — это меняло само задание, потому что
    убирало аудирование (замечание тестировщика 05.08.2026).

    **Слово из эталона (№39), `mode="word"`.** В разборе чтения ученику
    показывают слово, которое он прочитал не так, — и до 21.08.2026 экран не
    отвечал на главный вопрос: «а как надо?». Теперь отвечает голосом.

    Что здесь проверяется, а что нет, — `speak_check`. Коротко: форму запроса
    проверяем ВСЕГДА, сверку с текстом задания — только когда вариант лежит в
    базе. Встроенные варианты фронта серверу неизвестны, и это не оговорка, а
    признание границы (прежний докстринг обещал проверку, которой в коде не
    было вовсе).

    Своего вызова LLM здесь нет ни в одном режиме — только синтез.
    """
    await _require_account(x_device, x_admin_key)
    if not _rate_ok(f"say:{x_device or _client_ip(request)}", 40, 60.0):
        raise HTTPException(status_code=429, detail="Слишком часто — подожди минутку.")
    text = str(body.get("text") or "").strip()[:400]
    if not text:
        raise HTTPException(status_code=422, detail="Нечего озвучивать.")

    word_mode = str(body.get("mode") or "").strip() == "word"
    if word_mode:
        problem = speak_check.word_problem(text)
        if problem:
            raise HTTPException(status_code=422, detail=problem)
        await _check_word_against_task(text, str(body.get("variant") or ""))

    # Образец произношения говорит НЕЙТРАЛЬНЫМ голосом, а не голосом персоны.
    # Замер 21.08.2026: одно и то же слово у cheerful тянется 2.2 с с игровой
    # интонацией, у neutral — 0.8 с ровно. Ученику здесь нужен эталон, а не
    # характер; злиться на слово «observed» тем более незачем.
    who = persona_of(str(body.get("persona") or ""))
    if word_mode:
        who = {**who, "emotion": DEFAULT_EMOTION}
    try:
        audio = await synthesize(text, who)
    except Exception as e:  # noqa: BLE001
        note_failure("tts", f"{type(e).__name__}: {str(e)[:80]}")
        raise HTTPException(status_code=502, detail=f"Озвучка не удалась: {e}")
    # Слово из эталона кэшируется НАДОЛГО: оно не меняется никогда, а ученик
    # жмёт «послушать» по многу раз подряд. Вопросы интервью — no-store, как
    # было: они звучат один раз за попытку, и кэш там только мешал бы.
    cache = "public, max-age=604800, immutable" if word_mode else "no-store"
    return Response(content=audio, media_type="audio/mpeg",
                    headers={"Cache-Control": cache})


@app.post("/talk_review")
async def talk_review_endpoint(request: Request, body: dict = Body(...),
                               x_device: str | None = Header(None),
                               x_admin_key: str | None = Header(None)):
    """Разбор всей беседы — ОДИН вызов LLM по явному нажатию ученика.

    Почему не автоматически при уходе с экрана: разбор стоит запроса, а уход с
    экрана случается и случайно. Пусть человек сам решает, закончил он или нет.

    Почему история приезжает с клиента: она и так там живёт (сервер диалоги не
    хранит — приватность). В базу из разбора попадают только ОШИБКИ, как и у
    заданий, — они и есть память, которая делает следующие разборы точнее.
    """
    await _require_account(x_device, x_admin_key)
    # Разбор — редкое действие: один на сессию. Лимит ловит зациклившийся
    # клиент и скрипт, живому ученику не мешает.
    if not _rate_ok(f"rv:{x_device or _client_ip(request)}", 6, 300.0):
        raise HTTPException(status_code=429,
                            detail="Слишком часто — подожди пару минут.")
    # Дневной счётчик голоса разбор НЕ тратит: он не реплика, а итог занятия,
    # и отнимать за него право говорить было бы наказанием за прилежание.
    # Полный стоп по месячному бюджету — соблюдаем, как везде.
    if _budget_state().get("mode") == "empty":
        raise HTTPException(
            status_code=429,
            detail="Месячный запас занятий исчерпан — он обновится 1 числа.")

    # Здесь, в отличие от разговора, история НЕ сжимается по давности: разбор
    # ищет ошибки, а ошибка в обрезанном хвосте реплики просто не найдётся.
    # Один вызов на сессию это себе позволяет.
    history = _sanitize_history(json.dumps(body.get("history") or []),
                                turns=48, chars=400, full=48)
    exchanges = sum(1 for m in history if m["role"] == "user")
    if exchanges < talk_review.MIN_EXCHANGES:
        raise HTTPException(
            status_code=422,
            detail=f"Слишком короткий разговор для разбора — скажи хотя бы "
                   f"{talk_review.MIN_EXCHANGES} реплики.")

    who = persona_of(str(body.get("persona") or ""))
    # Тема беседы в разбор НЕ едет: она сбивала модель с расшифровки на
    # название — см. объяснение в talk_review.build_prompt.
    prompt = talk_review.build_prompt(str(who.get("review_tone") or ""))

    client = llm_client()
    t0 = time.time()
    try:
        completion = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": talk_review.transcript_of(history)},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=900,
            )
        )
    except Exception as e:  # noqa: BLE001
        note_failure("llm", f"{type(e).__name__}: {str(e)[:80]}")
        raise HTTPException(status_code=502, detail=f"LLM ошибка ({LLM_MODEL}): {e}")

    _track_llm(completion)
    _track_latency("talk_review", time.time() - t0)
    raw = (completion.choices[0].message.content or "").strip()
    parsed = _loads_forgiving(raw)
    if parsed is None:
        raise HTTPException(status_code=502, detail=f"LLM вернул не-JSON: {raw[:200]}")

    # Сверка цитат с речью ученика: всё, чего он не говорил, выбрасывается.
    review = talk_review.verify(parsed, history)

    # Ошибки — в копилку памяти (фоном: ученик ответа не ждёт). Разговор баллом
    # не оценивается, поэтому строки в results не появляется — только mistakes.
    if _storage_ok and x_device and review["mistakes"]:
        errors = [{"quote": m["quote"], "correction": m["correction"],
                   "explanation": m["why"]} for m in review["mistakes"]]

        async def _remember_talk():
            try:
                await asyncio.to_thread(storage.save_talk_mistakes, x_device, errors)
            except Exception as e:  # noqa: BLE001
                print(f"[memory] разговорные ошибки не записал ({type(e).__name__})")

        asyncio.create_task(_remember_talk())

    # Память беседы для СЛЕДУЮЩЕГО разговора: темы и интересы, без дословной
    # речи. Пишется только отсюда — то есть только когда ученик сам нажал
    # «Разбор»; сессия без разбора памяти не оставляет (и лишнего вызова LLM
    # ради неё нет: поле едет в том же ответе, что и весь разбор).
    if _storage_ok and x_device and review.get("memory"):

        async def _remember_gist():
            try:
                await asyncio.to_thread(
                    storage.talk_memory_set, x_device, review["memory"])
            except Exception as e:  # noqa: BLE001
                print(f"[memory] выжимку беседы не записал ({type(e).__name__})")

        asyncio.create_task(_remember_gist())

    return review


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
