# -*- coding: utf-8 -*-
"""Подписка бота GoSpeak на вебхук MAX и настройка команд.

Запускается один раз с ноутбука, токен берётся из backend/.env
(MAX_BOT_TOKEN) — в командную строку и в вывод он не попадает.

  .\\.venv\\Scripts\\python.exe max_subscribe.py            # подписать прод
  .\\.venv\\Scripts\\python.exe max_subscribe.py --list     # что подписано сейчас
  .\\.venv\\Scripts\\python.exe max_subscribe.py --delete   # снять подписку
  .\\.venv\\Scripts\\python.exe max_subscribe.py --url https://…/max/webhook

Секрет вебхука выводится из токена (max_bot.webhook_secret): сервер на
Render считает его сам, задавать отдельно ничего не нужно.
"""
from __future__ import annotations

import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

import max_bot  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

DEFAULT_URL = "https://pingo-ai-dpd9.onrender.com/max/webhook"


def main() -> int:
    token = os.environ.get("MAX_BOT_TOKEN", "").strip()
    if not token:
        print("MAX_BOT_TOKEN не задан в backend/.env")
        return 2
    url = DEFAULT_URL
    if "--url" in sys.argv:
        url = sys.argv[sys.argv.index("--url") + 1]
    client = httpx.Client(base_url=max_bot.API_BASE, headers={"Authorization": token},
                          timeout=30, trust_env=False)

    me = client.get("/me")
    print("бот:", me.status_code, {k: me.json().get(k) for k in ("name", "username", "user_id")}
          if me.status_code == 200 else me.text[:200])

    if "--list" in sys.argv:
        r = client.get("/subscriptions")
        print("подписки:", r.status_code, r.text[:500])
        return 0
    if "--delete" in sys.argv:
        r = client.delete("/subscriptions", params={"url": url})
        print("снята:", r.status_code, r.text[:200])
        return 0

    # Старую подписку на тот же адрес снимаем: MAX не обновляет секрет у
    # существующей, а просто отвечает «уже есть».
    client.delete("/subscriptions", params={"url": url})
    r = client.post("/subscriptions", json={
        "url": url,
        "update_types": max_bot.UPDATE_TYPES,
        "secret": max_bot.webhook_secret(token),
    })
    print("подписка:", r.status_code, r.text[:300])
    c = client.patch("/me/commands", json={"commands": max_bot.commands()})
    print("команды:", c.status_code, c.text[:200])
    r = client.get("/subscriptions")
    print("теперь подписано:", r.text[:500])
    return 0 if r.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
