"""Оценивание устной части ЕГЭ строго по критериям ФИПИ.

Источник (лежит у владельца, в репозиторий не кладём — авторский документ):
«Методические материалы для председателей и членов предметных комиссий
субъектов РФ по проверке выполнения заданий с развёрнутым ответом
экзаменационных работ ЕГЭ 2026 года. Английский язык (раздел "Говорение")»,
авторы-составители М.В. Вербицкая, К.С. Махмурян. Таблицы 1.3, 1.6-1.11,
Приложения 1-3.

ЗАЧЕМ ОТДЕЛЬНЫЙ МОДУЛЬ. Раньше балл целиком выдумывала языковая модель, и он
гулял от запуска к запуску. Теперь роли разделены:
  ИИ отвечает на вопросы «раскрыт ли аспект», «сколько ошибок», «принят ли
  вопрос» — это и есть работа эксперта;
  шкалу к этим наблюдениям применяет код — арифметика воспроизводима,
  объяснима ученику и проверена тестами против официальных образцов
  проверки работ (см. tests/test_ege_scoring.py: шесть работ из раздела II
  методички воспроизводятся балл в балл).

ЧЕГО ЗДЕСЬ ЧЕСТНО НЕТ — фонетики. На вход системы приходит автоматический
транскрипт, по нему нельзя судить о произношении, ударении и интонации.
Поэтому фонетические ошибки НЕ учитываются нигде, а задание 1, критерий
которого чисто фонетический, оценивается по тому единственному, что видно в
тексте: пропущено/переврано ли слово. Ученику это говорится прямым текстом.
"""

from __future__ import annotations

import difflib
import re

# Максимумы устной части (таблица 1.3 методички: 1 + 4 + 5 + 10 = 20 баллов).
# Внимание: в Приложении 1 методички у задания 2 опечатка («5 вопросов,
# максимум 5»), тело документа и структура КИМ дают 4 вопроса и 4 балла.
MAX_SCORE = {"reading": 1, "dialogue": 4, "interview": 5, "monologue": 10}

FULL, PARTIAL, MISSING = "full", "partial", "missing"
_ASPECT_SIGN = {FULL: "+", PARTIAL: "±", MISSING: "−"}


# --------------------------------------------------------------------------
# Задание 4. Критерий 1 — решение коммуникативной задачи (максимум 4)
# --------------------------------------------------------------------------

def content_from_aspects(missing: int, partial: int) -> int:
    """Балл по РКЗ из числа нераскрытых и неполно раскрытых аспектов.

    Прямая запись таблицы 1.10. Аспектов всегда четыре, поэтому пара
    (не раскрыто, раскрыто неполно) однозначно задаёт балл:

        −0 ±0 → 4 | −0 ±1 → 3 | −0 ±2 → 3 | −0 ±3 → 2 | −0 ±4 → 1
        −1 ±0 → 3 | −1 ±1 → 2 | −1 ±2 → 1 | −1 ±3 → 0
        −2 ±0 → 1 | −2 ±1 → 0 | −3 и более → 0
    """
    if missing >= 3 or (missing == 2 and partial >= 1) or (missing == 1 and partial >= 3):
        return 0
    if (missing == 1 and partial == 2) or (missing == 2 and partial == 0) or (
        missing == 0 and partial == 4
    ):
        return 1
    if (missing == 1 and partial == 1) or (missing == 0 and partial == 3):
        return 2
    if (missing == 1 and partial == 0) or (missing == 0 and 1 <= partial <= 2):
        return 3
    return 4


def _verdict_from_defects(defects: int, unintelligible: bool = False,
                          missing_at: int = 3) -> str:
    """Аспект без изъянов раскрыт, с одним-двумя — неполно/неточно, дальше — нет.

    Порог у аспекта 4 ниже: методичка говорит про мнение прямо — «если
    отсутствуют два элемента из трёх, аспект считается невыполненным».
    """
    if unintelligible or defects >= missing_at:
        return MISSING
    return FULL if defects == 0 else PARTIAL


def verb_form_matches(plan: str, student: str) -> bool:
    """Совпадает ли глагольная форма мнения с той, что требует план задания.

    По критериям это не придирка: «I prefer» на план с «you'd prefer» означает,
    что ученик не понял коммуникативную задачу, и аспект признаётся неточным.
    Сравнение механическое — модель только цитирует обе формы, решение здесь.
    Пустая цитата плана = проверять нечего, придираться не за что.
    """
    plan_s, student_s = (plan or "").lower(), (student or "").lower()
    if not plan_s.strip() or not student_s.strip():
        return True

    def shape(s: str) -> str:
        if "would" in s or "'d " in s or s.startswith("d "):
            return "conditional"
        if "preferred" in s or "used to" in s or "as a child" in s:
            return "past"
        return "present"

    return shape(plan_s) == shape(student_s)


def aspect_verdicts(checks: list[dict]) -> list[dict]:
    """Вердикты по четырём аспектам из простых признаков «да/нет».

    Модель отвечает на конкретные вопросы («описано ли первое фото», «названо
    ли достоинство для второго типа»), а трёхуровневый вердикт выводится здесь.
    Так сделано после замера: на прямой просьбе поставить full/partial/missing
    модель жалась к серединке и разъезжалась между запусками, а на булевых
    признаках держится ровно. Пороги подобраны так, чтобы воспроизводить
    решения экспертов на образцах из методички (см. test_ege_scoring.py).
    """
    by_n = {}
    for c in checks:
        if isinstance(c, dict):
            try:
                by_n[int(c.get("n") or 0)] = c
            except (TypeError, ValueError):
                continue

    out = []
    for n in (1, 2, 3, 4):
        c = by_n.get(n, {})
        no = lambda key: not bool(c.get(key))  # noqa: E731 — «признака нет»
        missing_at = 3

        if n == 1:
            # Описание обоих фото, различие, обобщение различия, связь с темой;
            # фактическая ошибка в описании — тоже изъян.
            defects = sum((no("described_first"), no("described_second"),
                           no("difference_stated"), no("difference_generalised"),
                           no("linked_to_topic"), bool(c.get("factual_error"))))
        elif n in (2, 3):
            # Достоинство (недостаток) названо для каждого из двух типов и не
            # является универсальной отпиской, годной для чего угодно.
            defects = sum((no("named_first"), no("named_second"),
                           no("specific_first"), no("specific_second")))
        else:
            # Мнение: заявлено как своё, выбор назван, обоснован; плюс глагольная
            # форма должна совпадать с той, что требует план задания.
            same_form = verb_form_matches(str(c.get("plan_verb_form") or ""),
                                          str(c.get("student_verb_form") or ""))
            defects = sum((no("opinion_explicit"), no("choice_stated"),
                           no("justified"), not same_form))
            missing_at = 2

        out.append({
            "n": n,
            "verdict": _verdict_from_defects(defects, bool(c.get("unintelligible")),
                                             missing_at),
            "comment": str(c.get("comment") or "").strip(),
        })
    return out


def volume_cap(phrases: int) -> int:
    """Потолок балла по РКЗ, который даёт объём высказывания.

    12-15 фраз — без ограничения, 10-11 — не выше 2, 8-9 — не выше 1,
    7 и меньше — 0 за всё задание. Верхняя граница (больше 15 фраз) в устной
    части не штрафуется: в критериях этого нет.
    """
    if phrases <= 7:
        return 0
    if phrases <= 9:
        return 1
    if phrases <= 11:
        return 2
    return 4


# --------------------------------------------------------------------------
# Задание 4. Критерий 2 — организация высказывания (максимум 3)
# --------------------------------------------------------------------------

def organization_score(opening: bool, closing: bool, logic_errors: int) -> int:
    """Вступление с обращением к другу, заключение и ошибки в логике/связках.

    Отсутствие одной из рамочных фраз само по себе роняет балл до 1
    («не может быть выставлено более 1 балла даже при отсутствии других
    ошибок»), отсутствие обеих — до 0.
    """
    if not opening and not closing:
        return 0
    if logic_errors >= 6:
        return 0
    if not opening or not closing:
        return 1
    if logic_errors >= 4:
        return 1
    if logic_errors >= 2:
        return 2
    return 3


# --------------------------------------------------------------------------
# Задание 4. Критерий 3 — языковое оформление (максимум 3)
# --------------------------------------------------------------------------

def language_score(errors: int, grave: int) -> int:
    """Лексико-грамматические ошибки: всего и из них грубых.

    Фонетику не считаем — её не видно в транскрипте (см. шапку модуля),
    поэтому в пересчёт идёт только лексика и грамматика.
    """
    if errors >= 8 or grave >= 4:
        return 0
    if errors <= 3 and grave == 0:
        return 3
    if errors <= 5 and grave <= 2:
        return 2
    return 1


def score_monologue(
    aspects: list[dict],
    phrases: int,
    opening: bool,
    closing: bool,
    logic_errors: int,
    lang_errors: int,
    grave_errors: int,
) -> dict:
    """Полная оценка задания 4 по трём критериям (максимум 10).

    Главное правило задания: 0 по РКЗ обнуляет всё задание целиком.
    """
    missing = sum(1 for a in aspects if a.get("verdict") == MISSING)
    partial = sum(1 for a in aspects if a.get("verdict") == PARTIAL)

    by_aspects = content_from_aspects(missing, partial)
    cap = volume_cap(phrases)
    content = min(by_aspects, cap)

    org = organization_score(opening, closing, logic_errors)
    lang = language_score(lang_errors, grave_errors)
    if content == 0:
        org = lang = 0

    signs = " ".join(
        f"{i + 1}{_ASPECT_SIGN.get(a.get('verdict'), '?')}" for i, a in enumerate(aspects)
    )
    content_note = f"аспекты: {signs}; объём — {phrases} фраз"
    if cap < by_aspects:
        content_note += f" (объём ограничил балл до {cap})"

    org_note = (
        "нет ни вступления с обращением, ни заключения"
        if not opening and not closing
        else "нет вступления с обращением к другу"
        if not opening
        else "нет заключительной фразы"
        if not closing
        else f"вступление и заключение на месте; ошибок в логике и связках — {logic_errors}"
    )
    lang_note = f"лексико-грамматических ошибок — {lang_errors}, из них грубых — {grave_errors}"
    if content == 0:
        org_note = lang_note = "0 баллов за РКЗ обнуляет всё задание"

    return {
        "criteria": [
            {"key": "task", "name": "Содержание", "score": content, "max": 4,
             "comment": content_note},
            {"key": "organization", "name": "Организация", "score": org, "max": 3,
             "comment": org_note},
            {"key": "language", "name": "Язык", "score": lang, "max": 3,
             "comment": lang_note},
        ],
        "score": content + org + lang,
        "max": 10,
    }


# --------------------------------------------------------------------------
# Задания 2 и 3 — каждый вопрос/ответ отдельно, 1 или 0
# --------------------------------------------------------------------------

def score_items(items: list[dict], max_items: int) -> dict:
    """Сумма зачтённых вопросов (задание 2) или ответов (задание 3).

    Повторяющиеся ошибки внутри одного ответа считаются один раз, но между
    разными вопросами правило повтора НЕ работает: одна и та же ошибка во всех
    вопросах обнуляет их все. Это забота промпта, здесь — только сумма.
    """
    accepted = sum(1 for it in items[:max_items] if it.get("accepted"))
    return {"score": accepted, "max": max_items}


# --------------------------------------------------------------------------
# Задание 1 — чтение вслух
# --------------------------------------------------------------------------

_WORD_RE = re.compile(r"[a-z0-9']+")

# Столько подряд пропущенных слов эталона считаем пропущенной строкой.
SKIPPED_LINE_RUN = 6


def _words(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower().replace("’", "'"))


def reading_diff(reference: str, transcript: str) -> dict:
    """Сверка эталона с тем, что распознано: где пропуски и подмены.

    Транскрипт — не стенограмма: распознавание само по себе ошибается, поэтому
    одиночные расхождения здесь только СОБИРАЮТСЯ как улики, а решение по ним
    принимает модель (она видит, похоже это на оговорку чтеца или на промах
    распознавания). Код решает сам только там, где улика надёжна: большой
    непрочитанный кусок в середине и оборванный хвост.
    """
    ref, got = _words(reference), _words(transcript)
    if not ref:
        return {"ok": False, "reason": "нет эталонного текста"}

    sm = difflib.SequenceMatcher(a=ref, b=got, autojunk=False)
    missing_runs: list[list[str]] = []
    swaps: list[dict] = []
    matched = 0
    tail_missing = 0

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            matched += i2 - i1
        elif tag == "delete":
            missing_runs.append(ref[i1:i2])
            if i2 == len(ref):  # хвост эталона не прозвучал
                tail_missing = i2 - i1
        elif tag == "replace":
            swaps.append({"expected": " ".join(ref[i1:i2]), "heard": " ".join(got[j1:j2])})

    longest_run = max((len(r) for r in missing_runs), default=0)
    missing_total = sum(len(r) for r in missing_runs)
    return {
        "ok": True,
        "ref_words": len(ref),
        "heard_words": len(got),
        "coverage": round(matched / len(ref), 3),
        "missing_total": missing_total,
        "longest_missing_run": longest_run,
        "tail_missing": tail_missing,
        "missing_fragments": [" ".join(r) for r in missing_runs if len(r) >= 2][:6],
        "swaps": swaps[:8],
    }


def score_reading(diff: dict, misread_words: int) -> tuple[int, str]:
    """1 или 0 за чтение вслух.

    Правила ФИПИ, которые видны в тексте: пропущенная строка — 0; не дочитано
    больше двух слов — 0; каждое пропущенное/перевранное слово считается грубой
    ошибкой, при трёх таких ответ — 0. Остальное (произношение, ударение,
    интонация) по транскрипту не проверяется и в балл не идёт.
    """
    if not diff.get("ok"):
        return 0, "не с чем сверять: нет эталонного текста"
    if diff["tail_missing"] > 2:
        return 0, f"текст не дочитан до конца: осталось {diff['tail_missing']} слов"
    if diff["longest_missing_run"] >= SKIPPED_LINE_RUN:
        return 0, f"пропущен кусок текста подряд ({diff['longest_missing_run']} слов) — по критериям это пропущенная строка"
    if misread_words >= 3:
        return 0, f"пропущено или прочитано неверно {misread_words} слова — по критериям это 0 баллов"
    if misread_words:
        return 1, f"текст прочитан, замечено {misread_words} оговорки — на балл это не влияет"
    return 1, "текст прочитан полностью и без пропусков"
