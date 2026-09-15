/**
 * Приветствие главной по времени суток.
 *
 * Список вынесен из HomeScreen, потому что от его самой длинной фразы
 * зависит минимальная длина ника (auth/nickname.ts): ник стоит под
 * приветствием и обязан быть длиннее его. Добавишь фразу длиннее —
 * тест ников (auth/nickname.test.ts) это заметит.
 *
 * Модуль без импортов: его гоняет тест в node.
 */

export const GREETINGS = ['Good night', 'Good morning', 'Good afternoon', 'Good evening']

export function greeting(now: Date = new Date()): string {
  const h = now.getHours()
  if (h < 5) return GREETINGS[0]
  if (h < 12) return GREETINGS[1]
  if (h < 18) return GREETINGS[2]
  return GREETINGS[3]
}
