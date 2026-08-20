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
