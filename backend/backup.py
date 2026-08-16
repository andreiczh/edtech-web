"""Ночной бэкап базы Pingo AI (у Neon free своих бэкапов нет).

Почему Python, а не PowerShell. backup.ps1 ТРИЖДЫ молча исчезал с диска
(05.08, ~12.08 и 16.08.2026, последний раз — через десять минут после
успешного запуска). Виновник — антивирус 360 Total Security: скрипт с
Invoke-WebRequest, заголовком-ключом и записью файлов подходит под его
эвристику «загрузчик», а удаляет он без записи в журналы Windows. Python из
.venv проекта та же эвристика не трогает — он тут месяцами гоняет тесты и
серверы. Логика перенесена один в один: дамп не засчитан, пока не распарсился
как JSON и не показал строки.

Запуск руками:
    .\.venv\Scripts\python.exe backup.py

Планировщик (задача PingoBackup) зовёт pythonw.exe — без окна на экране:
окно консоли уже один раз закрыли вручную, и бэкап умер с 0xC000013A.

Ключ берётся из переменной окружения PINGO_ADMIN_KEY (задана для пользователя,
см. docs/MONITORING.md) или из PROD_ADMIN_KEY в backend/.env.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.request

URL = os.environ.get(
    "PINGO_BACKUP_URL",
    "https://pingo-ai-dpd9.onrender.com/admin/backup?images=1")
OUT_DIR = os.path.join(os.path.expanduser("~"), "pingo-backups")
LOG = os.path.join(OUT_DIR, "backup.log")
# Дамп с картинками — единицы мегабайт; всё, что меньше сотни байт, — это
# страница ошибки, а не бэкап.
MIN_BYTES = 100
TIMEOUT_SEC = 300


def log(text: str) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {text}"
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line)


def _key() -> str:
    key = os.environ.get("PINGO_ADMIN_KEY", "").strip()
    if key:
        return key
    # Запасной путь: PROD_ADMIN_KEY из backend/.env, лежащего рядом.
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(env_path, encoding="utf-8") as fh:
            for raw in fh:
                if raw.strip().startswith("PROD_ADMIN_KEY="):
                    return raw.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return ""


def main() -> int:
    key = _key()
    if not key:
        log("FAILED: no admin key. Set PINGO_ADMIN_KEY or PROD_ADMIN_KEY in backend/.env.")
        return 1

    stamp = f"{dt.datetime.now():%Y-%m-%d_%H%M}"
    path = os.path.join(OUT_DIR, f"pingo-{stamp}.json")
    os.makedirs(OUT_DIR, exist_ok=True)

    req = urllib.request.Request(URL, headers={"X-Admin-Key": key})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            body = resp.read()
    except Exception as e:  # noqa: BLE001 — причина уходит в лог, не в трейс
        log(f"FAILED: request error - {type(e).__name__}: {str(e)[:160]}")
        return 1

    if len(body) < MIN_BYTES:
        log(f"FAILED: response is {len(body)} bytes - wrong key or wrong URL.")
        return 1

    # Дамп не засчитывается, пока не распарсился и не показал строки: месяц
    # копить страницы ошибок под видом бэкапа хуже, чем не копить ничего.
    try:
        dump = json.loads(body)
    except ValueError as e:
        log(f"FAILED: response is not valid JSON - {str(e)[:120]}")
        return 1
    tables = dump.get("tables", dump)
    counts = {t: len(tables.get(t) or []) for t in
              ("accounts", "results", "mistakes", "disputes", "tasks")}
    if not any(counts.values()):
        log("FAILED: dump has no rows at all - check the key.")
        return 1

    with open(path, "wb") as fh:
        fh.write(body)
    log(f"OK: {os.path.basename(path)} ({len(body) // 1024} KB) "
        + " ".join(f"{t}={n}" for t, n in counts.items()))

    # Храним последние 14 дампов, старые убираем.
    dumps = sorted(f for f in os.listdir(OUT_DIR)
                   if f.startswith("pingo-") and f.endswith(".json"))
    for old in dumps[:-14]:
        try:
            os.remove(os.path.join(OUT_DIR, old))
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
