"""Оценивание ответа: промпт эксперта, разбор его суждений, балл по шкале.

Третий блок, вынесенный из main.py (после personas и alerts). Здесь только
ЧИСТЫЕ функции: ни сети, ни базы, ни состояния процесса — на вход суждения
модели, на выход готовый разбор. Поэтому модуль проверяем целиком и не может
сломаться от того, что происходит в остальном сервере.

Разделение труда с соседями неизменно: ege_prompts просит модель вынести
суждения эксперта, ege_scoring применяет к ним официальные шкалы, а здесь эти
два конца сшиваются в то, что увидит ученик. Баллов модель не называет.
"""

from __future__ import annotations

import ege_prompts
import ege_scoring

FALLBACK_MONOLOGUE_BRIEF = (
    "Task 4. You and your friend are doing a school project. You have found two photos "
    "to illustrate it but cannot send them, so you leave a voice message: explain the "
    "choice of the photos by briefly describing them and noting the differences, "
    "mention the advantages (1-2) and the disadvantages (1-2) of the two options, and "
    "express your opinion on the subject of the project — which option you would prefer "
    "and why. Speak for 12-15 sentences."
)


def _feedback_prompt(kind: str, payload: dict, transcript: str,
                     persona: str | None = None) -> tuple[str, dict]:
    """Промпт эксперта и контекст, который понадобится при подсчёте балла.

    Транскрипт нужен уже здесь: для чтения вслух эталон сверяется с ним ДО
    обращения к модели, и модель получает готовые улики, а не сырой текст.

    `persona` меняет СТРОГОСТЬ и ГОЛОС разбора (см. ege_prompts.STRICTNESS),
    но не правила и не шкалу: спорное решается за или против ученика, а балл
    считается одной и той же таблицей ФИПИ."""
    extra = ege_prompts.strictness_block(persona)
    if kind == "reading":
        ref = str(payload.get("referenceText") or "")
        diff = ege_scoring.reading_diff(ref, transcript)
        return ege_prompts.reading_prompt(ref, diff) + extra, {"diff": diff}
    if kind == "dialogue":
        points = [str(p) for p in (payload.get("points") or [])]
        ad = str(payload.get("ad") or "")
        return ege_prompts.dialogue_prompt(ad, points) + extra, {"points": points}
    if kind == "interview":
        questions = [str(q) for q in (payload.get("questions") or [])]
        return ege_prompts.interview_prompt(questions) + extra, {"questions": questions}
    brief = str(payload.get("brief") or "") or FALLBACK_MONOLOGUE_BRIEF
    facts = [str(f) for f in (payload.get("photoFacts") or [])]
    return ege_prompts.monologue_prompt(brief, facts) + extra, {}


_loads_forgiving = ege_prompts.loads_forgiving


def _errors_from(raw: object, limit: int = 8) -> list[dict]:
    """Ошибки от модели — в форму, которую ждут фронт и профиль ошибок."""
    out = []
    for e in (raw if isinstance(raw, list) else [])[:limit]:
        if not isinstance(e, dict):
            continue
        quote = str(e.get("quote") or "").strip()
        if not quote:
            continue
        out.append({
            "cat": str(e.get("cat") or "gram"),
            "quote": quote,
            "correction": str(e.get("correction") or "").strip(),
            "explanation": str(e.get("explanation") or "").strip(),
        })
    return out


def _score_feedback(kind: str, obs: dict, ctx: dict) -> dict:
    """Суждения модели → балл по официальной шкале и разбор для экрана.

    Единая форма ответа для всех заданий: summary, score/max, errors и criteria
    (у 39 их нет, у 40 и 41 это по строке на вопрос, у 42 — три критерия ФИПИ).
    """
    summary = str(obs.get("summary") or "").strip()

    if kind == "reading":
        misread = [m for m in (obs.get("misread") or [])
                   if isinstance(m, dict) and m.get("real")]
        score, note = ege_scoring.score_reading(ctx["diff"], len(misread))
        errors = [{
            "cat": "missing" if not str(m.get("heard") or "").strip() else "lex",
            "quote": str(m.get("heard") or "").strip() or "пропущено",
            "correction": str(m.get("expected") or "").strip(),
            "explanation": str(m.get("explanation") or "").strip(),
        } for m in misread[:6]]
        # Оговорка про фонетику здесь обязательна, а не для галочки: в реальном
        # ЕГЭ этот балл ставят ИМЕННО за произношение и интонацию, а мы их не
        # слышим. Ученик должен понимать, что 1/1 у нас — не «прочитано идеально».
        parts = [summary, note if (score == 0 or errors) else "",
                 "Произношение и интонацию разбор не слышит — он сверяет текст с эталоном."]
        return {
            "summary": " ".join(p for p in parts if p).strip(),
            "score": score, "max": ege_scoring.MAX_SCORE["reading"], "errors": errors,
        }

    if kind in ("dialogue", "interview"):
        is_dialogue = kind == "dialogue"
        items = obs.get("questions" if is_dialogue else "answers") or []
        items = [it for it in items if isinstance(it, dict)]
        expected = len(ctx.get("points" if is_dialogue else "questions") or [])
        top = expected or ege_scoring.MAX_SCORE[kind]
        res = ege_scoring.score_items(items, top)

        label = "Вопрос" if is_dialogue else "Ответ"
        criteria, errors = [], []
        for i, it in enumerate(items[:top]):
            ok = bool(it.get("accepted"))
            heard = str(it.get("heard") or "").strip()
            correction = str(it.get("model") or "").strip()
            criterion = {
                "key": f"q{i + 1}", "name": f"{label} {i + 1}",
                "score": 1 if ok else 0, "max": 1,
                "comment": str(it.get("reason") or "").strip(),
            }
            if not ok:
                # Кладём heard/correction прямо на критерий — раньше экран
                # сопоставлял вопрос с ошибкой по порядковому номеру среди
                # незачтённых, и один лишний элемент в errors (например, из
                # _errors_from ниже) тихо сдвигал пару "вопрос-ошибка".
                criterion["quote"] = heard or ("вопрос не задан" if is_dialogue else "ответ не зачтён")
                criterion["correction"] = correction
                errors.append({
                    "cat": "missing" if not heard else "order",
                    "quote": criterion["quote"],
                    "correction": correction,
                    "explanation": str(it.get("reason") or "").strip(),
                })
            criteria.append(criterion)
        errors += _errors_from(obs.get("errors"), limit=8 - len(errors))
        return {"summary": summary, "score": res["score"], "max": res["max"],
                "errors": errors, "criteria": criteria}

    # monologue: модель отвечает признаками «да/нет», вердикты выводит шкала
    aspects = ege_scoring.aspect_verdicts(obs.get("aspects") or [])
    logic = [e for e in (obs.get("logic_errors") or []) if isinstance(e, dict)]
    lang = [e for e in (obs.get("lang_errors") or []) if isinstance(e, dict)]
    grave = sum(1 for e in lang if e.get("grave"))
    try:
        phrases = int(obs.get("phrases") or 0)
    except (TypeError, ValueError):
        phrases = 0

    res = ege_scoring.score_monologue(
        aspects, phrases,
        bool(obs.get("opening_with_address")), bool(obs.get("closing")),
        len(logic), len(lang), grave,
    )

    # Разбор по аспектам — самое полезное для ученика: дописываем к содержанию,
    # начиная с того, что не зачтено полностью.
    detail = [f"Аспект {i + 1} — {c}" for i, a in enumerate(aspects)
              if a.get("verdict") != ege_scoring.FULL and (c := str(a.get("comment") or "").strip())]
    if detail:
        res["criteria"][0]["comment"] += ". " + ". ".join(detail)

    errors = _errors_from(lang, limit=6)
    errors += [{"cat": "logic", "quote": str(e.get("quote") or "").strip() or "логика",
                "correction": "", "explanation": str(e.get("explanation") or "").strip()}
               for e in logic[:3]]
    return {"summary": summary, "score": res["score"], "max": res["max"],
            "errors": errors, "criteria": res["criteria"]}
