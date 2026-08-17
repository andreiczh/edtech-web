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

    # 7. Отсебятина вместо текста — ноль. Регресс на реальный обход
    # (03.08.2026): difflib метит чужую речь «заменой», missing_total = 0,
    # и без проверки coverage чепуха проходила как «прочитано полностью».
    d = sc.reading_diff(REF, "Well, you know, actually, interesting, nice, good, yes.")
    if sc.score_reading(d, 0)[0] != 0:
        bad.append(f"отсебятина прошла как чтение (coverage {d['coverage']})")
    # ...а слабое, но настоящее чтение (потерян каждый десятый кусок) — не ноль.
    weak = " ".join(w for i, w in enumerate(REF.split()) if i % 10 != 9)
    d = sc.reading_diff(REF, weak)
    if d["coverage"] < sc.MIN_READ_COVERAGE:
        bad.append(f"порог coverage душит настоящее чтение: {d['coverage']}")

    # 8. Пропуск, ПРИМКНУВШИЙ к ошибке распознавания (05.08.2026). difflib
    # показывает такое одной «заменой», и раньше это считалось оговоркой, а не
    # пропуском: балл оставался, хотя по критериям пропущенная строка — ноль.
    # Жалоба тестировщика: «я пропустил предложение, а написало, что прочитано
    # иначе».
    glued = " ".join(words[:12] + ["something"] + words[26:])
    d = sc.reading_diff(REF, glued)
    if d["longest_missing_run"] < sc.SKIPPED_LINE_RUN:
        bad.append(f"пропуск рядом с оговоркой не пойман: подряд "
                   f"{d['longest_missing_run']} слов при 14 выброшенных")
    if sc.score_reading(d, 0)[0] != 0:
        bad.append("пропуск рядом с оговоркой обязан обнулять ответ")

    # ...но обычная подмена в одно-два слова пропуском НЕ считается, иначе
    # каждая оговорка обнуляла бы задание.
    d = sc.reading_diff(REF, REF.replace("tall plant", "very small green plant"))
    if d["longest_missing_run"] or d["missing_total"]:
        bad.append(f"обычная подмена записана в пропуски: {d['missing_total']}")
    if sc.score_reading(d, 0)[0] != 1:
        bad.append("подмена пары слов не должна обнулять ответ")

    # 9. Фонетическая дистанция подмен (05.08.2026): далёкую засчитывает код.
    d = sc.reading_diff(REF, REF.replace("branches", "doctors"))
    s = next((x for x in d["swaps"] if "branches" in x["expected"]), None)
    if not (s and s.get("distant")):
        bad.append(f"branches->doctors не помечено далёкой подменой: {s}")
    d = sc.reading_diff(REF, REF.replace("branches", "branch"))
    s = next((x for x in d["swaps"] if "branch" in x["expected"]), None)
    if s and s.get("distant"):
        bad.append("потеря окончания ошибочно помечена далёкой подменой")
    # Короткие слова и цифры далёкими не считаются — это честный шум STT.
    d = sc.reading_diff("It is a tree", "At is a tree")
    if any(x.get("distant") for x in d["swaps"]):
        bad.append("короткое it->at ошибочно помечено далёкой подменой")

    # 10. Систематика окончаний: одна потеря прощается, две и больше — нет.
    # Эталон свой, короткий: в общем REF слова повторяются, и одна замена
    # превращалась бы в две (на этом тест меня и поймал).
    ends = ("The teacher helps the pupils and makes the lesson clear. "
            "Everyone listens and learns something new today.")
    one = sc.reading_diff(ends, ends.replace("helps", "help"))
    if sc.ending_pattern(one["swaps"]):
        bad.append(f"одиночное искажение окончания записано в систему: {one['swaps']}")
    many = sc.reading_diff(
        ends, ends.replace("helps", "help").replace("makes", "make")
                  .replace("listens", "listen"))
    pattern = sc.ending_pattern(many["swaps"])
    if len(pattern) < 2:
        bad.append(f"систематика окончаний не поймана: {many['swaps']}")
    # ...и три искажённые формы обязаны обнулить задание по критериям.
    if sc.score_reading(many, len(pattern))[0] != 0:
        bad.append("три искажённые формы не обнулили балл")
    if not sc._endings_only("helps", "help") or not sc._endings_only("happen", "happens"):
        bad.append("пара, отличающаяся только окончанием, не распознана")
    for a, b in (("teachers", "doctors"), ("tree", "three"), ("a", "as"),
                 ("tall plant", "tall plants")):
        if sc._endings_only(a, b):
            bad.append(f"«{a}»/«{b}» ошибочно принято за разницу в окончании")

    print(f"{'OK  ' if not bad else 'FAIL'} чтение вслух: пропуски, хвост, пропущенная строка")
    return bad


def check_quotes() -> list[str]:
    """Сверка цитат: приписано ли ученику несказанное (05.08.2026).

    Ошибка здесь стоит балла ЕГЭ, поэтому проверяются обе стороны: и что
    выдумка ловится, и что честная цитата НЕ объявляется выдумкой.
    """
    bad = []
    said = ("Hello, I am calling about your advertisement. Is there a course "
            "for beginners? How much does the whole course cost? Do I need "
            "special clothes for the lessons?")

    # 1. Настоящая цитата подтверждается — даже причёсанная моделью.
    for good in ("Is there a course for beginners?",
                 "How much does the whole course cost",
                 "is there a course for beginners",          # регистр
                 "Do I need special clothes for the lessons"):
        if sc.quote_is_fabricated(good, said):
            bad.append(f"настоящая цитата объявлена выдумкой: «{good}»")
    # Модель вправе почистить мусор распознавания — это не выдумка.
    if sc.quote_is_fabricated("How much does the course cost", said):
        bad.append("причёсанная цитата объявлена выдумкой")

    # 2. Выдумка ловится.
    for fake in ("What time do the lessons start?",
                 "Could you tell me about the teachers and their experience?"):
        if not sc.quote_is_fabricated(fake, said):
            bad.append(f"выдуманная цитата прошла как настоящая: «{fake}»")

    # 3. Пустая цитата — это «не прозвучало», а не выдумка.
    if sc.quote_is_fabricated("", said) or sc.quote_is_fabricated("   ", said):
        bad.append("пустая цитата ошибочно считается выдумкой")

    # 4. Короткие цитаты ищутся целиком: «половина» у них ничего не значит.
    if sc.quote_is_fabricated("special clothes", said):
        bad.append("короткая настоящая цитата объявлена выдумкой")
    if not sc.quote_is_fabricated("swimming pool", said):
        bad.append("короткая выдумка прошла как настоящая")

    # 5. Пометки на пунктах: выдумка и зачтённый обрывок уходят на пересмотр.
    obs = {"questions": [
        {"accepted": True, "heard": "Is there a course for beginners?", "reason": "ок"},
        {"accepted": True, "heard": "What time do the lessons start?", "reason": "ок"},
        {"accepted": True, "heard": "clothes?", "reason": "ок"},
        {"accepted": False, "heard": "", "reason": "не задан"},
    ]}
    notes = sc.flag_suspicious("dialogue", obs, said)
    q = obs["questions"]
    if q[0].get("borderline"):
        bad.append("честный пункт зря отправлен на пересмотр")
    if not (q[1].get("quote_missing") and q[1].get("borderline")):
        bad.append("выдуманная цитата не помечена")
    if not (q[2].get("too_short") and q[2].get("borderline")):
        bad.append("зачтённый обрывок не помечен")
    if q[3].get("borderline"):
        bad.append("незаданный вопрос с пустой цитатой зря помечен")
    if len(notes) != 2:
        bad.append(f"пометок {len(notes)}, а ожидалось 2: {notes}")

    # 6. У интервью порог длины выше: полный ответ — 2-3 предложения.
    # Расшифровка своя: у интервью она содержит ответы, а не вопросы.
    answered = ("Yes I do. I usually spend my weekend with my family and we go "
                "to the park together, because I really enjoy fresh air.")
    obs_i = {"answers": [
        {"accepted": True, "heard": "Yes I do", "reason": "ок"},
        {"accepted": True,
         "heard": "I usually spend my weekend with my family and we go to the "
                  "park together", "reason": "ок"},
    ]}
    sc.flag_suspicious("interview", obs_i, answered)
    if not obs_i["answers"][0].get("too_short"):
        bad.append("интервью: ответ из трёх слов не помечен коротким")
    if obs_i["answers"][1].get("too_short"):
        bad.append("интервью: развёрнутый ответ зря помечен коротким")

    # 7. Ошибки без опоры в речи — вон до подсчёта балла.
    errs = [
        {"quote": "course for beginners", "correction": "x"},   # настоящая
        {"quote": "yesterday I go to school", "correction": "x"},  # выдумка
        {"quote": "", "correction": "x"},                        # без улики
    ]
    kept = sc.drop_unsupported(errs, said, need_quote=True)
    if len(kept) != 1 or kept[0]["quote"] != "course for beginners":
        bad.append(f"отсев ошибок без улик сработал неверно: {kept}")
    # Логической ошибке цитата не обязательна: «нет связки» цитировать нечем.
    kept_logic = sc.drop_unsupported(errs, said, need_quote=False)
    if len(kept_logic) != 2:
        bad.append(f"логические ошибки отсеяны слишком жадно: {kept_logic}")

    print(f"{'OK  ' if not bad else 'FAIL'} сверка цитат: выдумки, обрывки, ошибки без улик")
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


def check_recheck_pick() -> list[str]:
    """Отбор спорных аспектов и слияние второго взгляда.

    Второй проход по умолчанию выключен (замер не подтвердил выигрыш, см.
    main.MONOLOGUE_RECHECK), но код живой и включается переменной — значит он
    обязан оставаться исправным. Иначе в день, когда золотой набор вырастет и
    его захотят включить, окажется, что он тихо сгнил.
    """
    bad = []
    said = "I like chess with my grandfather and we play every Sunday at home."

    full = {"n": 1, "evidence": "I like chess with my grandfather",
            "described_first": True, "described_second": True,
            "difference_stated": True, "difference_generalised": True,
            "linked_to_topic": True, "factual_error": False}
    part = {"n": 2, "evidence": "we play every Sunday", "named_first": True,
            "named_second": False, "specific_first": True, "specific_second": True}
    fake = {"n": 3, "evidence": "I went skiing in the Alps last winter",
            "named_first": True, "named_second": True,
            "specific_first": True, "specific_second": True}
    empty = {"n": 4, "evidence": "", "opinion_explicit": True,
             "choice_stated": True, "justified": True}

    picked = sc.doubtful_aspects({"aspects": [full, part, fake, empty]}, said)
    if 1 in picked:
        bad.append("на пересмотр ушёл аспект, раскрытый полностью и с цитатой")
    for n, why in ((2, "неполно раскрытый"), (3, "с выдуманной цитатой"),
                   (4, "без улик, но с признаками")):
        if n not in picked:
            bad.append(f"на пересмотр НЕ ушёл аспект {n} ({why})")
    if len(picked) > 3:
        bad.append("на пересмотр ушло больше трёх аспектов — это второй первый проход")

    obs = {"aspects": [dict(full), dict(part)]}
    changed = sc.merge_aspect_recheck(
        obs, [{"n": 2, "named_second": True, "evidence": "playing chess at home"}])
    if changed != 1:
        bad.append(f"слияние насчитало правок {changed}, а изменился один признак")
    if not obs["aspects"][1].get("named_second"):
        bad.append("пересмотренный признак не доехал до наблюдений")
    if obs["aspects"][0].get("evidence") != full["evidence"]:
        bad.append("второй взгляд затронул аспект, о котором его не спрашивали")

    # Мусор от модели не должен ронять разбор и не должен ничего менять.
    if sc.merge_aspect_recheck(obs, "не список") != 0:
        bad.append("слияние приняло не-список")
    print(f"{'ok  ' if not bad else 'FAIL'} отбор спорных аспектов и слияние")
    return bad


def check_reread() -> list[str]:
    """Правила перечитывания в задании 39 (правки тестировщика 05.08.2026).

    Смысл один: слово засчитано, если прозвучало ХОТЯ БЫ РАЗ, в любом заходе.
    Ученик, который поправляет сам себя, не должен получать за это минус — но
    и тот, кто честно недочитал, не должен получать плюс.
    """
    bad = []
    W = ("The old library on the hill keeps books that nobody reads today but the roof "
         "still leaks every spring and the town council promises to repair it each year "
         "without fail").split()
    ref = " ".join(W)

    def diff(words):
        return sc.reading_diff(ref, " ".join(words))

    cases = [
        # (название, что прозвучало, покрытие, пропущено)
        ("сквозное чтение", W, 1.0, 0),
        # Главная поломка: монотонное выравнивание видит один проход, и начало,
        # прочитанное ПОСЛЕ середины, считало непрочитанным (было 0.61).
        ("начал с середины, вернулся к началу", W[12:] + W[:12], 1.0, 0),
        ("читал, вернулся назад, дочитал", W[:20] + W[7:], 1.0, 0),
        ("прочитал половину и начал заново", W[:14] + W, 1.0, 0),
        ("дочитал и перечитал середину", W + W[6:12], 1.0, 0),
    ]
    for name, got, want_cov, want_missing in cases:
        d = diff(got)
        if abs(d["coverage"] - want_cov) > 0.001 or d["missing_total"] != want_missing:
            bad.append(f"39 перечитывание, {name}: покрытие {d['coverage']} "
                       f"(ждали {want_cov}), пропущено {d['missing_total']}")

    # Обратная сторона: щедрость не должна превращаться во всепрощение.
    stopped = diff(W[:14])
    if stopped["coverage"] > 0.6 or stopped["tail_missing"] < 10:
        bad.append(f"39: недочитанный текст перестал считаться недочитанным: {stopped}")
    skipped = diff(W[:8] + W[16:])
    if skipped["missing_total"] < 5:
        bad.append(f"39: пропуск в середине перестал ловиться: {skipped}")

    # Самоисправление: подмена, которую ученик сам же поправил, уликой не
    # является — иначе он наказан за то, что услышал свою ошибку.
    fixed = sc.reading_diff(ref, ref.replace("roof still", "roof steel roof still"))
    if fixed["swaps"] or fixed["missing_total"]:
        bad.append(f"39: самоисправление засчитано как ошибка: {fixed['swaps']}")

    print(f"{'ok  ' if not bad else 'FAIL'} 39: перечитывание и самоисправление")
    return bad


def check_gross_errors() -> list[str]:
    """Официальный счёт грубых ошибок в чтении (методичка ФИПИ, задание 1).

    Два разных правила, и путать их нельзя: повторно перевранное ОДНО И ТО ЖЕ
    слово — одна ошибка, а каждый пропуск — отдельная.
    """
    bad = []
    cases = [
        ("одна подмена", [{"expected": "science", "heard": "sinus"}], 1),
        ("то же слово переврано дважды",
         [{"expected": "science", "heard": "sinus"},
          {"expected": "science", "heard": "sinus"}], 1),
        ("разные слова переврано дважды",
         [{"expected": "science", "heard": "sinus"},
          {"expected": "leave", "heard": "live"}], 2),
        ("подмена накрыла два слова эталона",
         [{"expected": "stronger teachers", "heard": "strange doctors"}], 2),
        ("одно и то же слово пропущено дважды — считается дважды",
         [{"expected": "the", "heard": ""}, {"expected": "the", "heard": ""}], 2),
        ("пропуск и подмена того же слова считаются раздельно",
         [{"expected": "science", "heard": ""},
          {"expected": "science", "heard": "sinus"}], 2),
    ]
    for name, misread, want in cases:
        got = sc.gross_errors(misread)
        if got != want:
            bad.append(f"счёт грубых ошибок, {name}: {got} вместо {want}")

    # Практический смысл правила: ученик, споткнувшийся на ОДНОМ трудном слове
    # три раза, не должен получать ноль — эксперт поставил бы балл.
    stumble = [{"expected": "phenomenon", "heard": "fenomen"}] * 3
    if sc.gross_errors(stumble) >= 3:
        bad.append("три запинки на одном слове по-прежнему дают ноль")

    print(f"{'ok  ' if not bad else 'FAIL'} 39: счёт грубых ошибок по методичке")
    return bad


def main() -> int:
    print("Сверка шкалы с методичкой ФИПИ 2026\n")
    bad: list[str] = []
    bad += check_content_table()
    bad += check_volume()
    bad += check_organization()
    bad += check_language()
    bad += check_reading()
    bad += check_reread()
    bad += check_gross_errors()
    bad += check_quotes()
    bad += check_aspects()
    bad += check_recheck_pick()
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
