/**
 * Что считается ОБРАЗЦОМ ПРОИЗНОШЕНИЯ, а что уже текстом.
 *
 * Зеркало серверных правил из `backend/speak_check.py`. Здесь они нужны не
 * для защиты — она серверная и настоящая, — а чтобы не рисовать кнопку
 * «послушать» там, где сервер заведомо откажет.
 *
 * Отдельным файлом, потому что он ЧИСТЫЙ: ни сети, ни localStorage, ни
 * `import.meta.env`. Тесты фронта гоняются обычным node (см. package.json),
 * и всё, что тянет Vite-окружение, в них не заходит.
 *
 * Потолки обязаны совпадать с серверными. Разъедутся — на экране появится
 * кнопка, которая всегда отвечает отказом, или пропадёт там, где работала бы.
 */

/** Столько знаков помещается в «medium-sized» с запасом. */
export const MAX_CHARS = 48
/** Ошибка чтения бывает не в одном слове («can not» вместо «can't»), но три
    слова — это уже фраза, а не образец произношения. */
export const MAX_TOKENS = 3

/** Типографские апострофы и тире — к обычным: «can’t» и «can't» это одно
    слово, и разойтись они не должны. */
export function normalizeWord(text: string): string {
  return (text ?? '')
    .replace(/[’‘ʼ´`]/g, "'")
    .replace(/[‐‑‒–—―]/g, '-')
    .trim()
    .toLowerCase()
}

/** Слова текста — ровно так же, как их считает сервер: дефис РАЗДЕЛЯЕТ слова,
    апостроф внутри слова его НЕ разделяет («can't» — одно слово, не два). */
export function wordsOf(text: string): string[] {
  const flat = normalizeWord(text).replace(/-/g, ' ')
  return (flat.match(/[a-z][a-z']*/g) ?? [])
    .map((w) => w.replace(/^'+|'+$/g, ''))
    .filter(Boolean)
}

/** Можно ли это озвучить как образец произношения. */
export function speakable(text: string): boolean {
  const s = normalizeWord(text)
  if (!s || s.length > MAX_CHARS) return false
  if (!/^[a-z\s'-]+$/.test(s)) return false
  const tokens = wordsOf(s)
  return tokens.length > 0 && tokens.length <= MAX_TOKENS
}
