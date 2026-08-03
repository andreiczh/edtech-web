"""Сценарии разговора: скрытый план беседы.

Зачем это вообще (04.08.2026). До сценариев модель просто реагировала на
последнюю реплику: у разговора не было ни темы, ни цели, ни направления —
отсюда генерические вопросы («What do you like to do?») и ощущение
поверхностного собеседника. Теперь сервер выбирает тему и даёт модели скрытую
повестку: ступени разговора, зацепку для начала и полезную лексику.

Три правила, которые здесь важнее остального:

1. **План СКРЫТЫЙ.** Ученик видит только название темы. Модель не зачитывает
   ступени вслух и не сообщает, что у неё есть план, — иначе разговор
   превращается в анкету.

2. **Ступень считает СЕРВЕР, не модель.** Номер шага выводится из длины
   истории (`plan_block`), а не спрашивается у LLM отдельным запросом. Лишний
   вызов на каждую реплику удвоил бы расход и добавил задержку в горячий путь.

3. **Тема не догма.** В промпте прямо сказано: ученик увёл разговор в сторону —
   иди за учеником. План служит беседе, а не наоборот.

Ступени у всех сценариев идут одной лестницей — от простого к сложному, как в
устной части ЕГЭ: факты → личное → мнение → воображение. Это же и есть
естественный ход живого разговора: сначала «что было», потом «а ты как», потом
«а стоит ли», потом «а что если».

Разнообразие — не украшение, а требование владельца: ученик заходит каждый день,
и темы не должны повторяться. Сейчас их 48, то есть полтора месяца ежедневных
занятий без единого повтора; порядок случайный, недавние исключаются.
"""

from __future__ import annotations

import random
from typing import Sequence

# --------------------------------------------------------------------------
# Формат записи:
#   id      — стабильный ключ (уезжает на клиент, хранится в списке «недавние»)
#   title   — что видит ученик на экране (по-русски)
#   hint    — одна строка, о чём будет разговор: помогает собраться с мыслями
#   topic   — тема для модели, одной фразой
#   opener  — с чего начать, если ученик не задал направление сам
#   stages  — четыре ступени: факты → личное → мнение → воображение
#   vocab   — обороты уровня A2-B1, которые уместно подкинуть в речи
#   role    — необязательное: разыгранная сцена (модель играет роль)

SCENARIOS: list[dict] = [
    # ---------------------------------------------------------- быт и учёба
    {
        "id": "weekend",
        "title": "Выходные",
        "hint": "Чем занимался в выходные и каким был бы идеальный выходной.",
        "topic": "how the student spends their weekends",
        "opener": "ask what they actually did last weekend, not what they usually do",
        "stages": [
            "get the facts: what they did last weekend, where, with whom",
            "make it personal: who they like spending free time with, and why that person",
            "opinion: is two days enough to rest, or do they end up more tired",
            "imagine: a perfect weekend with no money and no time limits",
        ],
        "vocab": ["hang out with", "I ended up", "it was worth it", "I'd rather", "on my own"],
    },
    {
        "id": "school_day",
        "title": "Школьный день",
        "hint": "Как проходит обычный день, что нравится и что бесит.",
        "topic": "the student's school or college day",
        "opener": "ask what their first lesson today was and whether it was any good",
        "stages": [
            "get the facts: timetable, favourite and worst subject",
            "make it personal: a teacher who changed how they see a subject",
            "opinion: does school actually prepare them for real life",
            "imagine: they run the school for one week — what changes first",
        ],
        "vocab": ["it depends on", "I'm not really into", "make sense", "the point of", "used to"],
    },
    {
        "id": "exams",
        "title": "Экзамены и волнение",
        "hint": "Подготовка, стресс и что реально помогает.",
        "topic": "exams and the stress around them",
        "opener": "ask which exam scares them most right now and why that one",
        "stages": [
            "get the facts: which exams they take, when, how they prepare",
            "make it personal: what their nerves feel like and what actually helps",
            "opinion: do exams measure anything real about a person",
            "imagine: exams are cancelled tomorrow — how should universities choose students",
        ],
        "vocab": ["I'm nervous about", "cope with", "cram", "fall behind", "it pays off"],
    },
    {
        "id": "morning",
        "title": "Утро и режим",
        "hint": "Жаворонок или сова, как начинается день.",
        "topic": "the student's morning routine and sleep habits",
        "opener": "ask what time they got up today and whether that was on purpose",
        "stages": [
            "get the facts: wake-up time, first thing they do, breakfast or no breakfast",
            "make it personal: are they a morning person, and how it affects their mood",
            "opinion: should school start later than it does",
            "imagine: they can add three hours to the day — morning or night, and for what",
        ],
        "vocab": ["oversleep", "I'm used to", "get ready", "skip breakfast", "night owl"],
    },
    {
        "id": "procrastination",
        "title": "Прокрастинация",
        "hint": "Почему мы откладываем и как с этим бороться.",
        "topic": "putting things off and getting things done",
        "opener": "ask what they are putting off right now, honestly",
        "stages": [
            "get the facts: what they postpone most often and what they do instead",
            "make it personal: the last time they left something until the very last night",
            "opinion: is a deadline the only thing that really makes people work",
            "imagine: they design an app that cures procrastination — how does it work",
        ],
        "vocab": ["put off", "on time", "get round to", "give up", "keep track of"],
    },
    # ----------------------------------------------------------- люди рядом
    {
        "id": "best_friend",
        "title": "Друзья",
        "hint": "Про друга, дружбу и что её держит.",
        "topic": "friendship and the people the student is close to",
        "opener": "ask how they met their closest friend",
        "stages": [
            "get the facts: who this friend is, how long they have known each other",
            "make it personal: something this friend did that they still remember",
            "opinion: can an online friend be as close as one you see every day",
            "imagine: their friend moves abroad tomorrow — what keeps a friendship alive",
        ],
        "vocab": ["get on well with", "have a lot in common", "fall out", "count on", "keep in touch"],
    },
    {
        "id": "family",
        "title": "Семья и дом",
        "hint": "Кто дома, чем занимаются, какие традиции.",
        "topic": "the student's family and home life",
        "opener": "ask who is at home right now",
        "stages": [
            "get the facts: who they live with, what a normal evening looks like",
            "make it personal: a family habit or tradition only their family has",
            "opinion: should teenagers have their own room and their own rules",
            "imagine: their family swaps roles for a day — who takes over what",
        ],
        "vocab": ["take after", "look after", "get on with", "argue about", "give me a hand"],
    },
    {
        "id": "hero",
        "title": "Человек, которым восхищаешься",
        "hint": "Кто-то реальный или известный — и почему именно он.",
        "topic": "a person the student looks up to",
        "opener": "ask who they would want to have lunch with, dead or alive",
        "stages": [
            "get the facts: who the person is and what they are known for",
            "make it personal: what exactly they would want to learn from them",
            "opinion: is it healthy to have heroes at all",
            "imagine: someone looks up to them in ten years — for what",
        ],
        "vocab": ["look up to", "stand out", "give up", "achieve", "make a difference"],
    },
    {
        "id": "kindness",
        "title": "Добрый поступок",
        "hint": "Когда тебе помогли и когда помог ты.",
        "topic": "kindness — small things people do for each other",
        "opener": "ask about the last time a stranger helped them",
        "stages": [
            "get the facts: what happened, who, where",
            "make it personal: a time they helped someone and how it felt",
            "opinion: do people help less than they used to, or does it just seem so",
            "imagine: one rule that would make their city kinder overnight",
        ],
        "vocab": ["help out", "on purpose", "it turned out", "owe someone", "pay it forward"],
    },
    {
        "id": "argument",
        "title": "Спор с близким",
        "hint": "Из-за чего ссоримся и как миримся.",
        "topic": "disagreements with parents or friends",
        "opener": "ask what they and their parents disagree about most often",
        "stages": [
            "get the facts: the usual subject of the argument",
            "make it personal: how they usually end it — apology, silence, or nothing",
            "opinion: is it better to say everything straight away or to cool down first",
            "imagine: they could replay one argument — what would they say instead",
        ],
        "vocab": ["fall out with", "make up", "calm down", "have a point", "I see what you mean"],
    },
    # ------------------------------------------------------------- интересы
    {
        "id": "music",
        "title": "Музыка",
        "hint": "Что слушаешь, когда и почему.",
        "topic": "music in the student's life",
        "opener": "ask what was playing in their headphones today",
        "stages": [
            "get the facts: artists, genres, when they listen",
            "make it personal: a song tied to a specific memory",
            "opinion: does music help you study or is that a myth",
            "imagine: they can only keep three songs forever — which and why",
        ],
        "vocab": ["I'm into", "get stuck in my head", "turn it up", "live gig", "on repeat"],
    },
    {
        "id": "films",
        "title": "Кино и сериалы",
        "hint": "Что смотришь и что зацепило.",
        "topic": "films and series the student watches",
        "opener": "ask what they watched most recently and whether it was worth it",
        "stages": [
            "get the facts: last film or episode, genre they return to",
            "make it personal: a film that actually changed their mind about something",
            "opinion: is watching in English with subtitles real learning or an excuse",
            "imagine: their own life as a film — genre, title, who plays them",
        ],
        "vocab": ["it's based on", "spoiler", "the plot", "I couldn't stop watching", "overrated"],
    },
    {
        "id": "books",
        "title": "Книги",
        "hint": "Читаешь ли, что и зачем.",
        "topic": "reading and books",
        "opener": "ask whether they are reading anything right now, honestly",
        "stages": [
            "get the facts: last book they finished or abandoned",
            "make it personal: a book from childhood they still remember",
            "opinion: are people who do not read missing something real",
            "imagine: they write one book — what is it about",
        ],
        "vocab": ["get into a book", "put it down", "it's set in", "a page-turner", "give up on"],
    },
    {
        "id": "games",
        "title": "Игры",
        "hint": "Во что играешь и что это даёт.",
        "topic": "video games and gaming",
        "opener": "ask what they are playing at the moment",
        "stages": [
            "get the facts: the game, how long they play, alone or with friends",
            "make it personal: a moment in a game they still talk about",
            "opinion: do games teach anything, or is that what gamers tell parents",
            "imagine: they design a game about their own city — what happens in it",
        ],
        "vocab": ["level up", "get hooked", "take a break", "team up with", "waste of time"],
    },
    {
        "id": "sport",
        "title": "Спорт",
        "hint": "Чем занимаешься или за кем следишь.",
        "topic": "sport — playing it or following it",
        "opener": "ask when they last moved seriously — gym, football, anything",
        "stages": [
            "get the facts: what they do or watch, how often",
            "make it personal: a time they were proud of their own body or effort",
            "opinion: should PE lessons be graded at school",
            "imagine: they must take up a brand-new sport tomorrow — which one",
        ],
        "vocab": ["work out", "be into", "give it a go", "keep fit", "be worn out"],
    },
    {
        "id": "photography",
        "title": "Фотография",
        "hint": "Что снимаешь и зачем вообще фотографировать.",
        "topic": "taking photos and keeping memories",
        "opener": "ask what the last photo on their phone is",
        "stages": [
            "get the facts: what they photograph, phone or camera",
            "make it personal: a photo that means a lot to them",
            "opinion: do we experience less because we film everything",
            "imagine: one photo to describe their whole year — what is in it",
        ],
        "vocab": ["take a shot", "in the background", "it reminds me of", "delete", "look through"],
    },
    {
        "id": "cooking",
        "title": "Еда и готовка",
        "hint": "Что любишь, что умеешь готовить.",
        "topic": "food and cooking",
        "opener": "ask what they had for breakfast and whether they made it themselves",
        "stages": [
            "get the facts: favourite dish, who cooks at home",
            "make it personal: a dish that tastes like their childhood",
            "opinion: is fast food really as bad as people say",
            "imagine: they open a small café — what is on the menu",
        ],
        "vocab": ["I'm starving", "home-made", "have a sweet tooth", "give it a try", "taste like"],
    },
    {
        "id": "pets",
        "title": "Животные",
        "hint": "Свои питомцы или те, кого хотелось бы.",
        "topic": "pets and animals",
        "opener": "ask whether there is an animal in their home right now",
        "stages": [
            "get the facts: what pet they have or want, name, habits",
            "make it personal: the funniest or worst thing the animal has done",
            "opinion: should people keep big animals in city flats",
            "imagine: they can talk to one animal for a day — which and what do they ask",
        ],
        "vocab": ["look after", "take it for a walk", "make a mess", "get used to", "keep an eye on"],
    },
    # --------------------------------------------------------- город и мир
    {
        "id": "hometown",
        "title": "Родной город",
        "hint": "Где живёшь, что там хорошо и что плохо.",
        "topic": "the student's home town or city",
        "opener": "ask what they would show a visitor first",
        "stages": [
            "get the facts: where they live, what is nearby, how long they have been there",
            "make it personal: their own favourite spot and why that one",
            "opinion: is it better to grow up in a big city or a small town",
            "imagine: they are mayor with a real budget — the first thing they fix",
        ],
        "vocab": ["grow up in", "get around", "there used to be", "within walking distance", "run down"],
    },
    {
        "id": "transport",
        "title": "Транспорт и пробки",
        "hint": "Как добираешься и что с этим не так.",
        "topic": "getting around the city",
        "opener": "ask how they got to school or work today",
        "stages": [
            "get the facts: how they travel, how long it takes",
            "make it personal: the worst journey they remember",
            "opinion: should city centres ban cars completely",
            "imagine: free transport for everyone — better or worse city",
        ],
        "vocab": ["get stuck in traffic", "catch a bus", "on foot", "rush hour", "run late"],
    },
    {
        "id": "travel_dream",
        "title": "Путешествие мечты",
        "hint": "Куда хочешь и что там будешь делать.",
        "topic": "a trip the student dreams about",
        "opener": "ask where they would fly tomorrow if a ticket appeared",
        "stages": [
            "get the facts: the place, why that place, what they know about it",
            "make it personal: what they would do there on day one",
            "opinion: is it better to see many countries or know one deeply",
            "imagine: one year of travel, one rule — no planes. Where do they go",
        ],
        "vocab": ["I've always wanted to", "book a ticket", "get around", "worth seeing", "pack light"],
    },
    {
        "id": "trip_gone_wrong",
        "title": "Поездка, которая пошла не так",
        "hint": "Опоздания, потери, приключения.",
        "topic": "a journey that did not go to plan",
        "opener": "ask about a trip where something went wrong",
        "stages": [
            "get the facts: where they were going, what happened",
            "make it personal: how they felt at that moment and what they did",
            "opinion: are the trips that go wrong the ones we remember best",
            "imagine: they write a survival guide for travellers — three rules",
        ],
        "vocab": ["miss the train", "end up", "sort it out", "in the middle of nowhere", "look back on"],
    },
    {
        "id": "city_vs_village",
        "title": "Город или деревня",
        "hint": "Где на самом деле лучше жить.",
        "topic": "city life versus life in the countryside",
        "opener": "ask where they would live if work and money were not a problem",
        "stages": [
            "get the facts: where they live now and what that place is like",
            "make it personal: their experience of the other one — dacha, village, big city",
            "opinion: what people really lose when they move to a big city",
            "imagine: remote work everywhere — do cities empty out",
        ],
        "vocab": ["fresh air", "be bored to death", "get away from", "the pace of life", "settle down"],
    },
    {
        "id": "weather",
        "title": "Погода и времена года",
        "hint": "Любимый сезон и как погода меняет настроение.",
        "topic": "weather and seasons",
        "opener": "ask what it is like outside their window right now",
        "stages": [
            "get the facts: the weather today, the season they like most",
            "make it personal: what they do differently in winter and in summer",
            "opinion: does weather really change how people feel, or is that an excuse",
            "imagine: they choose the climate of their city forever — what do they set",
        ],
        "vocab": ["it's freezing", "cheer up", "stay in", "look forward to", "make the most of"],
    },
    {
        "id": "holidays",
        "title": "Праздники",
        "hint": "Как отмечаешь и что для тебя главное.",
        "topic": "holidays and celebrations",
        "opener": "ask which holiday they actually look forward to",
        "stages": [
            "get the facts: how their family marks it, food, people",
            "make it personal: the best holiday they remember",
            "opinion: are expensive presents necessary at all",
            "imagine: they invent a new national holiday — what is it for",
        ],
        "vocab": ["get together", "celebrate", "look forward to", "give a present", "stay up late"],
    },
    # ------------------------------------------------- деньги, будущее, труд
    {
        "id": "future_job",
        "title": "Будущая профессия",
        "hint": "Кем видишь себя и почему.",
        "topic": "the job the student wants",
        "opener": "ask what they will be doing in five years, in their own words",
        "stages": [
            "get the facts: the job they aim at, what it involves",
            "make it personal: where the idea came from — a person, a film, a lesson",
            "opinion: money or interest — what should decide the choice",
            "imagine: that job disappears tomorrow — plan B",
        ],
        "vocab": ["end up as", "apply for", "make a living", "be good at", "it runs in the family"],
    },
    {
        "id": "money",
        "title": "Деньги и подработка",
        "hint": "Карманные деньги, подработка, на что тратишь.",
        "topic": "money, spending and earning at their age",
        "opener": "ask whether they have ever earned their own money",
        "stages": [
            "get the facts: where money comes from, what it goes on",
            "make it personal: something they saved up for",
            "opinion: should teenagers work while studying",
            "imagine: one million roubles, one condition — it cannot be saved",
        ],
        "vocab": ["save up for", "afford", "waste money on", "be worth it", "part-time job"],
    },
    {
        "id": "university",
        "title": "Университет и переезд",
        "hint": "Куда поступать и стоит ли уезжать.",
        "topic": "choosing a university and possibly moving away",
        "opener": "ask which university is at the top of their list",
        "stages": [
            "get the facts: where they plan to apply and what for",
            "make it personal: how they feel about leaving home, or about staying",
            "opinion: is a degree still necessary for a good life",
            "imagine: they design a first-year course everyone would actually attend",
        ],
        "vocab": ["apply to", "move out", "make up my mind", "on my own", "it's up to me"],
    },
    {
        "id": "volunteering",
        "title": "Волонтёрство",
        "hint": "Помощь другим — опыт или планы.",
        "topic": "volunteering and helping the community",
        "opener": "ask whether they have ever done anything for free for strangers",
        "stages": [
            "get the facts: what they did or what exists in their town",
            "make it personal: what would make them sign up tomorrow",
            "opinion: should schools require volunteering hours",
            "imagine: they start a project in their district — what problem do they pick",
        ],
        "vocab": ["take part in", "raise money", "get involved", "make a difference", "give up time"],
    },
    {
        "id": "failure",
        "title": "Неудача, которая научила",
        "hint": "Когда не получилось — и что из этого вышло.",
        "topic": "a failure that taught the student something",
        "opener": "ask about something they tried and did not manage",
        "stages": [
            "get the facts: what it was and what went wrong",
            "make it personal: what they did the next day",
            "opinion: do we really learn more from failure than from success",
            "imagine: advice to themselves one year ago, in one sentence",
        ],
        "vocab": ["mess up", "let someone down", "try again", "in the end", "it taught me"],
    },
    # ------------------------------------------------- технологии и общество
    {
        "id": "social_media",
        "title": "Соцсети",
        "hint": "Сколько времени там живёшь и что это даёт.",
        "topic": "social media in the student's life",
        "opener": "ask which app ate the most of their time yesterday",
        "stages": [
            "get the facts: apps they use, roughly how long",
            "make it personal: something good that happened to them through social media",
            "opinion: should there be an age limit for social networks",
            "imagine: one week with no feed at all — what changes",
        ],
        "vocab": ["scroll through", "post", "come across", "keep up with", "log out"],
    },
    {
        "id": "screen_time",
        "title": "Экранное время",
        "hint": "Телефон как привычка и как проблема.",
        "topic": "phone habits and screen time",
        "opener": "ask how many hours their phone reported this week",
        "stages": [
            "get the facts: the number, what it goes on",
            "make it personal: when they last left the phone at home on purpose",
            "opinion: are phones actually the problem, or just an easy thing to blame",
            "imagine: phones banned in schools countrywide — good or bad",
        ],
        "vocab": ["cut down on", "be addicted to", "on purpose", "waste time", "switch it off"],
    },
    {
        "id": "ai",
        "title": "Искусственный интеллект",
        "hint": "Помогает или пугает — и где граница.",
        "topic": "artificial intelligence in everyday life",
        "opener": "ask what they used AI for most recently, if ever",
        "stages": [
            "get the facts: how they use it, for study or fun",
            "make it personal: a moment it helped or clearly failed them",
            "opinion: is using AI for homework cheating",
            "imagine: one job AI must never take — and why that one",
        ],
        "vocab": ["rely on", "come up with", "instead of", "make mistakes", "it's up to us"],
    },
    {
        "id": "robots_jobs",
        "title": "Роботы и работа",
        "hint": "Кого заменят машины и что делать людям.",
        "topic": "automation and the future of work",
        "opener": "ask which job they think will disappear first",
        "stages": [
            "get the facts: jobs they see being automated already",
            "make it personal: is their own future job safe",
            "opinion: should governments slow this down or speed it up",
            "imagine: nobody has to work for money — what do people do all day",
        ],
        "vocab": ["take over", "replace", "look for a job", "retrain", "in the long run"],
    },
    {
        "id": "online_learning",
        "title": "Онлайн-обучение",
        "hint": "Экран против класса.",
        "topic": "studying online versus in a classroom",
        "opener": "ask whether they have ever studied fully online",
        "stages": [
            "get the facts: what they tried — courses, apps, remote school",
            "make it personal: where they concentrate better and why",
            "opinion: what a screen can never replace",
            "imagine: they design an online lesson nobody would skip",
        ],
        "vocab": ["log in", "focus on", "keep up", "get distracted", "face to face"],
    },
    {
        "id": "ecology",
        "title": "Экология",
        "hint": "Что реально можно делать, а что показуха.",
        "topic": "the environment and what people actually do about it",
        "opener": "ask whether anything gets sorted for recycling in their home",
        "stages": [
            "get the facts: what they or their family do — or do not",
            "make it personal: a habit they changed or refuse to change",
            "opinion: can one person's habits matter against factories",
            "imagine: one law for the whole country, ecology only — what do they pass",
        ],
        "vocab": ["sort rubbish", "cut down on", "throw away", "harm the planet", "make an effort"],
    },
    {
        "id": "space",
        "title": "Космос",
        "hint": "Полёты, планеты и зачем это всё.",
        "topic": "space exploration",
        "opener": "ask whether they would take a free ticket to orbit",
        "stages": [
            "get the facts: what they know or follow about space",
            "make it personal: would they actually go, and what would stop them",
            "opinion: is space money better spent on Earth",
            "imagine: first message from humans to another planet — what does it say",
        ],
        "vocab": ["take off", "explore", "be worth it", "far away", "come back"],
    },
    {
        "id": "languages",
        "title": "Языки",
        "hint": "Зачем учить и как это делать.",
        "topic": "learning foreign languages",
        "opener": "ask why they started English — the honest reason",
        "stages": [
            "get the facts: languages they study, how long, where",
            "make it personal: the hardest part for them specifically",
            "opinion: can you learn a language without ever visiting the country",
            "imagine: a chip that installs any language instantly — would they use it",
        ],
        "vocab": ["pick up", "get better at", "make progress", "struggle with", "practise"],
    },
    {
        "id": "english_hard",
        "title": "Что трудно в английском",
        "hint": "Честно про свои слабые места.",
        "topic": "what the student finds difficult in English",
        "opener": "ask what part of English annoys them most",
        "stages": [
            "get the facts: grammar, listening, speaking — what exactly",
            "make it personal: a situation where their English let them down",
            "opinion: is speaking without mistakes the right goal at all",
            "imagine: they teach English to a beginner — what do they start with",
        ],
        "vocab": ["mix up", "get confused", "on purpose", "make sense", "the more I practise"],
    },
    # ------------------------------------------------------- воображение
    {
        "id": "superpower",
        "title": "Суперсила",
        "hint": "Одна способность — и что ты с ней сделаешь.",
        "topic": "having one superpower",
        "opener": "ask which power they would take and refuse the boring ones",
        "stages": [
            "get the facts: the power they pick and the rules of it",
            "make it personal: the first thing they do that same day",
            "opinion: would people with powers make the world better or worse",
            "imagine: everyone gets the same power — what happens to society",
        ],
        "vocab": ["be able to", "come in handy", "get away with", "I'd probably", "on the other hand"],
    },
    {
        "id": "time_machine",
        "title": "Машина времени",
        "hint": "Прошлое или будущее — и зачем.",
        "topic": "travelling in time",
        "opener": "ask past or future, one trip only",
        "stages": [
            "get the facts: which direction, which year, why",
            "make it personal: a day of their own life they would revisit",
            "opinion: should anyone be allowed to change the past",
            "imagine: they meet themselves at thirty — first question they ask",
        ],
        "vocab": ["go back to", "find out", "warn someone", "regret", "it would be strange"],
    },
    {
        "id": "island",
        "title": "Необитаемый остров",
        "hint": "Три вещи, один человек, никакой связи.",
        "topic": "being stuck on a desert island",
        "opener": "ask for their three objects, and no phone allowed",
        "stages": [
            "get the facts: the three things and the reasons",
            "make it personal: who they would take with them and why that person",
            "opinion: could modern people survive without the internet at all",
            "imagine: a month there is over — what do they miss most on the way home",
        ],
        "vocab": ["survive", "run out of", "get bored", "come up with", "I'd take"],
    },
    {
        "id": "change_school",
        "title": "Что изменить в школе",
        "hint": "Полномочия есть, бюджет тоже.",
        "topic": "reforming school",
        "opener": "ask for the one rule they would delete today",
        "stages": [
            "get the facts: rules and subjects they would change",
            "make it personal: a lesson they would keep exactly as it is",
            "opinion: should students grade their teachers",
            "imagine: school of the future — what does a day look like",
        ],
        "vocab": ["get rid of", "instead of", "be allowed to", "it makes no sense", "in my opinion"],
    },
    {
        "id": "fears",
        "title": "Страхи",
        "hint": "Чего боишься и как с этим живёшь.",
        "topic": "fears, big and small",
        "opener": "ask about something that scares them that others find silly",
        "stages": [
            "get the facts: what it is, how long it has been there",
            "make it personal: a time they did something despite being afraid",
            "opinion: is fear useful or only in the way",
            "imagine: one fear deleted from everyone forever — which one",
        ],
        "vocab": ["be afraid of", "get over", "face it", "it freaks me out", "deal with"],
    },
    # ------------------------------------------------- разыгранные ситуации
    {
        "id": "rp_cafe",
        "title": "В кафе (сценка)",
        "hint": "Ты заказываешь, собеседник — за стойкой.",
        "topic": "ordering in a coffee shop",
        "role": "You also play a barista in a small coffee shop; the student is the "
                "customer who has just walked in. Stay in the scene, but keep your own "
                "personality and all format rules.",
        "opener": "greet them as a barista and ask what they would like",
        "stages": [
            "take the order: drink, size, to stay or take away",
            "add a small complication: the machine is slow, or their choice is sold out",
            "small talk while they wait: ask where they are heading today",
            "step out of the scene at the end and ask how ordering in English felt",
        ],
        "vocab": ["I'd like", "to take away", "anything else", "how much is it", "keep the change"],
    },
    {
        "id": "rp_directions",
        "title": "Спросить дорогу (сценка)",
        "hint": "Ты потерялся в чужом городе.",
        "topic": "asking for directions in an unfamiliar city",
        "role": "You also play a local passer-by in a foreign city; the student is a "
                "tourist who is lost. Stay in the scene, but keep your own personality "
                "and all format rules.",
        "opener": "react as a local who has just been stopped in the street",
        "stages": [
            "find out where they are trying to get to",
            "give directions with two or three turns and check they followed",
            "add a complication: the road is closed, suggest the bus instead",
            "step out of the scene and point out one phrase they will need again",
        ],
        "vocab": ["excuse me", "go straight on", "turn left at", "how far is it", "you can't miss it"],
    },
    {
        "id": "rp_interview",
        "title": "Собеседование (сценка)",
        "hint": "Летняя подработка, ты — кандидат.",
        "topic": "a job interview for a summer job",
        "role": "You also play a manager interviewing the student for a summer job in a "
                "cinema. Stay in the scene, but keep your own personality and all "
                "format rules.",
        "opener": "open the interview and ask them to say a little about themselves",
        "stages": [
            "basics: why this job, when they can work",
            "one real question: a time they dealt with a difficult person",
            "let them ask YOU a question about the job",
            "step out of the scene and say what was strong and what to fix",
        ],
        "vocab": ["apply for", "I'm good at", "get on with people", "deal with", "look forward to"],
    },
    {
        "id": "rp_hotel",
        "title": "Проблема в отеле (сценка)",
        "hint": "Номер не тот — надо решить вопрос.",
        "topic": "complaining politely at a hotel reception",
        "role": "You also play a hotel receptionist; the student has a problem with "
                "their room. Stay in the scene, but keep your own personality and all "
                "format rules.",
        "opener": "greet them at reception and ask how you can help",
        "stages": [
            "find out what is wrong with the room",
            "offer a solution they will not fully like",
            "agree on something together",
            "step out of the scene and show one politer way to complain",
        ],
        "vocab": ["there's a problem with", "could you", "I'm afraid", "sort it out", "I'd appreciate it"],
    },
    {
        "id": "rp_invite",
        "title": "Позвать друга (сценка)",
        "hint": "Уговори собеседника пойти с тобой.",
        "topic": "inviting a friend somewhere and agreeing on details",
        "role": "You also play a friend the student is inviting somewhere. Be slightly "
                "hard to persuade: busy, unsure, but winnable. Stay in the scene, but "
                "keep your own personality and all format rules.",
        "opener": "answer the phone as a friend who is a bit busy",
        "stages": [
            "let them explain what they are inviting you to",
            "raise an objection: time, money, or something else on that day",
            "settle the details together — when and where",
            "step out of the scene and name the phrase that persuaded you",
        ],
        "vocab": ["do you fancy", "how about", "I can't make it", "let's meet at", "sounds good"],
    },
]

# Ступень меняется не каждую реплику: на одном шаге нужно успеть поговорить,
# иначе беседа превращается в опрос со скоростью пулемёта.
TURNS_PER_STAGE = 2


def pick(recent: Sequence[str] | None = None) -> dict:
    """Тема, которой не было в недавних. Пустой список — любая.

    Когда сценарии кончились (48 занятий подряд — уже достижение), круг
    начинается заново, но пять последних всё равно исключаются: подряд одно и
    то же не выпадет никогда.
    """
    used = {str(r) for r in (recent or []) if r}
    pool = [s for s in SCENARIOS if s["id"] not in used]
    if not pool:
        keep = {str(r) for r in list(recent or [])[-5:] if r}
        pool = [s for s in SCENARIOS if s["id"] not in keep] or list(SCENARIOS)
    return random.choice(pool)


def by_id(sid: str | None) -> dict | None:
    """Сценарий по id. Неизвестный id — не ошибка: разговор просто идёт без
    плана, как раньше. Клиент мог остаться на старой версии сборки."""
    if not sid:
        return None
    for s in SCENARIOS:
        if s["id"] == sid:
            return s
    return None


def public(s: dict) -> dict:
    """То, что видит ученик: название и одна строка подсказки. План — не видит:
    в этом вся идея. Отдаём и id — клиент запомнит его в списке недавних."""
    return {"id": s["id"], "title": s["title"], "hint": s["hint"]}


def plan_block(s: dict, exchanges: int) -> str:
    """Скрытая повестка для системного промпта.

    `exchanges` — сколько обменов уже было (пар «ученик-ответ»). Из него
    считается ступень: СЕРВЕРОМ, арифметикой, без отдельного вызова модели.
    Спрашивать у LLM «на каком мы шаге» стоило бы второго запроса на каждую
    реплику — то есть удвоения расхода ради того, что и так известно.
    """
    stages = s["stages"]
    idx = min(len(stages) - 1, max(0, exchanges) // TURNS_PER_STAGE)
    lines = [
        "",
        "HIDDEN CONVERSATION PLAN — private. Never read it out, never mention that "
        "you have a plan, never announce the steps.",
        f"Topic of this conversation: {s['topic']}.",
    ]
    if s.get("role"):
        lines.append(f"Scene: {s['role']}")
    if exchanges == 0:
        lines.append(f"This is the very first turn: {s['opener']}.")
    lines += [
        f"You are on step {idx + 1} of {len(stages)}: {stages[idx]}.",
        "Move on to the next step only once the student has said something real "
        "about this one. Never do two steps in a single reply.",
        "Words worth using yourself so the student hears them in context: "
        + ", ".join(s["vocab"]) + ". Do not list them and do not teach them "
        "explicitly — just use them naturally.",
        "If the student takes the conversation somewhere else, GO WITH THEM. The "
        "plan serves the conversation, not the other way round.",
    ]
    return "\n".join(lines)
