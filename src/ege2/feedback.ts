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
import type { DisputeContext, DisputeDraft, DisputeShot } from './dispute'
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
  /** Честная оговорка о точности балла — приходит с сервера, показывается под
      баллом. Держать текст на сервере, а не во фронте: цифры в нём меняются
      вместе с замером, и расходиться этим двум местам нельзя. */
  accuracy_note?: string
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
 * «Не согласен» — заполненная жалоба в копилку на сервере.
 *
 * Вместе с жалобой уходят улика (расшифровка ответа или спорные реплики) и
 * обстановка (текст задания, соседние реплики, снимок разбора): это
 * ЕДИНСТВЕННЫЙ случай, когда речь ученика сохраняется, и происходит он по
 * явному нажатию — человек сам отдаёт свой ответ на пересмотр, о чём форма
 * прямо предупреждает. Из таких жалоб складывается калибровочный набор,
 * который делает проверку точнее для всех.
 *
 * Ошибку возвращаем ТЕКСТОМ, а не флагом: сервер проверяет полноту жалобы
 * сам, и его «напиши, что ты сказал на самом деле» человеку надо показать —
 * иначе форма молча не отправляется и выглядит сломанной.
 */
/**
 * Техническая обстановка — то, что ученик не наберёт руками и не должен.
 *
 * «Не работает микрофон» без модели браузера и ширины экрана невозможно ни
 * воспроизвести, ни сгруппировать: половина таких жалоб окажется про Safari на
 * старом айфоне, и узнать это можно только отсюда. Личных данных здесь нет —
 * то же самое видит любой сайт, который человек открывает.
 */
function clientInfo(): Record<string, unknown> {
  try {
    return {
      ua: navigator.userAgent.slice(0, 240),
      screen: `${window.innerWidth}x${window.innerHeight}@${window.devicePixelRatio || 1}`,
      lang: navigator.language,
      online: navigator.onLine,
      theme: document.documentElement.getAttribute('data-theme') ?? '',
      at: new Date().toISOString(),
    }
  } catch {
    return {}
  }
}

export async function sendDispute(
  ctx: DisputeContext,
  draft: DisputeDraft,
  /** Снимок экрана — уже сжатый браузером, см. ege2/screenshot.ts. */
  shot?: DisputeShot | null,
): Promise<{ ok: boolean; error?: string }> {
  const body = {
    shot: shot ?? null,
    kind: ctx.kind,
    target: ctx.target,
    target_key: ctx.targetKey ?? '',
    target_label: ctx.targetLabel ?? '',
    reason: draft.reason,
    comment: draft.comment,
    said: draft.said,
    claim_score: draft.claimScore ?? -1,
    score: ctx.score ?? 0,
    max: ctx.max ?? 0,
    variant: ctx.variant ?? '',
    persona: getSettings().persona,
    transcript: ctx.transcript ?? '',
    feedback: ctx.feedback ?? null,
    context: { ...(ctx.context ?? {}), client: clientInfo() },
  }
  let res: Response
  try {
    res = await fetch(`${BACKEND}/task_dispute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Device': identityId() },
      body: JSON.stringify(body),
    })
  } catch {
    return { ok: false, error: backendUnreachableMessage() }
  }
  if (res.ok) return { ok: true }
  let detail: string | null = null
  try {
    const data = (await res.json()) as { detail?: unknown }
    detail = data?.detail ? String(data.detail) : null
  } catch {
    /* текст подставит httpErrorMessage по коду */
  }
  return { ok: false, error: httpErrorMessage(res.status, detail) }
}

export interface WeakWord {
  word: string
  p_norm: number
  ord: number
}

/**
 * Слова, которые звук подтвердил слабее всего, — «переслушай эти».
 *
 * Отдельным запросом, а не в разборе: замер идёт фоном и стоит на бесплатном
 * хостинге около 19 секунд, а балл ученик ждёт 2-6. Поэтому блок дорисовывается
 * позже, когда числа доедут; до тех пор экран выглядит как раньше.
 *
 * НА БАЛЛ НЕ ВЛИЯЕТ — это совет, а не оценка. Порог, отделяющий ошибку
 * произношения от акцента, ещё не выведен на живой речи, и пока его нет,
 * снимать за это баллы нельзя.
 */
export async function fetchWeakWords(variantId: string): Promise<WeakWord[]> {
  try {
    const res = await fetch(
      `${BACKEND}/pron/weakest?variant=${encodeURIComponent(variantId)}`,
      { headers: { 'X-Device': identityId() } },
    )
    if (!res.ok) return []
    const data = (await res.json()) as { words?: WeakWord[] }
    return data.words ?? []
  } catch {
    return []
  }
}
