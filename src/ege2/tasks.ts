/**
 * Данные и типы заданий устного ЕГЭ по новому макету.
 *
 * Тайминги взяты из формулировок самих заданий (они же на скринах): 39 — полторы
 * минуты на чтение про себя и полторы на чтение вслух; 40 — по 20 секунд на
 * каждый из четырёх вопросов; 41 — по 40 секунд на каждый из пяти; 42 — две с
 * половиной минуты подготовки и три минуты речи.
 */

export type TaskId = 39 | 40 | 41 | 42
export type TaskKind = 'reading' | 'dialogue' | 'interview' | 'monologue'

export interface TaskDef {
  id: TaskId
  kind: TaskKind
  /** Подпись под номером в меню: reading / dialogue / interview / monologue */
  label: string
  /** Текст задания на вводном экране (фото 4, 5, 7) */
  brief: string
  /** Картинки задания. Для 40 — одна (объявление), для 42 — две (сравнение). */
  images?: string[]
  imageCaption?: string
  /** Текст для чтения вслух — только у 39 */
  readText?: string
  /** Реплики-подсказки по шагам: вопросы для 40 и 41 */
  steps?: string[]
  /** Секунды на подготовку до начала ответа */
  prepSeconds: number
  /** Секунды на ОДИН шаг ответа (для 40 и 41 — на каждый вопрос) */
  answerSeconds: number
  /**
   * Есть ли на бэкенде разбор именно этого задания. Сейчас честно только у 42:
   * эндпоинт /monologue считает по критериям ФИПИ 4+3+3. Для остальных разбор
   * не написан, и притворяться, что он есть, нельзя.
   */
  hasAiFeedback: boolean
}

/* Картинки — публичные заглушки из Unsplash: своих материалов в репозитории нет,
   а без изображения задания 40 и 42 бессмысленны. Заменить на свои. */
const IMG_DANCE =
  'https://images.unsplash.com/photo-1518611012118-696072aa579a?w=900&q=70&auto=format&fit=crop'
const IMG_KNIT =
  'https://images.unsplash.com/photo-1584992236310-6edddc08acff?w=700&q=70&auto=format&fit=crop'
const IMG_SKATE =
  'https://images.unsplash.com/photo-1520045892732-304bc3ac5d8e?w=700&q=70&auto=format&fit=crop'

export const TASKS: Record<TaskId, TaskDef> = {
  39: {
    id: 39,
    kind: 'reading',
    label: 'reading',
    brief:
      '№39: Imagine that you are preparing a project with your friend. You have found some ' +
      'interesting material for the presentation and you want to read this text to your friend. ' +
      'You have 1.5 minutes to read the text silently, then be ready to read it out aloud. ' +
      'You will not have more than 1.5 minutes to read it.',
    readText:
      'A tree is a tall plant with a trunk and branches made of wood. Trees can live for many ' +
      'years. The oldest tree ever discovered is approximately 5,000 years old. The four main ' +
      'parts of a tree are the roots, the trunk, the branches, and the leaves. The roots of a ' +
      'tree are usually under the ground. A single tree has many roots. The roots carry nutrients ' +
      'and water from the ground through the trunk and branches to the leaves of the tree. They ' +
      'can also breathe in air. The trunk is the main body of the tree. The trunk is covered with ' +
      'bark which protects it from damage. Branches grow from the trunk. They spread out so that ' +
      'the leaves can get more sunlight. The leaves of a tree are green most of the time, but they ' +
      'can come in many colours, shapes and sizes. The leaves take in sunlight and use water and ' +
      'food from the roots to make the tree grow, and to reproduce.',
    prepSeconds: 90,
    answerSeconds: 90,
    hasAiFeedback: false,
  },

  40: {
    id: 40,
    kind: 'dialogue',
    label: 'dialogue',
    brief:
      'Task 2. Study the advertisement.\nYou are considering taking dance lessons in a new dance ' +
      'school and now you’d like to get more information. In 1.5 minutes you are to ask four ' +
      'direct questions to find out about the following:\n1. course for beginners\n2. duration of ' +
      'one lesson\n3. cost of the course\n4. special clothes\nYou have 20 seconds to ask each question.',
    images: [IMG_DANCE],
    imageCaption: 'Choose a dance and come to learn!',
    steps: [
      'Question 1: course for beginners',
      'Question 2: duration of one lesson',
      'Question 3: cost of the course',
      'Question 4: special clothes',
    ],
    prepSeconds: 90,
    answerSeconds: 20,
    hasAiFeedback: false,
  },

  41: {
    id: 41,
    kind: 'interview',
    label: 'interview',
    brief:
      '№41: You are going to give an interview. You have to answer five questions. Give full ' +
      'answers to the questions (2-3 sentences). Remember that you have 40 seconds to answer ' +
      'each question.',
    steps: [
      'What is your favourite way to spend a weekend?',
      'How much time do you spend on sport every week?',
      'What kind of music do you enjoy and why?',
      'Do you prefer reading books or watching films? Why?',
      'What would you like to change about your school?',
    ],
    prepSeconds: 0,
    answerSeconds: 40,
    hasAiFeedback: false,
  },

  42: {
    id: 42,
    kind: 'monologue',
    label: 'monologue',
    brief:
      'Task 4. Imagine that you and your friend are doing a school project “The world of hobbies”. ' +
      'You have found some photos to illustrate it but for technical reasons you cannot send them ' +
      'now. Leave a voice message to your friend explaining your choice of the photos and sharing ' +
      'some ideas about the project. In 2.5 minutes be ready to:\n' +
      '• explain the choice of the illustrations for the project by briefly describing them and ' +
      'noting the differences;\n' +
      '• mention the advantages (1–2) of the two hobbies;\n' +
      '• mention the disadvantages (1–2) of the two hobbies;\n' +
      '• express your opinion on the subject of the project – which hobby presented in the ' +
      'pictures you would prefer and why.\n\n' +
      'You will speak for not more than 3 minutes (12–15 sentences). You have to talk continuously.',
    images: [IMG_KNIT, IMG_SKATE],
    prepSeconds: 150,
    answerSeconds: 180,
    hasAiFeedback: true,
  },
}

export const TASK_ORDER: TaskId[] = [39, 40, 41, 42]

/* ------------------------------------------------- Что ученик уже прорешал */

/**
 * Меню должно вести на задания, которых ученик ещё не решал. Базы у нас нет
 * (логирование сессий — незакрытый пункт роадмапа), поэтому пока помним в
 * localStorage. Это честная заглушка: она переживает перезагрузку страницы и
 * ничего не обещает про синхронизацию между устройствами.
 */
const DONE_KEY = 'pingo.solvedTasks.v1'

export function loadSolved(): TaskId[] {
  try {
    const raw = localStorage.getItem(DONE_KEY)
    if (!raw) return []
    return (JSON.parse(raw) as number[]).filter((n): n is TaskId =>
      TASK_ORDER.includes(n as TaskId),
    )
  } catch {
    return []
  }
}

export function markSolved(id: TaskId) {
  try {
    const next = Array.from(new Set([...loadSolved(), id]))
    localStorage.setItem(DONE_KEY, JSON.stringify(next))
  } catch {
    /* приватный режим браузера — молча живём без памяти */
  }
}

/** Первое нерешённое задание; если решены все — undefined. */
export function firstUnsolved(solved: TaskId[]): TaskId | undefined {
  return TASK_ORDER.find((id) => !solved.includes(id))
}
