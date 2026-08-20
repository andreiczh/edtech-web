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


# Сколько аспектов максимум уходит на второй взгляд. Четвёртый не добавляем
# намеренно: пересмотр ВСЕГО ответа — это просто второй первый проход, а нам
# нужен сфокусированный взгляд на спорное.
_MAX_RECHECK_ASPECTS = 3


def doubtful_aspects(observations: dict, transcript: str) -> list[int]:
    """Номера аспектов, которые стоит пересмотреть вторым взглядом.

    Спорным считается ровно то, где балл РЕАЛЬНО может качнуться:

      * вердикт «неполно» — именно на этой границе шкала переключает балл, а
        первый проход выставляет её неустойчиво (замер 05.08.2026: три прогона
        на неизменном коде дали 5, 2 и 3 попадания из шести — вердикты по
        аспектам гуляют между запусками сильнее любой нашей правки);
      * улик нет, а признаки стоят «да» — аспект зачтён по памяти о работе, а
        не по словам ученика. Промпт это запрещает прямо, и когда запрет
        нарушен, вердикт не на чем держаться;
      * улика не находится в расшифровке — процитировано несказанное.

    Аспект, раскрытый полностью и подтверждённый цитатой, не трогаем: второй
    взгляд на бесспорное только добавит шума.
    """
    verdicts = {a["n"]: a["verdict"] for a in aspect_verdicts(
        observations.get("aspects") or [])}
    by_n: dict[int, dict] = {}
    for c in (observations.get("aspects") or []):
        if isinstance(c, dict):
            try:
                by_n[int(c.get("n") or 0)] = c
            except (TypeError, ValueError):
                continue

    out: list[tuple[int, int]] = []  # (вес, номер) — важное вперёд
    for n in (1, 2, 3, 4):
        c = by_n.get(n)
        if c is None:
            continue
        evidence = str(c.get("evidence") or "").strip()
        flags_on = any(v is True for k, v in c.items()
                       if k not in ("factual_error", "unintelligible"))
        weight = 0
        if evidence and quote_is_fabricated(evidence, transcript):
            weight = 3
        elif not evidence and flags_on:
            weight = 3
        elif verdicts.get(n) == PARTIAL:
            weight = 2
        if weight:
            out.append((weight, n))
    out.sort(key=lambda p: (-p[0], p[1]))
    return sorted(n for _w, n in out[:_MAX_RECHECK_ASPECTS])


def merge_aspect_recheck(observations: dict, verdicts: object) -> int:
    """Вложить пересмотренные признаки обратно. Возвращает число изменённых.

    Меняем ТОЛЬКО признаки тех аспектов, которые отправляли на пересмотр, и
    только те ключи, что модель вернула: второй проход не должен подчистить
    заодно то, о чём его не спрашивали.
    """
    if not isinstance(verdicts, list):
        return 0
    by_n: dict[int, dict] = {}
    for c in (observations.get("aspects") or []):
        if isinstance(c, dict):
            try:
                by_n[int(c.get("n") or 0)] = c
            except (TypeError, ValueError):
                continue
    changed = 0
    for v in verdicts:
        if not isinstance(v, dict):
            continue
        try:
            n = int(v.get("n") or 0)
        except (TypeError, ValueError):
            continue
        target = by_n.get(n)
        if target is None:
            continue
        for key, value in v.items():
            if key == "n":
                continue
            if isinstance(value, bool) and bool(target.get(key)) != value:
                changed += 1
            if key in ("evidence", "comment") or isinstance(value, bool) \
                    or key.endswith("_verb_form"):
                target[key] = value
    return changed


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

# Начала, которые методичка прямо НЕ считает обращением к другу: ученик сразу
# перешёл к делу. Если ответ начинается так — спасать нечего.
_NOT_AN_ADDRESS = (
    "i'd like", "i would like", "i want to", "i wanna", "i'm going to",
    "i am going to", "there are", "there is", "today i", "let me", "in the",
    "so i", "well i", "this is", "my name", "these two", "two photos",
)
# Мусорные зачины: их методичка велит не считать вовсе, и обращением они не были.
_FILLERS = {"um", "uh", "er", "erm", "mm", "hmm", "so", "well", "okay", "ok",
            "yeah", "yes", "right", "and", "but"}


def opening_rescued(transcript: str) -> bool:
    """Было ли обращение к другу, СЪЕДЕННОЕ распознаванием.

    Замер на проде 16.08.2026: «Hello Max!» с русским акцентом Voxtral
    расшифровал как «Philomach», модель честно не увидела обращения, и код по
    методичке срезал организацию с 3 до 1 — ученик потерял два балла за
    приветствие, которое произнёс. Механическое правило, зависящее от одного
    слова, обязано иметь спасение: обращение короткое, стоит первым и потому
    страдает от распознавания чаще всего в ответе.

    Спасаем ТОЛЬКО тот случай, который ни на что другое не похож: первая фраза
    короче четырёх слов, не мусорный зачин и не один из зачинов «сразу к делу»
    из методички. Настоящий ответ без обращения начинается длинной фразой
    («I want to tell you about two photos...») и под спасение не попадает.

    Это осознанная мягкость: цена ошибки здесь несимметрична. Лишний балл
    спорной работе — мелочь, отнятый у честной — то, из-за чего перестают
    верить проверке.
    """
    head = re.split(r"[.!?]", str(transcript or "").strip(), maxsplit=1)[0]
    words = [w for w in re.findall(r"[a-zA-Z']+", head)]
    if not words or len(words) > 3:
        return False
    low = " ".join(words).lower()
    if any(low.startswith(p) for p in _NOT_AN_ADDRESS):
        return False
    return not all(w.lower() in _FILLERS for w in words)


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

def missing_items(kind: str, observations: dict, expected: int) -> int:
    """Сколько пунктов разбора модель НЕ ВЕРНУЛА (задания 2 и 3).

    Балл здесь — сумма зачтённых пунктов, поэтому недостающий пункт молча
    становится нулём: ученик, ответивший на все пять вопросов, получает 1 из 5,
    если модель прислала один пункт. Это не строгость проверки, а её обрыв, и
    отличить одно от другого ученик не может — он видит «неправильно» и всё.

    Поймано прогоном по проду 16.08.2026 (интервью из пяти полных ответов:
    один критерий на экране, балл 1/5) и совпадает с жалобой владельца
    «теряет критерии». Возвращает 0, когда всё на месте.
    """
    if kind not in ("dialogue", "interview") or expected <= 0:
        return 0
    key = "questions" if kind == "dialogue" else "answers"
    got = len([it for it in (observations.get(key) or []) if isinstance(it, dict)])
    return max(0, expected - got)


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


# Ниже этого сходства подмена считается ФОНЕТИЧЕСКИ ДАЛЁКОЙ — то есть ошибкой
# чтеца по построению, без права модели её простить. Обоснование (05.08.2026):
# распознавание ошибается В СТОРОНУ ПОХОЖЕГО ЗВУЧАНИЯ — теряет окончания, путает
# омофоны, — но не превращает «teachers» в «doctors». Далёкая подмена означает,
# что другое слово ПРОЗВУЧАЛО. До этого решение целиком отдавалось модели, и
# она списывала на «шум распознавания» вообще всё: три явные подмены — балл 1/1
# и ноль ошибок в разборе (поймано живым прогоном и тестировщиком).
_DISTANT_SIMILARITY = 0.7


def _endings_only(exp: str, heard: str) -> bool:
    """Отличаются ли два слова ТОЛЬКО хвостовым -s/-es/-ed.

    Одиночная такая пара — законный промах распознавания: оно глотает
    окончания. Но две и больше в одной записи распознавание не производит,
    это уже манера чтеца (см. _ENDING_PATTERN_AT).
    """
    a, b = exp.strip().lower(), heard.strip().lower()
    if not a or not b or " " in a or " " in b or a == b:
        return False
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    # Корень короче трёх букв — это служебное слово («a» против «as»), и
    # разница в нём не про окончание, а про другое слово целиком.
    if len(short) < 3:
        return False
    return long_.startswith(short) and long_[len(short):] in ("s", "es", "d", "ed")


def _swap_entry(exp_words: list[str], heard_words: list[str]) -> dict:
    exp, heard = " ".join(exp_words), " ".join(heard_words)
    sim = difflib.SequenceMatcher(a=exp, b=heard, autojunk=False).ratio()
    # Страховки от самообвинения: короткие слова (it/at) распознавание путает
    # честно, а цифры оно записывает словами (5000 -> five thousand) — такое
    # далёкой подменой не считается, пусть решает модель.
    distant = (sim < _DISTANT_SIMILARITY and len(exp) >= 4 and bool(heard)
               and not any(ch.isdigit() for ch in exp + heard))
    return {"expected": exp, "heard": heard, "similarity": round(sim, 2),
            "distant": distant, "ending_only": _endings_only(exp, heard)}


# Со скольких искажённых окончаний это перестаёт быть шумом распознавания.
# Два — потому что одно распознавание глотает регулярно, а два подряд в одной
# короткой записи означают, что чтец систематически меняет формы слов.
# Правило было ТОЛЬКО в промпте — и модель его не исполняла: живой прогон
# 05.08.2026 дважды подряд простил три искажённые формы и поставил 1/1.
# Механическое правило должен исполнять код, а не уговоры.
_ENDING_PATTERN_AT = 2


def ending_pattern(swaps: list[dict]) -> list[dict]:
    """Подмены-окончания, если их набралось на систему. Иначе пусто."""
    marked = [s for s in swaps if s.get("ending_only")]
    return marked if len(marked) >= _ENDING_PATTERN_AT else []


# Длина совпадения, которую засчитываем ВТОРЫМ заходом. Три слова подряд —
# уже не случайность; на двух («of the», «in the») текст на сто слов дал бы
# ложное покрытие где угодно.
_REREAD_MIN_RUN = 3
_REREAD_PASSES = 2


def _rescue_reread(ref: list[str], leftover: list[str], covered: list[bool]) -> int:
    """Отметить слова эталона, прозвучавшие ВТОРЫМ заходом. Возвращает сколько.

    Зачем. Основное выравнивание монотонно: оно ищет один сквозной проход по
    тексту. Ученик, который начал читать с середины, а потом вернулся к началу,
    для него выглядит так, будто начало он не читал вовсе — и получает пропуск
    за прочитанное (замер 05.08.2026: покрытие 0.61 вместо 1.00, двенадцать
    прочитанных слов записаны в непрочитанные).

    Правило от тестировщика простое и справедливое: слово засчитано, если оно
    прозвучало ХОТЯ БЫ РАЗ, в любом заходе. Отсюда и остальные его случаи:
    ошибся и сам поправил — засчитано; прочитал половину и начал заново —
    засчитано; вернулся перечитать середину — то, что уже прочитано, не
    обнуляется.

    Спасаем ТОЛЬКО то, что основной проход счёл непрочитанным, и только по
    длинным совпадениям: обычное чтение ведёт себя ровно как раньше.
    """
    saved = 0
    rest = list(leftover)
    for _ in range(_REREAD_PASSES):
        if not rest:
            break
        sm = difflib.SequenceMatcher(a=ref, b=rest, autojunk=False)
        used: set[int] = set()
        progress = False
        for block in sm.get_matching_blocks():
            if block.size < _REREAD_MIN_RUN:
                continue
            for k in range(block.size):
                if not covered[block.a + k]:
                    covered[block.a + k] = True
                    saved += 1
                    progress = True
                used.add(block.b + k)
        if not progress:
            break
        rest = [w for i, w in enumerate(rest) if i not in used]
    return saved


def reading_diff(reference: str, transcript: str) -> dict:
    """Сверка эталона с тем, что распознано: где пропуски и подмены.

    Транскрипт — не стенограмма: распознавание само по себе ошибается, поэтому
    одиночные расхождения здесь только СОБИРАЮТСЯ как улики, а решение по ним
    принимает модель (она видит, похоже это на оговорку чтеца или на промах
    распознавания). Код решает сам только там, где улика надёжна: большой
    непрочитанный кусок в середине и оборванный хвост.

    Слово считается прочитанным, если прозвучало ХОТЯ БЫ РАЗ — см.
    _rescue_reread. Поэтому самоисправление ученику не вредит: подмена, которую
    он сам же и поправил, из улик выбрасывается.
    """
    ref, got = _words(reference), _words(transcript)
    if not ref:
        return {"ok": False, "reason": "нет эталонного текста"}

    sm = difflib.SequenceMatcher(a=ref, b=got, autojunk=False)
    opcodes = sm.get_opcodes()
    covered = [False] * len(ref)
    used_got: set[int] = set()
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            for k in range(i1, i2):
                covered[k] = True
            used_got.update(range(j1, j2))
    # Слова расшифровки, не вошедшие в сквозной проход, — это либо шум
    # распознавания, либо ВТОРОЙ ЗАХОД на текст. Проверяем второе.
    reread = _rescue_reread(
        ref, [w for i, w in enumerate(got) if i not in used_got], covered)

    missing_runs: list[list[str]] = []
    swaps: list[dict] = []
    matched = sum(covered)
    tail_missing = 0

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue
        # Кусок, спасённый вторым заходом, уликой больше не является: ученик
        # эти слова прочитал, пусть и не с первого раза.
        if tag in ("delete", "replace") and all(covered[i1:i2]):
            continue
        if tag == "delete":
            missing_runs.append(ref[i1:i2])
            if i2 == len(ref):  # хвост эталона не прозвучал
                tail_missing = i2 - i1
        elif tag == "replace":
            # Пропуск, примкнувший к ошибке распознавания, difflib показывает
            # как ОДНУ замену: «двадцать слов эталона -> два услышанных».
            # Считать это оговоркой нельзя — по критериям пропущенная строка
            # обнуляет задание, а «прочитано иначе» нет. Тестировщик поймал
            # ровно это: «я пропустил предложение, а написало, что прочитано
            # иначе» (05.08.2026).
            #
            # Порог 3 — чтобы не записывать в пропуски обычные подмены, где
            # услышано на слово-два меньше («is shaking» -> «shakes»).
            lost = (i2 - i1) - (j2 - j1)
            if lost >= 3:
                missing_runs.append(ref[i1:i2])
                if i2 == len(ref):
                    tail_missing = lost
            else:
                swaps.append(_swap_entry(ref[i1:i2], got[j1:j2]))

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
        # Сколько слов зачтено ВТОРЫМ заходом. Ноль — читал сквозняком; больше
        # нуля — возвращался и перечитывал, и это ему не в минус.
        "reread": reread,
    }


# --------------------------------------------------------------------------
# Санитарный шлюз: мусор отсеивается ДО вызова модели
# --------------------------------------------------------------------------

# Меньше стольких слов — это физически не ответ на задание такого типа.
# Пороги нарочно у пола: интервью из пяти ответов по две фразы не бывает
# короче 15 слов, монолог на 12-15 фраз — короче 25. Настоящая попытка,
# даже слабая, проходит с запасом; отсеивается только «пара абстрактных слов».
_GATE_MIN_WORDS = {"reading": 8, "dialogue": 6, "interview": 15, "monologue": 25}


# --------------------------------------------------------------------------
# Сверка цитат: сказал ли ученик то, что ему приписывают
# --------------------------------------------------------------------------
#
# Зачем (05.08.2026). Жалоба тестировщика «иногда находит ошибки там, где их
# нет» — это не про строгость, а про ВЫДУМАННЫЕ улики. Модель может честно
# ошибиться в суждении, но не имеет права цитировать несказанное: на цитате
# держится и балл, и доверие ученика к разбору.
#
# В разборе разговора такая сверка уже работает (talk_review.verify) и ловит
# выдумки штучно. Здесь то же самое, но для оцениваемых заданий, где цена
# ошибки — балл ЕГЭ.
#
# Проверка НАРОЧНО щадящая: модель имеет право почистить цитату от мусора
# распознавания («the the course» -> «the course»), и это не выдумка. Поэтому
# ищем не точное вхождение, а самый длинный НЕПРЕРЫВНЫЙ кусок совпадения:
# настоящая цитата даёт длинную серию, выдуманная — обрывки.

# Доля цитаты, которую обязан подтвердить источник. Половина — с большим
# запасом в пользу модели: ложное обвинение в выдумке стоит лишнего второго
# прохода и стёртой цитаты на экране, а пропущенная выдумка — только того же,
# что и сегодня.
_QUOTE_SUPPORT = 0.5


def quote_support(quote: str, source: str) -> float:
    """Какая доля слов цитаты подтверждается непрерывным куском источника."""
    q, s = _words(quote), _words(source)
    if not q:
        return 1.0  # пустую цитату проверять не на чем
    if not s:
        return 0.0
    match = difflib.SequenceMatcher(a=q, b=s, autojunk=False).find_longest_match(
        0, len(q), 0, len(s))
    return match.size / len(q)


def quote_is_fabricated(quote: str, source: str) -> bool:
    """Приписана ли ученику фраза, которой он не говорил.

    Пустая цитата выдумкой НЕ считается: у незаданного вопроса её и не может
    быть, это законный случай «не прозвучало».
    """
    q = _words(quote)
    if not q:
        return False
    if len(q) <= 2:
        # У цитаты в одно-два слова «половина» ничего не значит — ищем целиком.
        return f" {' '.join(q)} " not in f" {' '.join(_words(source))} "
    return quote_support(quote, source) < _QUOTE_SUPPORT


# Подозрительно короткий ЗАЧТЁННЫЙ ответ. Не приговор — повод для второго
# взгляда: тестировщик поймал, что оборванная на середине фраза засчитывалась.
#
# №40: прямой вопрос короче трёх слов не бывает («How much is it?» — четыре).
# №41: задание требует полного ответа в 2-3 предложения; восемь слов — это
# заведомо не он, но порог намеренно вдвое ниже правдоподобного, чтобы не
# трогать короткие, но настоящие ответы.
_MIN_ACCEPTED_WORDS = {"dialogue": 3, "interview": 8}


def flag_suspicious(kind: str, observations: dict, transcript: str) -> list[str]:
    """Пометить пункты, которым нельзя верить на слово. Возвращает список причин.

    Ничего не решает и баллов не трогает: только ставит `borderline`, чтобы
    пункт ушёл на второй проход, и `quote_missing`, чтобы выдуманная цитата не
    доехала до экрана.
    """
    if kind not in ("dialogue", "interview"):
        return []
    key = "questions" if kind == "dialogue" else "answers"
    items = [it for it in (observations.get(key) or []) if isinstance(it, dict)]
    need = _MIN_ACCEPTED_WORDS.get(kind, 3)
    notes = []
    for i, it in enumerate(items):
        heard = str(it.get("heard") or "").strip()
        if quote_is_fabricated(heard, transcript):
            it["quote_missing"] = True
            it["borderline"] = True
            notes.append(f"№{i + 1}: цитаты нет в расшифровке")
            continue
        if it.get("accepted") and heard and len(_words(heard)) < need:
            it["too_short"] = True
            it["borderline"] = True
            notes.append(f"№{i + 1}: зачтён ответ из {len(_words(heard))} слов")
    return notes


def drop_unsupported(errors: list, transcript: str, need_quote: bool = True) -> list:
    """Ошибки без опоры в речи ученика — вон, ДО подсчёта балла.

    Их две породы, и обе несправедливы одинаково: выдуманная цитата и цитата,
    которой нет вовсе. И то и другое занижает балл за язык, а проверить ученику
    нечем. Нет улики — нет наказания.
    """
    kept = []
    for e in errors:
        if not isinstance(e, dict):
            continue
        quote = str(e.get("quote") or "").strip()
        if need_quote and not quote:
            continue
        if quote and quote_is_fabricated(quote, transcript):
            continue
        kept.append(e)
    return kept


def _plural_words(n: int) -> str:
    """«2 слова», а не «2 слов»: текст видит ученик, и корявость в нём читается
    как небрежность всей проверки."""
    tail = n % 100
    if 11 <= tail <= 14:
        form = "слов"
    elif n % 10 == 1:
        form = "слово"
    elif n % 10 in (2, 3, 4):
        form = "слова"
    else:
        form = "слов"
    return f"{n} {form}"


def sanity_gate(kind: str, transcript: str) -> str | None:
    """Причина отказа без вызова модели — или None, если ответ похож на ответ.

    Смысл двойной: ученик получает мгновенный честный ноль вместо
    льстивого разбора чепухи, а квота LLM не тратится на мусор.
    Проверки только детерминированные — здесь НЕ место суждениям."""
    words = _words(transcript)
    need = _GATE_MIN_WORDS.get(kind, 8)
    if len(words) < need:
        return (f"ответ слишком короткий: {_plural_words(len(words))}, а для этого "
                f"задания нужно хотя бы {need} — попробуй ответить развёрнуто")
    # Одна фраза по кругу: уникальных слов почти нет. Порог 0.25 не трогает
    # живую речь (у неё доля уникальных 0.5+ даже с повторами-паразитами).
    if len(words) >= 12 and len(set(words)) / len(words) < 0.25:
        return ("похоже на одну и ту же фразу по кругу — повторение не "
                "считается ответом на задание")
    return None


# Ниже этой доли совпадения с эталоном «чтение» не считается чтением вообще.
# Порог нарочно щадящий: даже слабое чтение с акцентом и оговорками даёт
# coverage 0.7+, а полсотни процентов не набирает только речь НЕ по тексту.
MIN_READ_COVERAGE = 0.5


def gross_errors(misread: list[dict]) -> int:
    """Сколько ГРУБЫХ ошибок по официальному счёту (методичка ФИПИ, задание 1).

    Правил два, и они разные для двух видов ошибок:

      * «Считать повторяющимися ошибками только ошибки в произнесении ОДНОГО И
        ТОГО ЖЕ слова» — переврал `science` дважды, это ОДНА ошибка;
      * «каждый пропуск слова считается отдельно и не является повторяющейся
        ошибкой» — пропустил два раза одно и то же слово, это ДВЕ ошибки.

    Раньше мы считали всё подряд, и ученик, спотыкавшийся на одном трудном
    слове, набирал три «грубых» за одно и то же — то есть получал ноль там, где
    эксперт поставил бы балл.

    Подмена, накрывшая несколько слов сразу («stronger teachers» -> «strange
    doctors»), считается по числу слов эталона: по критериям каждое перевранное
    слово — отдельная грубая ошибка.
    """
    seen: set[str] = set()
    total = 0
    for m in misread:
        expected = str(m.get("expected") or "").strip()
        words = expected.split()
        skipped = not str(m.get("heard") or "").strip()
        if skipped:
            total += max(1, len(words))      # пропуски считаются каждый раз
            continue
        key = expected.lower()
        if key in seen:
            continue                          # то же слово переврано снова — не в счёт
        seen.add(key)
        total += max(1, len(words))
    return total


def score_reading(diff: dict, misread_words: int) -> tuple[int, str]:
    """1 или 0 за чтение вслух.

    Правила ФИПИ, которые видны в тексте: пропущенная строка — 0; не дочитано
    больше двух слов — 0; каждое пропущенное/перевранное слово считается грубой
    ошибкой, при трёх таких ответ — 0. Остальное (произношение, ударение,
    интонация) по транскрипту не проверяется и в балл не идёт.
    """
    if not diff.get("ok"):
        return 0, "не с чем сверять: нет эталонного текста"
    # Сначала — совпадение в целом. Без этой проверки был реальный обход:
    # скажи вместо текста любую отсебятину, и difflib пометит весь эталон
    # «заменой», а не «пропуском» — missing_total останется 0, и ответ
    # проходил как «прочитан полностью» при coverage 0.0. Поймано 03.08.2026
    # живым запросом: «Well, you know, actually...» получал 1/1.
    if diff.get("coverage", 0.0) < MIN_READ_COVERAGE:
        pct = round(diff.get("coverage", 0.0) * 100)
        return 0, (f"это не чтение задания: с текстом совпало лишь {pct}% слов — "
                   "нужно читать вслух именно предложенный текст")
    if diff["tail_missing"] > 2:
        return 0, f"текст не дочитан до конца: осталось {diff['tail_missing']} слов"
    if diff["longest_missing_run"] >= SKIPPED_LINE_RUN:
        return 0, f"пропущен кусок текста подряд ({diff['longest_missing_run']} слов) — по критериям это пропущенная строка"
    if misread_words >= 3:
        return 0, f"пропущено или прочитано неверно {misread_words} слова — по критериям это 0 баллов"
    if misread_words:
        return 1, f"текст прочитан, замечено {misread_words} оговорки — на балл это не влияет"
    return 1, "текст прочитан полностью и без пропусков"


# Формы вопросов, которые методичка ФИПИ (задание 2) отвергает ПОИМЁННО.
# Правила уже были в промпте, но модель прощала их через раз: замер на пяти
# работах практикума 19.08.2026 дал 16 вердиктов из 20, и все четыре промаха —
# в пользу ученика, на разобранных в методичке примерах. Принцип проекта: если
# правило механическое, исполняет его КОД, а не суждение модели.
_Q_MEANINGLESS = (
    # «место» вместо объекта: спрашивается, где находится ваше местоположение
    re.compile(r"\bwhere\s+is\s+(the|your|their)\s+location\b", re.I),
    re.compile(r"\bhow\s+much\s+is\s+the\s+price\b", re.I),
    re.compile(r"\bhow\s+long\s+are\s+the\s+opening\s+hours\b", re.I),
    re.compile(r"\bis\s+(the\s+)?admission\s+fee\s+free\b", re.I),
    re.compile(r"\bcan\s+i\s+get\s+the\s+admission\s+fee\b", re.I),
)
# Просьба вместо прямого вопроса.
_Q_REQUEST = (
    re.compile(r"^\s*what\s+about\b", re.I),
    re.compile(r"\bcould\s+you\s+tell\s+me\s+about\b", re.I),
    re.compile(r"^\s*tell\s+me\s+about\b", re.I),
)
# Страдательный залог переворачивает смысл: спрашивают, чему учат САМОГО
# ученика, а не что преподают в школе («What kind of dances are you taught?»).
_Q_PASSIVE = re.compile(r"\bare\s+you\s+(taught|offered|given|provided)\b", re.I)
# «Which» вместо «what» там, где выбирать не из чего: методичка разбирает
# два примера — «Which accommodation do you offer?» (надо what / what kind of)
# и «Which types of cars do you use?». «Which of the ...» не трогаем: там
# выбор идёт из НАЗВАННОГО набора, и такой вопрос правильный.
_Q_WHICH = re.compile("^" + r"\s*which\s+" + "(?!of[^a-z])" + "[a-z]", re.I)
# Определители, после которых артикль не нужен.
_DETERMINERS = {"the", "a", "an", "your", "their", "his", "her", "its", "my",
                "our", "this", "that", "these", "those", "any", "some"}


def question_rejected(text: str) -> str:
    """Почему вопрос не принимается по методичке — или пустая строка.

    Только те случаи, которые методичка разбирает ПОИМЁННО и которые видны в
    тексте без суждения. Спорное здесь не решается: сомнительный вопрос
    проходит и достаётся модели.
    """
    q = str(text or "").strip()
    if not q:
        return ""
    for rx in _Q_MEANINGLESS:
        if rx.search(q):
            return "вопрос бессмысленный: методичка разбирает эту формулировку отдельно"
    for rx in _Q_REQUEST:
        if rx.search(q):
            return "это просьба, а не прямой вопрос"
    if _Q_PASSIVE.search(q):
        return "страдательный залог переворачивает смысл вопроса"
    if _Q_WHICH.match(q):
        return "нужен «what», а не «which»: выбирать не из чего"
    # «What is minimum age for students?», «What is tutation fee?» — отсутствие
    # артикля меняет смысл: спрашивают о возрасте вообще, а не о минимальном
    # возрасте в ЭТОЙ школе. Собственные имена и определители не трогаем.
    m = re.match(r"^\s*what(?:'s|\s+is)\s+([a-z']+)", q, re.I)
    if m:
        first = m.group(1).lower()
        raw = re.match(r"^\s*what(?:'s|\s+is)\s+([A-Za-z']+)", q)
        proper = bool(raw and raw.group(1)[:1].isupper())
        if first not in _DETERMINERS and not proper:
            return "пропущен артикль, и это меняет смысл вопроса"
    return ""


# --------------------------------------------------------------------------
# Задание 3 (наше 41): счёт полных фраз в ответе
# --------------------------------------------------------------------------
# Методичка требует минимум ДВЕ полные фразы и прямо перечисляет, что фразой
# не является: «Not many», «Sure», «Quite warm», «In the village» — обрывки без
# сказуемого. Правило стояло в промпте, и модель исполняла его через раз:
# замер 19.08.2026 на шести работах дал 25 вердиктов из 30, и все пять
# промахов — в пользу ученика. Пятый случай в проекте, когда механическое
# правило приходится переносить в КОД.
#
# Глаголы уровня A1-A2 плюс связки и модальные: список закрытый и намеренно
# широкий. Ошибиться здесь можно в две стороны, и они НЕ равноценны: назвать
# фразой обрывок — мягкость на один ответ, назвать обрывком настоящую фразу —
# отнятый балл у того, кто ответил верно. Поэтому короткая фраза без глагола
# из списка считается обрывком, а длинная — фразой ВСЕГДА, даже если глагол
# нам незнаком.
_A2_VERBS = {
    "am", "is", "are", "was", "were", "be", "been", "being", "'s", "'re", "'m",
    "have", "has", "had", "do", "does", "did", "can", "could", "will", "would",
    "shall", "should", "may", "might", "must", "need", "used",
    "like", "likes", "liked", "love", "loves", "loved", "hate", "hates",
    "prefer", "prefers", "preferred", "want", "wants", "wanted", "think",
    "thinks", "thought", "know", "knows", "knew", "live", "lives", "lived",
    "go", "goes", "went", "come", "comes", "came", "get", "gets", "got",
    "make", "makes", "made", "take", "takes", "took", "give", "gives", "gave",
    "see", "sees", "saw", "read", "reads", "spend", "spends", "spent",
    "play", "plays", "played", "study", "studies", "studied", "work", "works",
    "worked", "help", "helps", "helped", "enjoy", "enjoys", "enjoyed",
    "visit", "visits", "visited", "travel", "travels", "travelled", "traveled",
    "watch", "watches", "watched", "listen", "listens", "eat", "eats", "ate",
    "drink", "drinks", "buy", "buys", "bought", "find", "finds", "found",
    "feel", "feels", "felt", "become", "becomes", "became", "seem", "seems",
    "look", "looks", "looked", "say", "says", "said", "tell", "tells", "told",
    "ask", "asks", "asked", "answer", "answers", "start", "starts", "started",
    "finish", "finishes", "learn", "learns", "learned", "learnt", "try",
    "tries", "tried", "keep", "keeps", "kept", "let", "put", "puts", "run",
    "runs", "ran", "walk", "walks", "walked", "swim", "swims", "swam",
    "remember", "remembers", "choose", "chooses", "chose", "believe",
    "believes", "hope", "hopes", "wish", "wishes", "consider", "considers",
    "cost", "costs", "last", "lasts", "depend", "depends", "improve",
    "improves", "develop", "develops", "teach", "teaches", "taught",
}
# Короче этого фраза без знакомого глагола считается обрывком. Пять токенов —
# порог из самих примеров методички: «Somewhere far from big cities» (пять
# слов) она называет неполным предложением.
_FRAGMENT_MAX = 5


def count_phrases(answer: str) -> int:
    """Сколько ПОЛНЫХ фраз в ответе ученика (методичка, задание 3).

    Фразой считается предложение со сказуемым. Обрывки («Quite warm»,
    «In the village», «Joan Rowling») не в счёт — методичка перечисляет их
    поимённо. Повтор той же фразы второй фразой не становится.
    """
    text = re.sub(r"\s+", " ", str(answer or "")).strip()
    if not text:
        return 0
    seen: set[str] = set()
    total = 0
    for raw in re.split(r"[.!?]+", text):
        words = re.findall(r"[A-Za-z']+", raw)
        if not words:
            continue
        low = [w.lower() for w in words]
        has_verb = any(w in _A2_VERBS for w in low) or any(
            w.endswith("'s") or w.endswith("'re") or w.endswith("'m") for w in low)
        if len(words) <= _FRAGMENT_MAX and not has_verb:
            continue                      # обрывок
        key = " ".join(low)
        if key in seen:
            continue                      # та же фраза дважды — одна фраза
        seen.add(key)
        total += 1
    return total


def answer_too_short(answer: str) -> str:
    """Причина отказа по объёму — или пустая строка.

    Отдельной функцией, а не проверкой на месте: причина уезжает ученику на
    экран, и она обязана быть человеческой.
    """
    n = count_phrases(answer)
    if n == 0:
        return "в ответе нет ни одной полной фразы — только обрывки"
    if n == 1:
        return "нужно минимум две полные фразы, здесь одна"
    return ""
