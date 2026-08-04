"""Сверка живого разбора с оценками экспертов ФИПИ.

test_ege_scoring.py проверяет арифметику шкалы. Здесь проверяется то, что
арифметике предшествует, — СУЖДЕНИЯ: в модель уходят настоящие промпты из
ege_prompts.py и настоящие ответы участников ЕГЭ из раздела II методички, а
получившийся балл сравнивается с тем, что поставили эксперты.

Совпадение балл в балл здесь не гарантировано и не требуется: два живых
эксперта тоже расходятся (методичка допускает расхождение и описывает третью
проверку). Смысл теста — держать расхождение в пределах ±1 балла из 10 и
ловить систематический перекос: если разбор вдруг станет добрым ко всем или
злым ко всем, это будет видно сразу.

Запуск (ключ берётся из backend/.env, в вывод не попадает):
    .\.venv\Scripts\python.exe test_ege_live.py
"""

from __future__ import annotations

import json
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

import ege_prompts
import ege_scoring
import scoring

load_dotenv()
MODEL = os.environ.get("LLM_MODEL", "mistral-small-latest")
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.mistral.ai/v1")


def brief(topic: str, thing: str, opinion: str = "you'd prefer") -> str:
    """Формулировка задания. Глагольная форма в последнем пункте важна: по
    критериям ответ «I'd prefer» на план с «you prefer» — уже неточный аспект."""
    return (
        f'Task 4. Imagine that you and your friend are doing a school project "{topic}". '
        "You have found some photos to illustrate it but for technical reasons you cannot "
        "send them now. Leave a voice message to your friend explaining your choice of the "
        "photos and sharing some ideas about the project. In 2.5 minutes be ready to:\n"
        "• explain the choice of the illustrations for the project by briefly describing "
        "them and noting the differences;\n"
        f"• mention the advantages (1-2) of {thing};\n"
        f"• mention the disadvantages (1-2) of {thing};\n"
        "• express your opinion on the subject of the project - which option presented in "
        f"the pictures {opinion} and why.\n\n"
        "You will speak for not more than 3 minutes (12-15 sentences)."
    )


# --------------------------------------------------------------------------
# Задание 4: работы участников ЕГЭ с официальными баллами (раздел II методички)
# --------------------------------------------------------------------------
MONOLOGUES = [
    {
        "name": "The games people like",
        "expected": (0, 0, 0),
        # План этого варианта требовал настоящего времени («which you prefer»),
        # а участник ответил «I'd prefer» — по критериям это неверная форма.
        "brief": brief("The games people like", "the two types of games", "you prefer"),
        "facts": [
            "a girl sitting alone at a screen playing a video game",
            "a mother and her daughter sitting at a table playing chess together",
        ],
        "script": (
            "Hi Max, as for our school project 'The games people like', you know, I have found "
            "some photos. Let me tell you about them. In the first picture, I can see a girl is "
            "playing alone, whereas in the second picture, I can see a family playing together. "
            "I have chosen these photos because they are appropriate for our school project. "
            "Also, this types have some differences between photos. In the first picture, a girl "
            "is playing video games, whereas in the second picture, a family is playing table "
            "games. Also, both types have some advantages. Talking about the first one, it is the "
            "best way to rest, whereas in the second picture, it is the best way of spending your "
            "free time with family. Also, both types have some disadvantages. Talking about the "
            "first one, you need a good computer to play in what you want. As for another type... "
            "it can be boring to play with your family. Personally, I'd prefer to play in video "
            "games, because I like it and I want to be in top of these games. That's all for now. "
            "Please give me some feedback. Bye."
        ),
    },
    {
        "name": "Ideal weekend",
        "expected": (2, 2, 2),
        "brief": brief("Ideal weekend", "the two ways of spending a weekend"),
        "facts": [
            "a woman wearing headphones relaxing on a sofa in her living room, a cat beside her",
            "three women riding bicycles along a road with trees around",
        ],
        "script": (
            "Hello mate, I've found some photos for our school project 'Ideal weekend', but "
            "unfortunately, I can't send them now, that's why I'll explain them to you and express "
            "my ideas about the project. Right, in one photo, you can see a woman wearing "
            "headphones, apparently, she's listening to music. She's relaxing in her living room "
            "with her cat at her side. In the other one, you can see three woman riding bicycles. "
            "Apparently, it looks like a forest, but no, there are roads, so I don't know. These "
            "pictures are very different. Well, one picture features a relaxing way of spending "
            "your weekend, the other one suggests a more active approach. There are advantages to "
            "spending your weekend both ways, like spending it in the living room is very "
            "appealing for many people who prefer to have a refreshing experience in the comfort "
            "of their homes. And the other one is more of an active approach for people who love "
            "sports. But there are also disadvantages, like spending your weekend in your living "
            "room won't have any health benefits. But the other way also has very unique way of "
            "coming down to preference. I think I love our project, and I prefer the way of "
            "spending my weekends in my living room because I enjoy the calming presence of myself "
            "in this world. Alright, I've got to go, goodbye."
        ),
    },
    {
        "name": "The best moments with grandparents",
        "expected": (1, 2, 1),
        "brief": brief("The best moments with grandparents",
                       "the two ways of spending time with grandparents"),
        "facts": [
            "a grandson and his grandfather playing chess at home, a woman watching them",
            "grandparents with their grandchildren outdoors in the mountains",
        ],
        "script": (
            "Hi, Timur, it's Kamila. How's everything been going? By the way, I've got some "
            "pictures that could be helpful for our project 'The best moments with grandparents'. "
            "Let's discuss them together. It seems to me that the first photo is suitable for our "
            "project as it shows a family playing chess at home. The second photo could be quite "
            "beneficial for our project as well as it shows a family taking photo in the forest. "
            "Clearly, these two photos show two different types of spending time with "
            "grandparents. In the first photo family is at home, whereas in the second photo "
            "family is in the open air. Well, both of this types of spending time with "
            "grandparents have their upsides. Clearly, a benefit of spending time with "
            "grandparents at home is that you are always together and you can enjoy each other's "
            "company. A benefit of spending time with grandparents in the forest is that you can "
            "get vivid emotions and unforgettable experience there. Obviously, some disadvantages "
            "of these two types of spending time with grandparents can be seen. It seems to me "
            "that a negative aspect about spending time at home is that sometimes there can be too "
            "boring. A drawback of spending time with grandparents in the forest is that children "
            "may catch a cold there. Personally, I prefer to spend time with grandparents in the "
            "forest. I think so because I like open air, and also it's really my cup of tea. "
            "That's all I wanted to discuss with you for the moment. Get back to me on it. Thanks."
        ),
    },
    {
        "name": "Hobbies (5471)",
        "expected": (4, 3, 0),
        "brief": brief("Hobbies", "the two hobbies"),
        "facts": [
            "a woman kneeling on the ground in a garden, planting a small tree",
            "a man in a kitchen cooking and filming himself on a camera",
        ],
        "script": (
            "Hi Kate, I've found two photos for our project Hobbies and I'd like to tell you about "
            "them and share my ideas. The first photo show us a woman who is sitting on her lap on "
            "the ground, and perhaps she is planting some tree or something. The second photo "
            "depicts a man who is on the kitchen, he is probably cooking and filming this process "
            "on the camera. In my opinion, these photos will perfectly suit our project because "
            "they show two different hobbies: the first photo shows us active outdoor hobby, while "
            "the second is more calm and a hobby that can be done indoor. I believe that two types "
            "of hobbies have their merits, for example, gardening outdoors can build specific "
            "skills like planting trees or it help to plant vegetables for yourself which is very "
            "healthy. As for cooking at home, it also can develop cooking skills, upgrade them or "
            "it helps to make new tasty dishes. As for speaking for disadvantages of two hobbies, "
            "I think that gardening outdoors depends on the weather and you can get very dirty and "
            "exhaust because of tough work. Cooking indoors has a drawback too. Because of not "
            "allowing the rules of how to use knives or other items you can get injured very "
            "easily. As for me, if you ask me, I would prefer to do cooking in front of a camera, "
            "I think it is very funny and develops a lot of useful skills. Also, you can pleasure "
            "your loved ones and yourself too with tasty food. That's all for now. I hope you like "
            "the photos and my ideas."
        ),
    },
    {
        "name": "Volunteering (3775)",
        "expected": (1, 2, 0),
        "brief": brief("Volunteering", "the two kinds of volunteering"),
        "facts": [
            "two girls outdoors collecting litter into bags",
            "a smiling woman in an animal shelter holding a dog",
        ],
        "script": (
            "Hi, Alina. I've just found two photos for our school project 'Volunteering', and I "
            "would like to discuss them with you. Let me start with describing the pictures. In "
            "the first picture there is a two girls, there is a two girls outside probably they "
            "pick up the trash. In the second picture there is a woman with dog. She is smiling. "
            "I think these pictures are a perfect choice for our project because they are shows a "
            "different types of volunteering. The key difference between them that the second "
            "picture the woman treat a dog and in the first picture the girls are helping the "
            "environment. I think these both types of volunteering have their advantages and "
            "disadvantages. Speaking of picking up the trash it's help to improve the environment, "
            "but at the same time people can be tired of this. As for treating the dog, it can "
            "help to stop the extinction of animals. However, as for me I would prefer to treat a "
            "dog because I really love them, they are very funny and cute. Well, that's all for "
            "now, bye."
        ),
    },
    {
        "name": "Sports (9377)",
        "expected": (2, 2, 0),
        "brief": brief("Sports", "the two types of sport"),
        "facts": [
            "a group of teenagers playing volleyball outdoors on a summer day",
            "two ice hockey teams playing against each other on an ice rink",
        ],
        "script": (
            "Hi there, Svetlana. I've found two pictures for our project 'Sports'. Unfortunately, "
            "I can't send them to you because my electricity was cut off, so I have to describe "
            "them for you. In the first picture a group of teenagers are playing baseball. They "
            "are wearing T-shirts, pants, light pants, jeans. It looks like that it's summer and "
            "they look very happy. In the second picture we can see a two teams of hockey playing "
            "against each other, it looks like it's winter and they look very focused on. The "
            "advantage of playing, oh, of course these pictures are perfect for our project "
            "because they describing the most common ways of sports, type of sports. The advantage "
            "of summer sports is the only one that you don't have to wear a bunch of clothes and "
            "it's very fun. The advantage of playing hockey is the fact that you're also enjoying "
            "the game and it's very fast. The disadvantage of playing summer sport is the fact "
            "that sometimes it can be very warm outside, it's nearly boiling sometimes, so it can "
            "cause death. The disadvantage of playing hockey it's, it's can, the fact that the "
            "injuries are very dangerous. In my opinion, I would choose probably playing summer "
            "sports like baseball because it's very fun and enjoying and I don't like to wear a "
            "bunch of clothes myself. Thank you for listening, Svetlana, please contact me back as "
            "soon as possible. Goodbye."
        ),
    },
]

# --------------------------------------------------------------------------
# Задание 3: ответы с покомментарными вердиктами экспертов (задания 7 и 8 практикума)
# --------------------------------------------------------------------------
INTERVIEW_QUESTIONS = [
    "What part of Russia do you live in? What's the weather like in summer there?",
    "What else would you like our listeners to know about your region?",
    "What can you tell us about your family?",
    "How did you use to spend your summer holidays when you were seven?",
    "How would you like to spend your summer holidays in 10 years?",
]

INTERVIEWS = [
    {
        "name": "интервью, практикум задание 7",
        # Эксперты: 0, 0, 1, 0, 0 — принят только ответ про семью.
        "expected_marks": [0, 0, 1, 0, 0],
        "script": (
            "In Troitsk. It's a part of Moscow. Quite warm. "
            "It's green. There is rivers. "
            "I live with my parents. I've got an elder sister called Masha. "
            "I used to go abroad. I swim in the sea. I had a great time. "
            "Somewhere far from big cities. Maybe on the Maldives."
        ),
    },
    {
        "name": "интервью, практикум задание 8",
        # Эксперты: все пять ответов не приняты.
        "expected_marks": [0, 0, 0, 0, 0],
        "script": (
            "I living in Siberia. The weather hot in summer. "
            "Quite big. Many animals living here. "
            "It's small. I living with parents. "
            "In the village. It's great to swim in a river. "
            "In the Crimea. I'd enjoy nature."
        ),
    },
]


# Температура разбора. Ставится ОДНОЙ переменной, чтобы замер и бой не
# разъезжались: цифра здесь обязана совпадать с main.py и _recheck_disputed.
GRADE_TEMPERATURE = float(os.environ.get("GRADE_TEMPERATURE", "0"))


def ask(client: OpenAI, prompt: str, transcript: str, max_tokens: int) -> dict:
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": prompt},
                  {"role": "user", "content": transcript}],
        response_format={"type": "json_object"},
        temperature=GRADE_TEMPERATURE,
        max_tokens=max_tokens,
    )
    return ege_prompts.loads_forgiving(completion.choices[0].message.content or "") or {}


def recheck_aspects(client: OpenAI, case: dict, obs: dict) -> int:
    """Второй взгляд на спорные аспекты — ТОТ ЖЕ отбор и тот же промпт, что в
    бою (main._recheck_aspects). Здесь он повторён из-за разницы клиентов
    (синхронный против асинхронного), но вся логика взята из общих функций:
    разъехаться замер с продом не может."""
    numbers = ege_scoring.doubtful_aspects(obs, case["script"])
    if not numbers:
        return 0
    first = {int(c.get("n") or 0): c for c in (obs.get("aspects") or [])
             if isinstance(c, dict)}
    data = ask(client, ege_prompts.aspect_recheck_prompt(
        numbers, case["brief"], case["facts"], first), case["script"], 700)
    return ege_scoring.merge_aspect_recheck(obs, data.get("aspects"))


def run_monologues(client: OpenAI, recheck: bool) -> tuple[int, int, list[str]]:
    print(f"ЗАДАНИЕ 4 — монолог по фотографиям (максимум 10)"
          f"{' + второй взгляд на спорные аспекты' if recheck else ''}\n")
    exact = close = 0
    notes = []
    for case in MONOLOGUES:
        obs = ask(client, ege_prompts.monologue_prompt(case["brief"], case["facts"]),
                  case["script"], 2000)
        changed = recheck_aspects(client, case, obs) if recheck else 0
        aspects = ege_scoring.aspect_verdicts(obs.get("aspects") or [])
        # Балл считаем ТЕМ ЖЕ кодом, что и на проде (05.08.2026). Раньше здесь
        # была своя копия подсчёта — она звала score_monologue напрямую, минуя
        # scoring.py. Калибровка мерила путь, которого в бою нет: отсев ошибок
        # без улик, санитизация и всё, что живёт в _score_feedback, в замер не
        # попадали. Такой замер может показывать благополучие там, где прод
        # ошибается, — и наоборот.
        fb = scoring._score_feedback("monologue", obs,
                                     {"transcript": case["script"]})
        lang = ege_scoring.drop_unsupported(
            obs.get("lang_errors") or [], case["script"], need_quote=True)
        logic = ege_scoring.drop_unsupported(
            obs.get("logic_errors") or [], case["script"], need_quote=False)
        marks = tuple(c["score"] for c in fb["criteria"])
        want = case["expected"]
        delta = abs(sum(marks) - sum(want))
        exact += marks == want
        close += delta <= 1
        flag = "==" if marks == want else ("~~" if delta <= 1 else "!!")
        print(f"{flag} {case['name']}: наш {marks[0]}/{marks[1]}/{marks[2]} = "
              f"{sum(marks)}/10 | эксперты {want[0]}/{want[1]}/{want[2]} = {sum(want)}/10 "
              f"(разница {delta})")
        print(f"     аспекты {[a.get('verdict') for a in aspects]}, фраз "
              f"{obs.get('phrases')}, ошибок: язык {len(lang)}, логика {len(logic)}"
              + (f", второй взгляд изменил признаков: {changed}" if recheck else ""))
        if delta > 1:
            notes.append(f"{case['name']}: разошлись на {delta} балла")
    return exact, close, notes


def run_interviews(client: OpenAI) -> tuple[int, list[str]]:
    print("\nЗАДАНИЕ 3 — интервью (по 1 баллу за ответ, максимум 5)\n")
    agree_total = 0
    notes = []
    for case in INTERVIEWS:
        obs = ask(client, ege_prompts.interview_prompt(INTERVIEW_QUESTIONS),
                  case["script"], 900)
        # Как на проде: сначала механическая сверка улик (она метит выдуманные
        # цитаты и зачтённые обрывки), потом общий подсчёт. Второго прохода
        # здесь нет — он живёт в main.py и стоит лишних вызовов; это
        # единственное, чем замер отличается от боевого пути.
        ege_scoring.flag_suspicious("interview", obs, case["script"])
        fb = scoring._score_feedback("interview", obs,
                                     {"questions": INTERVIEW_QUESTIONS})
        marks = [c["score"] for c in fb["criteria"]][:5]
        marks += [0] * (5 - len(marks))
        want = case["expected_marks"]
        agree = sum(1 for a, b in zip(marks, want) if a == b)
        agree_total += agree
        flag = "==" if marks == want else "~~"
        print(f"{flag} {case['name']}: наш {marks} = {sum(marks)}/5 | "
              f"эксперты {want} = {sum(want)}/5 | совпало вердиктов: {agree}/5")
        if agree < 4:
            notes.append(f"{case['name']}: совпало только {agree}/5 вердиктов")
    return agree_total, notes


def main() -> int:
    if not os.environ.get("LLM_API_KEY"):
        print("Нет LLM_API_KEY в backend/.env — живую сверку запустить нельзя.")
        return 2
    # ОДИН прогон этой сверки ничего не доказывает. Замер 05.08.2026: три
    # прогона подряд на неизменном коде дали «в пределах ±1» 5, 2 и 3 из шести.
    # Модель отвечает при temperature 0.2, и вердикты по аспектам гуляют между
    # запусками сильнее, чем любая наша правка. Судить о регрессе по одному
    # прогону — значит гоняться за шумом; поэтому по умолчанию их три, а решает
    # СРЕДНЕЕ. Цена: 8 вызовов на прогон.
    runs = 3
    # --recheck / --no-recheck: тот самый второй взгляд на спорные аспекты.
    # Ключ нужен ради ЧЕСТНОГО сравнения: обе ветки гоняются одной командой на
    # одних и тех же работах, иначе «стало лучше» останется вопросом веры.
    recheck = True
    for i, arg in enumerate(sys.argv):
        if arg == "--runs" and i + 1 < len(sys.argv):
            runs = max(1, int(sys.argv[i + 1]))
        if arg == "--no-recheck":
            recheck = False
    client = OpenAI(base_url=BASE_URL, api_key=os.environ["LLM_API_KEY"], timeout=90)
    print(f"Сверка живого разбора с экспертами ФИПИ. Модель: {MODEL}, "
          f"прогонов: {runs}\n")

    exacts, closes, agrees, notes = [], [], [], []
    for r in range(runs):
        if runs > 1:
            print(f"\n{'─' * 70}\nПРОГОН {r + 1} из {runs}\n{'─' * 70}")
        exact, close, n1 = run_monologues(client, recheck)
        agree, n2 = run_interviews(client)
        exacts.append(exact)
        closes.append(close)
        agrees.append(agree)
        notes += n1 + n2

    def avg(xs: list[int]) -> float:
        return sum(xs) / len(xs)

    total = len(MONOLOGUES)
    print(f"\n{'═' * 70}")
    print(f"Монолог: точное совпадение {avg(exacts):.1f}/{total} "
          f"(по прогонам {exacts}), в пределах ±1 балла {avg(closes):.1f}/{total} "
          f"(по прогонам {closes})")
    print(f"Интервью: совпало {avg(agrees):.1f}/10 вердиктов (по прогонам {agrees})")
    if runs > 1:
        print(f"Разброс между прогонами: монолог ±1 балл "
              f"{min(closes)}-{max(closes)}, интервью {min(agrees)}-{max(agrees)}. "
              "Правка, меняющая меньше этого, — не улучшение, а шум.")
    if notes:
        print("\nРасхождения, на которые стоит смотреть:")
        for n in sorted(set(notes)):
            print("  -", n)
    # Порог намеренно мягкий: требуем не идеала, а отсутствия перекоса. Судим
    # по среднему — одиночный неудачный прогон не должен объявлять регресс.
    ok = avg(closes) >= total - 1.5 and avg(agrees) >= 8
    print("\n" + ("ИТОГ: разбор держится рядом с экспертами." if ok
                  else "ИТОГ: расхождение великовато, промпты надо править."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
