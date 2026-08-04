/**
 * Озвучка вопроса задания — POST /speak.
 *
 * Зачем (05.08.2026, замечание тестировщика). В устной части ЕГЭ вопросы
 * интервьюера ЗВУЧАТ: экзаменуемый слышит вопрос и отвечает на слух, текста
 * перед ним нет. Мы показывали вопрос на экране — и это меняло само задание,
 * потому что убирало аудирование, то есть половину его сложности.
 *
 * Ошибка синтеза не должна ронять экзамен: если озвучить не вышло, экран
 * ПОКАЖЕТ вопрос текстом. Лучше упрощённое задание, чем задание без вопроса.
 */
import { identityId } from '../auth/auth'
import { getSettings } from '../account/me'

const BACKEND = (import.meta.env.VITE_BACKEND_URL ?? '').replace(/\/+$/, '')

/** Проиграть текст голосом. Возвращает true, если вопрос действительно
    прозвучал до конца, и false — если не вышло и его надо показать. */
export async function askAloud(text: string, signal?: AbortSignal): Promise<boolean> {
  let blob: Blob
  try {
    const res = await fetch(`${BACKEND}/speak`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Device': identityId() },
      body: JSON.stringify({ text, persona: getSettings().persona }),
      signal,
    })
    if (!res.ok) return false
    blob = await res.blob()
    if (!blob.size) return false
  } catch {
    return false
  }

  const url = URL.createObjectURL(blob)
  try {
    return await new Promise<boolean>((resolve) => {
      const audio = new Audio(url)
      audio.volume = getSettings().volume
      // Экзамен не должен зависнуть на молчащем плеере: даже если событие
      // окончания не придёт, ответ начнётся по этому потолку.
      const guard = window.setTimeout(() => resolve(true), 30_000)
      const done = (ok: boolean) => {
        window.clearTimeout(guard)
        resolve(ok)
      }
      audio.onended = () => done(true)
      audio.onerror = () => done(false)
      signal?.addEventListener('abort', () => {
        audio.pause()
        done(true)
      })
      audio.play().catch(() => done(false))
    })
  } finally {
    URL.revokeObjectURL(url)
  }
}
