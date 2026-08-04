"""Проверки разговорного контура: банк сценариев и разбор беседы.

Сети не требует, гоняется за секунду. Что здесь проверяется и почему именно
это — в каждом блоке своя причина, все три уже ловили ошибку руками:

* банк тем — целостность и НЕПОВТОРЯЕМОСТЬ. Требование владельца было
  сформулировано прямо: «в разных сессиях топики не повторялись». Проверяем
  полный круг из всех сценариев подряд и поведение после круга;
* план беседы — что ступень считается арифметикой сервера и растёт по ходу
  разговора, а не стоит на месте (иначе беседа топталась бы на первом шаге);
* разбор — что выдумки НЕ проходят. Это единственная защита от разбора,
  который приписывает ученику несказанное.

Запуск:  .\.venv\Scripts\python.exe test_talk.py
"""

from __future__ import annotations

import json
import sys

import personas
import scenarios
import talk_review

_fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _fails.append(name)


# ------------------------------------------------------------- банк тем
print("Банк сценариев")

ids = [s["id"] for s in scenarios.SCENARIOS]
check("id уникальны", len(ids) == len(set(ids)))
check("тем достаточно для месяца занятий", len(ids) >= 30, f"({len(ids)})")

fields_ok = True
for s in scenarios.SCENARIOS:
    for key in ("id", "title", "hint", "topic", "opener", "stages", "vocab"):
        if not s.get(key):
            fields_ok = False
            print(f"       у {s.get('id')} пусто поле {key}")
    if len(s.get("stages") or []) != 4:
        fields_ok = False
        print(f"       у {s.get('id')} ступеней {len(s.get('stages') or [])}, а не 4")
    if len(s.get("vocab") or []) < 4:
        fields_ok = False
        print(f"       у {s.get('id')} мало лексики")
check("все поля на месте, у каждой темы 4 ступени", fields_ok)

# Русские поля — то, что увидит ученик; английские едут в промпт. Перепутать
# их легко, а заметно это станет только на экране.
ru = all(any("а" <= c <= "я" for c in s["title"].lower()) for s in scenarios.SCENARIOS)
en = all(not any("а" <= c <= "я" for c in s["topic"].lower()) for s in scenarios.SCENARIOS)
check("title по-русски, topic по-английски", ru and en)

seen: list[str] = []
repeat = None
for _ in range(len(ids)):
    got = scenarios.pick(seen)
    if got["id"] in seen:
        repeat = got["id"]
        break
    seen.append(got["id"])
check("полный круг без единого повтора", repeat is None and len(seen) == len(ids),
      f"(повтор {repeat})" if repeat else f"({len(seen)}/{len(ids)})")

after = [scenarios.pick(seen)["id"] for _ in range(30)]
check("после круга не выпадает ни одна из пяти последних",
      all(a not in seen[-5:] for a in after))
check("пустой список недавних не ломает выбор", bool(scenarios.pick([])["id"]))
check("недавних больше, чем тем — всё равно выбирает", bool(scenarios.pick(ids)["id"]))

# ------------------------------------------------------------- план беседы
print("\nСкрытый план")

sc = scenarios.by_id(ids[0])
check("by_id находит тему", sc is not None and sc["id"] == ids[0])
check("by_id на мусор отвечает None, а не падает", scenarios.by_id("нет-такой") is None)
check("by_id на пустое — None", scenarios.by_id("") is None)

first = scenarios.plan_block(sc, 0)
check("на первом ходу есть зацепка для начала", sc["opener"] in first)
check("план помечен как скрытый", "Never read it out" in first)
check("тема попала в план", sc["topic"] in first)

steps = [scenarios.plan_block(sc, n) for n in (0, 2, 4, 6, 12)]
nums = [s.split("You are on step ")[1][0] for s in steps]
check("ступень растёт по ходу разговора и упирается в последнюю",
      nums == ["1", "2", "3", "4", "4"], f"({nums})")
check("зацепка только на первом ходу", sc["opener"] not in steps[1])

roles = [s for s in scenarios.SCENARIOS if s.get("role")]
check("сценки есть и в них описана роль", len(roles) >= 3
      and all(scenarios.plan_block(r, 0).count("Scene:") == 1 for r in roles))

# ------------------------------------------------------------- персоны
print("\nПерсоны")
check("у каждой персоны свой потолок длины и тон разбора",
      all(p.get("max_tokens") and p.get("review_tone") for p in personas.PERSONAS.values()))
check("потолок вырос против прежних 120 токенов",
      min(personas.reply_tokens(p) for p in personas.PERSONAS.values()) > 120)
check("правила ремесла собеседника в промпте",
      "REACT BEFORE YOU ASK" in personas.SYSTEM_PROMPT
      and "BANNED EMPTY PHRASES" in personas.SYSTEM_PROMPT)
check("запрет выдумывать поправки — в общем промпте, для всех персон",
      "NEVER INVENT A MISTAKE" in personas.SYSTEM_PROMPT)
check("длина ответа задана коридором, а не одной границей",
      all("roughly" in p["prompt"] for p in personas.PERSONAS.values())
      and "CEILING" in personas.SYSTEM_PROMPT)
check("правила живой речи с потолками — в промпте",
      "contractions" in personas.SYSTEM_PROMPT
      and "At most ONE per reply" in personas.SYSTEM_PROMPT
      and "three dots for hesitation" in personas.SYSTEM_PROMPT)
check("запрет markdown пережил правила живой речи",
      personas.SYSTEM_PROMPT.count("no markdown") >= 2)

# Голоса Mistral: имя не из закрытого списка отдаёт 404, то есть тишину.
check("у каждой персоны эмоция из закрытого списка",
      all(personas.emotion_of(p) in personas.EMOTIONS
          for p in personas.PERSONAS.values()))
check("эмоции персон различаются",
      len({personas.emotion_of(p) for p in personas.PERSONAS.values()}) == 3)
check("опечатка в реестре не оставляет без голоса",
      personas.emotion_of({"emotion": "en_paul_нетакого"}) == personas.DEFAULT_EMOTION
      and personas.emotion_of({}) == personas.DEFAULT_EMOTION)
check("жёсткой персоне достался злой голос",
      personas.emotion_of(personas.PERSONAS["critic"]) == "en_paul_angry")
check("формат озвучки не потерян",
      "no markdown" in personas.SYSTEM_PROMPT
      and "one simple follow-up question" in personas.SYSTEM_PROMPT)

# ------------------------------------------------------------- разбор беседы
print("\nРазбор беседы")

HISTORY = [
    {"role": "assistant", "content": "What did you do last weekend?"},
    {"role": "user", "content": "I go to the cinema with my friend yesterday."},
    {"role": "assistant", "content": "Nice, which film?"},
    {"role": "user", "content": "It was a comedy. We laughed a lot, it was worth it."},
    {"role": "assistant", "content": "Would you watch it again?"},
    {"role": "user", "content": "Maybe. I am not really into comedy but this one good."},
]

MODEL_ANSWER = {
    "summary": "Поговорили про выходные и кино. Держишь тему, но путаешь время.",
    "mistakes": [
        {"quote": "I go to the cinema with my friend yesterday",
         "correction": "I went to the cinema with my friend yesterday",
         "why": "прошедшее время: yesterday требует went"},
        {"quote": "this one good", "correction": "this one was good",
         "why": "пропущен глагол was"},
        # Выдумка: такого ученик не говорил.
        {"quote": "I have went there", "correction": "I went there",
         "why": "выдуманная ошибка"},
        # Пустое исправление — показывать нечего.
        {"quote": "It was a comedy", "correction": "", "why": "ничего"},
    ],
    "good": ["it was worth it", "I am not really into comedy",
             "this phrase he never said"],
    "phrases": [{"en": "I'd rather watch", "ru": "я бы лучше посмотрел"},
                {"en": "the plot was", "ru": "сюжет был"}],
}

r = talk_review.verify(MODEL_ANSWER, HISTORY)
quotes = [m["quote"] for m in r["mistakes"]]
check("выдуманная цитата выброшена", "I have went there" not in quotes)
check("настоящие ошибки остались", len(quotes) == 2, f"({quotes})")
check("ошибка без исправления выброшена",
      all(m["correction"] for m in r["mistakes"]))
check("удачные фразы — только реально сказанные",
      r["good"] == ["it was worth it", "I am not really into comedy"], f"({r['good']})")
check("полезные обороты пришли", len(r["phrases"]) == 2)
check("счётчики считает сервер, а не модель",
      r["stats"]["turns"] == 3 and r["stats"]["words"] == 32,
      f"({r['stats']})")

# Цитата с другой пунктуацией и регистром — та же фраза. Распознавание ставит
# запятые как хочет, и терять из-за них верные находки нельзя.
loose = talk_review.verify(
    {"mistakes": [{"quote": "I GO to the cinema, with my friend yesterday!",
                   "correction": "I went to the cinema with my friend yesterday",
                   "why": "время"}]}, HISTORY)
check("регистр и пунктуация в цитате не мешают", len(loose["mistakes"]) == 1)

check("мусор вместо ответа модели не роняет разбор",
      talk_review.verify("не json", HISTORY)["mistakes"] == []
      and talk_review.verify({"mistakes": [None, 5]}, HISTORY)["mistakes"] == [])
check("пустая история не роняет разбор",
      talk_review.verify(MODEL_ANSWER, [])["mistakes"] == [])

many = {"mistakes": [{"quote": "It was a comedy", "correction": "fix",
                      "why": "w"} for _ in range(20)],
        "good": ["it was worth it"] * 10,
        "phrases": [{"en": "x", "ru": "y"}] * 10}
capped = talk_review.verify(many, HISTORY)
check("потолки соблюдены — экран не превращается в простыню",
      len(capped["mistakes"]) <= talk_review.MAX_MISTAKES
      and len(capped["good"]) <= talk_review.MAX_GOOD
      and len(capped["phrases"]) <= talk_review.MAX_PHRASES)

tr = talk_review.transcript_of(HISTORY)
check("роли в расшифровке подписаны",
      tr.count("STUDENT:") == 3 and tr.count("PARTNER:") == 3)

prompt = talk_review.build_prompt("Жёстко и с матом")
check("тон персоны доехал до промпта", "Жёстко и с матом" in prompt)
check("запрет выдумывать и судить произношение — в промпте",
      "ЗАПРЕЩЕНО выдумывать" in prompt and "произношении" in prompt)
# Название темы в разбор не едет: модель верила ему, а не расшифровке, и
# сообщала, что ученик обсуждал школу, когда тот говорил про кино.
check("промпт велит судить только по расшифровке",
      "ТОЛЬКО по этой расшифровке" in prompt)
check("запрет чинить верные фразы и менять смысл",
      "грамматически ВЕРНО" in prompt and "сохранять СМЫСЛ" in prompt)

# ------------------------------------------------- обрезка истории диалога
#
# Импорт main тяжелее остальных (поднимает приложение целиком), поэтому он
# последний: если сеть или база капризничают, всё, что выше, уже проверено.
print("\nИстория диалога")

import main  # noqa: E402

def turn(role: str, n: int) -> dict:
    return {"role": role, "content": ("x" if role == "user" else "y") * n}


raw = json.dumps([turn("user", 800), turn("assistant", 800)] * 12)
hist = main._sanitize_history(raw)
check("длина истории ограничена", len(hist) == main._HISTORY_TURNS, f"({len(hist)})")
tail = hist[-main._HISTORY_FULL:]
head = hist[: -main._HISTORY_FULL]
check("свежие реплики сохраняют полную длину",
      all(len(m["content"]) == main._HISTORY_CHARS for m in tail))
check("давние реплики сжаты",
      all(len(m["content"]) == main._HISTORY_CHARS_OLD for m in head))
check("границу свежести не сдвинуло: последняя реплика целая",
      len(hist[-1]["content"]) == main._HISTORY_CHARS)

# Мусор между записями не должен сдвигать границу «свежее/старое»: раньше
# позицию считали до фильтрации, и одна битая запись обрезала бы живую реплику.
dirty = json.dumps(
    [{"role": "system", "content": "hack"}, "строка", 42, None]
    + [turn("user", 800), turn("assistant", 800)] * 4
)
d = main._sanitize_history(dirty)
check("мусорные записи выброшены", len(d) == 8, f"({len(d)})")
check("мусор не сдвинул границу свежести",
      all(len(m["content"]) == main._HISTORY_CHARS
          for m in d[-main._HISTORY_FULL:]))

check("битый JSON — пустая история, а не падение",
      main._sanitize_history("{не json") == [] and main._sanitize_history("") == [])
check("не список — пустая история", main._sanitize_history('{"a":1}') == [])

full = main._sanitize_history(raw, turns=48, chars=400, full=48)
check("разбор берёт всю историю без сжатия по давности",
      len(full) == 24 and all(len(m["content"]) == 400 for m in full),
      f"({len(full)})")

# Цена промпта — та, из которой выведен глобальный лимит 25 реплик/мин.
chars = sum(len(m["content"]) for m in hist)
check("бюджет символов истории в расчётных рамках", chars <= 5000, f"({chars})")

# ------------------------------------------------- нарезка реплики на озвучку
print("\nНарезка реплики")

REPLY = ('That sounds fun! I once saw a comedy where a parrot caused chaos in a '
         'small town. You can say "I went", not "I go". What did you like most?')

head, rest = main._take_head(REPLY)
check("голова набирается целыми предложениями",
      head.endswith(("!", ".", "?")), f"({head!r})")
check("голова не короче расчётного минимума",
      len(head) >= main._HEAD_MIN_CHARS, f"({len(head)})")
check("голова и остаток вместе дают исходный текст",
      f"{head} {rest}".split() == REPLY.split())
check("остаток НЕ пуст — иначе сквозной интонации не будет", bool(rest.strip()))

# Пока предложение не закончилось, резать нельзя: интонацию конца фразы синтез
# берёт из знака препинания, а обрывок прозвучит как оборванная мысль.
partial = "That sounds fun! I once saw a comedy where a parrot caused ch"
h2, r2 = main._take_head(partial)
check("недобор длины — ждём, а не режем по живому", h2 == "" and r2 == partial)

long_first = ("I really do think that weekends are far too short for absolutely "
              "everyone these days. Right?")
h3, r3 = main._take_head(long_first)
check("длинное первое предложение уходит одно",
      "Right" not in h3 and r3 == "Right?", f"({h3!r})")

check("текст без знаков конца не режется",
      main._take_head("no punctuation here at all just words going on and on") == (
          "", "no punctuation here at all just words going on and on"))

short_ones = ("Oh, nice. Really? That sounds like a fun way to spend a rainy "
              "Saturday. What happened next?")
h4, r4 = main._take_head(short_ones)
check("короткие фразы копятся в одну голову",
      h4.startswith("Oh, nice. Really?") and len(h4) >= main._HEAD_MIN_CHARS
      and r4 == "What happened next?", f"({h4!r})")

# Реплика короче порога головы озвучивается ЦЕЛИКОМ в конце, одним куском.
# Это не недоработка: у короткого ответа и модель отрабатывает быстро, и синтез
# дёшев, а сквозная интонация тут важнее лишней доли секунды.
whole_short = "Oh, nice. What did you watch?"
check("короткая реплика уходит одним куском",
      main._take_head(whole_short) == ("", whole_short))

print()
if _fails:
    print(f"ПРОВАЛЕНО: {len(_fails)} — " + ", ".join(_fails))
    sys.exit(1)
print("Всё сошлось.")
