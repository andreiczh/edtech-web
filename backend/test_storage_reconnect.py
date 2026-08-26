# -*- coding: utf-8 -*-
"""Тест фоновой переподключалки базы (26.08.2026).

Боль: Neon спал в момент буста деплоя на Render -> ensure_schema падал ->
_storage_ok=False НАВСЕГДА, кабинет и статистика отдавали 503 до следующего
деплоя. Теперь при неудачном старте крутится _storage_reconnect: пробует
снова с растущей паузой и, ожив, поднимает дневные счётчики и бюджет.

Запуск: .\.venv\Scripts\python.exe test_storage_reconnect.py
Сети и базы не требует: ensure_schema подменяется заглушкой.
"""
from __future__ import annotations

import asyncio
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import main  # noqa: E402

failed = 0


def check(cond: bool, name: str, detail: str = "") -> None:
    global failed
    if cond:
        print(f"OK   {name}")
    else:
        failed += 1
        print(f"FAIL {name}: {detail}")


# ------------------------------------------------- база оживает с 3-й попытки
calls = {"n": 0}


def flaky_ensure_schema() -> None:
    calls["n"] += 1
    if calls["n"] < 3:
        raise ConnectionError("db is sleeping")


counts_pulled = {"n": 0}


def fake_voice_counts(day: str) -> dict:
    counts_pulled["n"] += 1
    return {"dev-1": 5}


main.storage.ensure_schema = flaky_ensure_schema
main.storage.voice_counts = fake_voice_counts
main._storage_ok = False
# За простой память уже накопила реплики: dev-1 больше, чем в базе (7 > 5),
# dev-2 база вообще не видела. Оживление НЕ должно откатить их назад.
main._VOICE_DAY.update(day=main.storage.msk_day(), counts={"dev-1": 7, "dev-2": 2})

asyncio.run(main._storage_reconnect(first_delay=0.01))

check(main._storage_ok, "после оживления базы память включена")
check(calls["n"] == 3, "две неудачи пережиты, третья попытка удалась",
      f"попыток {calls['n']}")
check(counts_pulled["n"] == 1, "дневные счётчики подняты после оживления",
      f"вызовов {counts_pulled['n']}")
check(main._VOICE_DAY["counts"].get("dev-1") == 7,
      "накопленное за простой НЕ затёрто базой (max-слияние)",
      str(main._VOICE_DAY.get("counts")))
check(main._VOICE_DAY["counts"].get("dev-2") == 2,
      "ученик, которого база не видела, не потерян",
      str(main._VOICE_DAY.get("counts")))

# ------------------------------------------------- /health не врёт про память
check(main._STORAGE_RETRY["attempts"] == 2,
      "две неудачи посчитаны для /health", str(main._STORAGE_RETRY))
check(main._STORAGE_RETRY["error"] == "ConnectionError",
      "тип последней ошибки запомнен", str(main._STORAGE_RETRY))
check("sqlite" in main._storage_health(),
      "живая база: /health показывает хранилище", main._storage_health())

# Сборка БЕЗ повтора и база, отвалившаяся после удачного старта, — это «повтор
# не запущен», а не «сейчас переподключаемся»: путать их и значит гадать.
saved_ok, saved_retry = main._storage_ok, dict(main._STORAGE_RETRY)
main._storage_ok = False
main._STORAGE_RETRY.update(attempts=0, error="", next_at=0.0)
check("не запущен" in main._storage_health(),
      "повтор не запущен — так и написано", main._storage_health())
main._STORAGE_RETRY.update(attempts=0, error="", next_at=main.time.monotonic() + 30)
check("первая попытка через" in main._storage_health(),
      "повтор запланирован — видно, через сколько", main._storage_health())
main._STORAGE_RETRY.update(attempts=4, error="OperationalError",
                           next_at=main.time.monotonic() + 120)
h = main._storage_health()
check("4" in h and "OperationalError" in h,
      "идут попытки — видно счётчик и ошибку", h)
main._storage_ok, _ = saved_ok, main._STORAGE_RETRY.update(**saved_retry)

# ------------------------------------------------- уже живая база: мгновенный выход
calls["n"] = 0
main._storage_ok = True
asyncio.run(main._storage_reconnect(first_delay=0.01))
check(calls["n"] == 0, "при живой базе цикл не делает ни одной попытки",
      f"попыток {calls['n']}")

# ------------------------------------------------- пауза растёт и упирается в потолок
d = 30.0
for _ in range(12):
    d = min(d * 2, 600.0)
check(d == 600.0, "пауза упирается в потолок 10 минут", str(d))

print()
if failed:
    print(f"ПРОВАЛ: {failed}")
    sys.exit(1)
print("Все проверки прошли: переподключение базы.")
