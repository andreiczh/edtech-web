# -*- coding: utf-8 -*-
"""Избранные задания (16.09.2026): звёздочка в правом верхнем углу задания
и «избранный вариант» из отмеченного.

Проверяется путь запись -> база -> ответ: пусто у нового аккаунта, отметка,
повтор без дублей, порядок по времени, снятие, чужой аккаунт не видит,
проверка входных данных и входа, потолок 200 и попадание таблицы в бэкап.

Запуск: .\.venv\Scripts\python.exe test_favorites.py
Сети не требует, база во временном файле.
"""
from __future__ import annotations

import asyncio
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


tmp = os.path.join(tempfile.gettempdir(), "favorites_suite.db")
if os.path.exists(tmp):
    os.remove(tmp)
storage._SQLITE_PATH = tmp
storage._conn = None
storage.ensure_schema()

import main  # noqa: E402
from fastapi import HTTPException  # noqa: E402

main._storage_ok = True
anna = storage.create_account("CheerfulHummingbird", "x$y", "ege")
bob = storage.create_account("GleamingSandpiper", "x$y", "ege")


def call(coro):
    try:
        return asyncio.run(coro), None
    except HTTPException as e:
        return None, e


def get(who):
    return call(main.me_favorites_get(x_device=who, x_admin_key=None))


def post(who, body):
    return call(main.me_favorites_post(body=body, x_device=who, x_admin_key=None))


def ids(res):
    return [i["variant_id"] for i in (res or {}).get("items", [])]


def why(res, err) -> str:
    return str(res) if err is None else f"{err.status_code}: {err.detail}"


res, err = get(anna)
check(err is None and res == {"items": []}, "у нового аккаунта избранное пустое", why(res, err))

res, err = post(anna, {"task_id": 40, "variant_id": "40-2", "on": True})
check(err is None and ids(res) == ["40-2"] and res["items"][0]["task_id"] == 40,
      "звёздочка ставится, в ответе весь список", why(res, err))
res, err = post(anna, {"task_id": 42, "variant_id": "42-fipi-1"})
check(err is None and ids(res) == ["40-2", "42-fipi-1"],
      "без поля on звёздочка ставится; порядок — по времени отметки", why(res, err))
first_at = res["items"][0]["at"] if res else ""
res, err = post(anna, {"task_id": 40, "variant_id": "40-2", "on": True})
check(err is None and ids(res) == ["40-2", "42-fipi-1"] and res["items"][0]["at"] == first_at,
      "повторная звёздочка не плодит дублей и не сбивает время", why(res, err))

res, err = get(bob)
check(err is None and res == {"items": []}, "чужой аккаунт чужих звёздочек не видит", why(res, err))

res, err = post(anna, {"task_id": 40, "variant_id": "40-2", "on": False})
check(err is None and ids(res) == ["42-fipi-1"], "снятая звёздочка убирает задание", why(res, err))

for body, what in (
    ({"task_id": 38, "variant_id": "x"}, "номер не из устной части"),
    ({"task_id": "abc", "variant_id": "x"}, "номер не число"),
    ({"task_id": 40, "variant_id": ""}, "пустой вариант"),
    ({"task_id": 40, "variant_id": "40 2 <script>"}, "мусор в id варианта"),
    ({"task_id": 40, "variant_id": "v" * 65}, "id варианта длиннее 64"),
):
    res, err = post(anna, body)
    check(err is not None and err.status_code == 422, f"отказ 422: {what}", why(res, err))

res, err = post(None, {"task_id": 40, "variant_id": "40-1"})
check(err is not None and err.status_code == 401, "без аккаунта — 401", why(res, err))

for i in range(199):
    storage.favorite_set(bob, 41, f"41-{i}", True)
res, err = post(bob, {"task_id": 41, "variant_id": "41-last"})
check(err is None and len(ids(res)) == 200, "двухсотое задание ещё помещается", why(len(ids(res)), err))
res, err = post(bob, {"task_id": 41, "variant_id": "41-over"})
check(err is not None and err.status_code == 422, "двести первое — вежливый отказ", why(res, err))
res, err = post(bob, {"task_id": 41, "variant_id": "41-0", "on": False})
check(err is None and len(ids(res)) == 199, "снять можно всегда, и при полном избранном",
      why(len(ids(res)), err))

dump = storage.dump_all()
rows = dump.get("favorites") or []
check(any(r.get("variant_id") == "42-fipi-1" for r in rows),
      "таблица избранного попадает в ночной бэкап", str(list(dump)))

print()
print("ВСЁ ЗЕЛЁНОЕ" if not failed else f"ПРОВАЛОВ: {failed}")
sys.exit(1 if failed else 0)
