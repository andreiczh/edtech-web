"""Промпты эксперта ЕГЭ: правила проверки из методички ФИПИ 2026.

Разделение труда с `ege_scoring.py` жёсткое и намеренное:
  ЗДЕСЬ модель просят вынести суждения эксперта — раскрыт ли аспект, принят ли
  вопрос, сколько ошибок и какие они;
  ТАМ по этим суждениям считается балл.
Модель НЕ называет баллы вообще: как только ей позволяли это делать, оценка
гуляла от запуска к запуску и не сходилась с официальными образцами.

Правила ниже — не пересказ своими словами, а перенос конкретных указаний
экспертам: какие вопросы принимаются, что считается фразой, чем «неполно»
отличается от «не раскрыто». Формулировки на английском намеренно: транскрипт
английский, и модель на нём точнее; по-русски она пишет только то, что увидит
ученик (comment, reason, explanation, summary).
"""

from __future__ import annotations

import json

# --------------------------------------------------------------------------
# Строгость проверки — зависит от выбранного собеседника.
#
# ЧТО можно менять строгостью, а что нельзя, — граница принципиальная:
#   МОЖНО: как решаются спорные случаи (реальные эксперты расходятся на ±1 в
#   рамках тех же правил — методичка прямо описывает третью проверку); сколько
#   ошибок попадает в разбор; тон русских комментариев.
#   НЕЛЬЗЯ: сами правила, калибровочные примеры и шкалы ege_scoring. Иначе балл
#   перестаёт быть экзаменационным, и вся ценность тренажёра исчезает.
# Поэтому каждый блок начинается с напоминания, что калибровка выше строгости.

STRICTNESS: dict[str, str] = {
    # Наставник: нейтральный эксперт, поведение по умолчанию — как до персон.
    "tutor": "",
    # Гондон: строжайший из допустимых экспертов + голос персонажа в разборе.
    "critic": (
        "\n\nSTRICTNESS AND VOICE FOR THIS REVIEW:\n"
        "- The rules and CALIBRATION examples above stay binding — never fail an "
        "answer the calibration accepts, never pass one it rejects.\n"
        "- But where a judgement is genuinely borderline and the rules allow either "
        "reading, resolve it AGAINST the student, like the strictest real examiner "
        "on the panel.\n"
        "- Report EVERY error you can find in `errors` (up to the limit), including "
        "ones that did not cost points.\n"
        "- All Russian text the student sees (summary, reason, comment, explanation): "
        "the voice of a rude, sarcastic drill instructor. Russian swearing is allowed. "
        "Mock the ANSWER, never the person: no remarks about intelligence, looks, "
        "family, nationality or accent, no 'brosay eto delo'. Every comment must "
        "still teach: name what was wrong and what is correct.\n"
    ),
    # Терпеливый: сомнение — в пользу ученика, разбор объясняет, а не перечисляет.
    "mentor": (
        "\n\nSTRICTNESS AND VOICE FOR THIS REVIEW:\n"
        "- The rules and CALIBRATION examples above stay binding — never pass an "
        "answer the calibration rejects.\n"
        "- Where a judgement is genuinely borderline and the rules allow either "
        "reading, resolve it IN FAVOUR of the student.\n"
        "- In `errors`, pick only the few MOST instructive mistakes, and make each "
        "explanation genuinely teach: what was said, what is correct, WHY, plus one "
        "tiny example.\n"
        "- All Russian text the student sees: warm and unhurried; normalise mistakes "
        "('эту ошибку делают почти все'), never scold.\n"
    ),
}


def strictness_block(persona: str | None) -> str:
    """Блок строгости по id персоны; неизвестный id — нейтральная проверка."""
    return STRICTNESS.get((persona or "").strip(), "")


def recheck_prompt(kind: str, items: list[dict], task_text: str,
                   transcript: str, persona: str | None) -> str:
    """Второй проход по СПОРНЫМ пунктам — аналог третьей проверки из методички.

    Пересматриваются только пункты, которые первый проход сам пометил
    borderline (или завалил без внятной причины): полный повторный разбор
    удвоил бы задержку на каждой работе, а спорных пунктов обычно 0-2.
    Модель здесь видит один вопрос за раз и судит внимательнее, чем в общем
    проходе, — это и есть смысл второго взгляда."""
    unit = "question the student had to ask" if kind == "dialogue" else "question and the student's answer"
    # Правила ОБЯЗАНЫ ехать в промпт целиком. Первая версия писала «суди по тем
    # же правилам», не вкладывая их, — и «старший эксперт» судил вслепую,
    # ссылаясь на выдуманное «правило 3.2» и заваливая чистые ответы.
    rules = _DIALOGUE_RULES if kind == "dialogue" else _INTERVIEW_RULES
    listed = "\n".join(
        f'- n={it["n"]}: {it["point"]}\n  first verdict: '
        f'{"accepted" if it["accepted"] else "rejected"} ({it["reason"] or "no reason given"})'
        for it in items
    )
    return (
        "You are the SENIOR examiner called in for a second opinion on the Russian "
        f"EGE oral exam. A first examiner has already marked the work; only the "
        f"disputed items below are re-examined — each is a {unit}.\n\n"
        f"Task:\n{task_text}\n\n"
        f"Full transcript of the student's recording:\n{transcript}\n\n"
        f"THE OFFICIAL RULES:\n{rules}\n\n"
        f"Disputed items:\n{listed}\n\n"
        "Re-judge ONLY these items, carefully and by the rules above. You are the "
        "final word: do not split the difference, decide.\n"
        + strictness_block(persona) +
        "\nReturn ONLY this JSON:\n"
        '{"items": [{"n": <номер>, "accepted": true, "reason": "<по-русски, до 12 '
        "слов: какое правило и какие слова ученика — только из транскрипта, ничего "
        "не выдумывая>\"}]}"
    )


def loads_forgiving(raw: str) -> dict | None:
    """JSON от модели, даже если ответ обрезали на лимите токенов.

    Разбор монолога — самый длинный ответ в системе: четыре аспекта плюс полный
    список ошибок, по числу которых считается балл. Когда он не влезает, модель
    обрывается на середине строки, и ученик вместо разбора получал 502.
    Дозакрываем скобки и спасаем приехавшее: список ошибок окажется короче
    (балл за язык — мягче), но разбор ученик увидит.
    """
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    stack: list[str] = []
    in_string = escaped = False
    for ch in raw:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()

    head = raw + ('"' if in_string else "")
    for attempt in (head, head.rsplit(",", 1)[0]):
        try:
            parsed = json.loads(attempt + "".join(reversed(stack)))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            print("[разбор] ответ модели был обрезан — спасли по частям")
            return parsed
    return None


# Общая для всех заданий оговорка: на входе транскрипт, а не звук.
_NO_PHONETICS = (
    "You receive an AUTOMATIC TRANSCRIPT of speech, not the audio. You therefore "
    "CANNOT hear pronunciation, word stress or intonation: never invent phonetic "
    "errors and never mention them. Judge only what the text actually shows. "
    "The official rule for doubtful cases applies: decide in the student's favour."
)

_RU = (
    "Every field meant for the student (summary, comment, reason, explanation) is "
    "written in RUSSIAN, briefly and plainly, addressing the student as «ты». "
    "quote and correction stay in English. Be honest but never harsh: name the "
    "mistake and show the correct version."
)


# --------------------------------------------------------------------------
# Задание 1 — чтение текста вслух (максимум 1)
# --------------------------------------------------------------------------

def reading_prompt(reference: str, diff: dict) -> str:
    evidence = (
        f"- reference has {diff.get('ref_words')} words, transcript {diff.get('heard_words')};\n"
        f"- word coverage: {diff.get('coverage')};\n"
        f"- fragments of the reference missing from the transcript: "
        f"{diff.get('missing_fragments') or 'none'};\n"
        f"- longest missing run: {diff.get('longest_missing_run')} words;\n"
        f"- words missing at the very end: {diff.get('tail_missing')};\n"
        f"- substitutions (expected -> heard): {diff.get('swaps') or 'none'}."
    )
    return (
        "You are an examiner for the Russian EGE oral exam in English, Task 1 "
        "(reading a short text aloud, maximum 1 point).\n\n"
        f"{_NO_PHONETICS}\n\n"
        "The official criterion for this task is purely phonetic, so from a transcript "
        "you may judge ONE thing only: did the student actually read every word of the "
        "text. A word that was skipped, replaced or misread counts as a serious error; "
        "three of them, a skipped line, or an unread ending mean zero.\n\n"
        "A diff between the reference and the transcript has already been computed:\n"
        f"{evidence}\n\n"
        "Your job is to filter this evidence. Speech recognition makes its own "
        "mistakes, and they must NOT be charged to the student. Mark real=false for "
        "anything that looks like a recognition artefact rather than a misreading: "
        "homophones and near-homophones, numbers written as digits but read as words "
        "(5000 -> five thousand), contractions, lost -s or -ed on a correctly read "
        "word, punctuation, British/American spelling. Mark real=true only when the "
        "student clearly said something else or skipped text.\n\n"
        f"{_RU}\n\n"
        "Return ONLY this JSON:\n"
        '{"misread": [{"expected": "<from the reference>", "heard": "<from the '
        'transcript, or \\"пропущено\\">", "real": true, "explanation": "<по-русски>"}], '
        '"summary": "<одно предложение по-русски: как прочитан текст>"}\n'
        "List at most 6 items, the clearest ones first.\n\n"
        f"REFERENCE TEXT:\n{reference}"
    )


# --------------------------------------------------------------------------
# Задание 2 — условный диалог-расспрос (максимум 4)
# --------------------------------------------------------------------------

_DIALOGUE_RULES = (
    "ACCEPT a question (accepted=true) when it asks about its point, has the correct "
    "grammatical form of a DIRECT question (word order and tense) and any slips do not "
    "break communication. Details that must NOT reduce the mark: a synonym or full "
    "paraphrase of the prompt word instead of the word itself; all four questions being "
    "of the same type; an opening line like «I'm calling about your ad»; missing or "
    "extra articles and prepositions that do not change the meaning; some/any.\n\n"
    "REJECT (accepted=false) when:\n"
    "- the point was not asked about at all;\n"
    "- the word order is that of a statement, or the tense is wrong;\n"
    "- it is a request, not a question: «Could you tell me about the price?», "
    "«What about the price?», «Tell me about...»;\n"
    "- «Could you tell me...» is followed by interrogative word order: «Could you tell "
    "me where is the hotel situated?» is rejected, «Could you tell me where the hotel "
    "is situated?» is accepted;\n"
    "- the question is meaningless: «How much is the price?», «Where is the location?», "
    "«How long are the opening hours?», «Is the admission fee free?»;\n"
    "- «which» is used where «what» is required (Which types of cars do you use?);\n"
    "- «they» is used instead of «you» about the organisation being called;\n"
    "- the first question says «it» instead of naming the place, so it is unclear what "
    "is being asked about (Where is it located? — when nothing has been named yet);\n"
    "- an article error changes the meaning: «Where is a new bookstore located?» about "
    "one specific advertised shop.\n\n"
    "If the student asked about the same point several times in different wordings, "
    "judge ONLY the last version, right or wrong. The repeated-error rule does not "
    "work across questions: the same mistake made in all four questions zeroes all four."
)


def dialogue_prompt(ad: str, points: list[str]) -> str:
    pts = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(points))
    return (
        "You are an examiner for the Russian EGE oral exam in English, Task 2 "
        "(conditional dialogue: the student must ask FOUR direct questions about an "
        "advertisement). Each question is worth 1 or 0 point, maximum 4.\n\n"
        f"{_NO_PHONETICS}\n\n"
        f"Advertisement: {ad}\n"
        f"The student had to ask about:\n{pts}\n\n"
        f"{_DIALOGUE_RULES}\n\n"
        f"{_RU}\n\n"
        "Return ONLY this JSON:\n"
        '{"questions": [{"n": 1, "heard": "<the question as the student asked it, or '
        '\\"не задан\\">", "accepted": true, "borderline": false, "reason": '
        '"<по-русски>", "model": "<пример правильного вопроса, English — заполняй '
        'только если не принят>"}], "errors": [{"cat": "gram|lex|order|missing", '
        '"quote": "<English>", "correction": "<English>", "explanation": '
        '"<по-русски>"}], "summary": "<одно предложение по-русски>"}\n'
        "questions must contain exactly one object per point, in order, even when a "
        "question was not asked. errors: up to 6 most important, for the student's "
        "long-term mistake profile.\n"
        "reason: at most 12 Russian words, and for a rejection it MUST name the "
        "specific rule broken and quote the offending words («не вопрос, а "
        "утверждение: ...», «ошибка: do you can»). Never a bare «не принят».\n"
        "borderline: set true ONLY when the judgement could honestly go either way "
        "under the rules — it will trigger a second expert look. Clear cases: false."
    )


# --------------------------------------------------------------------------
# Задание 3 — условный диалог-интервью (максимум 5)
# --------------------------------------------------------------------------

_INTERVIEW_RULES = (
    "A full and precise answer means 2-3 communicatively meaningful phrases (two at the "
    "very least) that actually answer what was asked.\n\n"
    "Counting phrases: a complex or compound sentence with two content parts counts as "
    "two. These do NOT count as phrases: «I think», «I believe», «That's an interesting "
    "question», «Thank you for your question». A short answer immediately expanded («In "
    "Moscow. I live in Moscow.») is ONE phrase. Repeating the same phrase again does not "
    "add a second one.\n\n"
    "REJECT the answer (accepted=false) when:\n"
    "- there is no answer, or its content does not match the request for information;\n"
    "- it contains fewer than 2 phrases, or is an elliptical reply (Not many, Sure) with "
    "no development;\n"
    "- the question had two parts (where AND when) and only one is answered;\n"
    "- the tense of the question is ignored: a question about the past or the future "
    "answered in the present; «I like» in reply to «Would you like»;\n"
    "- there is a factual error (something that contradicts reality);\n"
    "- there is at least one elementary lexico-grammatical error, i.e. one in the "
    "9th-grade list: articles that change meaning, word order in statements and "
    "questions, Present/Past Simple and Continuous, Present Perfect, passive voice "
    "(Present/Past Simple), modals, countable/uncountable nouns and plurals, "
    "subject-verb agreement, degrees of comparison, pronouns, prepositions of place, "
    "time and direction, there is/it is, verb+ing and verb+to infinitive, "
    "I prefer / I'd prefer. A missing verb or link verb, or an answer that is a string "
    "of words, is always a rejection.\n\n"
    "Do not reject for: naming one item when the question used a plural; giving reasons "
    "for only one of two named preferences; an unfinished THIRD phrase when the first "
    "two are already a full and correct answer. Repeated errors inside ONE answer count "
    "once, but each answer is judged on its own.\n\n"
    "A phrase must be a real sentence with a subject and a verb. «Quite warm», «It's "
    "green», «In the village», «Somewhere far from big cities», «Maybe on the Maldives» "
    "are not phrases — they are fragments, and an answer built out of them is rejected "
    "however sensible it sounds.\n\n"
    "CALIBRATION — how real examiners marked real answers:\n"
    "- «In Troitsk. It's a part of Moscow. Quite warm.» — REJECTED: one real sentence "
    "and two fragments.\n"
    "- «It's green. There is rivers.» — REJECTED: a grave grammatical error in the "
    "second sentence.\n"
    "- «I live with my parents. I've got an elder sister called Masha.» — ACCEPTED: two "
    "full, correct, relevant sentences.\n"
    "- «I used to go abroad. I swim in the sea. I had a great time.» — REJECTED: the "
    "question was about the past, and «I swim» is present. One error anywhere in the "
    "answer sinks the whole answer — the mark is holistic.\n"
    "- «Somewhere far from big cities. Maybe on the Maldives.» — REJECTED: no complete "
    "sentence at all.\n"
    "- «Kaluga is an industrial city. It is famous for the State Space Museum named "
    "after Konstantin Tsiolkovsky.» — ACCEPTED.\n"
    "- «I'm from Kaluga. It located in the central region not far from Moscow. It was "
    "hot this summer.» — REJECTED: «It located» is a grammatical error, and the question "
    "asked about summers in general, not this particular summer.\n"
    "Being strict here is correct: in this task most answers of an average student are "
    "rejected, and pretending otherwise would mislead the student about the real exam."
)


def interview_prompt(questions: list[str]) -> str:
    qs = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
    return (
        "You are an examiner for the Russian EGE oral exam in English, Task 3 "
        "(interview: the student answers the interviewer's questions one after "
        "another). Each answer is worth 1 or 0 point.\n\n"
        f"{_NO_PHONETICS}\n\n"
        "The transcript is ONE continuous recording of all the answers in order; split "
        "it into answers yourself by meaning.\n\n"
        f"The questions were:\n{qs}\n\n"
        f"{_INTERVIEW_RULES}\n\n"
        f"{_RU}\n\n"
        "Return ONLY this JSON:\n"
        '{"answers": [{"n": 1, "phrases": <how many countable phrases>, "accepted": '
        'true, "borderline": false, "reason": "<по-русски>"}], "errors": [{"cat": '
        '"gram|lex|order|missing|logic", "quote": "<English>", "correction": '
        '"<English>", "explanation": "<по-русски>"}], "summary": "<одно предложение '
        'по-русски>"}\n'
        "answers must contain exactly one object per question, in order.\n"
        "reason: at most 12 Russian words; for a rejection it MUST name the rule "
        "broken and quote the offending words («одна фраза и фрагмент: Quite warm», "
        "«ошибка: it save»). Never a bare «не зачтён».\n"
        "borderline: set true ONLY when the judgement could honestly go either way "
        "under the rules — it will trigger a second expert look. Clear cases: false."
    )


# --------------------------------------------------------------------------
# Задание 4 — монолог: обоснование выбора иллюстраций (максимум 10)
# --------------------------------------------------------------------------

_MONOLOGUE_RULES = (
    "CONTENT — four aspects, each judged full / partial / missing.\n\n"
    "Aspect 1 — explaining the choice of the illustrations. A FULL answer briefly "
    "describes BOTH photos (who, what they are doing — Present Continuous — where, plus "
    "details that matter for the project topic) AND states the difference between them, "
    "and that difference must be a generalisation about the TWO TYPES the project "
    "contrasts (active vs quiet hobby, healthy vs unhealthy food, team vs individual "
    "sport), explicitly tied to the project topic. PARTIAL if the description is thin or "
    "generic, if the difference is only a trivial detail of the pictures (how many "
    "people, what colour the shirt is, indoors vs outdoors with no generalisation), if "
    "the link to the topic is not spelled out, or if there is a factual error about the "
    "photo. MISSING if there is no description or no difference at all, or the language "
    "makes it impossible to understand. One difference is enough — the mark is not "
    "reduced for giving only one. «In one photo — in the other photo» and «in the first "
    "photo» are fine; «photo number one» is not; «I've sent you the photos» or «look at "
    "the photo» contradicts the situation (a voice message about photos the friend "
    "cannot see) and makes the aspect inexact.\n\n"
    "Aspect 2 — advantages (1-2) of the two types. Aspect 3 — disadvantages (1-2). FULL "
    "when the advantage/disadvantage is specific to that type. PARTIAL when it is "
    "universal filler that fits anything («it's fun», «you enjoy it», «it's boring», "
    "«you get vivid emotions»), repeats the description, or is doubtful. MISSING when "
    "one of the two types is not covered at all, or the phrasing is incomprehensible. "
    "Dealing with aspects 2 and 3 together in one block is NOT an error.\n\n"
    "Aspect 4 — the author's opinion. Three things are required: the opinion is marked "
    "as the author's own («As for me», «In my opinion», «Personally, I»), the choice "
    "itself, and a justification. FULL when all three are there AND the verb form "
    "matches the one required by the plan (if the plan says «you'd prefer», then "
    "«I prefer» is the wrong form). PARTIAL when the justification is missing, or the "
    "opinion is not explicitly the author's, or the verb form is wrong. MISSING when two "
    "of the three are absent. «I like it» is not a justification.\n\n"
    "VOLUME. Count phrases as simple sentences, including those inside compound and "
    "complex ones. Do not count fillers and false starts.\n\n"
    "ORGANISATION. opening_with_address is true only if the message starts by addressing "
    "the friend (a greeting and/or the friend's name). «I'd like to compare», «I'm going "
    "to talk about», «There are two pictures», «Hi! My name is...» are NOT valid "
    "openings. closing is true if there is a final phrase that suits a voice message to "
    "a friend («That's all I wanted to tell you. Bye»). A monologue that breaks off "
    "mid-phrase has no closing. «Thank you for listening» alone is not accepted, but "
    "does no harm next to a proper closing.\n\n"
    "logic_errors — count each of these once: a missing linking transition between parts "
    "of the answer, a wrong linker (From the one hand), a statement that contradicts "
    "what was said before, an unfinished sentence, saying the PHOTOS differ when it is "
    "the activities that differ.\n\n"
    "lang_errors — lexical and grammatical only, never phonetic. grave=true for "
    "elementary-level errors (missing third-person -s, missing verb or link verb, an "
    "article error that changes the meaning, a string of words instead of a sentence) "
    "and for anything that breaks communication. The same error repeated is listed once.\n\n"
    "LANGUAGE AND CONTENT ARE SEPARATE. Grammar and vocabulary are already punished by "
    "the third criterion, so do NOT lower an aspect just because the sentence is clumsy "
    "or has mistakes. An aspect drops only when the MEANING does not get through: if the "
    "phrase that was supposed to name the difference, an advantage or a disadvantage "
    "cannot be understood at all, that aspect is missing.\n\n"
    "CALIBRATION — how real examiners marked real answers:\n"
    "- FULL aspect 1, despite several grammar errors: «The first photo show us a woman "
    "who is sitting on the ground, and perhaps she is planting some tree. The second "
    "photo depicts a man who is on the kitchen, he is probably cooking and filming this "
    "process. These photos will perfectly suit our project because they show two "
    "different hobbies: the first shows us active outdoor hobby, while the second is "
    "more calm, a hobby that can be done indoor.» — description of both photos plus a "
    "generalised difference tied to the topic. The errors here cost marks under the "
    "third criterion only.\n"
    "- PARTIAL aspect 1: «In the first picture the boy is playing football at the "
    "stadium, whereas in the second picture the girl is knitting in her room.» — a "
    "description with no difference drawn between the TYPES of hobby.\n"
    "- MISSING aspect 1: «this types have some differences between photos» — what the "
    "difference is never becomes clear.\n"
    "- PARTIAL aspects 2-3: «it is the best way to rest», «you can get vivid emotions "
    "and unforgettable experience», «it can be boring» — universal filler that fits any "
    "activity and does not name an advantage of THIS type.\n"
    "- FULL aspect 2, again despite errors: «gardening outdoors can build specific skills "
    "like planting trees or it help to plant vegetables for yourself which is very "
    "healthy. As for cooking at home, it also can develop cooking skills, upgrade them "
    "or it helps to make new tasty dishes.» — each of the two types gets its own "
    "concrete advantage. That is a full aspect, not a partial one.\n"
    "- FULL aspect 4: «As for me, I would prefer to do cooking in front of a camera, "
    "I think it is very funny and develops a lot of useful skills» — the opinion is "
    "explicitly the author's, the plan's verb form is used, the reason is given.\n"
    "- MISSING aspect 4: «Personally, I'd prefer to play video games, because I like it» "
    "when the plan asked which the author PREFERS — wrong verb form, and «I like it» is "
    "not a justification: two of the three required parts are absent."
)


def monologue_prompt(brief: str, photo_facts: list[str] | None = None) -> str:
    facts = ""
    if photo_facts:
        shots = "\n".join(f"- photo {i + 1}: {f}" for i, f in enumerate(photo_facts))
        facts = (
            "\nYou cannot see the photos, so here is what is actually on them. Use this "
            "to catch factual errors (the student describes something that is not there) "
            "and to check that the difference is drawn correctly:\n" + shots + "\n"
            "Judge the description by what these photos actually allow. If a photo shows "
            "an object, a landscape or only a pair of hands and has no people in it, do "
            "NOT require the student to say who is doing what — a description of what is "
            "shown, tied to the project topic, is a full answer for such a photo.\n"
        )
    return (
        "You are an examiner for the Russian EGE oral exam in English, Task 4: a voice "
        "message to a friend justifying the choice of two photos for a school project "
        "and giving the author's opinion on the topic.\n\n"
        f"{_NO_PHONETICS}\n\n"
        f"The student's task was:\n{brief}\n{facts}\n"
        f"{_MONOLOGUE_RULES}\n\n"
        f"{_RU}\n\n"
        "Do NOT give any marks, scores or verdicts — they are calculated from your "
        "answers. Your job is to answer plain yes/no questions about each aspect, and "
        "before answering them, to COPY OUT the student's own words that cover that "
        "aspect (evidence). Judging from memory of the whole answer is how aspects get "
        "mixed up; if you find no words for an aspect, evidence is an empty string and "
        "every flag for it is false.\n"
        "Return ONLY this JSON:\n"
        "{\"aspects\": [\n"
        '  {"n": 1, "evidence": "<the student\'s words, English>", '
        '"described_first": true, "described_second": true, "difference_stated": true, '
        '"difference_generalised": true, "linked_to_topic": true, '
        '"factual_error": false, "unintelligible": false, '
        '"comment": "<по-русски, коротко>"},\n'
        '  {"n": 2, "evidence": "...", "named_first": true, "named_second": true, '
        '"specific_first": true, "specific_second": true, "unintelligible": false, '
        '"comment": "<по-русски, коротко>"},\n'
        '  {"n": 3, "evidence": "...", "named_first": true, "named_second": true, '
        '"specific_first": true, "specific_second": true, "unintelligible": false, '
        '"comment": "<по-русски, коротко>"},\n'
        '  {"n": 4, "evidence": "...", "opinion_explicit": true, "choice_stated": true, '
        '"justified": true, "plan_verb_form": "<the verb form the last bullet of the '
        'plan uses, e.g. you would prefer>", "student_verb_form": "<the verb form the '
        'student used, e.g. I prefer>", "unintelligible": false, '
        '"comment": "<по-русски, коротко>"}\n'
        "], \"phrases\": <int>, "
        '"opening_with_address": true, "closing": true, '
        '"logic_errors": [{"quote": "<English>", "explanation": "<по-русски>"}], '
        '"lang_errors": [{"cat": "gram|lex", "quote": "<English>", "correction": '
        '"<English>", "explanation": "<по-русски>", "grave": false}], '
        '"summary": "<одно предложение по-русски: главное о работе>"}\n\n'
        "What the flags mean:\n"
        "- described_first / described_second — the photo is actually described, not "
        "just mentioned;\n"
        "- difference_stated — the answer says what the difference is;\n"
        "- difference_generalised — that difference is about the two TYPES the project "
        "contrasts. FALSE when the difference is only about the place or the picture "
        "(«at home» vs «in the open air», «one person» vs «three people») and never "
        "says what KINDS of hobby, food, sport or pastime are being contrasted;\n"
        "- linked_to_topic — the project topic is actually brought into the description. "
        "FALSE if the topic is only named in the opening line and then dropped;\n"
        "- factual_error — the student says something the photos do not show;\n"
        "- named_first / named_second — an advantage (aspect 2) or a disadvantage "
        "(aspect 3) is named for THAT type. If the student covers only one of the two "
        "types, the flag for the other one is FALSE — do not be generous here;\n"
        "- specific_first / specific_second — it belongs to that type in particular. "
        "FALSE for anything that would fit almost any activity: «it's fun», «it's very "
        "interesting», «it can be boring», «it is the best way to rest», «you get vivid "
        "emotions and unforgettable experience», «people can be tired of this», «you're "
        "enjoying the game». This filler is the commonest reason examiners mark aspects "
        "2 and 3 down, so judge it strictly;\n"
        "- opinion_explicit — the opinion is marked as the author's own;\n"
        "- justified — a reason is given. FALSE for «I like it», «it's fun», «it's "
        "really my cup of tea»: they repeat the choice instead of explaining it;\n"
        "- plan_verb_form / student_verb_form — quote both literally: the form the last "
        "bullet of the plan uses and the form the student actually used. Do not judge "
        "whether they match, just copy them out;\n"
        "- unintelligible — the wording makes the aspect impossible to understand.\n\n"
        "Language mistakes alone must NOT turn a flag false: they are counted "
        "separately in lang_errors. List every language error you find, up to 10 — their "
        "number decides that mark, so do not stop at the first few. Keep evidence, "
        "comments and explanations SHORT (about ten words): the answer must fit in one "
        "JSON object without being cut off."
    )
