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
        '\\"не задан\\">", "accepted": true, "reason": "<по-русски: почему принят или '
        'не принят>", "model": "<пример правильного вопроса, English — заполняй только '
        'если не принят>"}], "errors": [{"cat": "gram|lex|order|missing", "quote": '
        '"<English>", "correction": "<English>", "explanation": "<по-русски>"}], '
        '"summary": "<одно предложение по-русски>"}\n'
        "questions must contain exactly one object per point, in order, even when a "
        "question was not asked. errors: up to 6 most important, for the student's "
        "long-term mistake profile."
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
    "once, but each answer is judged on its own."
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
        'true, "reason": "<по-русски: почему зачтён или нет>"}], "errors": [{"cat": '
        '"gram|lex|order|missing|logic", "quote": "<English>", "correction": '
        '"<English>", "explanation": "<по-русски>"}], "summary": "<одно предложение '
        'по-русски>"}\n'
        "answers must contain exactly one object per question, in order."
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
    "and for anything that breaks communication. The same error repeated is listed once."
)


def monologue_prompt(brief: str, photo_facts: list[str] | None = None) -> str:
    facts = ""
    if photo_facts:
        shots = "\n".join(f"- photo {i + 1}: {f}" for i, f in enumerate(photo_facts))
        facts = (
            "\nYou cannot see the photos, so here is what is actually on them. Use this "
            "ONLY to catch factual errors (the student describes something that is not "
            "there) and to check that the difference is drawn correctly:\n" + shots + "\n"
        )
    return (
        "You are an examiner for the Russian EGE oral exam in English, Task 4: a voice "
        "message to a friend justifying the choice of two photos for a school project "
        "and giving the author's opinion on the topic.\n\n"
        f"{_NO_PHONETICS}\n\n"
        f"The student's task was:\n{brief}\n{facts}\n"
        f"{_MONOLOGUE_RULES}\n\n"
        f"{_RU}\n\n"
        "Do NOT give any marks or scores — they are calculated from your observations. "
        "Return ONLY this JSON:\n"
        '{"aspects": [{"n": 1, "verdict": "full|partial|missing", "comment": '
        '"<по-русски: чего не хватило или что сделано хорошо>"}], "phrases": <int>, '
        '"opening_with_address": true, "closing": true, '
        '"logic_errors": [{"quote": "<English>", "explanation": "<по-русски>"}], '
        '"lang_errors": [{"cat": "gram|lex", "quote": "<English>", "correction": '
        '"<English>", "explanation": "<по-русски>", "grave": false}], '
        '"summary": "<одно предложение по-русски: главное о работе>"}\n'
        "aspects must contain exactly four objects, n = 1..4, in order. List every "
        "language error you find (up to 12) — their number decides the mark, so do not "
        "stop at the first few."
    )
