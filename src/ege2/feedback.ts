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
import { getSettings } from '../account/me'
import { backendUnreachableMessage, httpErrorMessage } from '../backendError'
import { identityId } from '../auth/auth'
import type { TaskKind } from './tasks'

const BACKEND = (import.meta.env.VITE_BACKEND_URL ?? '').replace(/\/+$/, '')

export interface FeedbackCriterion {
  key: string
  name: string
  score: number
  max: number
  comment: string
  /** Только у вопросов/ответов (№40, №41), только когда не засчитан. */
  quote?: string
  correction?: string
}

export interface FeedbackError {
  quote: string
  correction: string
  explanation: string
  cat?: string
}

/** Подача чтения (№39): ИЗМЕРЕНО по пословным таймкодам, не суждение модели.
    На балл не влияет — см. backend/delivery.py. Приходит, только когда замер
    включён на сервере (процессор есть). */
export interface Delivery {
  wpm: number
  pace: 'slow' | 'ok' | 'fast'
  seconds: number
  pauses: Array<{ after: string; sec: number }>
  pause_count: number
  finished: boolean
  comment: string
}

export interface TaskFeedback {
  summary: string
  score: number
  max: number
  errors: FeedbackError[]
  /** Только у монолога: три критерия ФИПИ */
  criteria?: FeedbackCriterion[]
  delivery?: Delivery
}

export interface FeedbackResponse {
  transcript: string
  feedback: TaskFeedback
}

export async function requestTaskFeedback(
  blob: Blob,
  kind: TaskKind,
  payload: Record<string, unknown>,
  /** Для памяти об ошибках: какой вариант решался и сколько секунд говорил.
      sessionDone — последний вариант серии: сервер добавит бонус XP за
      доведённую до конца сессию. */
  meta?: { variantId?: string; durationSec?: number; sessionDone?: boolean },
): Promise<FeedbackResponse> {
  const fd = new FormData()
  fd.append('audio', blob, 'answer.webm')
  fd.append('kind', kind)
  fd.append('payload', JSON.stringify(payload))
  if (meta?.variantId) fd.append('variant', meta.variantId)
  if (meta?.durationSec) fd.append('duration', String(meta.durationSec))
  if (meta?.sessionDone) fd.append('session_done', '1')
  // Собеседник: Гондон решает спорное против ученика, Терпеливый — в пользу.
  // Шкала ФИПИ у всех одна — меняются суждения в спорных местах и тон разбора.
  fd.append('persona', getSettings().persona)

  let res: Response
  try {
    res = await fetch(`${BACKEND}/task_feedback`, {
      method: 'POST',
      body: fd,
      // По X-Device сервер копит профиль ошибок ученика. Не личные данные —
      // случайный uuid браузера, см. device.ts.
      headers: { 'X-Device': identityId() },
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

/**
 * «Не согласен с оценкой» — жалоба в копилку на сервере.
 *
 * Вместе с жалобой уходит расшифровка ответа: это ЕДИНСТВЕННЫЙ случай, когда
 * транскрипт речи сохраняется, и происходит он по явному нажатию ученика —
 * человек сам отдаёт свой ответ на пересмотр. Из таких жалоб складывается
 * калибровочный набор, который делает проверку точнее для всех.
 */
export async function reportDispute(args: {
  kind: TaskKind
  variant?: string
  score: number
  max: number
  transcript: string
  feedback: TaskFeedback
}): Promise<boolean> {
  try {
    const res = await fetch(`${BACKEND}/task_dispute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Device': identityId() },
      body: JSON.stringify({ ...args, persona: getSettings().persona }),
    })
    return res.ok
  } catch {
    return false
  }
}
