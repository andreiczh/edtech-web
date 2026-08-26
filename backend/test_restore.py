# -*- coding: utf-8 -*-
"""Тест восстановления из бэкапа (27.08.2026).

Боль: Neon поставил проект на паузу за квоту, и единственной копией данных
оказался ночной JSON-дамп. Здесь проверяем весь путь восстановления НА
НАСТОЯЩЕМ дампе с ноута владельца (если он есть): свежая база -> restore_all
-> строки на месте, картинки декодированы из base64 в байты, повторная
заливка в непустую базу отклонена.

Запуск: .\.venv\Scripts\python.exe test_restore.py
Сети не требует, базу поднимает во временном файле SQLite.
"""
from __future__ import annotations

import glob
import io
import json
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import storage  # noqa: E402

failed = 0


def check(cond: bool, name: str, detail: str = "") -> None:
    global failed
    if cond:
        print(f"OK   {name}")
    else:
        failed += 1
        print(f"FAIL {name}: {detail}")


# ---------------------------------------------- база во временном файле
tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
storage._SQLITE_PATH = tmp.name
storage.ensure_schema()

# ---------------------------------------------- источник: настоящий дамп
dumps = sorted(glob.glob(os.path.join(os.path.expanduser("~"), "pingo-backups", "pingo-*.json")))
if dumps:
    with open(dumps[-1], encoding="utf-8") as f:
        tables = json.load(f)["tables"]
    print(f"Дамп: {os.path.basename(dumps[-1])}")
else:
    # На чужой машине дампа нет — синтетический минимум той же формы.
    import base64
    tables = {
        "students": [{"id": "s1", "created_at": "2026-08-01T00:00:00+00:00"}],
        "accounts": [{"id": "s1", "nickname": "Tester", "pass_hash": "x",
                      "exam": "ege", "created_at": "2026-08-01T00:00:00+00:00"}],
        "task_images": [{"id": "img1", "mime": "image/png",
                         "data": base64.b64encode(b"\x89PNG fake").decode(),
                         "source": "test", "created_at": "2026-08-01T00:00:00+00:00"}],
    }
    print("Дампа на диске нет — синтетические данные")

counts = storage.restore_all(tables)

for t, rows in tables.items():
    if not rows:
        continue
    got = storage._exec(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    check(got == len(rows), f"{t}: {len(rows)} строк легли",
          f"в базе {got}, в дампе {len(rows)}")

# ---------------------------------------------- картинки — байты, не base64
if tables.get("task_images"):
    raw = storage._exec("SELECT data FROM task_images LIMIT 1").fetchone()[0]
    check(isinstance(raw, (bytes, memoryview)),
          "картинка декодирована в байты", type(raw).__name__)
    head = bytes(raw)[:8]
    check(head[:4] in (b"\x89PNG", b"\xff\xd8\xff\xe0", b"\x89PNG"[:4]) or head[:3] == b"\xff\xd8\xff",
          "у картинки настоящий заголовок PNG/JPEG", repr(head))

# ---------------------------------------------- вторая заливка отклонена
try:
    storage.restore_all(tables)
    check(False, "повторная заливка в непустую базу отклонена", "прошла молча")
except ValueError:
    check(True, "повторная заливка в непустую базу отклонена")

# ---------------------------------------------- dump_all видит новые таблицы
dump2 = storage.dump_all()
for t in ("invites", "pron_samples", "voice_daily", "meta"):
    check(t in dump2, f"бэкап теперь включает {t}")

print()
if failed:
    print(f"ПРОВАЛ: {failed}")
    sys.exit(1)
print("Все проверки прошли: восстановление из бэкапа.")
