/**
 * Банк заданий устного ЕГЭ и память о прогрессе.
 *
 * По просьбе пользователя каждый номер — это СЕРИЯ: клик по карточке №39 даёт не
 * один случайный текст, а сессию из пяти ранее не решённых вариантов этого типа
 * с общим фидбэком в конце. Поэтому у TaskDef появились variants[], а отметки
 * «пройдено» ставятся на вариант, не на номер.
 *
 * Тайминги взяты из формулировок самих заданий: 39 — полторы минуты на чтение;
 * 40 — по 20 секунд на каждый из четырёх вопросов; 41 — по 40 секунд на каждый
 * из пяти ответов; 42 — три минуты речи.
 */
import { mergeSolved, pickVariants } from './selection'

export type TaskId = 39 | 40 | 41 | 42
export type TaskKind = 'reading' | 'dialogue' | 'interview' | 'monologue'

export interface TaskVariant {
  id: string
  /** Текст задания на вводном экране. У 40 и 42 отличается между вариантами. */
  brief: string
  /** Текст для чтения вслух — только у 39 */
  readText?: string
  images?: string[]
  imageCaption?: string
  /** Шаги ответа: вопросы-подсказки у 40, вопросы интервью у 41 */
  steps?: string[]
  /** Что НА САМОМ ДЕЛЕ изображено на каждом фото задания 42.
      Разбор фотографий не видит, а по критериям ФИПИ обязан ловить фактические
      ошибки («на фото девочки», когда там мальчики) — без этих описаний он их
      не поймает и будет верить ученику на слово. */
  photoFacts?: string[]
}

export interface TaskDef {
  id: TaskId
  kind: TaskKind
  label: string
  prepSeconds: number
  /** Секунды на ОДИН шаг ответа (для 40 и 41 — на каждый вопрос) */
  answerSeconds: number
  /** Максимум баллов, который ставит разбор (ориентир по устной части ЕГЭ) */
  maxScore: number
  variants: TaskVariant[]
}

/* Картинки — публичные заглушки из Unsplash: своих материалов в репозитории нет,
   а без изображения задания 40 и 42 бессмысленны. Заменить на свои.

   Адреса ведут на НАШ бэкенд, а не на images.unsplash.com: из России без VPN
   Unsplash не открывается (29.07.2026: TLS-хендшейк виснет, ни одна картинка не
   грузится), и ученик получал бы задание «опиши две фотографии» без фотографий.
   Сервер тянет картинку сам и отдаёт со своего домена — см. /img в main.py. */
const IMG = {
  dance: '/img/photo-1518611012118-696072aa579a?w=900&q=70',
  pool: '/img/photo-1530549387789-4c1017266635?w=900&q=70',
  books: '/img/photo-1512820790803-83ca734da794?w=900&q=70',
  bike: '/img/photo-1485965120184-e220f721d03e?w=900&q=70',
  camera: '/img/photo-1502920917128-1aa500764cbd?w=900&q=70',
  knit: '/img/photo-1584992236310-6edddc08acff?w=700&q=70',
  skate: '/img/photo-1520045892732-304bc3ac5d8e?w=700&q=70',
  mountains: '/img/photo-1464822759023-fed622ff2c3b?w=700&q=70',
  beach: '/img/photo-1507525428034-b723cf961d3e?w=700&q=70',
  homeFood: '/img/photo-1546069901-ba9599a7e63c?w=700&q=70',
  restaurant: '/img/photo-1414235077428-338989a2e8c0?w=700&q=70',
  guitar: '/img/photo-1510915361894-db8b60106cb1?w=700&q=70',
  concert: '/img/photo-1470229722913-7c0e2dbbafd3?w=700&q=70',
  chess: '/img/photo-1529699211952-734e80c4d42b?w=700&q=70',
}

/* ------------------------------------------------------------------- №39 */

export const BRIEF_39 =
  '№39: Imagine that you are preparing a project with your friend. You have found some ' +
  'interesting material for the presentation and you want to read this text to your friend. ' +
  'You have 1.5 minutes to read the text silently, then be ready to read it out aloud. ' +
  'You will not have more than 1.5 minutes to read it.'

const READ_TEXTS: string[] = [
  // 1 — деревья (текст из макета)
  'A tree is a tall plant with a trunk and branches made of wood. Trees can live for many ' +
    'years. The oldest tree ever discovered is approximately 5,000 years old. The four main ' +
    'parts of a tree are the roots, the trunk, the branches, and the leaves. The roots of a ' +
    'tree are usually under the ground. A single tree has many roots. The roots carry ' +
    'nutrients and water from the ground through the trunk and branches to the leaves of the ' +
    'tree. They can also breathe in air. The trunk is the main body of the tree. The trunk is ' +
    'covered with bark which protects it from damage. Branches grow from the trunk. They ' +
    'spread out so that the leaves can get more sunlight. The leaves of a tree are green most ' +
    'of the time, but they can come in many colours, shapes and sizes. The leaves take in ' +
    'sunlight and use water and food from the roots to make the tree grow, and to reproduce.',
  // 2 — вода
  'Water is the most important substance on Earth. People, animals and plants cannot live ' +
    'without it. About seventy percent of our planet is covered with water, but most of it is ' +
    'salty. Only a small part is fresh water that people can drink. In everyday life we use ' +
    'water for cooking, washing and cleaning. Farmers need it to grow food, and factories use ' +
    'it to make almost everything, from paper to computers. Scientists say that many countries ' +
    'may have problems with clean water in the future. That is why it is important to save ' +
    'water today: turn off the tap when you brush your teeth, fix dripping taps at home and ' +
    'never throw rubbish into rivers and lakes.',
  // 3 — пчёлы
  'Honey bees are small insects, but they are very important for people and nature. They live ' +
    'in large families, and each bee has its own job. Worker bees fly from flower to flower ' +
    'and collect sweet nectar, which they later turn into honey. While they are doing this, ' +
    'they carry pollen from one plant to another and help fruits and vegetables grow. One bee ' +
    'family can visit millions of flowers in one summer. Bees even talk to each other with a ' +
    'special dance which shows where food can be found. Sadly, the number of bees is getting ' +
    'smaller because of chemicals and the loss of wild flowers, so many countries now protect ' +
    'these useful insects.',
  // 4 — Луна
  'The Moon is the closest space object to our planet and its only natural satellite. It ' +
    'looks bright in the night sky, but it does not make any light itself — it only reflects ' +
    'the light of the Sun. The Moon is about four hundred thousand kilometres away from the ' +
    'Earth. Its gravity moves huge masses of water in our oceans and makes tides. People have ' +
    'always dreamed about travelling there, and in 1969 the first astronauts finally walked on ' +
    'its surface. They brought back stones which scientists still study today. New missions to ' +
    'the Moon are being prepared now in several countries, and one day people may even build ' +
    'a station there.',
  // 5 — сон
  'Sleep is as important for our health as food and water. When we sleep, the body repairs ' +
    'itself and the brain sorts the information of the day. That is why students remember new ' +
    'material better after a good night’s rest. Doctors say that teenagers need about nine ' +
    'hours of sleep, but many of them sleep much less because of phones, computers and ' +
    'homework. If people do not sleep enough, they feel tired, make more mistakes and get ill ' +
    'more often. To sleep well, it is useful to go to bed at the same time every day and to ' +
    'put away all screens at least one hour before sleep.',
]

/* ------------------------------------------------------------------- №40 */

export function ad(intro: string, points: string[]): string {
  return (
    'Task 2. Study the advertisement.\n' +
    `${intro} In 1.5 minutes you are to ask four direct questions to find out about the ` +
    'following:\n' +
    points.map((p, i) => `${i + 1}. ${p}`).join('\n') +
    '\nYou have 20 seconds to ask each question.'
  )
}

const DIALOGUE_VARIANTS: Array<{
  intro: string
  caption: string
  image: string
  points: string[]
}> = [
  {
    intro: 'You are considering taking dance lessons in a new dance school and now you’d like to get more information.',
    caption: 'Choose a dance and come to learn!',
    image: IMG.dance,
    points: ['course for beginners', 'duration of one lesson', 'cost of the course', 'special clothes'],
  },
  {
    intro: 'You are thinking about visiting the new City Aqua Centre and now you’d like to get more information.',
    caption: 'City Aqua Centre — dive in!',
    image: IMG.pool,
    points: ['opening hours', 'price of one visit', 'individual lessons', 'things to bring'],
  },
  {
    intro: 'You are considering joining the Speak Easy language school and now you’d like to get more information.',
    caption: 'Speak Easy — languages for everyone!',
    image: IMG.books,
    points: ['languages available', 'size of the groups', 'length of the course', 'free trial lesson'],
  },
  {
    intro: 'You are considering renting a bike at GreenWheels and now you’d like to get more information.',
    caption: 'GreenWheels — see the city by bike!',
    image: IMG.bike,
    points: ['rental price per hour', 'helmet included', 'opening hours', 'discounts for students'],
  },
  {
    intro: 'You are considering booking a photo session at the Focus studio and now you’d like to get more information.',
    caption: 'Focus studio — your best photos!',
    image: IMG.camera,
    points: ['price of a photo session', 'duration of the session', 'printed photos', 'booking in advance'],
  },
]

/* ------------------------------------------------------------------- №41 */

export const BRIEF_41 =
  '№41: You are going to give an interview. You have to answer five questions. Give full ' +
  'answers to the questions (2-3 sentences). Remember that you have 40 seconds to answer ' +
  'each question.'

const INTERVIEW_SETS: string[][] = [
  [
    'What is your favourite way to spend a weekend?',
    'How much time do you spend on sport every week?',
    'What kind of music do you enjoy and why?',
    'Do you prefer reading books or watching films? Why?',
    'What would you like to change about your school?',
  ],
  [
    'Do you like travelling? Why or why not?',
    'What country would you like to visit one day and why?',
    'Do you prefer travelling with your family or with friends?',
    'What things do you usually take with you on a trip?',
    'Is it better to plan a trip carefully or to travel without any plan? Why?',
  ],
  [
    'What is your favourite dish and who usually cooks it?',
    'Do you help your family to cook at home? What can you cook yourself?',
    'Why do many people think fast food is bad for us?',
    'What Russian dishes would you recommend to a foreign friend?',
    'Is it important for a family to have dinner together? Why?',
  ],
  [
    'How much time do you usually spend on your phone every day?',
    'What do you use the Internet for most of all?',
    'Can a modern school work without computers? Why or why not?',
    'What are the good sides of social networks?',
    'What gadget would you like to get and why?',
  ],
  [
    'What is your favourite school subject and why?',
    'What profession would you like to choose in the future?',
    'Why do you learn English?',
    'Do you think exams are useful for students? Why?',
    'What advice can you give to younger students about studying?',
  ],
]

/* ------------------------------------------------------------------- №42 */

export function monologueBrief(topic: string, aspectA: string, aspectB: string): string {
  return (
    `Task 4. Imagine that you and your friend are doing a school project “${topic}”. You have ` +
    'found some photos to illustrate it but for technical reasons you cannot send them now. ' +
    'Leave a voice message to your friend explaining your choice of the photos and sharing ' +
    'some ideas about the project. In 2.5 minutes be ready to:\n' +
    '• explain the choice of the illustrations for the project by briefly describing them and noting the differences;\n' +
    `• mention the advantages (1–2) of ${aspectA};\n` +
    `• mention the disadvantages (1–2) of ${aspectB};\n` +
    '• express your opinion on the subject of the project – which option presented in the pictures you would prefer and why.\n\n' +
    'You will speak for not more than 3 minutes (12–15 sentences). You have to talk continuously.'
  )
}

/* facts — что НА САМОМ ДЕЛЕ на фото. Уезжает в разбор: он фотографий не видит,
   а по критериям обязан ловить фактические ошибки в описании. Заодно видно, из
   какого материала ученику предлагают строить ответ: у восьми из десяти
   заглушек в кадре нет людей, а формат задания просит описать, кто что делает.
   Когда появятся свои материалы, менять надо ОБА поля разом — картинку и факт. */
const MONOLOGUE_VARIANTS: Array<{
  topic: string
  a: string
  b: string
  images: string[]
  facts: string[]
}> = [
  {
    topic: 'The world of hobbies', a: 'the two hobbies', b: 'the two hobbies',
    images: [IMG.knit, IMG.skate],
    facts: [
      'a close-up of many balls of wool in different colours with two knitting needles lying on them; there are no people in the shot — the photo stands for knitting as a quiet hobby you can do alone at home',
      'a close-up of a skateboard balanced on the edge of a concrete ramp at sunset; only the rider’s legs and trainers are visible — the photo stands for skateboarding as an active outdoor hobby',
    ],
  },
  {
    topic: 'Ways of travelling', a: 'the two ways of spending holidays', b: 'the two ways of spending holidays',
    images: [IMG.mountains, IMG.beach],
    facts: [
      'a wide view of a green mountain valley with snow-capped peaks, pine forest in the foreground and clouds; there are no people in the shot',
      'an empty tropical beach at sunset: turquoise waves washing over pale sand, palm trees far away on the left; there are no people in the shot',
    ],
  },
  {
    topic: 'Eating at home and eating out', a: 'the two ways of eating', b: 'the two ways of eating',
    images: [IMG.homeFood, IMG.restaurant],
    facts: [
      'a bowl of home-made salad photographed from above: lettuce, tomatoes, cucumber, sweetcorn, red cabbage, a boiled egg and pieces of grilled meat; there are no people in the shot',
      'a restaurant table close up: a waiter’s hands are placing a small decorated dish in front of a guest, with wine glasses, a bread basket and other diners blurred in the background',
    ],
  },
  {
    topic: 'Music in our life', a: 'the two ways of enjoying music', b: 'the two ways of enjoying music',
    images: [IMG.guitar, IMG.concert],
    facts: [
      'a close-up of a person’s hands playing an acoustic guitar indoors in warm light; the face is not visible and it is impossible to tell who it is',
      'a large open-air concert at night: a dark crowd of people seen from behind, some with raised hands, facing a brightly lit stage with spotlights',
    ],
  },
  {
    topic: 'Sport and games in our life', a: 'the two activities', b: 'the two activities',
    images: [IMG.pool, IMG.chess],
    facts: [
      'a swimmer in a swimming cap doing the butterfly stroke in a blue indoor pool with lane ropes, water splashing around them',
      'a close-up of a wooden chessboard with the pieces set up: one dark pawn stands in front of a row of light pieces; there are no players in the shot',
    ],
  },
]

/* -------------------------------------------------------------- Сборка */

export const TASKS: Record<TaskId, TaskDef> = {
  39: {
    id: 39,
    kind: 'reading',
    label: 'reading',
    prepSeconds: 90,
    answerSeconds: 90,
    maxScore: 1,
    variants: READ_TEXTS.map((text, i) => ({
      id: `39-${i + 1}`,
      brief: BRIEF_39,
      readText: text,
    })),
  },
  40: {
    id: 40,
    kind: 'dialogue',
    label: 'dialogue',
    prepSeconds: 90,
    answerSeconds: 20,
    maxScore: 4,
    variants: DIALOGUE_VARIANTS.map((v, i) => ({
      id: `40-${i + 1}`,
      brief: ad(v.intro, v.points),
      images: [v.image],
      imageCaption: v.caption,
      steps: v.points.map((p, n) => `Question ${n + 1}: ${p}`),
    })),
  },
  41: {
    id: 41,
    kind: 'interview',
    label: 'interview',
    // 20 секунд собраться перед интервью — по ТЗ владельца от 23.07.2026
    prepSeconds: 20,
    answerSeconds: 40,
    maxScore: 5,
    variants: INTERVIEW_SETS.map((qs, i) => ({
      id: `41-${i + 1}`,
      brief: BRIEF_41,
      steps: qs,
    })),
  },
  42: {
    id: 42,
    kind: 'monologue',
    label: 'monologue',
    prepSeconds: 150,
    answerSeconds: 180,
    maxScore: 10,
    variants: MONOLOGUE_VARIANTS.map((v, i) => ({
      id: `42-${i + 1}`,
      brief: monologueBrief(v.topic, v.a, v.b),
      images: v.images,
      imageCaption: v.topic,
      photoFacts: v.facts,
    })),
  },
}

export const TASK_ORDER: TaskId[] = [39, 40, 41, 42]

/* ----------------------------------------- Банк заданий с сервера (админка)
 *
 * Встроенные варианты — аварийный минимум, который работает без базы. Сверху
 * подмешиваются варианты из банка на сервере (их добавляет админка): продукт
 * пополняется без правки кода и деплоя. Если сервер не ответил — молча живём
 * на встроенных, ученик разницы не видит.
 */

const BACKEND = (import.meta.env.VITE_BACKEND_URL ?? '').replace(/\/+$/, '')

const remoteVariants: Partial<Record<TaskId, TaskVariant[]>> = {}

export function getVariants(taskId: TaskId): TaskVariant[] {
  return [...TASKS[taskId].variants, ...(remoteVariants[taskId] ?? [])]
}

export async function syncRemoteTasks(): Promise<void> {
  try {
    const res = await fetch(`${BACKEND}/tasks`)
    if (!res.ok) return
    const data = (await res.json()) as {
      tasks?: Array<{ id: string; exam: string; task_no: number; payload: Record<string, unknown> }>
    }
    const next: Partial<Record<TaskId, TaskVariant[]>> = {}
    for (const t of data.tasks ?? []) {
      // Пока приложение — про ЕГЭ; ОГЭ-задания лежат в банке до своего раздела.
      if (t.exam !== 'ege') continue
      const no = t.task_no as TaskId
      if (!TASK_ORDER.includes(no)) continue
      const p = t.payload ?? {}
      const v: TaskVariant = {
        // Префикс x отличает серверные варианты от встроенных "39-1".
        id: `${no}-x${String(t.id).slice(0, 8)}`,
        brief: typeof p.brief === 'string' && p.brief ? p.brief : TASKS[no].variants[0].brief,
        readText: typeof p.readText === 'string' ? p.readText : undefined,
        images: Array.isArray(p.images) ? (p.images as string[]) : undefined,
        imageCaption: typeof p.imageCaption === 'string' ? p.imageCaption : undefined,
        steps: Array.isArray(p.steps) ? (p.steps as string[]) : undefined,
        photoFacts: Array.isArray(p.photoFacts) ? (p.photoFacts as string[]) : undefined,
      }
      ;(next[no] ??= []).push(v)
    }
    for (const id of TASK_ORDER) remoteVariants[id] = next[id] ?? []
  } catch {
    /* сервер молчит — встроенного банка достаточно */
  }
}

/**
 * Прогресс с сервера: какие варианты ученик сдавал на ЛЮБОМ устройстве.
 *
 * Источник правды — СЕРВЕР: у него есть время каждой сдачи, а значит честная
 * хронология. localStorage остаётся кэшем (мгновенная отрисовка без сети) и
 * буфером для того, что сервер ещё не знает: разбор мог не доехать из-за сети,
 * но вариант ученик уже решил, и повторно подсовывать его нечестно.
 *
 * Раньше здесь стоял цикл markVariantSolved по ответу сервера. Это ломало
 * порядок: каждый вызов двигает вариант в конец, а сервер отдавал их
 * произвольно — «самые давние» переставали быть давними, и добор в сессию
 * выдавал случайные повторы (03.08.2026).
 */
export async function syncServerProgress(identity: string): Promise<void> {
  try {
    const res = await fetch(`${BACKEND}/progress`, { headers: { 'X-Device': identity } })
    if (!res.ok) return
    const data = (await res.json()) as { solved?: string[] }
    const fromServer = (data.solved ?? []).filter((s) => typeof s === 'string')
    writeSolved(mergeSolved(fromServer, solvedVariantIds()))
  } catch {
    /* без сети останутся локальные отметки */
  }
}

export function variantById(taskId: TaskId, variantId: string): TaskVariant | undefined {
  return getVariants(taskId).find((v) => v.id === variantId)
}

/* ------------------------------------------- Память о пройденном (localStorage)
 *
 * КЭШ, а не источник правды: правда живёт на сервере (таблица results, где у
 * каждой сдачи есть время). Локальная копия нужна для двух вещей — мгновенно
 * отрисовать прогресс без сети и не потерять отметку, если разбор не доехал.
 * Порядок в массиве = хронология, самые давние первыми: на этом стоит добор
 * давно решённых вариантов в сессию (см. pickSession).
 */

const SOLVED_KEY = 'pingo.solvedVariants.v2'

export function solvedVariantIds(): string[] {
  try {
    const raw = localStorage.getItem(SOLVED_KEY)
    return raw ? (JSON.parse(raw) as string[]).filter((s) => typeof s === 'string') : []
  } catch {
    return []
  }
}

function writeSolved(ids: string[]) {
  try {
    localStorage.setItem(SOLVED_KEY, JSON.stringify(ids))
  } catch {
    /* приватный режим — живём без памяти */
  }
}

export function markVariantSolved(id: string) {
  // Повтор варианта двигает его в конец: он снова «самый свежий», и добор
  // в следующую сессию возьмёт его в последнюю очередь.
  writeSolved([...solvedVariantIds().filter((s) => s !== id), id])
}

export function taskProgress(id: TaskId): { done: number; total: number } {
  const solved = new Set(solvedVariantIds())
  const variants = getVariants(id)
  return { done: variants.filter((v) => solved.has(v.id)).length, total: variants.length }
}

/**
 * Сессия по номеру: сначала все нерешённые варианты (в порядке банка), а если их
 * меньше пяти — добор из решённых, начиная с самых давних. Так «пять ранее не
 * решённых» выполняется, пока банк не исчерпан, а после — честный повтор без
 * тупика «всё пройдено, нажимать нечего».
 */
export function pickSession(id: TaskId, want = 5): TaskVariant[] {
  const variants = getVariants(id)
  const byId = new Map(variants.map((v) => [v.id, v]))
  // Сам отбор — в selection.ts: там он без localStorage и покрыт тестами.
  const chosen = pickVariants(
    variants.map((v) => v.id),
    solvedVariantIds(),
    want,
  )
  return chosen.map((vid) => byId.get(vid)!).filter(Boolean)
}

/** DEMO: по одному варианту каждого типа — первый нерешённый (или самый давний). */
export function pickDemoItems(): Array<{ taskId: TaskId; variantId: string }> {
  return TASK_ORDER.map((taskId) => ({ taskId, variantId: pickSession(taskId, 1)[0].id }))
}

/* --------------------------------------- Последний разбор — для экрана STATS */

export interface StoredError {
  quote: string
  correction: string
  explanation: string
}

export interface StoredFeedback {
  when: string
  summary: string
  score: number
  max: number
  errors: StoredError[]
}

const FEEDBACK_KEY = 'pingo.lastFeedback.v1'

export function loadTaskFeedback(): Partial<Record<TaskId, StoredFeedback>> {
  try {
    const raw = localStorage.getItem(FEEDBACK_KEY)
    return raw ? (JSON.parse(raw) as Partial<Record<TaskId, StoredFeedback>>) : {}
  } catch {
    return {}
  }
}

export function saveTaskFeedback(id: TaskId, fb: StoredFeedback) {
  try {
    localStorage.setItem(FEEDBACK_KEY, JSON.stringify({ ...loadTaskFeedback(), [id]: fb }))
  } catch {
    /* приватный режим */
  }
}

/** Что уходит на бэкенд вместе с аудио — контекст, без которого разбор невозможен. */
export function feedbackPayload(task: TaskDef, v: TaskVariant): Record<string, unknown> {
  switch (task.kind) {
    case 'reading':
      return { referenceText: v.readText }
    case 'dialogue':
      return { ad: v.imageCaption ?? '', points: v.steps ?? [] }
    case 'interview':
      return { questions: v.steps ?? [] }
    case 'monologue':
      return { brief: v.brief, photoFacts: v.photoFacts ?? [] }
  }
}
