# -*- coding: utf-8 -*-
"""Тест воронки запуска (30.08.2026).

Воронка отвечает владельцу на «где отваливаются люди», и врать ей нельзя ни в
какую сторону: заниженный «дошёл до задания» заставит чинить то, что работает,
завышенный — прятать настоящую дыру. Здесь каждый показатель проверяется на
маленькой рукотворной когорте, где правильный ответ известен заранее.

Запуск: .\.venv\Scripts\python.exe test_funnel.py
Сети не требует, база во временном файле.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

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


tmp = os.path.join(tempfile.gettempdir(), "funnel_suite.db")
if os.path.exists(tmp):
    os.remove(tmp)
storage._SQLITE_PATH = tmp
storage.ensure_schema()

now = datetime.now(timezone.utc)
today = now.strftime("%Y-%m-%d")
yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")


_seq = iter(range(1000))


def make_account(created_at: str) -> str:
    # Ник уникален по схеме — каждому тестовому аккаунту свой.
    sid = storage.create_account(f"TestUser{next(_seq)}", "hash", "ege")
    storage._exec("UPDATE accounts SET created_at=? WHERE id=?", (created_at, sid))
    return sid


def add_result(sid: str, created_at: str) -> None:
    import uuid
    storage._exec(
        "INSERT INTO results(id, student_id, kind, variant, score, max_score,"
        " duration_sec, created_at) VALUES(?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), sid, "monologue", "v1", 7, 10, 60, created_at))


def add_activity(sid: str, day: str) -> None:
    storage._exec(
        "INSERT INTO activity_days(student_id, day, replies, tasks, xp)"
        " VALUES(?,?,?,?,?)", (sid, day, 1, 1, 10))


# Когорта, где всё известно заранее:
#  A: зарегистрировался вчера, сдал задание через 30 минут, вернулся сегодня;
#  B: зарегистрировался вчера, ни одного задания, не вернулся;
#  C: зарегистрировался сегодня, сдал сразу (5 минут);
#  D: старый (месяц назад), 3 задания — в дневную сетку не попадает,
#     в когорте участвует.
a = make_account(f"{yesterday}T10:00:00+00:00")
add_result(a, f"{yesterday}T10:30:00+00:00")
add_activity(a, yesterday)
add_activity(a, today)

b = make_account(f"{yesterday}T11:00:00+00:00")

c = make_account(f"{today}T09:00:00+00:00")
add_result(c, f"{today}T09:05:00+00:00")
add_activity(c, today)

old_day = (now - timedelta(days=30)).strftime("%Y-%m-%d")
d = make_account(f"{old_day}T12:00:00+00:00")
for i in range(3):
    add_result(d, f"{old_day}T13:0{i}:00+00:00")
add_activity(d, old_day)

f = storage.funnel_summary(days=14)
days = {row["day"]: row for row in f["days"]}
co = f["cohort"]

# ------------------------------------------------------------------ по дням
check(days[yesterday]["registered"] == 2, "вчера зарегистрировано двое",
      str(days.get(yesterday)))
check(days[yesterday]["reached_task"] == 1,
      "из вчерашних до задания дошёл один (B не дошёл)")
check(days[yesterday]["returned_next_day"] == 1,
      "из вчерашних назавтра вернулся один (A)")
check(days[today]["registered"] == 1 and days[today]["reached_task"] == 1,
      "сегодняшний C зарегистрирован и дошёл", str(days.get(today)))
check(old_day not in days, "старый аккаунт не попадает в 14-дневную сетку")

# ------------------------------------------------------------------ когорта
check(co["accounts"] == 4, "в когорте все четверо", str(co))
check(co["reached_first_task"] == 3, "до задания дошли трое (A, C, D)")
check(co["reached_pct"] == 75.0, "процент дошедших верен", str(co["reached_pct"]))
check(co["returned_next_day"] == 1, "назавтра вернулся один")
check(co["avg_tasks_per_active"] == round((1 + 1 + 3) / 3, 1),
      "среднее заданий на активного: (1+1+3)/3", str(co["avg_tasks_per_active"]))
# медиана задержки: 30, 5, ~60 минут (три значения) -> средняя по счёту = 30
check(co["median_minutes_to_first_task"] == 30.0,
      "медианная задержка до первого задания — 30 минут",
      str(co["median_minutes_to_first_task"]))

# ------------------------------------------------------------- пустая база
tmp2 = os.path.join(tempfile.gettempdir(), "funnel_empty.db")
if os.path.exists(tmp2):
    os.remove(tmp2)
storage._SQLITE_PATH = tmp2
storage._conn = None
storage.ensure_schema()
empty = storage.funnel_summary()
check(empty["cohort"]["accounts"] == 0 and empty["days"] == [],
      "пустая база даёт нули, а не деление на ноль", str(empty["cohort"]))

print()
if failed:
    print(f"ПРОВАЛ: {failed}")
    sys.exit(1)
print("Все проверки прошли: воронка запуска.")
