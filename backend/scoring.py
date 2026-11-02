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
    # Exam marks cannot depend on the conversational character selected in UI.
    extra = ""
    if kind == "reading":
        ref = str(payload.get("referenceText") or "")
        diff = ege_scoring.reading_diff(ref, transcript)
        # Эталон кладём в контекст: по нему проверяется, что «ошибка» указывает
        # на реально написанное слово, а не на выдуманное.
        return ege_prompts.reading_prompt(ref, diff) + extra, {"diff": diff,
                                                              "reference": ref}
    if kind == "dialogue":
        points = [str(p) for p in (payload.get("points") or [])]
        ad = str(payload.get("ad") or "")
        return ege_prompts.dialogue_prompt(ad, points) + extra, {"points": points,
                                                                 "ad": ad}
    if kind == "interview":
        questions = [str(q) for q in (payload.get("questions") or [])]
        return ege_prompts.interview_prompt(questions) + extra, {"questions": questions}
    brief = str(payload.get("brief") or "") or FALLBACK_MONOLOGUE_BRIEF
    facts = [str(f) for f in (payload.get("photoFacts") or [])]
    # Транскрипт нужен при подсчёте: по нему проверяется, что каждая языковая
    # ошибка опирается на реально сказанные слова. Текст задания и описания фото
    # — для второго взгляда на спорные аспекты: он должен видеть то же, что и
    # первый, иначе будет судить вслепую.
    return ege_prompts.monologue_prompt(brief, facts) + extra, {
        "transcript": transcript, "brief": brief, "facts": facts}


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
        correction = str(e.get("correction") or "").strip()
        if correction and ege_scoring._words(quote) == ege_scoring._words(correction):
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
        return reading_feedback(ctx["diff"])

    if kind in ("dialogue", "interview"):
        is_dialogue = kind == "dialogue"
        items = obs.get("questions" if is_dialogue else "answers") or []
        items = [it for it in items if isinstance(it, dict)]
        if items and all(isinstance(it.get("n"), int) for it in items):
            items = sorted(items, key=lambda it: it["n"])
        expected = len(ctx.get("points" if is_dialogue else "questions") or [])
        # Задание без списка пунктов — это дырка в банке, а не строгая работа.
        # Балл всё равно считаем из максимума (иначе ученик вовсе без оценки),
        # но говорим об этом ГРОМКО: молча делить на пять, не зная вопросов,
        # значит выставлять балл вслепую (поймано прогоном 16.08.2026).
        if not expected:
            print(f"[{kind}] в задании НЕТ списка пунктов — балл считается "
                  f"из максимума {ege_scoring.MAX_SCORE[kind]} вслепую, "
                  f"проверь вариант в банке")
        top = expected or ege_scoring.MAX_SCORE[kind]
        res = ege_scoring.score_items(items, top)

        label = "Вопрос" if is_dialogue else "Ответ"
        criteria, errors = [], []
        for i, it in enumerate(items[:top]):
            ok = bool(it.get("accepted"))
            # Формы, которые методичка отвергает ПОИМЁННО, решает КОД: замер на
            # пяти работах практикума 19.08.2026 дал 16 вердиктов из 20, и все
            # четыре промаха — в пользу ученика, ровно на разобранных примерах
            # («Where is your location?», «What is minimum age for students?»).
            # Правила были в промпте, модель исполняла их через раз — третий
            # случай в проекте, когда механическое правило переезжает в код.
            if ok and is_dialogue:
                why = ege_scoring.question_rejected(str(it.get("heard") or ""),
                                                    str(ctx.get("ad") or ""))
                if why:
                    ok = False
                    it = {**it, "accepted": False, "reason": why}
                    print(f"[40] вопрос {i + 1} отклонён кодом: {why}")
            # Обратное направление: модель отклонила за «повествовательный
            # порядок слов», а вопрос начинается со вспомогательного глагола —
            # причина самоопровергается, отказ снят (работа 0487 из архива
            # ФИПИ: «Do you have opportunity...» шёл как «утверждение»).
            # Пункт с выдуманной цитатой не спасаем: неизвестно, что звучало.
            if (ok is False and is_dialogue and not it.get("quote_missing")
                    and ege_scoring.rejection_refuted(
                        str(it.get("heard") or ""), str(it.get("reason") or ""))):
                ok = True
                it = {**it, "accepted": True, "reason": ""}
                print(f"[40] отказ по вопросу {i + 1} снят кодом: "
                      f"порядок слов вопросительный")
            # Интервью: минимум две ПОЛНЫЕ фразы — счёт ведёт код (замер
            # 19.08.2026: 25/30, все промахи — зачтённые обрывки). Правило
            # применяется только к развёрнутой цитате (от шести слов): короткая
            # может быть усечением модели, и такие уже уходят на второй проход
            # через flag_suspicious. Отнять балл из-за НАШЕГО усечения нельзя.
            if ok and not is_dialogue:
                heard_q = str(it.get("heard") or "")
                if len(heard_q.split()) >= 6:
                    why = ege_scoring.answer_too_short(heard_q)
                    if why:
                        ok = False
                        it = {**it, "accepted": False, "reason": why}
                        print(f"[41] ответ {i + 1} отклонён кодом: {why}")
            heard = str(it.get("heard") or "").strip()
            correction = str(it.get("model") or "").strip()
            # Цитата, которой нет в расшифровке, до экрана НЕ доезжает: на
            # незачёте это было бы ложное обвинение, на зачёте — балл за
            # несказанное. Пометку ставит ege_scoring.flag_suspicious ещё до
            # второго прохода, так что такой пункт уже пересмотрен старшим
            # экспертом (05.08.2026).
            unverified = bool(it.get("quote_missing"))
            if unverified:
                heard = ""
            criterion = {
                "key": f"q{i + 1}", "name": f"{label} {i + 1}",
                "score": 1 if ok else 0, "max": 1,
                "comment": str(it.get("reason") or "").strip(),
                # Цитата теперь и у ЗАЧТЁННОГО пункта (05.08.2026, жалоба
                # тестировщика). Раньше её клали только на незачёт, и на экране
                # вместо своего ответа человек читал вердикт модели: «вопрос
                # засчитан, грамматика верна». Свой ответ увидеть было негде —
                # а именно его и надо перечитать, чтобы чему-то научиться.
                "quote": heard,
            }
            if not ok:
                # Кладём heard/correction прямо на критерий — раньше экран
                # сопоставлял вопрос с ошибкой по порядковому номеру среди
                # незачтённых, и один лишний элемент в errors (например, из
                # _errors_from ниже) тихо сдвигал пару "вопрос-ошибка".
                # Подпись говорит ровно то, что известно. «Вопрос не задан» —
                # утверждение о факте, и оно уместно только когда проверка
                # цитаты прошла: при выдуманной цитате мы не знаем, звучал
                # вопрос или нет, и врать в эту сторону тоже нельзя.
                criterion["quote"] = heard or (
                    "не удалось сопоставить с записью" if unverified
                    else "вопрос не задан" if is_dialogue else "ответ не зачтён")
                criterion["correction"] = correction
                errors.append({
                    "cat": "missing" if not heard else "order",
                    "quote": criterion["quote"],
                    "correction": correction,
                    "explanation": str(it.get("reason") or "").strip(),
                })
            criteria.append(criterion)
        errors += _errors_from(obs.get("errors"), limit=8 - len(errors))
        # Итог — по ОКОНЧАТЕЛЬНЫМ вердиктам, а не по ответу модели: код выше
        # отклоняет и спасает пункты (question_rejected, rejection_refuted,
        # answer_too_short), и до 23.09.2026 эти правки в сумму не попадали —
        # ученик видел «вопрос 3 не засчитан» и балл 4 из 4 на одном экране
        # (поймано живым прогоном №40 в мини-приложении).
        score = sum(c["score"] for c in criteria) if criteria else res["score"]
        return {"summary": summary, "score": score, "max": res["max"],
                "errors": errors, "criteria": criteria}

    # monologue: модель отвечает признаками «да/нет», вердикты выводит шкала
    # Форма глагола мнения (аспект 4) — КОДОМ из самой речи (30.08.2026).
    # Правило verb_form_matches стояло с §6.26, но работало вхолостую: модель
    # цитировала формы через раз, и «I'd prefer» на план «you prefer» проходил
    # незамеченным — ровно за это эксперт обнулил работу из методички. Теперь
    # обе формы ищет регэксп: план — в brief задания, мнение — в транскрипте;
    # пустая находка оставляет цитату модели, ложных срабатываний нет.
    raw_aspects = [dict(c) if isinstance(c, dict) else c
                   for c in (obs.get("aspects") or [])]
    _speech_form = ege_scoring.opinion_form_from_speech(
        str(ctx.get("transcript") or ""))
    _plan_form = ege_scoring.plan_form_from_brief(str(ctx.get("brief") or ""))
    for c in raw_aspects:
        if isinstance(c, dict) and int(c.get("n") or 0) == 4:
            if _speech_form:
                c["student_verb_form"] = _speech_form
            if _plan_form:
                c["plan_verb_form"] = _plan_form
    aspects = ege_scoring.aspect_verdicts(raw_aspects)
    # Ошибки без опоры в речи ученика вон ДО подсчёта (05.08.2026): их число
    # напрямую решает баллы за организацию и за язык, а проверить их ученику
    # нечем. Выдуманная цитата и цитата, которой нет вовсе, несправедливы
    # одинаково — нет улики, нет наказания.
    #
    # Логическим ошибкам цитата не обязательна: «нет связки между частями» —
    # это про отсутствие слов, цитировать там нечего. Языковым — обязательна,
    # у них всегда есть конкретная фраза, и схема промпта её требует.
    transcript = str(ctx.get("transcript") or "")
    logic = ege_scoring.drop_unsupported(
        obs.get("logic_errors") or [], transcript, need_quote=False)
    lang = ege_scoring.drop_unsupported(
        obs.get("lang_errors") or [], transcript, need_quote=True)
    grave = sum(1 for e in lang if e.get("grave"))
    # Объём — КОДОМ, не мнением модели (30.08.2026): модельное «фраз: N»
    # гуляло от 0 до 15 на одной работе, а объём решает балл ступенями
    # (7 и меньше — ноль за всё задание): на живом прогоне прода сбойный
    # счёт обнулил нормальный ответ. count_phrases детерминирован, на
    # восьми работах ФИПИ совпал с ожиданиями (короткая работа эксперта
    # с нулём — 6 фраз, полные — 12-18). Модельное число — запасной путь
    # на случай пустого транскрипта в ctx.
    phrases = ege_scoring.count_phrases(transcript)
    if not phrases:
        try:
            phrases = int(obs.get("phrases") or 0)
        except (TypeError, ValueError):
            phrases = 0

    # Обращение к другу — самое короткое место ответа и потому самое хрупкое:
    # одно искажённое распознаванием слово стоило ученику двух баллов по
    # организации (прод, 16.08.2026: «Hello Max!» -> «Philomach»). Если модель
    # обращения не увидела, а ответ начинается коротким невнятным куском —
    # засчитываем в пользу ученика, см. ege_scoring.opening_rescued.
    opening = bool(obs.get("opening_with_address"))
    if not opening and ege_scoring.opening_rescued(transcript):
        opening = True
        print("[42] обращение спасено: первая фраза похожа на съеденное "
              "распознаванием приветствие")

    res = ege_scoring.score_monologue(
        aspects, phrases, opening, bool(obs.get("closing")),
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
            "errors": errors, "criteria": res["criteria"],
            # ЧЕСТНАЯ ОГОВОРКА. Замер на восьми работах ФИПИ (30.08.2026): в
            # пределах балла от эксперта мы попадаем в 3-5 случаях из 8, и
            # ошибка идёт в обе стороны. Скрыть это значит выдать ориентир за
            # приговор — а ученик, поверивший «7 из 10» и получивший на экзамене
            # другое, потеряет доверие ко всему разбору. Живые эксперты, к
            # слову, тоже расходятся: методичка описывает третью проверку.
            "accuracy_note": (
                "Ориентировочная оценка по распознанному тексту. Ошибки "
                "распознавания могут изменить балл и разбор; фонетика не оценена. "
                "Это тренировочный ориентир, а не оценка эксперта ФИПИ."
            )}


def reading_feedback(diff: dict) -> dict:
    """A reproducible text comparison, never an LLM guess about what audio meant.

    Endings, near-homophones and number formatting remain uncertain even when
    repeated: a transcript cannot prove a pronunciation error. Only explicit
    lexical substitutions and omissions contribute to this provisional score.
    """
    swaps = diff.get("swaps") or []
    counted = [s for s in swaps if s.get("distant") and not s.get("ending_only")]
    uncertain = [s for s in swaps if s not in counted]
    omissions = [{"expected": fragment, "heard": ""}
                 for fragment in diff.get("missing_runs", [])]
    mistakes = counted + omissions
    misread_words = ege_scoring.gross_errors(mistakes)
    score, note = ege_scoring.score_reading(diff, misread_words)
    errors = [{
        "cat": "lex" if m.get("heard") else "missing",
        "quote": m.get("heard") or "не найдено в расшифровке",
        "correction": m.get("expected") or "",
        "explanation": ("В расшифровке другое слово; проверь запись."
                        if m.get("heard") else "Этот фрагмент не найден в расшифровке; проверь запись."),
    } for m in mistakes[:6]]
    accuracy = ("Балл предварительный: это сверка распознанного текста с эталоном. "
                "Произношение и интонация не оценены; ошибка распознавания возможна.")
    if uncertain:
        accuracy += " Неуверенные различия, включая окончания, не снижают балл."
    return {
        "summary": note + ". " + accuracy,
        "score": score, "max": 1, "errors": errors,
        "misread_words": misread_words,
        "score_status": "provisional",
        "accuracy_note": accuracy,
        "uncertain_words": [{"expected": s["expected"], "heard": s["heard"]}
                            for s in uncertain[:8]],
    }
