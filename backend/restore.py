# -*- coding: utf-8 -*-
"""Заливка локального бэкапа в ПУСТУЮ базу прода (пара к backup.py).

Сценарий 27.08.2026: Neon поставил проект на паузу за месячную квоту
compute-часов, данные остались только в ночных дампах на этом ноуте.
Владелец создаёт свежий проект Neon, меняет DATABASE_URL на Render — и
запускает этот скрипт. Сервер примет дамп только в пустую базу
(/admin/restore, защита от случайной перезаписи живых данных).

Запуск руками:
    .\.venv\Scripts\python.exe restore.py                 # свежайший дамп
    .\.venv\Scripts\python.exe restore.py путь\к\дампу.json

Ключ — из PINGO_ADMIN_KEY (как у backup.py) или PROD_ADMIN_KEY в backend/.env.
Python, не PowerShell: антивирус 360 Total Security трижды съедал backup.ps1,
у python-скриптов из .venv такой судьбы не было (см. backup.py).
"""
from __future__ import annotations

import glob
import json
import os
import sys
import urllib.request

URL = os.environ.get(
    "PINGO_RESTORE_URL",
    "https://pingo-ai-dpd9.onrender.com/admin/restore")
BACKUP_DIR = os.path.join(os.path.expanduser("~"), "pingo-backups")
TIMEOUT_SEC = 300


def _admin_key() -> str:
    key = os.environ.get("PINGO_ADMIN_KEY", "").strip()
    if key:
        return key
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("PROD_ADMIN_KEY="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def main() -> int:
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        dumps = sorted(glob.glob(os.path.join(BACKUP_DIR, "pingo-*.json")))
        if not dumps:
            print(f"В {BACKUP_DIR} нет дампов pingo-*.json")
            return 1
        path = dumps[-1]

    key = _admin_key()
    if not key:
        print("Нет ключа: задай PINGO_ADMIN_KEY или PROD_ADMIN_KEY в backend/.env")
        return 1

    with open(path, encoding="utf-8") as f:
        dump = json.load(f)
    tables = dump.get("tables") or {}
    print(f"Дамп: {os.path.basename(path)} от {dump.get('created_at', '?')}")
    print("Строк по таблицам:", {t: len(r) for t, r in tables.items()})

    req = urllib.request.Request(
        URL,
        data=json.dumps({"tables": tables}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Admin-Key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        print(f"Сервер ответил {e.code}: {detail}")
        if e.code == 409:
            print("База не пустая. Если перезаливка сознательная — добавь ?force=1 к URL.")
        return 1

    print("Восстановлено:", body.get("restored"))
    print(f"Всего строк: {body.get('rows')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
