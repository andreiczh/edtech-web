// Логика прохождения устной части ЕГЭ по английскому (структура станции).
// Порядок экранов и тайминги — по реальному сценарию; контент — плейсхолдеры.

export type MaterialKind = 'text' | 'ad' | 'interview' | 'photos' | 'none'

export type Step =
  | { kind: 'registration' }
  | { kind: 'instruction' }
  | { kind: 'important' }
  | { kind: 'melody' }
  | { kind: 'prep'; task: number; seconds: number; material: MaterialKind }
  | { kind: 'ready'; task: number }
  | { kind: 'answer'; task: number; seconds: number; material: MaterialKind }
  | { kind: 'questions'; task: number; count: number; seconds: number; material: MaterialKind }
  | { kind: 'finish' }

// Полный сценарий: вступительные экраны + 4 задания.
export const STEPS: Step[] = [
  { kind: 'registration' },
  { kind: 'instruction' },
  { kind: 'important' },
  { kind: 'melody' },

  // Задание 1 — чтение текста вслух
  { kind: 'prep', task: 1, seconds: 90, material: 'text' },
  { kind: 'ready', task: 1 },
  { kind: 'answer', task: 1, seconds: 90, material: 'text' },

  // Задание 2 — диалог-расспрос по объявлению (5 вопросов)
  { kind: 'prep', task: 2, seconds: 90, material: 'ad' },
  { kind: 'ready', task: 2 },
  { kind: 'questions', task: 2, count: 5, seconds: 20, material: 'ad' },

  // Задание 3 — интервью (5 вопросов, без подготовки)
  { kind: 'ready', task: 3 },
  { kind: 'questions', task: 3, count: 5, seconds: 40, material: 'interview' },

  // Задание 4 — монолог по двум фотографиям
  { kind: 'prep', task: 4, seconds: 150, material: 'photos' },
  { kind: 'ready', task: 4 },
  { kind: 'answer', task: 4, seconds: 120, material: 'photos' },

  { kind: 'finish' },
]

export const TASK_TITLES: Record<number, string> = {
  1: 'Чтение текста вслух',
  2: 'Условный диалог-расспрос',
  3: 'Интервью',
  4: 'Монолог по фотографиям',
}

export function fmt(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}
