# -*- coding: utf-8 -*-
"""Тест приёмки бэкапа (30.08.2026).

Приёмка родилась из трёх потерянных дней: авария испортила картинки, и три
ночных дампа подряд молча скопировали hex-мусор — свежего целого бэкапа не
осталось. Здесь проверяется, что каждая из тех бед теперь ЛОВИТСЯ: битые
картинки, усадка таблиц, пропавшие invites, невосстановимый дамп.

Запуск: .\.venv\Scripts\python.exe test_backup_check.py
Сети не требует.
"""
from __future__ import annotations

import base64
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import backup  # noqa: E402

failed = 0


def check(cond: bool, name: str, detail: str = "") -> None:
    global failed
    if cond:
        print(f"OK   {name}")
    else:
        failed += 1
        print(f"FAIL {name}: {detail}")


PNG = base64.b64encode(bytes([0x89]) + b"PNG fake image data").decode()
GOOD = {
    "students": [{"id": "s1", "created_at": "2026-08-01T00:00:00+00:00"}],
    "accounts": [{"id": "s1", "nickname": "Tester", "pass_hash": "x",
                  "exam": "ege", "created_at": "2026-08-01T00:00:00+00:00"}],
    "results": [{"id": "r1", "student_id": "s1", "kind": "monologue",
                 "variant": "v", "score": 7, "max_score": 10,
                 "duration_sec": 60, "created_at": "2026-08-02T00:00:00+00:00"}],
    "mistakes": [],
    "invites": [],
    "pron_samples": [],
    "task_images": [{"id": "img1", "mime": "image/png", "data": PNG,
                     "source": "t", "created_at": "2026-08-01T00:00:00+00:00"}],
}

# ------------------------------------------------------------- целый дамп
check(backup.validate_dump(GOOD, None) == [], "целый дамп проходит приёмку",
      str(backup.validate_dump(GOOD, None)))

# ------------------------------------------------------- битые картинки
hexed = json.loads(json.dumps(GOOD))
hexed["task_images"][0]["data"] = chr(92) + "x89504e470d0a"  # след аварии 27.08
probs = backup.validate_dump(hexed, None)
check(any("images" in p for p in probs), "hex вместо base64 ловится", str(probs))

nonpic = json.loads(json.dumps(GOOD))
nonpic["task_images"][0]["data"] = base64.b64encode(b"just text, not a picture").decode()
probs = backup.validate_dump(nonpic, None)
check(any("images" in p for p in probs),
      "base64 без PNG/JPEG-заголовка ловится", str(probs))

# --------------------------------------------------------------- усадка
prev = json.loads(json.dumps(GOOD))
prev["accounts"] = prev["accounts"] * 3   # раньше было три аккаунта
probs = backup.validate_dump(GOOD, prev)
check(any("accounts" in p and "shrank" in p for p in probs),
      "усадка аккаунтов против прошлого дампа ловится", str(probs))
check(backup.validate_dump(GOOD, GOOD) == [],
      "равные дампы усадкой не считаются")

# ------------------------------------------------- пропавшие таблицы
no_inv = {k: v for k, v in GOOD.items() if k != "invites"}
probs = backup.validate_dump(no_inv, None)
check(any("invites" in p for p in probs),
      "дамп без таблицы invites отклонён (уже закрывал регистрацию)", str(probs))

# ------------------------------------------------- пробное восстановление
body = json.dumps({"tables": GOOD}, ensure_ascii=False).encode("utf-8")
res = backup.restore_probe(body)
check(res == "", "целый дамп восстанавливается в пробную базу", res)

broken_body = b'{"tables": {"accounts": [{"id": "s1", "no_such_column": 1}]}}'
res = backup.restore_probe(broken_body)
check(res != "", "невосстановимый дамп проваливает пробу", "прошёл молча")

print()
if failed:
    print(f"ПРОВАЛ: {failed}")
    sys.exit(1)
print("Все проверки прошли: приёмка бэкапа.")
