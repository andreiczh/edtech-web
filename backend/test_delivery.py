# -*- coding: utf-8 -*-
"""Тесты замера подачи. Считают, что модуль ВЫКЛЮЧЕН по умолчанию, и проверяют
чистую арифметику вокруг него — без whisper и без сети.

Тяжёлую часть (реальный прогон записи через модель) сюда не тащим намеренно:
она требует процессора и минуты времени, а проверять надо ровно то, что легко
сломать правкой — пороги темпа, отбор пауз и текст для ученика.

Запуск: .\.venv\Scripts\python.exe test_delivery.py
"""
from __future__ import annotations

import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import delivery  # noqa: E402

failed = 0


def check(cond: bool, name: str, detail: str = "") -> None:
    global failed
    if cond:
        print(f"OK   {name}")
    else:
        failed += 1
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))


check(delivery.DELIVERY_ANALYSIS is False,
      "выключен по умолчанию — на бесплатном Render процессора нет")
check(delivery.measure(b"x") is None,
      "выключенный замер молча возвращает None, а не падает")

# --------------------------------------------------------------- комментарий

ровно = {"wpm": 150, "pace": "ok", "seconds": 40.0, "pauses": [], "pause_count": 0}
c = delivery.comment(ровно, finished=True)
check("Темп ровный" in c and "150" in c, "ровное чтение: хвалим и называем темп", c)

медленно = {**ровно, "wpm": 90, "pace": "slow"}
c = delivery.comment(медленно, finished=True)
check("низковат" in c and "90" in c, "медленно: говорим про время экзамена", c)

быстро = {**ровно, "wpm": 260, "pace": "fast"}
c = delivery.comment(быстро, finished=True)
check("тараторишь" in c, "быстро: предупреждаем про разборчивость", c)

# «Не дочитано» приходит из сверки с эталоном, а не из аудио.
c = delivery.comment(ровно, finished=False)
check("не дочитан" in c, "недочитанный текст назван первым — это дороже темпа", c)

одна_пауза = {**ровно, "pauses": [{"after": "trunk", "sec": 1.4}], "pause_count": 1}
c = delivery.comment(одна_пауза, finished=True)
check("1.4" in c and "trunk" in c,
      "одна заминка: называем длительность и место — ученику есть что отработать", c)

много_пауз = {**ровно, "pauses": [{"after": "a", "sec": 1.0}], "pause_count": 4}
c = delivery.comment(много_пауз, finished=True)
check("4 длинных пауз" in c, "много заминок: считаем, а не перечисляем", c)

# Худший случай: всё сразу, и ничего не теряется.
плохо = {"wpm": 80, "pace": "slow", "seconds": 90.0,
         "pauses": [{"after": "x", "sec": 2.0}], "pause_count": 5}
c = delivery.comment(плохо, finished=False)
check(all(s in c for s in ("не дочитан", "низковат", "5 длинных")),
      "всё сразу: перечислены все замечания", c)

# --------------------------------------------------------------------- пороги

check(delivery.SLOW_WPM < delivery.FAST_WPM, "границы темпа не перепутаны")
check(delivery.PAUSE_SEC >= 0.5,
      "порог паузы не ниже 0.5 с — иначе естественные паузы между "
      "предложениями пойдут в заминки")

print("\nВсе проверки прошли: замер подачи." if failed == 0
      else f"\nПРОВАЛЕНО проверок: {failed}")
sys.exit(0 if failed == 0 else 1)
