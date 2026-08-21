"""Записи ЖИВОЙ речи участников ЕГЭ с вердиктами экспертов — золотой набор.

Откуда: официальный архив ФИПИ к методичке 2026
(doc.fipi.ru/ege/dlya-predmetnyh-komissiy-subektov-rf/2026/aya_mr_ege_audio 2026.zip),
28 записей — по семь на каждое из четырёх заданий устной части. Разбор
каждой записи с поимённым списком ошибок лежит в самой методичке, раздел II.

ЧЕМ ЭТО ОТЛИЧАЕТСЯ ОТ ВСЕГО, ЧТО У НАС БЫЛО. Все наши сетки до 20.08.2026
гонялись на СИНТЕЗИРОВАННОЙ речи, и это дважды выходило боком: обе поломки,
найденные 16.08 (DECISIONS §6.21), прятались именно на чистом синтезе и
вылезли только на русском голосе. Здесь речь настоящая — с акцентом,
запинками, паузами и самоисправлениями, и к ней приложен балл человека.

Сами файлы В РЕПОЗИТОРИЙ НЕ КЛАДЁМ: 44 МБ звука в git — это надолго и
навсегда. Они лежат рядом, путь ниже; манифест хранит только связку
«файл ↔ эталон ↔ вердикт», а это текст.

ЗАДАНИЕ 1 (чтение вслух) — единственная часть, где вердикт эксперта
ПОФОНЕМНЫЙ: он перечисляет конкретные ошибки произношения. Это готовая
сетка для фонемной ступени (gop.py), когда у неё появится порог: мы знаем,
сколько ошибок услышал человек и какие именно.
"""

from __future__ import annotations

import os

# Звук лежит вне репозитория. Переедет — поменять одну строку.
AUDIO_DIR = os.environ.get(
    "FIPI_AUDIO_DIR", r"C:\Users\Lenovo\pingo-fipi\audio")


def path(name: str) -> str:
    """Полный путь к записи. Существование НЕ проверяем: манифест
    осмыслен и без файлов — по нему видно, чего не хватает."""
    return os.path.join(AUDIO_DIR, name)


# --------------------------------------------------------------------------
# Задание 1: чтение вслух. Балл 1 или 0, критерий чисто фонетический.
# --------------------------------------------------------------------------
READING_AUDIO = [
    {
        "work": "0051",
        "audio": "task1_19_0051.ogg",
        "expert_score": 0,   # балл эксперта ФИПИ
        "expert_errors": 6,
        # что услышал эксперт: пропущено слово very, observed /əbˈsɜːvd/, пропущен артикль the, can’t / ka:nt/,
        "reference": (
            "If you are thinking of what pet to get, a parrot may be what you "
            "need. It is not very difficult to have a parrot as a pet. They are "
            "happy to eat fruits, nuts, seeds and buds. It is easy to find such "
            "food in pet shops, and it is not very expensive. Some par rot "
            "species from the South American continent have been observed to eat "
            "clay. They do so to flush out the toxins from their bodies which get "
            "into their system through the seeds that they feed on. There are "
            "also some parrots who feed on snails or insects, but they can’t be "
            "bought in a pet shop. Parrots are also great as pets because they "
            "have a relatively long lifespan. It varies according to the species. "
            "Small ones can live for up to twenty years, whereas medium-sized "
            "ones may have a lifespan of thirty years. Big parrots can live more "
            "than a hundred years."
        ),
    },
    {
        "work": "3775",
        "audio": "task1_21_3775.mp3",
        "expert_score": 0,   # балл эксперта ФИПИ
        "expert_errors": 8,
        # что услышал эксперт: (1) fre[e]quently; (2) They (читает then); (3) it (читает its); (4) of nasty (амер.)
        "reference": (
            "During the dry season in the savanna, the only reliable place to "
            "find water is at a water hole. Thus, it can be a very busy place. "
            "Basically, a water hole is a pool or a depression in the ground in "
            "which water can collect. Animals visit a water hole frequently, "
            "especially elephants which have to drink about 200 litres of water a "
            "day. Oftentimes an animal leaves a water hole dirtier than ever. "
            "They try to cover themselves in the mud because it cools them down "
            "and it may also help them to get rid of nasty insects that usually "
            "infect the animal’s skin. Sometimes larger animals are accompanied "
            "by small birds to a water hole. These birds hope to find insects on "
            "the animal’s skin. As well as insect control, such birds may also "
            "clean up any wounds the host animal may have. Thus, both host "
            "animals and birds are happy. In general, birds can often be seen "
            "wading in water holes, looking for fish and frogs."
        ),
    },
    {
        "work": "4596",
        "audio": "task1_17_4596.ogg",
        "expert_score": 1,   # балл эксперта ФИПИ
        "expert_errors": 2,
        # что услышал эксперт: пропущен артикль перед существительным catalogue, пропущен артикль
        "reference": (
            "Snowflakes are ice crystals which fall through the Earth’s "
            "atmosphere as snow. People like to think that every snowflake has a "
            "unique shape. However, it’s not true. While snowflakes may look "
            "different, they can still be classified into eight groups and about "
            "eighty different variants. Some scientists have done a lot of "
            "research into making a kind of a catalogue of snowflakes. The most "
            "typical patterns for a snowflake are needles, columns, plates and "
            "rimes. The shape and the pattern of a snowflake largely depend on "
            "the weather conditions. The study of snowflakes has identified that "
            "long, thin needle-like ice crystals form at around zero, while a "
            "lower temperature will lead to very flat crystals. Further changes "
            "in temperature as a snowflake falls determine m ore complicated "
            "shapes of snowflakes. The size of a snowflake also depends on the "
            "air temperature."
        ),
    },
    {
        "work": "5563",
        "audio": "task1_18_5563.ogg",
        "expert_score": 0,   # балл эксперта ФИПИ
        "expert_errors": 7,
        # что услышал эксперт: retained, the вместо and, пропущен глагол is, million вместо millions, пропущен
        "reference": (
            "Rain is an important part of the water cycle which never stops on "
            "our planet. Water is delivered to the ground by rains. It is "
            "retained as clouds in the sky and falls over and through the land. "
            "Actually, this is one of the reasons why the earth is cold in winter "
            "and warm in summer. Water escapes into the atmosphere and turns into "
            "clouds. Rain is useful for us in many different ways. Firstly, it "
            "waters the Earth and refills streams, rivers, lakes, and oceans. The "
            "water in the oceans is home to millions of sea creatures and the "
            "water in the streams, rivers, and lakes is home to fresh- water fish "
            "and other water animals. Secondly, rain provides the water trees and "
            "other plants need. Rain also gives wild animals the water they need "
            "to drink. Finally, people love rainy weather. It makes the air fresh "
            "and clean."
        ),
    },
    {
        "work": "7323",
        "audio": "task1_20_7323.mp3",
        "expert_score": 1,   # балл эксперта ФИПИ
        "expert_errors": 3,
        # что услышал эксперт: (1) accompa’nie[ai]d by small birds to a water hole; (2) such birds may also
        "reference": (
            "During the dry season in the savanna, the only reliable place to "
            "find water is at a water hole. Thus, it can be a very busy place. "
            "Basically, a water hole is a pool or a depression in the ground in "
            "which water can collect. Animals visit a water hole frequently, "
            "especially elephants which have to drink about 200 litres of water a "
            "day. Oftentimes an animal leaves a water hole dirtier than ever. "
            "They try to cover themselves in the mud because it cools them down "
            "and it may also help them to get rid of nasty insects that usually "
            "infect the animal’s skin. Sometimes larger animals are accompanied "
            "by small birds to a water hole. These birds hope to find insects on "
            "the animal’s skin. As well as insect control, such birds may also "
            "clean up any wounds the host animal may have. Thus, both host "
            "animals and birds are happy. In general, birds can often be seen "
            "wading in water holes, looking for fish and frogs."
        ),
    },
    {
        "work": "9213",
        "audio": "task1_23_9213.mp3",
        "expert_score": 0,   # балл эксперта ФИПИ
        "expert_errors": 10,
        # что услышал эксперт: some (добавляет нейтральный звук в конце слова), ge[e]nre, readers
        "reference": (
            "Many people want to write a book at some point of their life. Now "
            "anyone can manage it if they follow some simple steps. First of all, "
            "one needs to understand what the book is going to be about. Then "
            "it’s time to think about the genre. It should suit the idea and be "
            "attractive for the potential readers. The next logical step would be "
            "to outline the story and write the first draft. It’s also necessary "
            "to think of a good beginning. The first pages should catch the "
            "reader’s eye – it’s they which can either make or break the book. If "
            "these pages are not good enough, most readers will just lose their "
            "interest and will never return to the book again. At this point one "
            "should also organize their writing space and set their writing "
            "routine. Many writers have word count goals per day to keep the "
            "process going. Finally, one may self-publish the book on the "
            "Internet and wait for the response."
        ),
    },
    {
        "work": "9377",
        "audio": "task1_22_9377.mp3",
        "expert_score": 1,   # балл эксперта ФИПИ
        "expert_errors": 1,
        # что услышал эксперт: Others spend the (the пропускает) day
        "reference": (
            "In order to survive, desert animals have developed ways of either "
            "keeping out of the heat or cooling down. Desert foxes, for instance, "
            "lose heat through big ears, and furry soles help them to walk on hot "
            "sand. Kangaroos lick their forearms to cool themselves down. Some "
            "animals have got bushy tails which create a sunshade for them. "
            "Others spend the day underground and hunt at night. However, extreme "
            "heat is not the only problem for desert animals. There is little "
            "water in deserts, so animals had to learn to survive without it for "
            "a long time. A camel can spend about three weeks without water. When "
            "it does have a chance to drink, it ca n take in a huge amount. Many "
            "people think that the water goes to the hump on its back. However, "
            "it’s only a myth. Camels’ humps store fat, which, when needed, will "
            "be converted to food or water. Besides, camels’ coats reflect the "
            "sun rays, so camels never get too hot."
        ),
    },
]


def reading_cases() -> list[dict]:
    """Записи чтения, для которых файл реально лежит на диске."""
    return [c for c in READING_AUDIO if os.path.exists(path(c["audio"]))]


# --------------------------------------------------------------------------
# Задание 2 (наше 40): четыре прямых вопроса к объявлению.
# Вердикты экспертов — методичка 2026, стр. 62-69, поимённо по вопросам.
# Тексты заданий в PDF нарисованы картинками; расшифрованы вручную 21.08.2026
# (страницы 63-69), у 9213 текст лежал в самой странице.
# --------------------------------------------------------------------------
DIALOGUE_AUDIO = [
    {
        "work": "0051", "audio": "task2_7_0051.ogg",
        # Вопрос 1 отклонён: «a grocery store» вместо «the» — вопрос не о ТОМ
        # магазине. Наш конвейер этого НЕ ВИДИТ: Voxtral нормализует артикль
        # в «the» (проверено 21.08.2026 прямым запросом) — ограничение STT.
        "expert": [0, 1, 1, 1],
        "ad": "Freshness you can taste!",
        "points": ["location", "opening hours", "kind of fruits sold",
                   "delivery service"],
    },
    {
        "work": "4596", "audio": "task2_8_4596.ogg",
        "expert": [1, 1, 1, 1],
        "ad": "The best clinic in town!",
        "points": ["location", "public transport", "dentist",
                   "family discounts"],
    },
    {
        "work": "5563", "audio": "task2_9_5563.ogg",
        # Вопрос 1 отклонён: последняя попытка не закончена («Where is…?»).
        # Фальстарт и обрыв Voxtral вырезает — тоже невидимо для нас.
        "expert": [0, 1, 1, 1],
        "ad": "All the flowers of the world!",
        "points": ["location", "cost of delivery",
                   "special occasion decorations", "potted flowers"],
    },
    {
        "work": "0487", "audio": "task2_10_0487.mp3",
        # Вопрос 4 отклонён: лексическая ошибка «employ a coach».
        "expert": [1, 1, 1, 0],
        "ad": "Join our volleyball club!",
        "points": ["location", "special clothes", "opportunity to play inside",
                   "coach for beginners"],
    },
    {
        "work": "3775", "audio": "task2_11_3775.mp3",
        "expert": [1, 1, 1, 1],
        "ad": "Join our hockey club!",
        "points": ["location", "minimum age", "type of ice rink",
                   "special equipment needed"],
    },
    {
        "work": "9377", "audio": "task2_12_9377.mp3",
        # Вопрос 3 отклонён: «in that motorcycle club» — вопрос о ДРУГОМ клубе,
        # сбой коммуникации. С 21.08.2026 это ловит код
        # (ege_scoring.question_rejected, правило «that + предмет объявления»).
        "expert": [1, 1, 0, 1],
        "ad": "Welcome to our motorcycle club!",
        "points": ["location", "special clothes", "coach", "competitions"],
    },
    {
        "work": "9213", "audio": "task2_13_9213.mp3",
        # Вопрос 2: «There are historical costumes?» — повествовательный
        # порядок; вопрос 4: «How much does the cost…» — сломанная форма.
        "expert": [1, 0, 1, 0],
        "ad": "A professional photographer for you!",
        "points": ["location of the studio", "historical costumes",
                   "professional make-up", "the cost of an hour's work"],
    },
]


# --------------------------------------------------------------------------
# Задание 4 (наше 42): монолог-голосовое. Вердикты (К1, К2, К3) — методичка
# 2026, стр. 93-113. Шкала 2026: 4+3+3=10. У записи task4_19_9213 разбора в
# методичке НЕТ (ЗАДАНИЕ 19 отсутствует) — в манифест не входит.
#
# В brief важна ФОРМА глагола мнения: у 5563 план требует «you prefer»
# (эксперт валит «I'd prefer» как неверную форму), у остальных — «you'd
# prefer». Перепутать — сломать правило verb_form_matches.
# --------------------------------------------------------------------------
_MONO_BRIEF = (
    "Task 4. Imagine that you and your friend are doing a school project "
    "“{topic}”. You have found some photos to illustrate it but for "
    "technical reasons you cannot send them now. Leave a voice message to "
    "your friend explaining your choice of the photos and sharing some ideas "
    "about the project. In 2.5 minutes be ready to: explain the choice of the "
    "illustrations for the project by briefly describing them and noting the "
    "differences; mention the advantages (1–2) of the two {thing}; "
    "mention the disadvantages (1–2) of the two {thing}; express your "
    "opinion on the subject of the project – which of these {thing} "
    "{prefer} and why. You will speak for not more than 3 minutes "
    "(12–15 sentences). You have to talk continuously."
)


def _mono_brief(topic: str, thing: str, prefer: str = "you’d prefer") -> str:
    return _MONO_BRIEF.format(topic=topic, thing=thing, prefer=prefer)


MONOLOGUE_AUDIO = [
    {
        "work": "5563", "audio": "task4_13_5563.ogg",
        # Аспекты эксперта: ±, −, ±, −  →  К1=0, и нуль обнуляет всё.
        "expert": (0, 0, 0),
        "brief": _mono_brief("The games people like", "types of games",
                             "you prefer"),
        "photoFacts": [
            "A girl is playing video games alone at home",
            "Two people, probably a mother and her daughter, are playing "
            "chess (a table game) together at home",
        ],
    },
    {
        "work": "4596", "audio": "task4_14_4596.ogg",
        # Аспекты: +, ±, ±, ±  →  К1=2; логика 3 ошибки → К2=2; язык → К3=2.
        "expert": (2, 2, 2),
        "brief": _mono_brief("Ideal weekend", "ways of spending the weekend"),
        "photoFacts": [
            "A woman wearing headphones is listening to music and relaxing "
            "in her living room with a cat at her side",
            "Three women are riding bicycles along a road in the countryside",
        ],
    },
    {
        "work": "0051", "audio": "task4_15_0051.ogg",
        # Аспекты: −, ±, +, ±  →  К1=1. Работа у самого обрыва: качнуть один
        # вердикт — и вся оценка падает с 4 до 0 (см. DECISIONS §6.9).
        "expert": (1, 2, 1),
        "brief": _mono_brief("The best moments with grandparents",
                             "ways of spending time with grandparents"),
        "photoFacts": [
            "A boy is playing chess with his grandfather at home; the "
            "grandmother and a young woman who may be the mother or sister "
            "are nearby",
            "Grandparents and children are walking together outdoors in the "
            "mountains in winter",
        ],
    },
    {
        "work": "5471", "audio": "task4_16_5471.mp3",
        # Все аспекты +, организация 3, но 11 языковых ошибок → К3=0.
        "expert": (4, 3, 0),
        "brief": _mono_brief("Hobbies", "hobbies"),
        "photoFacts": [
            "A woman is kneeling on the ground outdoors, planting a young "
            "tree",
            "A man is cooking in the kitchen and filming the process with a "
            "camera",
        ],
    },
    {
        "work": "3775", "audio": "task4_17_3775.mp3",
        # Аспекты: ±, ±, −, +  →  К1=1; более 8 языковых ошибок → К3=0.
        "expert": (1, 2, 0),
        "brief": _mono_brief("Volunteering", "types of volunteering"),
        "photoFacts": [
            "Two girls are picking up trash outdoors",
            "A smiling woman is looking after a dog, apparently at an animal "
            "shelter",
        ],
    },
    {
        "work": "9377", "audio": "task4_18_9377.mp3",
        # Аспекты: ±, ±, ±, +  →  К1=2; 9 языковых ошибок → К3=0.
        "expert": (2, 2, 0),
        "brief": _mono_brief("Sports", "kinds of sport"),
        "photoFacts": [
            "A group of teenagers wearing T-shirts are playing volleyball in "
            "summer, they look happy",
            "Two ice hockey teams are playing against each other in winter, "
            "the players look focused",
        ],
    },
]


def dialogue_cases() -> list[dict]:
    """Записи задания 2, для которых файл реально лежит на диске."""
    return [c for c in DIALOGUE_AUDIO if os.path.exists(path(c["audio"]))]


def monologue_cases() -> list[dict]:
    """Записи задания 4, для которых файл реально лежит на диске."""
    return [c for c in MONOLOGUE_AUDIO if os.path.exists(path(c["audio"]))]
