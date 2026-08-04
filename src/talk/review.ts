/**
 * Разбор беседы — POST /talk_review.
 *
 * Один запрос на всю сессию, по явному нажатию ученика. История уходит та же,
 * что живёт во вкладке; на сервере она не сохраняется — в базу попадают только
 * ошибки, как и у заданий ЕГЭ.
 */
import { getSettings } from '../account/me'
import { backendUnreachableMessage, httpErrorMessage } from '../backendError'
import { identityId } from '../auth/auth'

const BACKEND = (import.meta.env.VITE_BACKEND_URL ?? '').replace(/\/+$/, '')

export interface ReviewMistake {
  /** Точные слова ученика — сервер сверяет их с расшифровкой и выдумки режет. */
  quote: string
  correction: string
  why: string
}

export interface TalkReview {
  summary: string
  mistakes: ReviewMistake[]
  good: string[]
  phrases: Array<{ en: string; ru: string }>
  /** Считает сервер, а не модель: числа модель путает. */
  stats: { turns: number; words: number }
}

export type DialogTurn = { role: 'user' | 'assistant'; content: string }

export async function requestTalkReview(history: DialogTurn[]): Promise<TalkReview> {
  let res: Response
  try {
    res = await fetch(`${BACKEND}/talk_review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Device': identityId() },
      body: JSON.stringify({ history, persona: getSettings().persona }),
    })
  } catch {
    throw new Error(backendUnreachableMessage())
  }
  let data: unknown = null
  let parsed = true
  try {
    data = await res.json()
  } catch {
    parsed = false
  }
  const detail =
    parsed && data && typeof data === 'object' && 'detail' in data
      ? String((data as { detail: unknown }).detail)
      : null
  if (!res.ok || !parsed || detail) throw new Error(httpErrorMessage(res.status, detail))
  return data as TalkReview
}
