/**
 * Личный кабинет: настройки и статистика аккаунта.
 *
 * Настройки живут в ДВУХ местах намеренно:
 *  - localStorage — мгновенное применение и работа без сети;
 *  - таблица settings на сервере — следуют за аккаунтом между устройствами,
 *    как и память об ошибках.
 * Правило слияния простое: при старте сервер ПОБЕЖДАЕТ локальную копию
 * (настройки принадлежат аккаунту, а не браузеру), дальше каждое изменение
 * применяется сразу локально и уезжает на сервер с задержкой-дебаунсом.
 */
import { useSyncExternalStore } from 'react'

import { currentUser, identityId } from '../auth/auth'

const BACKEND = (import.meta.env.VITE_BACKEND_URL ?? '').replace(/\/+$/, '')
const KEY = 'pingo.settings.v1'

/* -------------------------------------------------------------- Настройки */

export interface Settings {
  theme: 'dark' | 'light'
  volume: number // 0..1 — громкость голоса ИИ
  showText: boolean // показывать ли текст ответа в Conversation
}

export const DEFAULT_SETTINGS: Settings = { theme: 'dark', volume: 1, showText: true }

function normalize(raw: unknown): Settings {
  const r = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  return {
    theme: r.theme === 'light' ? 'light' : 'dark',
    volume:
      typeof r.volume === 'number' && r.volume >= 0 && r.volume <= 1
        ? Math.round(r.volume * 100) / 100
        : DEFAULT_SETTINGS.volume,
    showText: typeof r.showText === 'boolean' ? r.showText : DEFAULT_SETTINGS.showText,
  }
}

function load(): Settings {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? normalize(JSON.parse(raw)) : { ...DEFAULT_SETTINGS }
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

let current: Settings = load()
const listeners = new Set<() => void>()

function persistLocal() {
  try {
    localStorage.setItem(KEY, JSON.stringify(current))
  } catch {
    /* приватный режим: настройки проживут до перезагрузки */
  }
}

export function getSettings(): Settings {
  return current
}

/** Реактивная подписка для компонентов: тема, громкость и текст применяются
    сразу во всех местах, где их читают. */
export function useSettings(): Settings {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    () => current,
  )
}

let pushTimer: ReturnType<typeof setTimeout> | null = null

function pushRemoteDebounced() {
  // Дебаунс: ползунок громкости меняется десятки раз в секунду, а серверу
  // достаточно финального значения.
  if (pushTimer) clearTimeout(pushTimer)
  pushTimer = setTimeout(() => {
    pushTimer = null
    if (!currentUser()) return
    void fetch(`${BACKEND}/me/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Device': identityId() },
      body: JSON.stringify({
        theme: current.theme,
        volume: current.volume,
        show_text: current.showText,
      }),
    }).catch(() => {
      /* без сети настройки остаются локальными — не ошибка */
    })
  }, 800)
}

export function updateSettings(patch: Partial<Settings>) {
  current = normalize({ ...current, ...patch })
  persistLocal()
  listeners.forEach((cb) => cb())
  pushRemoteDebounced()
}

/** При выходе из аккаунта: настройки — часть аккаунта, следующий человек за
    этим компьютером должен начать с чистых, а не с чужих. */
export function resetSettings() {
  current = { ...DEFAULT_SETTINGS }
  try {
    localStorage.removeItem(KEY)
  } catch {
    /* ignore */
  }
  listeners.forEach((cb) => cb())
}

/** При старте и после входа: настройки аккаунта побеждают локальные. */
export async function syncSettingsFromServer(): Promise<void> {
  if (!currentUser()) return
  try {
    const res = await fetch(`${BACKEND}/me/settings`, {
      headers: { 'X-Device': identityId() },
    })
    if (!res.ok) return
    const data = (await res.json()) as { settings?: Record<string, unknown> }
    const s = data.settings ?? {}
    current = normalize({
      ...current,
      ...('theme' in s ? { theme: s.theme } : {}),
      ...('volume' in s ? { volume: s.volume } : {}),
      ...('show_text' in s ? { showText: s.show_text } : {}),
    })
    persistLocal()
    listeners.forEach((cb) => cb())
  } catch {
    /* сервер недоступен — работаем на локальной копии */
  }
}

/* ------------------------------------------------------------- Статистика */

export interface MeStats {
  level: {
    level: number
    name: string
    xp: number
    level_start: number
    next_at: number
    progress: number
  }
  streak: { days: number; active_today: boolean; freeze_available: boolean }
  week: Array<{ day: string; xp: number; actions: number }>
  totals: { replies: number; tasks: number; xp: number }
}

/** null — сервер недоступен или база лежит: экран покажет прочерки, а не
    выдуманные числа (принцип честности данных из StatsScreen). */
export async function fetchMeStats(): Promise<MeStats | null> {
  if (!currentUser()) return null
  try {
    const res = await fetch(`${BACKEND}/me/stats`, { headers: { 'X-Device': identityId() } })
    if (!res.ok) return null
    return (await res.json()) as MeStats
  } catch {
    return null
  }
}

/* -------------------------------------------------------------- Смена ника */

/** Меняет ник на сервере. Имя — только сгенерированное (то же правило, что при
    регистрации); занятое сервер отвергает 409 — генерируем другое и пробуем
    снова, человек коллизии не разруливает. Возвращает итоговое имя. */
export async function changeNickname(generate: () => string): Promise<string> {
  let lastError = 'Не получилось сменить ник — попробуй ещё раз.'
  for (let attempt = 0; attempt < 6; attempt++) {
    const nickname = generate()
    let res: Response
    try {
      res = await fetch(`${BACKEND}/me/nickname`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Device': identityId() },
        body: JSON.stringify({ nickname }),
      })
    } catch {
      throw new Error('Сервер недоступен — ник не изменился.')
    }
    if (res.ok) return nickname
    try {
      const data = (await res.json()) as { detail?: string }
      if (data.detail) lastError = data.detail
    } catch {
      /* тело не JSON — оставляем общую фразу */
    }
    if (res.status !== 409) break // повторяем только коллизию имени
  }
  throw new Error(lastError)
}
