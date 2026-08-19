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
        # Эталон кладём в контекст: по нему проверяется, что «ошибка» указывает
        # на реально написанное слово, а не на выдуманное.
        return ege_prompts.reading_prompt(ref, diff) + extra, {"diff": diff,
                                                              "reference": ref}
    if kind == "dialogue":
        points = [str(p) for p in (payload.get("points") or [])]
        ad = str(payload.get("ad") or "")
        return ege_prompts.dialogue_prompt(ad, points) + extra, {"points": points}
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
        # Ошибка чтения обязана указывать на слово ИЗ ЭТАЛОНА. Слова, которого
        # в тексте нет, ученик не мог прочитать неверно — такую «ошибку»
        # снимаем до подсчёта (05.08.2026, жалоба «находит ошибки там, где их
        # нет»). Сверяем с эталоном, а не с расшифровкой: expected — это то,
        # что было НАПИСАНО.
        reference = str(ctx.get("reference") or "")
        misread = [m for m in (obs.get("misread") or [])
                   if isinstance(m, dict) and m.get("real")
                   and not (reference and ege_scoring.quote_is_fabricated(
                       str(m.get("expected") or ""), reference))]
        # Дубли модели схлопываются ДО всего остального: счёт их и так не
        # считал дважды (gross_errors), но на экране «Повторная ошибка в том
        # же месте» выглядела как двойное наказание — ровно на это пришла
        # жалоба 15.08.2026 («одну и ту же ошибку посчитали за 2 разные»).
        seen_pairs: set[tuple[str, str]] = set()
        unique: list[dict] = []
        for m in misread:
            pair = (str(m.get("expected") or "").strip().lower(),
                    str(m.get("heard") or "").strip().lower())
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            unique.append(m)
        misread = unique
        # Фонетически ДАЛЁКИЕ подмены засчитывает КОД, модель их простить не
        # может (05.08.2026). Распознавание ошибается в сторону похожего
        # звучания; «teachers -> doctors» означает, что другое слово
        # прозвучало. До этого модель списывала на шум вообще всё: три явные
        # подмены получали 1/1 и пустой разбор.
        covered = {str(m.get("expected") or "").strip().lower() for m in misread}
        swaps = ctx["diff"].get("swaps") or []
        for s in swaps:
            if s.get("distant") and s["expected"].strip().lower() not in covered:
                misread.append({"expected": s["expected"], "heard": s["heard"],
                                "explanation": "прочитано другое слово"})
                covered.add(s["expected"].strip().lower())
        # Систематически искажённые окончания — тоже решение КОДА: одиночное
        # распознавание глотает честно, но два и больше в одной записи оно не
        # производит. Правило было только в промпте, и модель его не исполняла.
        for s in ege_scoring.ending_pattern(swaps):
            if s["expected"].strip().lower() not in covered:
                misread.append({"expected": s["expected"], "heard": s["heard"],
                                "explanation": "форма слова прочитана неверно"})
                covered.add(s["expected"].strip().lower())
        # Одиночная потеря окончания — шум распознавания, а не ошибка чтеца.
        # Для подмен, которые находит КОД, это правило действует давно
        # (ending_pattern требует двух и больше), но модель могла записать
        # одиночное окончание грубой ошибкой САМА — и «game» вместо «games»
        # становилось третьим словом, обнулявшим работу (жалоба 15.08.2026:
        # счёт 3 = games + choose + thus). Правило одно, исполняет его код:
        # без систематики ending-подмены не считаются и не показываются.
        systematic = {(s["expected"].strip().lower(), s["heard"].strip().lower())
                      for s in ege_scoring.ending_pattern(swaps)}
        if not systematic:
            endings = {(s["expected"].strip().lower(), s["heard"].strip().lower())
                       for s in swaps if s.get("ending_only")}
            misread = [m for m in misread
                       if (str(m.get("expected") or "").strip().lower(),
                           str(m.get("heard") or "").strip().lower())
                       not in endings]
        # Считаем СЛОВА, а не пункты списка, и по официальным правилам счёта:
        # одно и то же перевранное слово — одна ошибка, а каждый пропуск —
        # отдельная (методичка ФИПИ, задание 1; см. ege_scoring.gross_errors).
        misread_words = ege_scoring.gross_errors(misread)
        score, note = ege_scoring.score_reading(ctx["diff"], misread_words)
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
                why = ege_scoring.question_rejected(str(it.get("heard") or ""))
                if why:
                    ok = False
                    it = {**it, "accepted": False, "reason": why}
                    print(f"[40] вопрос {i + 1} отклонён кодом: {why}")
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
        return {"summary": summary, "score": res["score"], "max": res["max"],
                "errors": errors, "criteria": criteria}

    # monologue: модель отвечает признаками «да/нет», вердикты выводит шкала
    aspects = ege_scoring.aspect_verdicts(obs.get("aspects") or [])
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
            "errors": errors, "criteria": res["criteria"]}
