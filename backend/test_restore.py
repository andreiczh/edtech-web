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
def _images_ok(tables: dict) -> bool:
    """Целы ли картинки в дампе: base64-строка, а не hex испорченных данных.

    Проверять приходится, потому что дамп снимается С ПРОДА: если прод болен,
    свежий дамп болен тоже, и тест на нём проверял бы не код, а аварию.
    """
    imgs = tables.get("task_images") or []
    if not imgs:
        return True
    d = imgs[0].get("data")
    return isinstance(d, str) and not d.startswith(chr(92) + "x") and len(d) % 4 == 0


dumps = sorted(glob.glob(os.path.join(os.path.expanduser("~"), "pingo-backups", "pingo-*.json")))
tables = None
for path in reversed(dumps):        # от свежих к старым — берём первый целый
    with open(path, encoding="utf-8") as f:
        cand = json.load(f)["tables"]
    if _images_ok(cand):
        tables = cand
        print(f"Дамп: {os.path.basename(path)}")
        if path != dumps[-1]:
            print(f"  ВНИМАНИЕ: свежий дамп {os.path.basename(dumps[-1])} "
                  "содержит испорченные картинки — взят предыдущий целый.")
        break
if tables is None:
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

# ------------------------------------- картинки: base64-ТЕКСТ, как в схеме
# Колонка task_images.data объявлена TEXT и хранит base64 (общий знаменатель
# SQLite и Postgres). Восстановление обязано класть туда СТРОКУ как есть.
#
# Проверка именно такая, потому что обратное сломало прод на три дня:
# декодированные байты Postgres записал в TEXT-колонку как hex, и все 138
# картинок заданий стали отдавать 500. Прежний тест был зелёным, потому что
# SQLite молча принимает bytes в TEXT — он проверял ровно то, что ломало прод.
if tables.get("task_images"):
    import base64 as _b64

    raw = storage._exec("SELECT data FROM task_images LIMIT 1").fetchone()[0]
    check(isinstance(raw, str), "картинка лежит СТРОКОЙ, а не байтами",
          type(raw).__name__)
    check(not raw.startswith(chr(92) + "x"),
          "это base64, а не hex-представление байтов", raw[:12])
    decoded = _b64.b64decode(raw)
    check(decoded[:4] == bytes([0x89]) + b"PNG"
          or decoded[:3] == bytes([0xFF, 0xD8, 0xFF]),
          "строка декодируется в настоящий PNG/JPEG", repr(decoded[:8]))

# ------------------------------------------------- режим перезаливки
# Чинить испорченные данные надо поверх существующих строк: иначе остаётся
# только чистить базу целиком, теряя всё, что накопилось после аварии.
if tables.get("task_images"):
    before = storage._exec("SELECT COUNT(*) FROM task_images").fetchone()[0]
    storage.restore_all({"task_images": tables["task_images"]}, replace=True)
    after = storage._exec("SELECT COUNT(*) FROM task_images").fetchone()[0]
    check(before == after, "перезаливка не плодит дубликаты",
          f"было {before}, стало {after}")
    raw2 = storage._exec("SELECT data FROM task_images LIMIT 1").fetchone()[0]
    check(isinstance(raw2, str) and not raw2.startswith(chr(92) + "x"),
          "после перезаливки картинка по-прежнему base64-строка")

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
