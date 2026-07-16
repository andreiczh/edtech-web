// Данные тренажёра (заглушки). В реале это подтягивается из истории ответов ученика.

export type Cat = 'lex' | 'gram' | 'phon' | 'logic'

export const CAT_LABEL: Record<Cat, string> = {
  lex: 'Лексическая ошибка',
  gram: 'Грамматическая ошибка',
  phon: 'Фонетическая ошибка',
  logic: 'Логическая ошибка',
}

// Прошлые ошибки ученика: короткий заголовок + контекст + правильное решение.
export const PAST_ERRORS: {
  cat: Cat
  title: string
  context: string
  correct: string
}[] = [
  {
    cat: 'gram',
    title: 'Порядок слов в прямом вопросе',
    context: 'В задании 2 вопрос был построен как утверждение: «It costs how much?».',
    correct: 'Вспомогательный глагол — перед подлежащим: «How much does it cost?».',
  },
  {
    cat: 'lex',
    title: '«make a photo» вместо «take a photo»',
    context: 'В задании 3 при ответе прозвучало «make a photo».',
    correct: 'Верно «take a photo» — это устойчивое сочетание.',
  },
  {
    cat: 'phon',
    title: 'Ударение в «development»',
    context: 'В задании 1 ударение поставлено на первый слог.',
    correct: 'Ударение на второй слог: de-VE-lop-ment.',
  },
  {
    cat: 'logic',
    title: 'Вывод не связан с темой монолога',
    context: 'В задании 4 заключение уходило от основной мысли.',
    correct: 'Вернитесь к теме в выводе и добавьте связки: however, in addition, as a result.',
  },
]

// Типы заданий устной части — нарешивание по 5 подряд.
export const TASK_TYPES: { id: number; label: string }[] = [
  { id: 1, label: 'Задание 1 · Reading' },
  { id: 2, label: 'Задание 2 · Вопросы' },
  { id: 3, label: 'Задание 3 · Интервью' },
  { id: 4, label: 'Задание 4 · Монолог' },
]
