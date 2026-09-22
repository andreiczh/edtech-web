"""Бот GoSpeak в MAX: разбор обновлений вебхука и сборка ответов.

Модуль без ввода-вывода — только словари. Отправляет и принимает main.py
(эндпоинт POST /max/webhook и httpx к https://botapi.max.ru), подписку на
вебхук ставит backend/max_subscribe.py.

Что делает бот (минимум для допуска на хакатон): на /start и любое
сообщение отвечает приветствием с кнопкой, открывающей мини-приложение.
Кнопка `open_app` — родная кнопка MAX для мини-приложений; рядом `link`
на тот же адрес — запасной вход, если клиент кнопку не покажет.

Форматы — из официального клиента @maxhub/max-bot-api 0.3.1:
  update_type 'bot_started'      {chat_id, user{user_id,...}, payload}
  update_type 'message_created'  {message{sender{user_id}, recipient{chat_id,user_id}, body{text}}}
  update_type 'message_callback' {callback{callback_id, payload, user}, message}
  POST /messages?user_id=… | ?chat_id=…   {text, attachments:[inline_keyboard]}
"""
from __future__ import annotations

import hashlib
import hmac

API_BASE = "https://botapi.max.ru"

# Обновления, на которые подписываемся: старт диалога, сообщения и нажатия.
UPDATE_TYPES = ["bot_started", "message_created", "message_callback"]

WELCOME = (
    "Привет! Это GoSpeak — голосовой тренажёр устной части ЕГЭ по английскому.\n\n"
    "Открой тренажёр, прочитай текст вслух — и получи разбор по критериям ФИПИ "
    "с подсветкой ошибок. Всё внутри MAX, ничего ставить не нужно."
)


def webhook_secret(bot_token: str) -> str:
    """Секрет вебхука выводится из токена бота, а не хранится отдельно:
    одной переменной окружения меньше, а подделать его без токена нельзя.
    MAX принимает 5–256 знаков из A-Z a-z 0-9 и дефиса — hex подходит."""
    return hashlib.sha256(f"gospeak-webhook:{bot_token}".encode()).hexdigest()[:48]


def secret_ok(header_value: str | None, bot_token: str) -> bool:
    if not header_value or not bot_token:
        return False
    return hmac.compare_digest(header_value.strip(), webhook_secret(bot_token))


def parse_update(update: dict) -> dict | None:
    """Кому и на что отвечать. None — обновление нам не интересно
    (сообщение от самого бота, служебные события)."""
    if not isinstance(update, dict):
        return None
    kind = str(update.get("update_type") or "")
    if kind == "bot_started":
        user = update.get("user") or {}
        return {"kind": kind, "user_id": user.get("user_id"), "chat_id": update.get("chat_id"),
                "text": "", "payload": update.get("payload")}
    if kind == "message_created":
        msg = update.get("message") or {}
        sender = msg.get("sender") or {}
        if sender.get("is_bot"):
            return None
        rec = msg.get("recipient") or {}
        body = msg.get("body") or {}
        return {"kind": kind, "user_id": sender.get("user_id"), "chat_id": rec.get("chat_id"),
                "text": str(body.get("text") or ""), "payload": None}
    if kind == "message_callback":
        cb = update.get("callback") or {}
        user = cb.get("user") or {}
        msg = update.get("message") or {}
        rec = msg.get("recipient") or {}
        return {"kind": kind, "user_id": user.get("user_id"), "chat_id": rec.get("chat_id"),
                "text": "", "payload": cb.get("payload"), "callback_id": cb.get("callback_id")}
    return None


def welcome_message(app_url: str, bot_name: str = "", with_open_app: bool = True) -> dict:
    """Тело POST /messages: приветствие и клавиатура с кнопкой мини-приложения.

    `web_app` у кнопки open_app — по схеме MAX это username (или ссылка) БОТА,
    чьё мини-приложение открыть, а не адрес сайта: адрес мини-приложения
    владелец бота задаёт в партнёрской платформе (business.max.ru → Чат-боты →
    бот → Настройки). До 23.09.2026 сюда уходил адрес сайта — и тестировщик
    получал не мини-приложение, а веб-ссылку. Без имени бота кнопки нет:
    остаётся запасная ссылка в браузер."""
    rows: list[list[dict]] = []
    if with_open_app and bot_name:
        rows.append([{"type": "open_app", "text": "Открыть тренажёр", "web_app": bot_name}])
    rows.append([{"type": "link", "text": "Открыть в браузере", "url": app_url}])
    return {
        "text": WELCOME,
        "attachments": [{"type": "inline_keyboard", "payload": {"buttons": rows}}],
    }


def commands() -> list[dict]:
    """Список команд бота (PATCH /me/commands) — то, что клиент показывает в меню."""
    return [
        {"name": "start", "description": "Открыть тренажёр"},
        {"name": "help", "description": "Что умеет GoSpeak"},
    ]
