"""Работы участников ЕГЭ из практикума методички ФИПИ — размеченный корпус.

Раздел II методички («Практикум по оцениванию заданий по говорению»): скрипты
реальных ответов с вердиктом эксперта ПО КАЖДОМУ пункту и итоговым баллом.
Это единственная разметка, которая у нас есть от людей, поэтому она вынесена
в отдельный модуль: сетка (test_ege_live.py) её только гоняет, а пополнять
корпус можно, не трогая код замера.

Что здесь есть: задания 2, 3 и 4 (наши 40, 41 и 42).

ЛОВУШКА СО ШКАЛОЙ, проверять у КАЖДОЙ работы отдельно. Методичка 2024
содержит ДВЕ схемы оценивания задания 4: на стр. 78 (проект «Part-time
jobs») максимумы 3+2+2=7, а на стр. 83, 86 и 93 — 4+3+3=10, то есть наша.
Семибалльная — legacy-пример внутри того же документа; практикум разобран по
десятибалльной. Год на обложке ничего не решает, решает схема у работы.

Работ по заданию 1 (чтение) здесь нет и быть не может: там все ошибки
ФОНЕТИЧЕСКИЕ (pa[a:]tron, le[e]gal, couch [ou]), а на вход разбора приходит
текстовая расшифровка. Эти работы — цель для фонемной ступени (gop.py), и
когда у неё появится порог, они станут её сеткой.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Задание 3 (наше 41): условный диалог-интервью, по 1 баллу за ответ
# --------------------------------------------------------------------------
# У каждой работы СВОИ вопросы: темы в практикуме разные, и подменять их общим
# списком нельзя — половина вердиктов держится на том, отвечает ли ученик
# именно на свой запрос («спросили как часто — сказано где»).

INTERVIEW_EXTRA = [
    {
        "name": "интервью 5471, фотография",
        "questions": [
            "Why do you think people like taking photographs?",
            "Do you like having your photo taken? Why or why not?",
            "How often do you take photos? What of?",
            "What is your favourite photo? Describe it.",
            "Why do you think so many people enjoy taking selfies?",
        ],
        # Эксперты 3/5: второй ответ не по вопросу («не поняла вопрос»),
        # пятый — по содержанию и объёму годится, но с ошибками уровня A2.
        "expected_marks": [1, 0, 1, 1, 0],
        "script": (
            "People like taking photographs because people can capture a lot of "
            "sights, a lot of beautiful places that they see. And photos bring "
            "memories, so people could remember places they visited and remember "
            "emotions that they felt that day when they took a picture. "
            "Yes, I love my photo taking it is a breathtaking process and I love "
            "capturing all the things that I see and things I consider very "
            "beautiful and fascinating. Also, I love pictures that I take usually "
            "because I have kind of a talent taking them. "
            "I take photos almost every day, usually I take photos of nature, for "
            "example, flowers or beautiful trees, especially in the summertime or "
            "in the spring because all plants are green and colourful, so it is a "
            "big pleasure to take photos and then enjoy them. "
            "My favourite photo is the photo of a big big tree that I can see I "
            "can observe near my house. It is very beautiful and it is huge, so, "
            "its view fascinates me, and every season I like taking a photo of it. "
            "Every season. "
            "I think they enjoy it because selfies are very easy to take. Also, "
            "people when they get dressed up or doing make-ups, they love "
            "themselves and they like doing photos of themselves, so they can "
            "enjoy their very beautiful look and of course upload these photos in "
            "social media so they can get a lot of attention from other people."
        ),
    },
    {
        "name": "интервью 9213, наука",
        "questions": [
            "What science subjects have you studied? Which of them did you enjoy?",
            "Are there any inventions or discoveries which had negative effects?",
            "What would you like scientists to discover or invent in the future? Why?",
            "What scientist of the past or the present do you admire? Why?",
            "What discovery or invention can you not live without? Why?",
        ],
        # Эксперты 0/5: ошибки уровня A2, недобор объёма, дважды «вопрос не
        # понят», на пятый вопрос ответа нет вовсе.
        "expected_marks": [0, 0, 0, 0, 0],
        "script": (
            "I studied mathematic, informatic. It is my favourite subjects. "
            "I think these subjects do not get negative effects. "
            "I would like to be scientist. It was a very interesting and amazing "
            "profession. "
            "I think I admire scientists which can help nature in the future."
        ),
    },
    {
        "name": "интервью 7901, свободное время",
        "questions": [
            "How old are you? What class are you in?",
            "How do you usually spend your free time? What do you like to do on Sundays?",
            "Do you prefer to spend your free time with your friends or your family? Why?",
            "How do your friends spend their free time? Where do they go and what do they do?",
            "How do you think you will spend your free time in ten years time?",
        ],
        # Эксперты 3/5. Четвёртый ответ — нет ответа на ВТОРУЮ часть вопроса
        # (куда они ходят), пятый — ошибка уровня A2 в конце первой фразы.
        # Первый ответ поучителен обратным: ошибка в артикле есть, но на смысл
        # не влияет, и балл поставлен.
        "expected_marks": [1, 1, 1, 0, 0],
        "script": (
            "I am seventeen years old and I am in eleventh grade. "
            "I usually like reading some detective and science fiction book. On "
            "Sundays I like walking in the streets, go to some remote places with "
            "my family and friends. I do it for recharging the batteries and "
            "putting my feet up. "
            "I prefer spending my time with my friends because it is very fun and "
            "very great for me. We like spending time together in some quest rooms "
            "or in my home. We are an avid we are the avid fans of cooking, "
            "playing some boardgames, and also we like cycling. "
            "Speaking about my best friend, she always plays a guitar and piano, "
            "and it is a very great way for her to recharge the batteries and "
            "relax. And another my best friend, he plays football in his free "
            "time, and he is also interested in cooking. "
            "I will spend my free time in 10 years very great, I think. First of "
            "all, I will study more languages like Spanish and German; also, I "
            "would like to learn some French, learn French and polish up my "
            "language skills."
        ),
    },
    {
        "name": "интервью, практикум задание 10, книги",
        "questions": [
            "What books do you prefer to read?",
            "Who is your favourite writer?",
            "How often do you borrow books in the library?",
            "Why do teenagers use libraries less nowadays than they used to?",
            "Do you prefer e-books or printed books? Why?",
        ],
        # Эксперты 0/5. Третий ответ — самый поучительный в корпусе: две полные
        # грамотные фразы, но отвечают НЕ НА ТОТ вопрос (спросили «как часто»,
        # сказано «где»). Ровно та щедрость, которой грешит наша проверка.
        "expected_marks": [0, 0, 0, 0, 0],
        "script": (
            "I prefer different books. "
            "Joan Rowling. I like her stories very much. "
            "I usually read e-books at home or at school. I have many e-books in "
            "my tablet. "
            "I I prefer printed books because it is most interested to read these "
            "books."
        ),
    },
]


# --------------------------------------------------------------------------
# Задание 4 (наше 42): монолог по двум фотографиям
# --------------------------------------------------------------------------
# ВАЖНО ПРО ШКАЛУ. Методичка 2024 содержит ДВЕ схемы оценивания задания 4:
# на стр. 78 (проект «Part-time jobs») максимумы 3+2+2=7, а на стр. 83, 86 и
# 93 — 4+3+3=10, то есть НАША. Семибалльная схема — legacy-пример внутри того
# же документа; работы практикума разобраны по десятибалльной, и потому
# применимы как есть. Сверять надо схему у КОНКРЕТНОЙ работы, а не год на
# обложке.

MONOLOGUE_EXTRA = [
    {
        "name": "Happy childhood (стр. 89-91)",
        "brief": (
            "Task 4. Imagine that you and your friend are doing a school project "
            "\"Happy childhood\". You have found two photos to illustrate it but "
            "cannot send them, so you leave a voice message: explain the choice of "
            "the illustrations by briefly describing them and noting the "
            "differences; mention the advantages (1-2) of the two types of "
            "children's leisure activities; mention the disadvantages (1-2); "
            "express your opinion on the subject of the project - which leisure "
            "activity you preferred as a child and why. Speak for 12-15 sentences."
        ),
        "facts": ["four children playing outside",
                  "a girl reading books indoors alone"],
        # Эксперты: аспект 1 неточный (различия названы малозначительные — число
        # людей и место, не связанные с темой проекта), аспекты 2-4 полные.
        # К1=3, К2=2 (одно нарушение логики и одна ошибка связки), К3=0 (восемь
        # и более неповторяющихся ошибок). Итого 5 из 10.
        "expected": (3, 2, 0),
        "script": (
            "Hello! I've just found two photos for our project and I'm going to "
            "discuss them with you. Well, the first photo demonstrates us four "
            "children playing outside, while second photo shows us a girl who is "
            "interesting who is interested in books and studying. That's why I "
            "think that these pictures illustrate our project perfectly, because "
            "they show happy childhood. "
            "It is obvious that these pictures are completely different. The main "
            "difference between these photos are number of children and the place. "
            "In the first photo we can see 4 children playing outside on the "
            "ground, whereas second photo in the second photo girl is inside and "
            "she is alone. "
            "Also, different childhoods have some advantages and disadvantages. "
            "And speaking about first photo, people while walking and playing "
            "outside, communicate with another children and they improve some "
            "communication skills, leadership skills and it is very great for "
            "their future. But unfortunately, they run a risk of suffering from "
            "bullying and different insults from other children. "
            "Speaking about second photo, the girl loves studying, and it is also "
            "great for your future. She has an opportunity to improve her "
            "critical, logical and analytical thinking, also books are the great "
            "relaxation technique for everyone. But speaking about some cons, this "
            "reading and studying can be exhausting and sometimes time-consuming "
            "and even boring, so person runs a risk of being overcharged. "
            "Speaking about my childhood, I preferred attending dancing classes, I "
            "was an avid fan of ballet-dancing. And I communicated with another "
            "people and liked to spend time with them. "
            "Please let me know whether you like the choice of two photos for our "
            "project."
        ),
    },
    {
        "name": "Family pastime 9213 (стр. 84)",
        "brief": (
            "Task 4. Imagine that you and your friend are doing a school project "
            "\"Family pastime\". You have found two photos to illustrate it but "
            "cannot send them, so you leave a voice message: explain the choice of "
            "the illustrations by briefly describing them and noting the "
            "differences; mention the advantages (1-2) of the two types of family "
            "pastime; mention the disadvantages (1-2); express your opinion - "
            "which type of family pastime you prefer and why. Speak for 12-15 "
            "sentences."
        ),
        "facts": ["a family looking at smartphones",
                  "a family walking outside"],
        # Эксперты: аспект 1 неточный, аспекты 2-4 не раскрыты (паузы по 8-11
        # секунд, содержание отсутствует). К1=0 обнуляет всё задание.
        # Работа собрана из цитат разбора: сплошного скрипта в методичке нет,
        # паузы обозначены как в разборе.
        "expected": (0, 0, 0),
        "script": (
            "Hello, my dear friend! I've found two photos for hour project Family "
            "Pastime. And I'd like discuss with you. I chose these photos because "
            "they best illustrate family pastime. In the first picture we can see "
            "a family who spend their time on smart phone. Whiles in second "
            "picture we can see family who walking outside. "
            "The biggest disadvantage first picture family can't speaking with "
            "your parents whiles two photo family can speaking with "
            "In my opinion, I prefer two photo because spending time on outside "
            "it's healthy and enjoy."
        ),
    },
]
