# -*- coding: utf-8 -*-
"""Тест разметки монолога №42 (01.09.2026).

Разметка тестировщика — калибровочный корпус для слабейшего места оценивания,
и ей нельзя теряться или искажаться: здесь проверяется путь запись -> база ->
экспорт в формат золотого набора (fipi_cases.MONOLOGUE_EXTRA), попадание в
бэкап и серверная валидация правил ФИПИ (РКЗ=0 обнуляет всё).

Запуск: .\.venv\Scripts\python.exe test_label42.py
Сети не требует, база во временном файле; LLM не вызывается.
"""
from __future__ import annotations

import io
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


tmp = os.path.join(tempfile.gettempdir(), "label42_suite.db")
if os.path.exists(tmp):
    os.remove(tmp)
storage._SQLITE_PATH = tmp
storage._conn = None
storage.ensure_schema()

REC = {
    "name": "тестовая работа",
    "variant": "42-fipi-1",
    "brief": "Task 4. Imagine that you and your friend are doing a school project "
             "about hobbies. Leave a voice message explaining your choice of photos.",
    "facts": ["a girl reading a book", "two boys playing football"],
    "script": " ".join(["word"] * 60),
    "k1": 3, "k2": 2, "k3": 2,
    "rationale": {"k1": "аспект 3 неполный", "k2": "нет связок между частями",
                  "k3": "4 ошибки, 2 грубые"},
    "aspects": ["full", "full", "partial", "full"],
    "opening": True, "closing": False,
    "errors": [{"where": "lang", "cat": "gram", "quote": "he go",
                "correction": "he goes", "grave": True}],
    "notes": "для сетки",
    "labeler": "тестировщик",
}

# ------------------------------------------------------------- сохранение
rid = storage.labeled42_add(REC)
check(bool(rid), "работа сохранилась, id выдан")

rows = storage.labeled42_list()
check(len(rows) == 1 and rows[0]["marks"] == [3, 2, 2],
      "список отдаёт работу с баллами", str(rows))
check(rows[0]["system"] is None, "вердикта системы пока нет — и это не ошибка")

storage.labeled42_set_system(rid, {"marks": [3, 2, 1], "total": 6})
rows = storage.labeled42_list()
check(rows[0]["system"] == {"marks": [3, 2, 1], "total": 6},
      "вердикт системы дописался отдельным шагом", str(rows[0]["system"]))

# ------------------------------------------------------ формат золотого набора
exp = storage.labeled42_export()
check(exp["count"] == 1, "экспорт видит работу")
g = exp["golden"][0]
check(set(g.keys()) == {"name", "brief", "facts", "script", "expected"},
      "golden-кейс несёт ровно поля MONOLOGUE_EXTRA", str(sorted(g.keys())))
check(g["expected"] == (3, 2, 2) or g["expected"] == [3, 2, 2],
      "expected — тройка баллов человека, не системы", str(g["expected"]))
w = exp["works"][0]
check(w["errors"][0]["quote"] == "he go" and w["rationale"]["k2"].startswith("нет"),
      "сырой экспорт сохраняет ошибки и обоснования")
check(w["system"]["total"] == 6, "сырой экспорт несёт и вердикт системы")

# ---------------------------------------------------------------- бэкап
dump = storage.dump_all()
check("labeled42" in dump and len(dump["labeled42"]) == 1,
      "разметка попадает в ночной бэкап")

# ------------------------------------------------- восстановление из бэкапа
tmp2 = os.path.join(tempfile.gettempdir(), "label42_restore.db")
if os.path.exists(tmp2):
    os.remove(tmp2)
storage._SQLITE_PATH = tmp2
storage._conn = None
storage.ensure_schema()
storage.restore_all({"labeled42": dump["labeled42"]})
check(storage.labeled42_export()["count"] == 1,
      "restore_all возвращает разметку в новую базу")

# ------------------------------------------------------- серверная валидация
# Валидацию делает main.label42_save; проверяем её без сети через прямой вызов.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LABELER_KEY", "test-key")
import asyncio  # noqa: E402

import main  # noqa: E402
from fastapi import HTTPException  # noqa: E402

main.LABELER_KEY = "test-key"
main._storage_ok = True


def try_save(body: dict) -> tuple[bool, str]:
    try:
        asyncio.run(main.label42_save(body=body, x_labeler_key="test-key"))
        return True, ""
    except HTTPException as e:
        return False, str(e.detail)


ok, why = try_save({**REC, "k1": 0, "k2": 2, "k3": 2})
check(not ok and "обнуля" in why.lower() or "0" in why,
      "РКЗ=0 с ненулевыми k2/k3 отклонён (правило ФИПИ)", why)

ok, why = try_save({**REC, "script": "too short"})
check(not ok, "короткий ответ отклонён", why)

ok, why = try_save({**REC, "rationale": {"k1": "ok", "k2": "", "k3": "hm"}})
check(not ok, "пустое обоснование отклонено", why)

try:
    asyncio.run(main.label42_save(body=REC, x_labeler_key="wrong"))
    check(False, "чужой ключ отклонён", "прошёл")
except HTTPException as e:
    check(e.status_code == 403, "чужой ключ отклонён", str(e.status_code))

# Валидный сейв (сверка с системой не пойдёт: гейт только что не открывался —
# выставим его в будущее, чтобы LLM гарантированно не вызывался).
main._LABEL_RUN_GATE["at"] = 1e18
ok, why = try_save(REC)
check(ok, "валидная работа проходит серверную валидацию", why)

print()
if failed:
    print(f"ПРОВАЛ: {failed}")
    sys.exit(1)
print("Все проверки прошли: разметка монолога.")
