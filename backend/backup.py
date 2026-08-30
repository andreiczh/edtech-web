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


def validate_dump(tables: dict, prev_tables: dict | None) -> list[str]:
    """Глубокая приёмка дампа. Возвращает список проблем; пустой = дамп годен.

    Родилась из трёх потерянных дней: авария 27.08 испортила картинки заданий,
    и три ночных дампа подряд молча скопировали hex-мусор — свежего ЦЕЛОГО
    бэкапа не осталось. Дамп, который нельзя восстановить, хуже отсутствующего:
    он выглядит защитой, не будучи ею. Поэтому проверяется не форма, а суть:
    декодируются ли картинки и не усохли ли таблицы, которые могут только
    расти.
    """
    import base64

    problems: list[str] = []

    # Картинки: base64-строки, которые декодируются в настоящий PNG/JPEG.
    # Хекс-представление байтов ("\x89504e...") — след той самой аварии.
    png = bytes([0x89]) + b"PNG"
    jpg = bytes([0xFF, 0xD8, 0xFF])
    hexmark = chr(92) + "x"
    imgs = tables.get("task_images") or []
    broken = 0
    for im in imgs:
        d = im.get("data")
        if not isinstance(d, str) or d.startswith(hexmark) or len(d) % 4:
            broken += 1
            continue
        try:
            head = base64.b64decode(d[:64] + "=" * (-len(d[:64]) % 4))
        except Exception:  # noqa: BLE001
            broken += 1
            continue
        if not (head[:4] == png or head[:3] == jpg):
            broken += 1
    if broken:
        problems.append(f"images: {broken} of {len(imgs)} are not decodable pictures")

    # Таблицы, которые могут только расти: усадка против прошлого дампа --
    # это либо потеря данных, либо дамп не с той базы.
    if prev_tables:
        for t in ("accounts", "results", "mistakes"):
            was = len(prev_tables.get(t) or [])
            now = len(tables.get(t) or [])
            if now < was:
                problems.append(f"{t}: shrank {was} -> {now}")

    # Коды доступа и копилка произношения обязаны присутствовать КАК ТАБЛИЦЫ
    # (пустые - можно): их отсутствие значит, что дамп снят старым кодом,
    # который молча терял invites, - однажды это уже закрыло регистрацию.
    for t in ("invites", "pron_samples"):
        if t not in tables:
            problems.append(f"{t}: table missing from dump entirely")

    return problems


def restore_probe(body: bytes) -> str:
    """Пробное восстановление дампа во временную SQLite.

    Единственная честная проверка бэкапа - восстановиться из него. Дамп
    маленький (мегабайты), проба стоит секунды. Пустая строка = успех,
    иначе - описание провала.
    """
    import tempfile

    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import importlib

        import storage as st
        st = importlib.reload(st)   # прошлый прогон мог оставить соединение
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        st._SQLITE_PATH = tmp.name
        st._conn = None
        st.ensure_schema()
        tables = json.loads(body).get("tables") or {}
        counts = st.restore_all(tables)
        got = sum(counts.values())
        want = sum(len(v) for v in tables.values() if isinstance(v, list))
        try:
            os.remove(tmp.name)
        except OSError:
            pass
        if got != want:
            return f"restored {got} rows of {want}"
        return ""
    except Exception as e:  # noqa: BLE001 - провал пробы = провал приёмки
        return f"{type(e).__name__}: {str(e)[:140]}"


def alert(key: str, text: str) -> None:
    """Провал приёмки кричит в Telegram владельца ЧЕРЕЗ ПРОД (/admin/notify):
    у ноута нет своего токена, а backup.log никто не читает."""
    try:
        base = URL.split("/admin/")[0]
        req = urllib.request.Request(
            base + "/admin/notify",
            data=json.dumps({"text": text}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Admin-Key": key},
            method="POST")
        urllib.request.urlopen(req, timeout=30)
    except Exception as e:  # noqa: BLE001 - алерт не важнее самого бэкапа
        log(f"alert failed: {type(e).__name__}")


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

    # ГЛУБОКАЯ ПРИЁМКА: целостность картинок, отсутствие усадки, пробное
    # восстановление. Дамп, не прошедший её, сохраняется с суффиксом BAD -
    # для разбора, но не в ротацию и не как "свежий целый".
    prev_tables = None
    prev_dumps = sorted(f for f in os.listdir(OUT_DIR)
                        if f.startswith("pingo-") and f.endswith(".json")
                        and "-BAD" not in f)
    if prev_dumps:
        try:
            with open(os.path.join(OUT_DIR, prev_dumps[-1]), encoding="utf-8") as fh:
                prev_tables = json.load(fh).get("tables")
        except Exception:  # noqa: BLE001 - прошлый дамп мог быть битым
            prev_tables = None

    problems = validate_dump(tables, prev_tables)
    probe = restore_probe(body)
    if probe:
        problems.append(f"restore probe failed: {probe}")

    if problems:
        bad_path = path.replace(".json", "-BAD.json")
        with open(bad_path, "wb") as fh:
            fh.write(body)
        msg = "; ".join(problems)[:400]
        log(f"FAILED validation: {msg} -> {os.path.basename(bad_path)}")
        alert(key, "Бэкап НЕ прошёл приёмку: " + msg)
        return 1

    with open(path, "wb") as fh:
        fh.write(body)
    log(f"OK: {os.path.basename(path)} ({len(body) // 1024} KB) "
        + " ".join(f"{t}={n}" for t, n in counts.items())
        + " | images ok, restore probe ok")

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
