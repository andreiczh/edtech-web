"""Проверка допуска к озвучке: форма запроса и сверка с эталоном.

Сети не требует.

Запуск:  .\\.venv\\Scripts\\python.exe test_speak_check.py
"""

from __future__ import annotations

import sys

import speak_check

_fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _fails.append(name)


print("Допуск к озвучке")

# --- форма: что такое «слово» -------------------------------------------
for good in ("observed", "lifespan", "medium-sized", "can't", "they can not",
             "  Parrots  "):
    check(f"слово проходит: {good.strip()!r}",
          speak_check.word_problem(good) == "",
          f"({speak_check.word_problem(good)})")

for bad, why in (
    ("", "пусто"),
    ("   ", "одни пробелы"),
    ("Привет, как дела", "кириллица"),
    ("word " * 12, "слишком длинно"),
    ("one two three four", "четыре слова"),
    ("Buy cheap pills now!", "знаки препинания и реклама"),
    ("12345", "цифры"),
    ("a.b", "точка внутри"),
):
    check(f"отклоняется ({why})", speak_check.word_problem(bad) != "")

check("причина отказа человеческая и по-русски",
      "слов" in speak_check.word_problem("one two three four").lower())

# Длина считается по ЗНАКАМ, а не только по словам: два очень длинных слова
# в потолок не влезают, хотя токенов всего два.
check("два очень длинных слова не проходят по длине",
      speak_check.word_problem(
          "antidisestablishmentarianism antidisestablishmentarianism") != "")
# А три обычных слова в 48 знаков влезают и проходить обязаны.
check("три обычных слова проходят",
      speak_check.word_problem("have been observed") == "",
      f"({speak_check.word_problem('have been observed')})")

# --- сверка с эталоном ---------------------------------------------------
REF = ("Some par rot species from the South American continent have been "
       "observed to eat clay. They can’t be bought in a pet shop. Small ones "
       "live up to twenty years, whereas medium-sized parrots live longer.")

check("слово из эталона проходит", speak_check.missing_from("observed", REF) == [])
check("регистр не мешает", speak_check.missing_from("Observed", REF) == [])
check("типографский апостроф равен обычному",
      speak_check.missing_from("can't", REF) == []
      and speak_check.missing_from("can’t", REF) == [])
check("дефис — это два слова, и оба в эталоне",
      speak_check.missing_from("medium-sized", REF) == []
      and speak_check.missing_from("medium sized", REF) == [])
check("связка соседних слов проходит",
      speak_check.missing_from("been observed", REF) == [])

check("чужое слово не проходит",
      speak_check.missing_from("kangaroo", REF) == ["kangaroo"])
check("названы ИМЕННО лишние слова",
      speak_check.missing_from("observed kangaroo", REF) == ["kangaroo"])

# Сверка ПОСЛОВНАЯ: подстрокой «par» нашлась бы внутри «parrots», и обрывок
# проезжал бы как настоящее слово.
check("обрывок слова не считается словом из эталона",
      speak_check.missing_from("parr", REF) == ["parr"])
check("а целое слово из эталона — считается",
      speak_check.missing_from("parrots", REF) == [])

# Порядок не важен: цитата разбора склеивает куски как ей удобно.
check("порядок слов не требуется",
      speak_check.missing_from("clay observed", REF) == [])

# Пустой эталон = сверять не с чем; молча пропускаем, решение за формой.
check("пустой эталон никого не обвиняет",
      speak_check.missing_from("anything", "") == [])

print()
if _fails:
    print(f"ПРОВАЛЕНО: {len(_fails)} — " + ", ".join(_fails))
    sys.exit(1)
print("Всё сошлось: слово пройдёт, текст и чужое — нет.")
