/**
 * Запрос разбора ответа у бэкенда — POST /task_feedback.
 *
 * Ответ приходит потоком с «сердцебиением»: пока сервер распознаёт и считает,
 * он шлёт переводы строк, иначе прокси рвут молчащий запрос (замерено на serveo:
 * обрыв на 5.1 с тишины). Ведущие \n валидны для JSON — res.json() их проглотит.
 * Но статус уходит ДО результата, поэтому ошибка приезжает полем detail с кодом
 * 200 — проверять надо И код, И поле. res.json() тоже может упасть: страница
 * ошибки прокси это HTML, без try человек увидел бы «Unexpected token <».
 */
import { backendUnreachableMessage, httpErrorMessage } from '../backendError'
import { deviceId } from './device'
import type { TaskKind } from './tasks'

const BACKEND = (import.meta.env.VITE_BACKEND_URL ?? '').replace(/\/+$/, '')

export interface FeedbackCriterion {
  key: string
  name: string
  score: number
  max: number
  comment: string
}

export interface FeedbackError {
  quote: string
  correction: string
  explanation: string
  cat?: string
}

export interface TaskFeedback {
  summary: string
  score: number
  max: number
  errors: FeedbackError[]
  /** Только у монолога: три критерия ФИПИ */
  criteria?: FeedbackCriterion[]
}

export interface FeedbackResponse {
  transcript: string
  feedback: TaskFeedback
}

export async function requestTaskFeedback(
  blob: Blob,
  kind: TaskKind,
  payload: Record<string, unknown>,
  /** Для памяти об ошибках: какой вариант решался и сколько секунд говорил */
  meta?: { variantId?: string; durationSec?: number },
): Promise<FeedbackResponse> {
  const fd = new FormData()
  fd.append('audio', blob, 'answer.webm')
  fd.append('kind', kind)
  fd.append('payload', JSON.stringify(payload))
  if (meta?.variantId) fd.append('variant', meta.variantId)
  if (meta?.durationSec) fd.append('duration', String(meta.durationSec))

  let res: Response
  try {
    res = await fetch(`${BACKEND}/task_feedback`, {
      method: 'POST',
      body: fd,
      // По X-Device сервер копит профиль ошибок ученика. Не личные данные —
      // случайный uuid браузера, см. device.ts.
      headers: { 'X-Device': deviceId() },
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
  return data as FeedbackResponse
}
