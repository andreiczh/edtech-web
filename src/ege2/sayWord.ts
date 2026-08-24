/**
 * «А как это читается?» — озвучка слова из эталона задания 39.
 *
 * Зачем (21.08.2026, идея владельца). Разбор чтения показывает слово, которое
 * ученик прочитал не так, и на этом останавливается. Главный вопрос при этом
 * остаётся без ответа: а КАК надо? Прочитать транскрипцию умеют не все, да и
 * её у нас нет, — зато слово можно просто дать услышать.
 *
 * Почему кэш здесь ОБЯЗАТЕЛЕН, а не «оптимизация на потом»: кнопку жмут
 * подряд по многу раз — в этом весь смысл упражнения («послушал, повторил,
 * ещё раз»). Без кэша каждое нажатие — запрос к Mistral и трата квоты за то,
 * что уже лежит во вкладке. Ответ на POST браузер не кэширует сам (это его
 * правило для POST, а не наша недоработка), поэтому кэш — вот этот Map.
 *
 * Слово озвучивается НЕЙТРАЛЬНЫМ голосом, а не голосом персоны: это решает
 * сервер. Образец произношения не должен звучать раздражённо, даже если
 * ученик выбрал Гондона.
 */
import { identityId } from '../auth/auth'
import { getSettings } from '../account/me'
import { normalizeWord, speakable } from './speakable'

export { speakable } from './speakable'

const BACKEND = (import.meta.env.VITE_BACKEND_URL ?? '').replace(/\/+$/, '')

/** Столько разных слов держим во вкладке. Одно слово — 5–15 КБ, сорок штук
    это меньше половины мегабайта, а больше сорока за сессию не нажимают. */
const CACHE_LIMIT = 40

/** слово -> обещание ссылки на его звук. Обещание, а не готовая ссылка:
    двойное нажатие не должно превращаться в два запроса. */
const cache = new Map<string, Promise<string | null>>()

/** Звучит всегда что-то одно: новое нажатие обрывает предыдущее слово. */
let current: HTMLAudioElement | null = null

async function fetchWord(word: string, variant?: string): Promise<string | null> {
  try {
    const res = await fetch(`${BACKEND}/speak`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Device': identityId() },
      body: JSON.stringify({ text: word, mode: 'word', variant }),
    })
    if (!res.ok) return null
    const blob = await res.blob()
    if (!blob.size) return null
    return URL.createObjectURL(blob)
  } catch {
    return null
  }
}

/**
 * Проиграть слово. `true` — прозвучало, `false` — не вышло.
 *
 * Неудача НЕ кэшируется: сеть могла моргнуть, и второе нажатие обязано
 * попробовать снова. Кэшируется только то, что реально прозвучало.
 */
export async function sayWord(text: string, variant?: string): Promise<boolean> {
  const word = normalizeWord(text)
  if (!speakable(word)) return false

  let pending = cache.get(word)
  if (!pending) {
    pending = fetchWord(word, variant)
    cache.set(word, pending)
    if (cache.size > CACHE_LIMIT) {
      const oldest = cache.keys().next().value
      if (oldest !== undefined) {
        void cache.get(oldest)?.then((url) => url && URL.revokeObjectURL(url))
        cache.delete(oldest)
      }
    }
  }

  const url = await pending
  if (!url) {
    cache.delete(word)
    return false
  }

  current?.pause()
  const audio = new Audio(url)
  current = audio
  audio.volume = getSettings().volume
  return await new Promise<boolean>((resolve) => {
    // Молчащий плеер не должен оставить кнопку в вечном «звучит».
    const guard = window.setTimeout(() => resolve(true), 10_000)
    const done = (ok: boolean) => {
      window.clearTimeout(guard)
      if (current === audio) current = null
      resolve(ok)
    }
    audio.onended = () => done(true)
    audio.onerror = () => done(false)
    audio.play().catch(() => done(false))
  })
}
