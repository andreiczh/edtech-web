/**
 * Тема разговора: выбор, память о пройденном, смена.
 *
 * Тему выбирает СЕРВЕР (там же лежит скрытый план беседы), а клиент помнит,
 * какие темы у этого человека уже были, и присылает их списком. Так сделано по
 * той же причине, что и история диалога: серверу не нужно ни таблицы, ни
 * состояния, а память живёт ровно столько, сколько браузер.
 *
 * Две разные памяти, и путать их нельзя:
 *  - ТЕКУЩАЯ тема — sessionStorage: одна беседа = одна тема, закрыл вкладку —
 *    новый разговор с новой темы;
 *  - ПРОЙДЕННЫЕ темы — localStorage: переживают вкладки и дни, иначе ученик
 *    каждый вечер начинал бы с одних и тех же «выходных».
 */
import { identityId } from '../auth/auth'

const BACKEND = (import.meta.env.VITE_BACKEND_URL ?? '').replace(/\/+$/, '')

const CURRENT_KEY = 'pingo.topic.v1'
const SEEN_KEY = 'pingo.topics.seen.v1'
/** Сколько тем помним пройденными. Банк на сервере примерно такого же размера:
    список короче — начнутся повторы, длиннее — выбирать будет не из чего. */
const SEEN_LIMIT = 40

export interface Topic {
  id: string
  title: string
  hint: string
}

function readSeen(): string[] {
  try {
    const raw = localStorage.getItem(SEEN_KEY)
    const items = raw ? (JSON.parse(raw) as unknown) : []
    return Array.isArray(items) ? items.filter((i): i is string => typeof i === 'string') : []
  } catch {
    return []
  }
}

function noteSeen(id: string) {
  if (!id) return
  try {
    const next = [...readSeen().filter((i) => i !== id), id].slice(-SEEN_LIMIT)
    localStorage.setItem(SEEN_KEY, JSON.stringify(next))
  } catch {
    /* приватный режим — просто не запомним, повтор темы это не катастрофа */
  }
}

export function currentTopic(): Topic | null {
  try {
    const raw = sessionStorage.getItem(CURRENT_KEY)
    if (!raw) return null
    const t = JSON.parse(raw) as Topic
    return t && typeof t.id === 'string' && t.title ? t : null
  } catch {
    return null
  }
}

function saveCurrent(t: Topic | null) {
  try {
    if (t) sessionStorage.setItem(CURRENT_KEY, JSON.stringify(t))
    else sessionStorage.removeItem(CURRENT_KEY)
  } catch {
    /* см. выше */
  }
}

/**
 * Взять у сервера тему, которой ещё не было. Ошибка сети — не беда: вернём
 * null, и разговор пойдёт вообще без темы, ровно как до появления сценариев.
 * Экран из-за отсутствия темы блокировать нельзя.
 */
export async function fetchTopic(): Promise<Topic | null> {
  try {
    const recent = encodeURIComponent(readSeen().join(','))
    const res = await fetch(`${BACKEND}/talk_topic?recent=${recent}`, {
      headers: { 'X-Device': identityId() },
    })
    if (!res.ok) return null
    const t = (await res.json()) as Topic
    if (!t?.id) return null
    noteSeen(t.id)
    saveCurrent(t)
    return t
  } catch {
    return null
  }
}

/** Забыть текущую тему — следующий заход возьмёт новую. */
export function clearTopic() {
  saveCurrent(null)
}
