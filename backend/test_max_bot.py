# -*- coding: utf-8 -*-
"""Бот GoSpeak в MAX (22.09.2026): разбор обновлений, секрет вебхука,
приветствие с кнопкой мини-приложения и сам эндпоинт /max/webhook.

Запуск: .\\.venv\\Scripts\\python.exe test_max_bot.py
Сети не требует: отправка в MAX подменяется заглушкой.
"""
from __future__ import annotations

import asyncio
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import max_bot  # noqa: E402

failed = 0


def check(cond: bool, name: str, detail: str = "") -> None:
    global failed
    if cond:
        print(f"OK   {name}")
    else:
        failed += 1
        print(f"FAIL {name}: {detail}")


TOKEN = "test-token"
SECRET = max_bot.webhook_secret(TOKEN)

check(5 <= len(SECRET) <= 256 and all(c in "0123456789abcdef" for c in SECRET),
      "секрет вебхука — hex допустимой длины", SECRET)
check(SECRET != max_bot.webhook_secret("other"), "секрет зависит от токена")
check(max_bot.secret_ok(SECRET, TOKEN) and not max_bot.secret_ok("x" * 48, TOKEN)
      and not max_bot.secret_ok(None, TOKEN) and not max_bot.secret_ok(SECRET, ""),
      "проверка секрета: свой проходит, чужой и пустой — нет")

started = {"update_type": "bot_started", "timestamp": 1, "chat_id": 77,
           "user": {"user_id": 5, "first_name": "Аня", "is_bot": False}, "payload": "ref"}
p = max_bot.parse_update(started)
check(p == {"kind": "bot_started", "user_id": 5, "chat_id": 77, "text": "", "payload": "ref"},
      "bot_started разбирается", str(p))

msg = {"update_type": "message_created", "timestamp": 1, "message": {
    "sender": {"user_id": 5, "is_bot": False},
    "recipient": {"chat_id": 77, "chat_type": "dialog", "user_id": None, "post_id": None},
    "body": {"mid": "m1", "seq": 1, "text": "/start"}}}
p = max_bot.parse_update(msg)
check(p is not None and p["kind"] == "message_created" and p["user_id"] == 5
      and p["chat_id"] == 77 and p["text"] == "/start", "message_created разбирается", str(p))

own = {"update_type": "message_created", "timestamp": 1, "message": {
    "sender": {"user_id": 1, "is_bot": True}, "recipient": {"chat_id": 77}, "body": {"text": "x"}}}
check(max_bot.parse_update(own) is None, "своё сообщение бот не разбирает")
check(max_bot.parse_update({"update_type": "dialog_muted", "chat_id": 1}) is None,
      "служебные события пропускаются")
check(max_bot.parse_update("junk") is None, "мусор вместо словаря — None")

w = max_bot.welcome_message("https://example.test/", "gospeak_bot", bot_id=42)
rows = w["attachments"][0]["payload"]["buttons"]
check(w["attachments"][0]["type"] == "inline_keyboard" and rows[0][0]["type"] == "open_app"
      and rows[0][0]["web_app"] == "gospeak_bot" and rows[0][0]["contact_id"] == 42
      and rows[1][0]["type"] == "link"
      and rows[1][0]["url"] == "https://example.test/",
      "приветствие: open_app с именем БОТА (не адресом сайта) и запасная ссылка", str(rows))
check([b["type"] for r in max_bot.welcome_message("https://example.test/")["attachments"][0]["payload"]["buttons"] for b in r] == ["link"],
      "без имени бота open_app не собирается — только ссылка")
w2 = max_bot.welcome_message("https://example.test/", "gospeak_bot", with_open_app=False)
check([b["type"] for r in w2["attachments"][0]["payload"]["buttons"] for b in r] == ["link"],
      "без open_app остаётся только ссылка")
check(all(c["name"] for c in max_bot.commands()), "команды непустые")
w3 = max_bot.welcome_message("https://example.test/", "gospeak_bot", with_open_app=False,
                             login_url="https://example.test/#mlogin=v1.5.1.x")
b3 = [b for r in w3["attachments"][0]["payload"]["buttons"] for b in r]
check(len(b3) == 1 and b3[0]["type"] == "link" and b3[0]["text"] == "Открыть тренажёр"
      and b3[0]["url"].endswith("#mlogin=v1.5.1.x") and "личная" in w3["text"],
      "без мини-приложения главная кнопка — личная ссылка со входом", str(b3))

# ------------------------------------------------------------ эндпоинт

os.environ["MAX_BOT_TOKEN"] = TOKEN
os.environ["MAX_MINIAPP_READY"] = "0"  # без привязки — личная ссылка (§6.51)
import main  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from starlette.requests import Request  # noqa: E402

sent: list[tuple] = []


async def fake_send(user_id, chat_id, body, fallback=None):  # noqa: ANN001
    sent.append((user_id, chat_id, body))
    return True


main._max_send = fake_send  # type: ignore[attr-defined]
main._MAX_BOT_NAME = "gospeak_bot"  # без сети: /me не спрашивается
main._MAX_BOT_ID = 42


def req(secret: str | None) -> Request:
    headers = [(b"x-max-bot-api-secret", secret.encode())] if secret else []
    return Request({"type": "http", "method": "POST", "path": "/max/webhook", "query_string": b"",
                    "headers": headers, "client": ("10.0.0.1", 1)})


async def run(secret, body):  # noqa: ANN001
    res = await main.max_webhook(req(secret), body)
    # ответ уходит фоном — даём задачам выполниться
    await asyncio.sleep(0.05)
    return res


async def scenario():
    global failed
    try:
        await run("wrong", started)
        check(False, "чужой секрет отвергается")
    except HTTPException as e:
        check(e.status_code == 403, "чужой секрет отвергается", str(e.status_code))
    try:
        await run(None, started)
        check(False, "без секрета — отказ")
    except HTTPException as e:
        check(e.status_code == 403, "без секрета — отказ", str(e.status_code))

    sent.clear()
    r = await run(SECRET, started)
    check(r == {"ok": True} and len(sent) == 1 and sent[0][0] == 5,
          "bot_started → приветствие пользователю", str(sent))
    body = sent[0][2]
    first = body["attachments"][0]["payload"]["buttons"][0][0]
    check("GoSpeak" in body["text"] and first["type"] == "link" and "#mlogin=" in first["url"],
          "в приветствии — личная кнопка входа (мини-приложение к боту ещё не привязано)", str(body)[:200])

    sent.clear()
    await run(SECRET, msg)
    check(len(sent) == 1, "/start текстом → приветствие", str(sent))
    import max_auth as _ma
    btns = [b for r in sent[0][2]["attachments"][0]["payload"]["buttons"] for b in r]
    url = btns[0].get("url", "")
    tok = url.split("#mlogin=", 1)[1] if "#mlogin=" in url else ""
    check(btns[0]["type"] == "link" and _ma.verify_link(tok, TOKEN)["user_id"] == 5,
          "в приветствии личная ссылка на того, кто написал", str(btns))
    os.environ["MAX_MINIAPP_READY"] = "1"
    sent.clear()
    await run(SECRET, msg)
    kinds = [b["type"] for r in sent[0][2]["attachments"][0]["payload"]["buttons"] for b in r]
    check(kinds == ["open_app", "link"], "MAX_MINIAPP_READY=1: кнопка мини-приложения и ссылка", str(kinds))
    os.environ["MAX_MINIAPP_READY"] = ""  # авто: после входа по подписи
    main._MAX_APP_READY["val"] = True
    sent.clear()
    await run(SECRET, msg)
    kinds = [b["type"] for r in sent[0][2]["attachments"][0]["payload"]["buttons"] for b in r]
    check(kinds == ["open_app", "link"], "после входа по подписи кнопка включается сама", str(kinds))
    main._MAX_APP_READY["val"] = False
    os.environ["MAX_MINIAPP_READY"] = "0"
    sent.clear()

    sent.clear()
    await run(SECRET, own)
    check(sent == [], "на своё сообщение бот не отвечает")

    sent.clear()
    await run(SECRET, {"update_type": "user_added", "chat_id": 1})
    check(sent == [], "на служебное событие не отвечает")

    saved = os.environ.pop("MAX_BOT_TOKEN")
    try:
        await run(SECRET, started)
        check(False, "без токена на сервере — 503")
    except HTTPException as e:
        check(e.status_code == 503, "без токена на сервере — 503", str(e.status_code))
    os.environ["MAX_BOT_TOKEN"] = saved


asyncio.run(scenario())

print()
print("ВСЁ ЗЕЛЁНОЕ" if not failed else f"ПРОВАЛОВ: {failed}")
sys.exit(1 if failed else 0)
