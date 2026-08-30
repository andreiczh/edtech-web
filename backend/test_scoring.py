# -*- coding: utf-8 -*-
"""Тесты сборки разбора: суждения модели -> то, что увидит ученик.

test_ege_scoring.py проверяет ШКАЛЫ (сколько баллов за N ошибок).
Здесь — слой выше: как ответ модели превращается в разбор. Тут легко посадить
тихий баг, который не уронит сервер, а просто покажет ученику не то: потерять
пару «вопрос-ошибка», забыть санитизацию, отдать критерий без обоснования.

Запуск: .\.venv\Scripts\python.exe test_scoring.py
Сети и базы не требует — модуль scoring.py намеренно без ввода-вывода.
"""
from __future__ import annotations

import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import ege_scoring  # noqa: E402
import scoring  # noqa: E402

failed = 0


def check(cond: bool, name: str, detail: str = "") -> None:
    global failed
    if cond:
        print(f"OK   {name}")
    else:
        failed += 1
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))


# --------------------------------------------------------- диалог и интервью

obs_dialogue = {
    "summary": "Два вопроса из четырёх.",
    "questions": [
        {"accepted": True, "heard": "Is there a course?", "reason": "принят"},
        {"accepted": False, "heard": "", "model": "How much is it?",
         "reason": "вопрос о цене не задан"},
        {"accepted": True, "heard": "Where is it?", "reason": "принят"},
        {"accepted": False, "heard": "You have clothes?",
         "model": "Do I need special clothes?", "reason": "не вопрос, а утверждение"},
    ],
    # Общая ошибка НЕ должна сдвигать пары «вопрос-ошибка»: ровно на этом
    # ломался экран, пока сопоставление шло по порядковому номеру.
    "errors": [{"cat": "gram", "quote": "you have", "correction": "do you have",
                "explanation": "порядок слов"}],
}
fb = scoring._score_feedback("dialogue", obs_dialogue, {"points": ["a", "b", "c", "d"]})

check(fb["score"] == 2 and fb["max"] == 4, "диалог: балл = числу принятых вопросов",
      f'получено {fb["score"]}/{fb["max"]}')
check(len(fb["criteria"]) == 4, "диалог: критерий на каждый вопрос")
check(fb["criteria"][1]["correction"] == "How much is it?",
      "диалог: образец вопроса лежит НА критерии, а не ищется по порядку")
check(fb["criteria"][3]["quote"] == "You have clothes?",
      "диалог: цитата ученика привязана к своему вопросу")
# Требование изменено 05.08.2026 по жалобе тестировщика. Раньше цитата
# полагалась только незачтённому пункту, и на экране у зачтённого вместо своего
# ответа человек читал вердикт модели («вопрос засчитан, грамматика верна»).
# Перечитать собственную формулировку было негде — а именно она и учит.
check(fb["criteria"][0].get("quote") == "Is there a course?",
      "диалог: у ЗАЧТЁННОГО вопроса тоже видна своя формулировка")

# Выдуманная цитата до экрана не доезжает: на незачёте это ложное обвинение,
# на зачёте — балл за несказанное (05.08.2026).
fb_fake = scoring._score_feedback(
    "dialogue",
    {"summary": "s", "questions": [
        {"accepted": False, "heard": "What time do you open?",
         "quote_missing": True, "reason": "нет такого вопроса"},
    ]},
    {"points": ["a"]})
shown = fb_fake["criteria"][0].get("quote") or ""
check("What time" not in shown,
      "диалог: выдуманная цитата на экран не попадает")
check("не удалось сопоставить" in shown,
      "диалог: вместо выдумки честная подпись, а не «вопрос не задан»")
check(all("What time" not in (e.get("quote") or "") for e in fb_fake["errors"]),
      "диалог: выдуманная цитата не утекла и в список ошибок")

# Монолог: языковая ошибка без опоры в речи балл не снижает.
MONO_SAID = ("Hi Max, I have found two photos for our project. The first photo "
             "show a girl who is reading a book in the park.")
mono_obs = {
    "summary": "s",
    "aspects": [], "phrases": 12,
    "opening_with_address": True, "closing": True,
    "logic_errors": [],
    "lang_errors": [
        {"cat": "gram", "quote": "The first photo show a girl", "grave": True},
        {"cat": "gram", "quote": "yesterday I go to the cinema", "grave": True},
        {"cat": "lex", "quote": "", "grave": True},
    ],
}
fb_mono = scoring._score_feedback("monologue", mono_obs, {"transcript": MONO_SAID})
fb_mono_blind = scoring._score_feedback("monologue", mono_obs, {})
check(fb_mono["score"] >= fb_mono_blind["score"],
      "монолог: отсев ошибок без улик не может УХУДШИТЬ балл ученика")
kept = [e["quote"] for e in fb_mono["errors"] if e.get("quote")]
check(all("yesterday" not in q for q in kept),
      "монолог: выдуманная языковая ошибка не попала в разбор")
check(all(c["comment"] for c in fb["criteria"]),
      "диалог: обоснование есть у каждого критерия")

# Интервью считается той же веткой, но по «answers» и с максимумом 5.
obs_interview = {
    "summary": "s",
    "answers": [{"accepted": True, "reason": "две фразы"} for _ in range(5)],
}
fb_i = scoring._score_feedback("interview", obs_interview,
                               {"questions": ["q"] * 5})
check(fb_i["score"] == 5 and fb_i["max"] == 5, "интервью: все ответы приняты — 5 из 5")

# Модель прислала лишние пункты — берём ровно столько, сколько было вопросов.
obs_extra = {"summary": "s", "questions": [{"accepted": True, "reason": "r"}] * 9}
fb_e = scoring._score_feedback("dialogue", obs_extra, {"points": ["a", "b", "c", "d"]})
check(fb_e["score"] == 4 and len(fb_e["criteria"]) == 4,
      "диалог: лишние пункты от модели отброшены, балл не раздут",
      f'получено {fb_e["score"]}, критериев {len(fb_e["criteria"])}')

# ------------------------------------------------------------------- чтение

ref = "A tree is a tall plant with a trunk and branches made of wood."
diff_ok = ege_scoring.reading_diff(ref, ref)
fb_r = scoring._score_feedback("reading", {"summary": "s", "misread": []},
                               {"diff": diff_ok})
check(fb_r["score"] == 1 and fb_r["max"] == 1, "чтение: прочитано верно — 1 балл")
check("Произношение" in fb_r["summary"],
      "чтение: оговорка про произношение на месте — ученик должен знать границы оценки")

# Три перевранных слова — по критериям это ноль.
fb_r0 = scoring._score_feedback(
    "reading",
    {"summary": "s", "misread": [{"real": True, "expected": w, "heard": "x"}
                                 for w in ("tree", "trunk", "wood")]},
    {"diff": diff_ok})
check(fb_r0["score"] == 0, "чтение: три грубые ошибки обнуляют балл")
check(len(fb_r0["errors"]) == 3, "чтение: каждая ошибка попала в разбор")

# Модель пометила расхождения как НЕ настоящие (промах распознавания) —
# они не должны стоить ученику балла.
fb_rf = scoring._score_feedback(
    "reading",
    {"summary": "s", "misread": [{"real": False, "expected": w, "heard": "x"}
                                 for w in ("tree", "trunk", "wood")]},
    {"diff": diff_ok})
check(fb_rf["score"] == 1,
      "чтение: расхождения, отвергнутые моделью, балл не снижают")

# Фонетически ДАЛЁКИЕ подмены модель простить не может: их засчитывает код
# (05.08.2026 — модель списывала на шум teachers->doctors и ставила 1/1).
diff_far = ege_scoring.reading_diff(
    ref, ref.replace("tall", "small").replace("trunk", "doctor")
           .replace("branches", "wonderful"))
fb_far = scoring._score_feedback(
    "reading", {"summary": "s", "misread": []}, {"diff": diff_far})
check(fb_far["score"] == 0,
      "чтение: три далёкие подмены обнуляют балл, даже если модель промолчала")
check(len(fb_far["errors"]) >= 2,
      "чтение: далёкие подмены попали в разбор без участия модели")

# Подмена, накрывшая ДВА слова, стоит двух ошибок, а не одной: по критериям
# каждое перевранное слово — грубая ошибка.
diff_two = ege_scoring.reading_diff(ref, ref.replace("trunk and", "wonderful person"))
fb_two = scoring._score_feedback(
    "reading",
    {"summary": "s", "misread": [{"real": True, "expected": "wood", "heard": "food"}]},
    {"diff": diff_two})
check(fb_two["score"] == 0,
      "чтение: двухсловная далёкая подмена плюс оговорка = три слова = ноль")

# Дубль модели (то же слово, то же прочтение) на экран попадает один раз:
# жалоба 15.08.2026 — «Повторная ошибка в том же месте» читалась как двойное
# наказание, хотя счёт её и не задваивал.
fb_dup = scoring._score_feedback(
    "reading",
    {"summary": "s", "misread": [
        {"real": True, "expected": "choose", "heard": "those"},
        {"real": True, "expected": "choose", "heard": "those"},
        {"real": True, "expected": "tree", "heard": "three"},
    ]},
    {"diff": diff_ok})
check(len(fb_dup["errors"]) == 2,
      "чтение: дубль пары от модели схлопнут в одну запись",
      f"записей {len(fb_dup['errors'])}")

# Одиночная потеря окончания — шум распознавания. Код давно требует
# систематики (два и больше), но модель могла записать одиночное окончание
# грубой ошибкой сама — и «game» вместо «games» становилось третьим словом,
# обнулявшим работу (жалоба 15.08.2026).
diff_end = ege_scoring.reading_diff(ref, ref.replace("branches", "branch"))
fb_end = scoring._score_feedback(
    "reading",
    {"summary": "s", "misread": [
        {"real": True, "expected": "branches", "heard": "branch"},
        {"real": True, "expected": "tree", "heard": "three"},
        {"real": True, "expected": "wood", "heard": "food"},
    ]},
    {"diff": diff_end})
check(fb_end["score"] == 1,
      "чтение: одиночное окончание от модели не считается и не обнуляет",
      f"балл {fb_end['score']}")
check(all(e["correction"] != "branches" for e in fb_end["errors"]),
      "чтение: одиночное окончание не показывается ошибкой")

# А СИСТЕМАТИКА окончаний (две и больше в одной записи) считается как прежде.
diff_sys = ege_scoring.reading_diff(
    ref, ref.replace("branches", "branch").replace("is", "was"))
sys_swaps = diff_sys.get("swaps") or []
fb_sys = scoring._score_feedback(
    "reading",
    {"summary": "s", "misread": [{"real": True, "expected": "wood", "heard": "food"}]},
    {"diff": ege_scoring.reading_diff(
        "Cats eat plants and dogs eat bones in gardens near houses.",
        "Cat eat plant and dogs eat bone in gardens near houses.")})
check(fb_sys["score"] == 0,
      "чтение: систематика окончаний по-прежнему в счёте",
      f"балл {fb_sys['score']}")

# ------------------------------------------------ обрыв разбора 40/41
# Прод 16.08.2026: интервью из пяти полных ответов получило один критерий и
# балл 1/5 — модель вернула один пункт, остальные молча стали нулями.

five = {"answers": [{"accepted": True} for _ in range(5)]}
one = {"answers": [{"accepted": True}]}
check(ege_scoring.missing_items("interview", five, 5) == 0,
      "полный разбор интервью недобором не считается")
check(ege_scoring.missing_items("interview", one, 5) == 4,
      "обрыв разбора виден: не хватает четырёх пунктов")
check(ege_scoring.missing_items("dialogue", {"questions": [{"accepted": True}] * 4}, 4) == 0,
      "полный разбор вопросов недобором не считается")
check(ege_scoring.missing_items("monologue", {}, 4) == 0,
      "монолог этой проверкой не трогается — у него другие критерии")
check(ege_scoring.missing_items("interview", {"answers": []}, 0) == 0,
      "без списка вопросов в задании недобор не считается")

# -------------------------------------------- рамочная фраза против распознавания
# Прод 16.08.2026: «Hello Max!» с русским акцентом расшифровано как «Philomach»,
# модель обращения не увидела, организация упала с 3 до 1 — минус два балла за
# приветствие, которое ученик произнёс.

RESCUE = [
    ("Philomach. I want to tell you about two photos.", True, "съеденное распознаванием обращение"),
    ("Hi! I want to tell you about two photos.", True, "обычное приветствие"),
    ("I want to tell you about two photos from my project.", False, "сразу к делу — не спасаем"),
    ("There are two pictures in front of me.", False, "запрещённый методичкой зачин"),
    ("Um. I want to tell you about the photos.", False, "мусорный зачин обращением не был"),
]
for text, want, name in RESCUE:
    check(ege_scoring.opening_rescued(text) == want, f"обращение: {name}")

# И сквозь весь слой сборки: балл обязан вернуться к трём.
mono_obs_rescue = {
    "summary": "s", "phrases": 18, "opening_with_address": False, "closing": True,
    "aspects": [{"n": n, "described_first": True, "described_second": True,
                 "difference_stated": True, "difference_generalised": True,
                 "linked_to_topic": True, "named_first": True, "named_second": True,
                 "specific_first": True, "specific_second": True,
                 "opinion_explicit": True, "choice_stated": True, "justified": True}
                for n in (1, 2, 3, 4)],
    "logic_errors": [], "lang_errors": [],
}
fb_resc = scoring._score_feedback(
    "monologue", mono_obs_rescue,
    {"transcript": "Philomach. I want to tell you about two photos. In the first photo I can see a girl reading a book. In the second photo I can see two boys playing football. Both photos show hobbies. The first hobby is quiet. The second hobby is active. Reading develops imagination. Sport makes you healthy. Reading can be lonely. Sport can be dangerous. I prefer reading because it is calm. It helps me relax. That's all, bye!"})
check(fb_resc["criteria"][1]["score"] == 3,
      "организация не падает из-за съеденного распознаванием обращения",
      f"балл {fb_resc['criteria'][1]['score']}")
fb_nores = scoring._score_feedback(
    "monologue", mono_obs_rescue,
    {"transcript": "I want to tell you about two photos. In the first photo I can see a girl reading a book. In the second photo I can see two boys playing football. Both photos show hobbies. The first hobby is quiet. The second hobby is active. Reading develops imagination. Sport makes you healthy. Reading can be lonely. Sport can be dangerous. I prefer reading because it is calm. It helps me relax. That's all, bye!"})
check(fb_nores["criteria"][1]["score"] == 1,
      "настоящее отсутствие обращения по-прежнему роняет организацию",
      f"балл {fb_nores['criteria'][1]['score']}")

# ------------------------------------------------------------- санитизация

dirty = [
    {"cat": "gram", "quote": "a", "correction": "b", "explanation": "c"},
    {"quote": "", "correction": "x"},          # без цитаты — выбросить
    "не словарь",                                # мусор — выбросить
    {"quote": "d"},                              # без cat — подставить gram
]
errs = scoring._errors_from(dirty, limit=8)
check(len(errs) == 2, "санитизация: мусор и записи без цитаты отброшены",
      f"осталось {len(errs)}")
check(all(set(e) >= {"cat", "quote", "correction", "explanation"} for e in errs),
      "санитизация: у каждой ошибки полный набор полей")
check(errs[1]["cat"] == "gram", "санитизация: категория по умолчанию проставлена")
check(len(scoring._errors_from([{"quote": str(i)} for i in range(20)], limit=3)) == 3,
      "санитизация: лимит соблюдается")

# ---------------------------------------------------------------- промпты

p_neutral, ctx = scoring._feedback_prompt("dialogue", {"ad": "x", "points": ["a"]}, "t")
p_critic, _ = scoring._feedback_prompt("dialogue", {"ad": "x", "points": ["a"]}, "t", "critic")
check(len(p_critic) > len(p_neutral),
      "промпт: строгость персоны дописывается, а не заменяет правила")
check(ctx["points"] == ["a"], "промпт: контекст для подсчёта балла возвращается")
check("referenceText" not in p_neutral or True, "промпт: собирается без падения")

p_mono, _ = scoring._feedback_prompt("monologue", {}, "t")
check(scoring.FALLBACK_MONOLOGUE_BRIEF[:20] in p_mono,
      "промпт: у монолога без текста задания подставляется запасной")

# ------------------------------------------------ интервью: счёт фраз кодом
# Замер 19.08.2026: 25/30 вердиктов, все промахи — зачтённые обрывки. Счёт
# полных фраз переехал в код (шестое механическое правило).

PHRASES = [
    ("In Troitsk. It's a part of Moscow. Quite warm.", 1),
    ("It's green. There is rivers.", 2),
    ("I live with my parents. I've got an elder sister called Masha.", 2),
    ("Somewhere far from big cities. Maybe on the Maldives.", 0),
    ("Joan Rowling. I like her stories very much.", 1),
    # Эксперт читает двояко («два неполных» или «неверная форма») — в обоих
    # чтениях меньше двух полных фраз, вердикт одинаковый.
    ("Quite big. Many animals living here.", 0),
    ("Kaluga is an industrial city. It is famous for the State Space Museum.", 2),
]
for text, want in PHRASES:
    got = ege_scoring.count_phrases(text)
    check(got == want, f"фразы: {text[:44]}… = {want}", f"насчитано {got}")

check(ege_scoring.answer_too_short("In Troitsk. Quite warm.") != "",
      "обрывочный ответ получает человеческую причину отказа")
check(ege_scoring.answer_too_short(
    "I live in Moscow. It is a big city.") == "",
      "две полные фразы проходят без придирок")

fb_iv = scoring._score_feedback("interview", {"answers": [
    {"accepted": True, "heard": "In Troitsk. It's a part of Moscow. Quite warm."},
    {"accepted": True, "heard": "I live with my parents. I've got an elder sister called Masha."},
    {"accepted": True, "heard": "Somewhere far from big cities. Maybe on the Maldives."},
    {"accepted": True, "heard": "I am"},
    {"accepted": False, "heard": ""},
]}, {"questions": ["a", "b", "c", "d", "e"]})
marks_iv = [c["score"] for c in fb_iv["criteria"]]
check(marks_iv == [0, 1, 0, 1, 0],
      "интервью: обрывки валит код, усечённые цитаты не тронуты",
      f"вердикты {marks_iv}")

# --------------------------------- задание 40: правила из живых записей ФИПИ
# Архив 2026, работа 9377: «that motorcycle club» у представителя клуба —
# вопрос о ДРУГОМ клубе, эксперт фиксирует сбой коммуникации.
check(ege_scoring.question_rejected(
    "Do you have any coach in that motorcycle club?",
    "Welcome to our motorcycle club!") != "",
      "«that» + предмет объявления отклоняется кодом")
check(ege_scoring.question_rejected(
    "Do you have any competitions in the motorcycle club?",
    "Welcome to our motorcycle club!") == "",
      "«the» + предмет объявления проходит")
check(ege_scoring.question_rejected(
    "Can I come on that day?", "Join our hockey club!") == "",
      "безобидное «that» без привязки к объявлению не трогаем")

# Работа 0487: «Do you have opportunity to play inside?» модель отклонила как
# «утверждение» — порядок слов вопросительный, отказ самоопровергается.
check(ege_scoring.rejection_refuted(
    "Do you have opportunity to play inside?",
    "не вопрос, а утверждение: do you have"),
      "отказ «это утверждение» на вопросе с инверсией снимается")
check(not ege_scoring.rejection_refuted(
    "There are historical costumes?", "нарушен порядок слов прямого вопроса"),
      "повествовательный порядок без инверсии остаётся отклонённым")
check(not ege_scoring.rejection_refuted(
    "Could you tell me about the price?", "это просьба, а не прямой вопрос"),
      "отказ за просьбу не трогаем")
check(not ege_scoring.rejection_refuted(
    "How much does the cost of an hour's work?", "нарушен порядок слов"),
      "wh-вопрос со сломанной грамматикой не спасаем")

fb_dlg = scoring._score_feedback("dialogue", {"questions": [
    {"accepted": True, "heard": "Do you have any coach in that motorcycle club?"},
    {"accepted": False, "heard": "Do you have opportunity to play inside?",
     "reason": "не вопрос, а утверждение"},
    {"accepted": True, "heard": "Where is your motorcycle club located?"},
    {"accepted": True, "heard": "Do you have any competitions in the club?"},
]}, {"points": ["coach", "inside", "location", "competitions"],
     "ad": "Welcome to our motorcycle club!"})
marks_dlg = [c["score"] for c in fb_dlg["criteria"]]
check(marks_dlg == [0, 1, 1, 1],
      "диалог: «that» валит код, ложное «утверждение» снимает код",
      f"вердикты {marks_dlg}")

print("\nВсе проверки прошли: сборка разбора." if failed == 0
      else f"\nПРОВАЛЕНО проверок: {failed}")
sys.exit(0 if failed == 0 else 1)
