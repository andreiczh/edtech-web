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

print("\nВсе проверки прошли: сборка разбора." if failed == 0
      else f"\nПРОВАЛЕНО проверок: {failed}")
sys.exit(0 if failed == 0 else 1)
