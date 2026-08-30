# -*- coding: utf-8 -*-
"""Тест корпуса голоса (28.08.2026).

Корпус — единственное место, где хранится САМА РЕЧЬ ученика, поэтому здесь
проверяется не только «работает ли», но и каждый предохранитель: без согласия
не пишем, за потолок места не выходим, одним учеником корпус не забиваем.

Запуск: .\.venv\Scripts\python.exe test_corpus.py
Сети и прода не требует — база во временном файле.
"""
from __future__ import annotations

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


tmp = os.path.join(tempfile.gettempdir(), "corpus_suite.db")
if os.path.exists(tmp):
    os.remove(tmp)
storage._SQLITE_PATH = tmp
storage.ensure_schema()

AUDIO = b"\x1aE\xdf\xa3" + b"x" * 5000

# ------------------------------------------------------------ запись и чтение
cid = storage.corpus_add(
    "stud-1", "reading", "v-39-1", AUDIO, "audio/webm", 42.5,
    "The old bridge over the water looks dangerous",
    "The old bridge over the water looks dangerous after the storm",
    1, 1, {"criteria": {"phonetic": {"score": 1, "max": 1}},
           "errors": [{"cat": "phon", "quote": "bridge"}], "errors_n": 1})
check(len(cid) == 36, "запись создана с uuid")
check(storage.corpus_bytes_total() == len(AUDIO), "байты посчитаны",
      str(storage.corpus_bytes_total()))

items = storage.corpus_list(limit=10)
check(len(items) == 1, "запись в списке")
check("data" not in items[0], "звук в списке НЕ едет (список должен быть лёгким)")
check(items[0]["labels"]["criteria"]["phonetic"]["score"] == 1,
      "автоматическая разметка сохранилась целиком")
check(items[0]["transcript"].startswith("The old bridge"), "расшифровка на месте")
check(items[0]["reference"].endswith("after the storm"), "эталон на месте")

got = storage.corpus_audio(cid)
check(got is not None and got[0] == AUDIO, "звук достаётся байт в байт")
check(got[1] == "audio/webm", "тип записи сохранён")

# ------------------------------------------------------------------- вердикт
check(storage.corpus_verify(cid, "балл 1, эксперт согласен"), "вердикт ставится")
check(storage.corpus_list(limit=10)[0]["verified"].startswith("балл 1"),
      "вердикт виден в списке")
check(storage.corpus_verify("нет-такого-id", "x") is False,
      "вердикт несуществующей записи отвергнут")

# ------------------------------------------------------------------- отбор
storage.corpus_add("stud-1", "monologue", "v-42-1", AUDIO, "audio/webm", 60.0,
                   "I think that", "", 7, 10, {"errors_n": 3})
storage.corpus_add("stud-2", "reading", "v-39-2", AUDIO, "audio/webm", 40.0,
                   "Another text", "Another text", 0, 1, {"errors_n": 6})
check(storage.corpus_count_for("stud-1") == 2, "счёт по ученику")
check(storage.corpus_count_for("stud-1", "reading") == 1, "счёт по ученику и типу")
check(len(storage.corpus_list(kind="reading")) == 2, "фильтр по типу задания")
check(len(storage.corpus_list(unverified_only=True)) == 2,
      "фильтр «ещё не проверено владельцем»")

stats = storage.corpus_stats()
check(stats["total"] == 3 and stats["students"] == 2, "сводка считает записи и учеников",
      str(stats))
check(set(stats["by_kind"]) == {"reading", "monologue"}, "разрез по заданиям",
      str(stats["by_kind"]))
check(stats["by_kind"]["reading"]["avg_pct"] == 50.0,
      "средний процент по типу (1/1 и 0/1 -> 50%)", str(stats["by_kind"]["reading"]))
check(stats["verified"] == 1, "проверенных ровно одна")

# -------------------------------------------------------------------- отзыв
check(storage.corpus_delete(cid), "запись удаляется (отзыв согласия)")
check(storage.corpus_count_for("stud-1") == 1, "после удаления счёт упал")
check(storage.corpus_audio(cid) is None, "удалённый звук не отдаётся")

# ------------------------------------------- согласие: белый список настроек
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main  # noqa: E402

check(main._sanitize_settings({"corpus_consent": True}) == {"corpus_consent": True},
      "согласие проходит белый список настроек")
check(main._sanitize_settings({"corpus_consent": "да"}) == {},
      "строка вместо флага согласия отвергнута")
check("corpus_consent" not in main._sanitize_settings({"theme": "dark"}),
      "согласие не появляется само собой")

# Сбор молчит, когда согласия нет: проверяем через настоящую функцию, подменив
# только запись в базу (чтобы поймать именно логику предохранителя).
#
# _storage_ok обязателен: без него сбор отказывается ВСЕГДА, и проверка
# «без согласия не пишем» была бы ложно-зелёной — она поймала бы выключенную
# базу вместо отсутствия согласия (что и случилось при первом прогоне).
main._storage_ok = True
main.storage._SQLITE_PATH = tmp
saved_add = storage.corpus_add
calls: list = []
storage.corpus_add = lambda *a, **k: calls.append(a) or "id"
storage.save_settings("stud-3", json.dumps({"theme": "dark"}))
main._collect_corpus_bg("stud-3", "reading", "v1", AUDIO, "audio/webm", 30.0,
                        "text", "ref", {"score": 1, "max_score": 1})
import time as _t
_t.sleep(0.4)
check(calls == [], "БЕЗ СОГЛАСИЯ не записано ничего", f"вызовов {len(calls)}")

storage.save_settings("stud-3", json.dumps({"corpus_consent": True}))
main._collect_corpus_bg("stud-3", "reading", "v1", AUDIO, "audio/webm", 30.0,
                        "text", "ref", {"score": 1, "max_score": 1})
_t.sleep(0.4)
check(len(calls) == 1, "с согласием запись пошла", f"вызовов {len(calls)}")
storage.corpus_add = saved_add

# ------------------------------------------------------------ длинная запись
calls2: list = []
storage.corpus_add = lambda *a, **k: calls2.append(a) or "id"
main._collect_corpus_bg("stud-3", "reading", "v1", AUDIO, "audio/webm",
                        main.CORPUS_MAX_SEC + 10, "text", "ref", {})
_t.sleep(0.3)
check(calls2 == [], "слишком длинная запись отсеяна до потока")
storage.corpus_add = saved_add

# --------------------------------------------------------------- разметка
labels = main._corpus_labels("reading", {
    "score": 1, "max_score": 1,
    "criteria": [{"key": "phonetic", "score": 1, "max": 1}],
    "errors": [{"cat": "phon", "quote": "bridge", "correction": "bridge"}],
    "delivery": {"wpm": 120, "pauses": 3, "finished": True, "junk": "не нужно"},
}, {"seconds": 42.0, "loud_frames": 900})
check(labels["_score"] == 1 and labels["_max"] == 1, "балл вынесен в свои поля")
check(labels["criteria"]["phonetic"]["score"] == 1, "критерии разложены")
check(labels["errors_n"] == 1 and labels["errors"][0]["quote"] == "bridge",
      "ошибки с цитатами сохранены")
check("junk" not in labels.get("delivery", {}), "лишние поля подачи отброшены")
check(labels["audio"]["seconds"] == 42.0, "осмотр звука приложен")
check(labels["stt"] and labels["model"], "модели записаны — иначе не понять, чей это балл")

# ------------------------------------------------------ бэкап корпус НЕ тянет
dump = storage.dump_all()
check("voice_corpus" not in dump,
      "ночной бэкап НЕ тащит корпус (иначе дамп вырастет до сотен МБ)")
dump_img = storage.dump_all(with_images=True)
check("voice_corpus" not in dump_img, "и с картинками тоже не тащит")

print()
if failed:
    print(f"ПРОВАЛ: {failed}")
    sys.exit(1)
print("Все проверки прошли: корпус голоса.")
