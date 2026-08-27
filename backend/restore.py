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
import time
import urllib.error
import urllib.request

URL = os.environ.get(
    "PINGO_RESTORE_URL",
    "https://pingo-ai-dpd9.onrender.com/admin/restore")
BACKUP_DIR = os.path.join(os.path.expanduser("~"), "pingo-backups")
TIMEOUT_SEC = 300
# Дамп с картинками — 5+ МБ, и одним куском он не доезжает: TLS рвётся
# посреди тела (SSL: UNEXPECTED_EOF_WHILE_READING, поймано 27.08.2026 на
# первой же настоящей заливке). Режем на порции около мегабайта.
CHUNK_BYTES = 1_000_000
RETRIES = 3


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


def _chunks(tables: dict) -> list:
    """Режем дамп на порции ~CHUNK_BYTES: строки одной таблицы не склеиваем
    с соседними произвольно — просто набираем, пока порция не потяжелеет."""
    out, cur, cur_bytes = [], {}, 0
    for t, rows in tables.items():
        for row in rows:
            size = len(json.dumps(row, ensure_ascii=False).encode("utf-8"))
            if cur_bytes + size > CHUNK_BYTES and cur:
                out.append(cur)
                cur, cur_bytes = {}, 0
            cur.setdefault(t, []).append(row)
            cur_bytes += size
    if cur:
        out.append(cur)
    return out


def _post(tables: dict, key: str, force: bool) -> dict:
    url = URL + ("?force=1" if force else "")
    data = json.dumps({"tables": tables}).encode("utf-8")
    last = None
    for attempt in range(1, RETRIES + 1):
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json", "X-Admin-Key": key},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError:
            raise  # ответ сервера — не сетевая беда, повтор не поможет
        except Exception as e:  # noqa: BLE001 — обрыв TLS/сети: пробуем ещё
            last = e
            print(f"    сеть подвела ({type(e).__name__}), попытка {attempt} из {RETRIES}")
            time.sleep(3 * attempt)
    raise last


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

    parts = _chunks(tables)
    print(f"Порций: {len(parts)}")

    total = 0
    for n, part in enumerate(parts, 1):
        what = ", ".join(f"{t} {len(r)} стр." for t, r in part.items())
        print(f"  [{n}/{len(parts)}] {what}")
        try:
            # Пустоту базы проверяет ТОЛЬКО первая порция: дальше она уже не
            # пуста нашими же строками, и force здесь — не обход защиты.
            body = _post(part, key, force=(n > 1))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:300]
            print(f"Сервер ответил {e.code}: {detail}")
            if e.code == 409:
                print("База не пустая — восстановление отменено, ничего не залито.")
            return 1
        except Exception as e:  # noqa: BLE001
            print(f"Порция {n} не доехала: {type(e).__name__}: {e}")
            print("Часть строк уже залита; повторный запуск упрётся в 409 — "
                  "чистить базу и начинать заново.")
            return 1
        total += body.get("rows", 0)

    print(f"Готово. Всего строк: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
