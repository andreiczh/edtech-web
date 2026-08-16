"""Тесты копилки несогласий: разбор жалобы + хранение + разметка вердиктом.

Запуск: cd backend && python test_disputes.py

Проверяем ровно то, из-за чего копилка может оказаться бесполезной ПОЗЖЕ, когда
в ней уже накопятся сотни записей:
  1) неполная жалоба не должна попадать в базу — иначе набор для калибровки
     разбавляется мусором, который потом надо руками отсеивать;
  2) кластеризация должна быть жёсткой: код причины из закрытого списка и
     применимый к тому, что оспаривается;
  3) обстановка спора обязана переживать сохранение целиком и разбираться
     обратно — обрезанный посередине JSON равен потерянному контексту;
  4) миграция должна дописывать колонки к УЖЕ СУЩЕСТВУЮЩЕЙ таблице: на проде
     (Neon) таблица disputes создана в старом виде и её никто не пересоздаёт.

База — временный файл sqlite, боевой pingo.db не трогаем.
"""

from __future__ import annotations

import base64
import json
import os
import re
import tempfile

import disputes

failed = 0


def check(ok: bool, name: str, extra: str = "") -> None:
    global failed
    if ok:
        print(f"OK   {name}")
    else:
        failed += 1
        print(f"FAIL {name}{(' — ' + extra) if extra else ''}")


def eq(actual, expected, name: str) -> None:
    check(actual == expected, name, f"ожидалось {expected!r}, получено {actual!r}")


# ------------------------------------------------------------ разбор жалобы

FULL = {
    "kind": "monologue", "target": "criterion", "target_key": "K1",
    "target_label": "Решение коммуникативной задачи", "reason": "unfair",
    "comment": "Аспект 2 я раскрыл: сказал про экономию времени",
    "score": 2, "max": 3, "claim_score": 3,
    "transcript": "I would like to tell you about these two photos",
    "feedback": {"score": 2, "criteria": [{"key": "K1", "score": 2}]},
    "context": {"brief": "Task 4. You and your friend...", "photoFacts": ["a", "b"]},
}


def sent(**over) -> tuple[dict | None, str]:
    body = dict(FULL)
    body.update(over)
    return disputes.normalize(body)


data, err = disputes.normalize(dict(FULL))
check(data is not None, "полная жалоба принимается", err)
if data:
    eq(data["reason"], "unfair", "причина сохранена")
    eq(data["claim_score"], 3, "балл по мнению ученика сохранён")
    eq(json.loads(data["context"])["photoFacts"], ["a", "b"], "обстановка разбирается обратно")
    eq(json.loads(data["feedback"])["score"], 2, "снимок разбора разбирается обратно")

# --- чего быть не должно
check(sent(kind="essay")[0] is None, "чужой тип задания отвергнут")
check(sent(target="nowhere")[0] is None, "неизвестный объект спора отвергнут")
check(sent(reason="zzz")[0] is None, "неизвестная причина отвергнута")
# Самая коварная ошибка формы: причина настоящая, но не про этот объект.
check(sent(reason="tone")[0] is None, "причина не из этой области отвергнута")
check(sent(comment="не так")[0] is None, "слишком короткое объяснение отвергнуто")
check(sent(comment="   " + "x" * 3)[0] is None, "пробелы за длину не считаются")
check(sent(transcript="")[0] is None, "жалоба без улики отвергнута")

# --- «записали не то» без «а что на самом деле» бесполезна: проверить нечем
check(sent(reason="misheard", said="")[0] is None, "misheard без своей версии отвергнут")
d, _ = sent(reason="misheard", said="I said 'their', not 'there'")
check(d is not None and d["said"].startswith("I said"), "misheard со своей версией принят")

# --- отзыв о приложении: улики нет и не требуется
d, e = disputes.normalize({"kind": "app", "target": "app", "reason": "bug",
                           "comment": "Кнопка разбора не нажимается на телефоне"})
check(d is not None, "отзыв о приложении принимается без расшифровки", e)

# --- балл: -1 значит «дело не в балле», выше максимума не бывает
eq(sent(claim_score=-1)[0]["claim_score"], -1, "«дело не в балле» сохраняется как -1")
eq(sent(claim_score=99)[0]["claim_score"], 3, "балл выше максимума подрезан")
eq(sent(claim_score="три")[0]["claim_score"], -1, "нечисловой балл не роняет разбор")

# --- обстановка больше лимита остаётся ВАЛИДНЫМ json
big, _ = sent(context={"text": "щ" * 20000})
parsed = json.loads(big["context"])
check(parsed.get("_truncated") is True, "переросшая обстановка помечена как урезанная")
check(len(big["context"]) < 13000, "переросшая обстановка подрезана")

# --- снимок экрана: принимаем картинку, отвергаем всё остальное
PNG = base64.b64encode(
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 200).decode()
JPEG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 200).decode()

d, e = sent(shot={"mime": "image/png", "data": PNG})
check(d is not None and d["shot"]["mime"] == "image/png", "PNG принимается", e)
d, _ = sent(shot={"mime": "image/png", "data": JPEG})
# Тип берём ПО СОДЕРЖИМОМУ: клиент заявил png, приехал jpeg — верим байтам.
check(d is not None and d["shot"]["mime"] == "image/jpeg",
      "тип снимка определяется по содержимому, а не по словам клиента")

# Под видом картинки может приехать что угодно, и оно попадёт в <img> в
# админке владельца. Отвергаем по сигнатуре, а не по расширению.
html = base64.b64encode(b"<svg onload=alert(1)></svg>").decode()
d, e = sent(shot={"mime": "image/png", "data": html})
check(d is None, "не-картинка под видом картинки отвергнута")
check("PNG" in e or "картинк" in e, "и объяснение человеческое", e)

check(sent(shot={"mime": "image/png", "data": "не base64!!!"})[0] is None,
      "мусор вместо base64 отвергнут")

# Base64 разбираем СТРОГО. Небрежный разбор молча выбрасывает посторонние
# символы, и строка с мусором внутри всё равно превращается в картинку —
# то есть проверка перестаёт быть проверкой. Тест ловит именно это: без
# validate=True такая строка развернулась бы в валидный PNG и прошла.
sloppy = PNG[:8] + "!!!" + PNG[8:]
check(disputes.screenshot({"data": sloppy})[0] is None,
      "base64 с мусором внутри отвергнут, а не почищен молча")

# Слишком большой снимок должен отвергаться ИМЕННО за размер. Раньше здесь
# стояла строка из букв «A»: она отсеивалась заодно и как не-картинка, и тест
# проходил бы даже со снятым лимитом. Берём НАСТОЯЩИЙ PNG нужной длины.
big_png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 600_000).decode()
check(len(big_png) > disputes.MAX_SHOT_B64, "заготовка для проверки лимита достаточно велика")
d, e = disputes.screenshot({"data": big_png})
check(d is None and "больш" in e, "слишком большой снимок отвергнут ЗА РАЗМЕР", e)
check(sent(shot={"mime": "image/png", "data": big_png})[0] is None,
      "и всю жалобу с ним тоже не принимаем молча")

check(sent(shot=None)[0] is not None, "жалоба без снимка по-прежнему проходит")
check(disputes.screenshot(None) == (None, ""), "пустой снимок — не ошибка")
check(disputes.screenshot({"data": ""}) == (None, ""), "пустые данные — не ошибка")

# --- вердикт владельца
v, _ = disputes.resolution({"status": "done", "verdict": "student", "verdict_score": 3,
                            "verdict_note": "аспект 2 действительно раскрыт"})
check(v is not None and v["verdict_score"] == 3, "вердикт владельца принимается")
check(disputes.resolution({"status": "done"})[0] is None, "разбор без вердикта отвергнут")
check(disputes.resolution({"status": "skip"})[0] is not None, "«пока не знаю» разрешено")
check(disputes.resolution({"status": "wat", "verdict": "ours"})[0] is None,
      "неизвестный статус отвергнут")

# --- каталог причин: то, что уедет на фронт
cat = disputes.catalog()
check(all(r["code"] in disputes.REASONS for r in cat["reasons"]), "каталог согласован с реестром")
check(len(disputes.reasons_for("talk_reply")) >= 4, "у реплики разговора есть свои причины")
check("unfair" not in disputes.reasons_for("talk_reply"),
      "балльной причины у реплики разговора нет")

# ------------------------------------------------------------ хранение

tmp = os.path.join(tempfile.gettempdir(), "pingo_disputes_test.db")
for suffix in ("", "-wal", "-shm"):
    try:
        os.remove(tmp + suffix)
    except OSError:
        pass

import storage  # noqa: E402 — только после подмены пути к базе

storage._SQLITE_PATH = tmp

# Сначала создаём таблицу В СТАРОМ ВИДЕ — ровно так она лежит на проде — и
# только потом зовём ensure_schema: это и есть проверка миграции.
storage._exec("CREATE TABLE IF NOT EXISTS disputes ("
              " id TEXT PRIMARY KEY, student_id TEXT NOT NULL, kind TEXT NOT NULL,"
              " variant TEXT, persona TEXT, score INTEGER, max_score INTEGER,"
              " transcript TEXT NOT NULL, feedback TEXT NOT NULL, comment TEXT,"
              " status TEXT NOT NULL DEFAULT 'new', created_at TEXT NOT NULL)")
storage._exec("INSERT INTO disputes(id, student_id, kind, transcript, feedback,"
              " comment, status, created_at) VALUES('old','stu','reading','раньше',"
              " '{}','старая жалоба','new','2026-08-01T00:00:00+00:00')")
storage.ensure_schema()

cols = storage._columns("disputes")
check({"target", "reason", "claim_score", "said", "context", "verdict",
       "verdict_score", "resolved_at"} <= cols, "миграция дописала колонки", str(sorted(cols)))

kept = [d for d in storage.disputes_list() if d["id"] == "old"]
eq(len(kept), 1, "старая жалоба пережила миграцию")
eq(kept[0]["reason"], None, "у старой жалобы причина пустая, а не выдуманная")

did = storage.dispute_add("stu-1", disputes.normalize(dict(FULL))[0])
check(bool(did), "жалоба записалась")

rows = storage.disputes_list()
row = next(r for r in rows if r["id"] == did)
eq(row["target_key"], "K1", "объект спора сохранён")
eq(row["claim_score"], 3, "требуемый балл сохранён")
eq(json.loads(row["context"])["photoFacts"], ["a", "b"], "обстановка достаётся из базы")
eq(row["status"], "new", "свежая жалоба ждёт разбора")

talk, _ = disputes.normalize({
    "kind": "talk", "target": "talk_reply", "reason": "off_context",
    "comment": "Я говорил про футбол, а он ответил про еду",
    "transcript": "I play football every Sunday",
    "context": {"turns": [{"role": "user", "content": "I play football"},
                          {"role": "assistant", "content": "What do you eat?"}]},
})
storage.dispute_add("stu-2", talk)

stats = storage.disputes_stats()
eq(stats["total"], 3, "в сводке все жалобы, включая старую")
eq(stats["pending"], 3, "все три ждут разбора")
eq(stats["by_kind"].get("talk"), 1, "разговор попал в разрез по типу")
eq(stats["by_reason"].get("off_context"), 1, "причина попала в разрез")
eq(stats["by_target"].get("criterion"), 1, "объект спора попал в разрез")

check(storage.dispute_resolve(did, "done", "student", 3, "ученик прав"),
      "вердикт сохраняется")
check(not storage.dispute_resolve("нет-такого", "done", "ours", 0, ""),
      "вердикт по несуществующей жалобе не выдумывается")

row = next(r for r in storage.disputes_list() if r["id"] == did)
eq(row["verdict"], "student", "вердикт лёг в строку")
eq(row["status"], "done", "статус сменился")
check(bool(row["resolved_at"]), "время разбора проставлено")
eq(storage.disputes_stats()["pending"], 2, "разобранная больше не ждёт")
eq(storage.disputes_stats()["by_verdict"].get("student"), 1, "вердикт попал в разрез")
eq(len(storage.disputes_list("new")), 2, "фильтр по статусу работает")

# --- снимки экрана: отдельная таблица, признак в списке, картинка по ручке
shot_case, _ = disputes.normalize(dict(FULL, shot={"mime": "image/png", "data": PNG}))
did_shot = storage.dispute_add("stu-3", {k: v for k, v in shot_case.items() if k != "shot"})
sid = storage.shot_add(did_shot, shot_case["shot"]["mime"],
                       shot_case["shot"]["data"], shot_case["shot"]["bytes"])

got = storage.shot_get(sid)
check(got is not None and got[0] == "image/png", "снимок достаётся по id")
check(got is not None and got[1] == PNG, "снимок не испортился в базе")
check(storage.shot_get("нет-такого") is None, "несуществующий снимок не выдумывается")

marks = storage.shots_for([did_shot, did])
check(did_shot in marks and marks[did_shot][0]["id"] == sid,
      "список жалоб знает, что снимок есть")
check("data" not in marks[did_shot][0],
      "но саму картинку в список не тащит — иначе сотня жалоб весит десятки МБ")
check(did not in marks, "у жалобы без снимка признака нет")
eq(storage.disputes_stats()["with_shot"], 1, "снимки посчитаны в сводке")

# Бэкап обязан выносить жалобы целиком: Neon free без бэкапов, и потеря
# калибровочного набора невосполнима — заново его не соберёшь.
dump = storage.dump_all()
check("dispute_shots" not in dump,
      "обычный бэкап не тащит картинки — иначе ночной дамп распухнет")
check(len(storage.dump_all(with_images=True).get("dispute_shots", [])) == 1,
      "с флагом картинок снимки в бэкап попадают")
check("disputes" in dump and len(dump["disputes"]) == len(storage.disputes_list()),
      "в бэкап попадают ВСЕ жалобы, а не часть")
check("context" in dump["disputes"][0], "обстановка попадает в бэкап")

# ------------------------------------- фронт и сервер знают одни и те же коды
#
# Списки причин лежат в двух местах: тексты — интерфейс, им место во фронте,
# а проверка — на сервере. Разъехавшись, они дадут жалобу с кодом, который
# сервер молча отвергнет, и потеря найдётся через месяц по дыре в статистике.
# Поэтому сверяем прямо файлами.
_ts = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "ege2",
                   "dispute.ts")
if os.path.exists(_ts):
    with open(_ts, encoding="utf-8") as fh:
        source = fh.read()
    front = set(re.findall(r"^\s*code: '([a-z_]+)',", source, re.MULTILINE))
    eq(front, set(disputes.REASONS), "коды причин на фронте и на сервере совпадают")
    targets = set(re.findall(r"'([a-z_]+)'", source[source.index("DisputeTarget ="):
                                                   source.index("export type DisputeKind")]))
    eq(targets, set(disputes.TARGETS), "объекты спора на фронте и на сервере совпадают")
else:
    check(False, "файл src/ege2/dispute.ts на месте", _ts)

# ------------------------------------------------- копилка произношения
# Порог выбирается только по словам, которые ученик ПЫТАЛСЯ произнести:
# пропущенные куски и строки до колонки spoken в распределение не идут,
# но остаются в базе и видны счётчиком excluded.

cols = storage._columns("pron_samples")
check({"method", "spoken"} <= cols, "миграция дописала method и spoken")

# Строка «до колонки» — spoken NULL, как лежит на проде.
storage._exec("INSERT INTO pron_samples(id, student_id, kind, variant, word,"
              " ord, p, p_norm, created_at) VALUES('legacy','stu','reading',"
              " 'v0','ghost',0,0.001,0.001,'2026-08-10T00:00:00+00:00')")
storage.pron_add("stu", "reading", "v1", [
    {"word": "library", "p": 0.9, "p_norm": 1.0, "dur": 0.3, "spoken": 1},
    {"word": "council", "p": 0.5, "p_norm": 0.6, "dur": 0.3, "spoken": 1},
    {"word": "money", "p": 0.001, "p_norm": 0.001, "dur": 0.2, "spoken": 0},
], "base.en", "forced")
storage.pron_add("stu", "talk", "", [
    {"word": "skateboard", "p": 0.8, "p_norm": 0.95, "dur": 0.4, "spoken": 1},
], "base.en", "cross")

st = storage.pron_stats()
fr, cr = st["by_method"]["forced"], st["by_method"]["cross"]
eq(fr["total"], 2, "forced: в распределении только spoken=1")
eq(fr["excluded"], {"unspoken": 1, "legacy": 1},
   "forced: пропуск и старая строка видны счётчиком")
check(all(w["word"] != "money" for w in fr["worst"]),
      "непрозвучавшее слово не лезет в слабые")
eq(cr["total"], 1, "cross: свои слова на месте")
eq(st["total"], 5, "общий счёт считает всё записанное")

raw = storage.pron_raw()
eq(len(raw), 5, "сырая выгрузка отдаёт все строки")
check({"word", "ord", "p_norm", "method", "spoken", "variant"} <=
      set(raw[0].keys()), "в сырой выгрузке есть чем разбирать хвост")

print()
print("ВСЁ ЗЕЛЕНО" if not failed else f"ПРОВАЛОВ: {failed}")
raise SystemExit(1 if failed else 0)
