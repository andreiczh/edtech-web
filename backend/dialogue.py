"""Ход свободной беседы: куда вести разговор, о чём бы ни зашла речь.

История вопроса (04.08.2026, за один день дважды). Сначала разговор был
бесцельным: модель отвечала на последнюю реплику и не вела никуда — отсюда
генерические вопросы и ощущение поверхностного собеседника. Лечили это банком
из 48 тем со скрытым планом: сервер выбирал тему, у темы были четыре ступени.

Владелец посмотрел и решил иначе: **тему выбирает человек**, а система должна
подстраиваться под него, под разговор и под то, о чём он сам захотел говорить.
Банк тем убран (лежит в истории git, коммит 66427d3).

Что из той конструкции ОСТАЛОСЬ и почему именно это:

  Работала не тема, а ЛЕСТНИЦА — движение от фактов к личному, от личного к
  мнению, от мнения к воображению. Это ход любого живого разговора, и он не
  зависит от того, о чём говорят: про кино, про мать или про космос — сначала
  «что было», потом «а ты как», потом «а стоит ли», потом «а что если».

  Ступень по-прежнему считает СЕРВЕР, арифметикой из длины разговора. Спросить
  у модели «на какой мы глубине» стоило бы второго запроса на каждую реплику —
  то есть удвоения расхода ради того, что и так известно.

Чего здесь принципиально НЕТ: никакого списка тем, никаких заготовленных
вопросов и никакой попытки угадать, о чём человек захочет говорить. Тема —
это то, что он сказал.
"""

from __future__ import annotations

# Сколько обменов держимся на одной ступени. Один обмен — слишком быстро:
# разговор превращается в анкету со скоростью пулемёта. Три — слишком долго:
# ученик успевает заскучать на «что, где, когда».
TURNS_PER_RUNG = 2

# Лестница. Формулировки — ДЕЙСТВИЯ («выясни», «спроси»), а не пожелания:
# расплывчатую инструкцию модель выполняет расплывчато.
#
# Последняя ступень намеренно открытая: к шестому обмену разговор уже сам знает,
# куда идёт, и подсказывать ему направление — значит мешать.
RUNGS = (
    "Stay concrete. Find out the facts of what they just brought up: what "
    "exactly happened, where, when, who else was there. Do not philosophise yet "
    "and do not jump to big questions.",

    "Make it personal. Ask how they felt about it, why they chose it, what it "
    "means to them, what they would do differently. The subject is theirs — you "
    "are digging into THEIR side of it.",

    "Widen it. Ask what they think about the wider subject their story touches — "
    "an opinion, a judgement, a disagreement. Give your own view first if that "
    "makes it easier for them to argue with you.",

    "Go wherever this conversation has genuinely gone: imagine, suppose, "
    "disagree, follow the thing they lit up about. Never restart from small "
    "talk, and never go back to questions this conversation has answered.",
)


def rung_index(exchanges: int) -> int:
    """Номер ступени по числу состоявшихся обменов. Дальше последней не идём."""
    return min(len(RUNGS) - 1, max(0, exchanges) // TURNS_PER_RUNG)


def flow_block(exchanges: int) -> str:
    """Подсказка о ходе беседы для системного промпта.

    `exchanges` — сколько пар «ученик - ответ» уже было. Ноль означает первую
    реплику: человек только что открыл рот, и подстраиваться пока не под что.
    """
    idx = rung_index(exchanges)
    lines = [
        "",
        "WHOSE CONVERSATION THIS IS — read before anything else:",
        "- The student chooses the subject. Whatever they bring up IS the topic, "
        "even if it is odd, tiny or not on any syllabus. You never announce a "
        "topic, never steer them back to a 'better' one, and never hand them a "
        "list of topics unless they ask for one.",
        "- If they change the subject, go with them and do not remark on it.",
        "- If they say they do not know what to talk about, do NOT ask them what "
        "they would like to talk about. Offer two or three CONCRETE things built "
        "from what they have already told you in this conversation, and if they "
        "still hesitate, simply start on one yourself.",
        "- If they open with nothing but a greeting, do not interview them about "
        "their plans. Say something real of your own — a small observation, "
        "something you noticed, something you think — and let the subject grow "
        "out of what they answer.",
        "",
        "READ THE PERSON, not just the sentence:",
        "- Match their level. Short simple sentences from them means simple words "
        "from you. Complex structures from them means you can stretch them.",
        "- Match their energy. If they are giving you one line at a time, keep it "
        "light and short; if they are telling a story, let them tell it and ask "
        "for the next part.",
        "- Remember what they got animated about earlier in this conversation and "
        "come back to it later. That is what makes a partner feel like a person "
        "rather than a question generator.",
        "",
        f"DEPTH RIGHT NOW — this is exchange {exchanges + 1} of this conversation. "
        f"{RUNGS[idx]}",
        "This is a direction, not a script: if the conversation has already gone "
        "deeper than this on its own, stay deeper.",
    ]
    return "\n".join(lines)
