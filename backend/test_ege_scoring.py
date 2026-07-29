"""Проверка шкалы оценивания против официальных образцов ФИПИ.

В разделе II методички разобраны реальные работы участников ЕГЭ: эксперты
выставили аспектам «+», «±», «−», посчитали ошибки и вывели итоговый балл.
Здесь эти же входные данные подаются в наш модуль — итог обязан совпасть
с официальным до балла. Если однажды не совпадёт, значит шкалу сломали.

Запуск (без pytest, отдельной зависимости не нужно):
    .\.venv\Scripts\python.exe test_ege_scoring.py
"""

from __future__ import annotations

import sys

import ege_scoring as sc

FULL, PARTIAL, MISSING = sc.FULL, sc.PARTIAL, sc.MISSING


def aspects(*verdicts: str) -> list[dict]:
    return [{"verdict": v} for v in verdicts]


# --------------------------------------------------------------------------
# Задание 4: шесть работ из раздела II методички
# --------------------------------------------------------------------------
# Каждая строка: название работы, вердикты по четырём аспектам, объём в фразах,
# вступление, заключение, ошибки логики, лексико-грамматические ошибки (всего
# и грубых) и официальный итог (К1, К2, К3).
MONOLOGUE_CASES = [
    # «The games people like»: 2 аспекта не раскрыты, 2 неточны -> РКЗ 0,
    # а ноль по РКЗ обнуляет и организацию, и язык.
    ("The games people like", (PARTIAL, MISSING, PARTIAL, MISSING), 15,
     True, True, 1, 4, 1, (0, 0, 0)),
    # «Ideal weekend»: 1 полный аспект и 3 неточных; 3 ошибки логики; 5 ЛГ-ошибок.
    ("Ideal weekend", (FULL, PARTIAL, PARTIAL, PARTIAL), 15,
     True, True, 3, 5, 2, (2, 2, 2)),
    # «The best moments with grandparents»: 1 не раскрыт, 2 неточны, 1 полный.
    ("The best moments with grandparents", (MISSING, PARTIAL, FULL, PARTIAL), 15,
     True, True, 3, 6, 2, (1, 2, 1)),
    # «Hobbies» (5471): содержание идеально, 1 ошибка связки, но 11 ЛГ-ошибок.
    ("Hobbies 5471", (FULL, FULL, FULL, FULL), 15,
     True, True, 1, 11, 3, (4, 3, 0)),
    # «Volunteering» (3775): 2 неточны, 1 не раскрыт, 1 полный; больше 8 ошибок.
    ("Volunteering 3775", (PARTIAL, PARTIAL, MISSING, FULL), 14,
     True, True, 3, 9, 3, (1, 2, 0)),
    # «Sports» (9377): 3 неточны, 1 полный; 2 ошибки связок; 9 ЛГ-ошибок.
    ("Sports 9377", (PARTIAL, PARTIAL, PARTIAL, FULL), 15,
     True, True, 2, 9, 3, (2, 2, 0)),
]


def check_monologues() -> list[str]:
    bad = []
    for name, verdicts, phrases, opening, closing, logic, lex, grave, want in MONOLOGUE_CASES:
        got = sc.score_monologue(aspects(*verdicts), phrases, opening, closing, logic, lex, grave)
        marks = tuple(c["score"] for c in got["criteria"])
        ok = marks == want
        print(f"{'OK  ' if ok else 'FAIL'} задание 4 «{name}»: "
              f"К1={marks[0]} К2={marks[1]} К3={marks[2]} (итог {got['score']}/10), "
              f"эксперты: {want[0]}/{want[1]}/{want[2]}")
        if not ok:
            bad.append(f"монолог «{name}»: {marks} вместо {want}")
    return bad


# --------------------------------------------------------------------------
# Таблица РКЗ целиком: все допустимые сочетания аспектов
# --------------------------------------------------------------------------
CONTENT_TABLE = {
    (0, 0): 4, (0, 1): 3, (0, 2): 3, (0, 3): 2, (0, 4): 1,
    (1, 0): 3, (1, 1): 2, (1, 2): 1, (1, 3): 0,
    (2, 0): 1, (2, 1): 0, (2, 2): 0,
    (3, 0): 0, (3, 1): 0, (4, 0): 0,
}


def check_content_table() -> list[str]:
    bad = []
    for (missing, partial), want in sorted(CONTENT_TABLE.items()):
        got = sc.content_from_aspects(missing, partial)
        if got != want:
            bad.append(f"РКЗ при {missing} нераскрытых и {partial} неточных: {got} вместо {want}")
    print(f"{'OK  ' if not bad else 'FAIL'} таблица РКЗ: {len(CONTENT_TABLE)} сочетаний аспектов")
    return bad


def check_volume() -> list[str]:
    bad = []
    # Объём режет балл, даже если все аспекты раскрыты полностью.
    for phrases, want in ((7, 0), (8, 1), (9, 1), (10, 2), (11, 2), (12, 4), (15, 4), (20, 4)):
        got = sc.score_monologue(aspects(FULL, FULL, FULL, FULL), phrases, True, True, 0, 0, 0)
        content = got["criteria"][0]["score"]
        if content != want:
            bad.append(f"объём {phrases} фраз: РКЗ {content} вместо {want}")
    # 7 фраз и меньше — ноль за всё задание, а не только за содержание.
    zero = sc.score_monologue(aspects(FULL, FULL, FULL, FULL), 6, True, True, 0, 0, 0)
    if zero["score"] != 0:
        bad.append(f"7 и менее фраз должны обнулять задание, получили {zero['score']}")
    print(f"{'OK  ' if not bad else 'FAIL'} объём высказывания режет балл по таблице")
    return bad


def check_organization() -> list[str]:
    bad = []
    cases = [
        # (вступление, заключение, ошибки логики) -> балл
        ((True, True, 0), 3), ((True, True, 1), 3), ((True, True, 2), 2), ((True, True, 3), 2),
        ((True, True, 4), 1), ((True, True, 5), 1), ((True, True, 6), 0),
        # нет одной рамочной фразы — потолок 1 даже без других ошибок
        ((False, True, 0), 1), ((True, False, 0), 1), ((True, False, 7), 0),
        # нет обеих — 0
        ((False, False, 0), 0),
    ]
    for (opening, closing, logic), want in cases:
        got = sc.organization_score(opening, closing, logic)
        if got != want:
            bad.append(f"организация ({opening}, {closing}, {logic} ош.): {got} вместо {want}")
    print(f"{'OK  ' if not bad else 'FAIL'} организация: рамочные фразы и ошибки связок")
    return bad


def check_language() -> list[str]:
    bad = []
    cases = [
        ((0, 0), 3), ((3, 0), 3), ((3, 1), 2), ((4, 0), 2), ((5, 2), 2),
        ((5, 3), 1), ((6, 3), 1), ((7, 3), 1), ((8, 0), 0), ((4, 4), 0), ((11, 3), 0),
    ]
    for (errors, grave), want in cases:
        got = sc.language_score(errors, grave)
        if got != want:
            bad.append(f"язык ({errors} ош., {grave} грубых): {got} вместо {want}")
    print(f"{'OK  ' if not bad else 'FAIL'} язык: пороги по числу ошибок и грубости")
    return bad


# --------------------------------------------------------------------------
# Задание 1: сверка эталона с распознанным текстом
# --------------------------------------------------------------------------
REF = ("A tree is a tall plant with a trunk and branches made of wood. Trees can live for many "
       "years. The oldest tree ever discovered is approximately 5000 years old. The four main "
       "parts of a tree are the roots, the trunk, the branches, and the leaves.")


def check_reading() -> list[str]:
    bad = []

    # 1. Прочитано верно — балл есть, придирок нет.
    d = sc.reading_diff(REF, REF)
    score, note = sc.score_reading(d, 0)
    if not (score == 1 and d["coverage"] == 1.0):
        bad.append(f"чистое чтение: {score}, покрытие {d['coverage']}")

    # 2. Регистр и пунктуация не считаются ошибкой.
    d = sc.reading_diff(REF, REF.lower().replace(",", "").replace(".", ""))
    if sc.score_reading(d, 0)[0] != 1:
        bad.append("пунктуация и регистр не должны влиять на балл")

    # 3. Не дочитал хвост: два слова — прощаем, шесть — ноль.
    words = REF.split()
    d = sc.reading_diff(REF, " ".join(words[:-2]))
    if sc.score_reading(d, 0)[0] != 1:
        bad.append("недочитанные 1-2 слова не должны обнулять ответ")
    d = sc.reading_diff(REF, " ".join(words[:-6]))
    if sc.score_reading(d, 0)[0] != 0:
        bad.append("недочитанные 6 слов обязаны обнулить ответ")

    # 4. Пропущена строка в середине — ноль.
    skipped = " ".join(words[:12] + words[22:])
    d = sc.reading_diff(REF, skipped)
    if not (d["longest_missing_run"] >= sc.SKIPPED_LINE_RUN and sc.score_reading(d, 0)[0] == 0):
        bad.append(f"пропуск строки не пойман: {d['longest_missing_run']} слов подряд")

    # 5. Три подтверждённых оговорки — ноль, две — балл остаётся.
    if sc.score_reading(sc.reading_diff(REF, REF), 3)[0] != 0:
        bad.append("три перевранных слова обязаны обнулить ответ")
    if sc.score_reading(sc.reading_diff(REF, REF), 2)[0] != 1:
        bad.append("две оговорки не должны обнулять ответ")

    # 6. Улики для модели: подмену слова видно.
    d = sc.reading_diff(REF, REF.replace("tall plant", "small plant"))
    if not any("tall" in s["expected"] for s in d["swaps"]):
        bad.append("подмена слова не попала в улики")

    print(f"{'OK  ' if not bad else 'FAIL'} чтение вслух: пропуски, хвост, пропущенная строка")
    return bad


# --------------------------------------------------------------------------
# Вердикты по аспектам из признаков «да/нет»
# --------------------------------------------------------------------------
def a1(**kw) -> dict:
    """Аспект 1 со всеми признаками в норме; в kw передаём то, чего не хватило."""
    base = {"n": 1, "described_first": True, "described_second": True,
            "difference_stated": True, "difference_generalised": True,
            "linked_to_topic": True, "factual_error": False}
    return {**base, **kw}


def a23(n: int, **kw) -> dict:
    base = {"n": n, "named_first": True, "named_second": True,
            "specific_first": True, "specific_second": True}
    return {**base, **kw}


def a4(**kw) -> dict:
    base = {"n": 4, "opinion_explicit": True, "choice_stated": True, "justified": True,
            "plan_verb_form": "you would prefer", "student_verb_form": "I would prefer"}
    return {**base, **kw}


def check_aspects() -> list[str]:
    bad = []

    def verdict(check: dict) -> str:
        n = check["n"]
        return sc.aspect_verdicts([check])[n - 1]["verdict"]

    cases = [
        # Аспект 1: описания обоих фото, различие, обобщение, связь с темой.
        ("аспект 1, всё на месте", a1(), FULL),
        ("аспект 1, различие не обобщено", a1(difference_generalised=False), PARTIAL),
        ("аспект 1, есть фактическая ошибка", a1(factual_error=True), PARTIAL),
        # Работа «grandparents»: нет обобщения, нет связи с темой, фактическая ошибка.
        ("аспект 1, три изъяна сразу",
         a1(difference_generalised=False, linked_to_topic=False, factual_error=True), MISSING),
        ("аспект 1, смысл не дошёл", a1(unintelligible=True), MISSING),
        # Аспекты 2-3: достоинство/недостаток названы для обоих типов и не отписка.
        ("аспект 2, названы конкретные достоинства", a23(2), FULL),
        ("аспект 2, отписки для обоих типов",
         a23(2, specific_first=False, specific_second=False), PARTIAL),
        # Работа «volunteering»: про второй тип недостаток не назван вовсе.
        ("аспект 3, второй тип не разобран",
         a23(3, named_second=False, specific_second=False, specific_first=False), MISSING),
        # Аспект 4: мнение своё, выбор назван, обоснован, форма глагола из плана.
        ("аспект 4, всё на месте", a4(), FULL),
        ("аспект 4, нет обоснования", a4(justified=False), PARTIAL),
        ("аспект 4, форма глагола не та", a4(student_verb_form="I prefer"), PARTIAL),
        # Работа «games»: и обоснования нет, и форма не та — аспект не раскрыт.
        ("аспект 4, нет обоснования и форма не та",
         a4(justified=False, student_verb_form="I'd prefer",
            plan_verb_form="you prefer"), MISSING),
    ]
    for name, check, want in cases:
        got = verdict(check)
        if got != want:
            bad.append(f"{name}: {got} вместо {want}")

    # Глагольная форма сравнивается механически.
    forms = [
        ("you would prefer", "I would prefer", True),
        ("you'd prefer", "I'd prefer", True),
        ("you prefer", "I prefer", True),
        ("you would prefer", "I prefer", False),
        ("you prefer", "I would prefer", False),
        ("you preferred as a child", "I preferred", True),
        ("you preferred as a child", "I prefer", False),
        ("", "I prefer", True),  # план не процитирован — придираться не за что
    ]
    for plan, student, want in forms:
        if sc.verb_form_matches(plan, student) != want:
            bad.append(f"форма глагола «{plan}» / «{student}»: ждали {want}")

    # Модель промолчала про аспект — он не засчитан, а не «раскрыт по умолчанию».
    empty = sc.aspect_verdicts([])
    if [a["verdict"] for a in empty] != [MISSING] * 4:
        bad.append(f"пустой ответ модели должен давать четыре «не раскрыто»: {empty}")

    print(f"{'OK  ' if not bad else 'FAIL'} вердикты по аспектам: "
          f"{len(cases)} сочетаний признаков + {len(forms)} проверок глагольной формы")
    return bad


def check_items() -> list[str]:
    bad = []
    got = sc.score_items([{"accepted": True}, {"accepted": False}, {"accepted": True},
                          {"accepted": True}], 4)
    if got != {"score": 3, "max": 4}:
        bad.append(f"задание 2: {got}")
    # Лишние ответы сверх максимума не добавляют баллов.
    got = sc.score_items([{"accepted": True}] * 8, 5)
    if got != {"score": 5, "max": 5}:
        bad.append(f"задание 3: {got}")
    print(f"{'OK  ' if not bad else 'FAIL'} задания 2 и 3: сумма зачтённых вопросов")
    return bad


def main() -> int:
    print("Сверка шкалы с методичкой ФИПИ 2026\n")
    bad: list[str] = []
    bad += check_content_table()
    bad += check_volume()
    bad += check_organization()
    bad += check_language()
    bad += check_reading()
    bad += check_aspects()
    bad += check_items()
    print()
    bad += check_monologues()
    print()
    if bad:
        print(f"ПРОВАЛЕНО {len(bad)}:")
        for b in bad:
            print("  -", b)
        return 1
    print("Все проверки пройдены: шкала совпадает с официальной до балла.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
