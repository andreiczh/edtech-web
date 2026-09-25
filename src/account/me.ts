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
  theme: 'dark' | 'light' | 'auto'
  volume: number // 0..1 — громкость голоса ИИ
  showText: boolean // показывать ли текст ответа в Conversation
  /** Согласие хранить свои записи в корпусе (обучение и проверка точности).
      Отдельный флаг, а не часть общих условий: снять его можно в любой момент,
      и сервер перестаёт писать немедленно — он проверяет согласие при каждой
      записи, а не запоминает его. */
  corpusConsent: boolean
  /** id собеседника из каталога сервера (GET /personas). Здесь это просто
      строка: список персон принадлежит серверу, и фронт его не дублирует —
      иначе новая персона требовала бы пересборки фронта. */
  persona: string
}

export const DEFAULT_SETTINGS: Settings = {
  // Новый дизайн (26.08.2026) светлый по умолчанию — молочный фон из брифа.
  // Выбор в кабинете по-прежнему уважается и приезжает с сервера.
  theme: 'light',
  volume: 1,
  showText: true,
  corpusConsent: true,
  persona: 'tutor',
}

function normalize(raw: unknown): Settings {
  const r = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  return {
    theme:
      r.theme === 'light' || r.theme === 'dark' || r.theme === 'auto' ? r.theme : DEFAULT_SETTINGS.theme,
    volume:
      typeof r.volume === 'number' && r.volume >= 0 && r.volume <= 1
        ? Math.round(r.volume * 100) / 100
        : DEFAULT_SETTINGS.volume,
    showText: typeof r.showText === 'boolean' ? r.showText : DEFAULT_SETTINGS.showText,
    corpusConsent:
      typeof r.corpusConsent === 'boolean' ? r.corpusConsent : DEFAULT_SETTINGS.corpusConsent,
    persona:
      typeof r.persona === 'string' && r.persona ? r.persona : DEFAULT_SETTINGS.persona,
  }
}

/* ------------------------------------------------------ Каталог собеседников */

export interface PersonaQuit {
  title: string
  body: string
  stay: string
  leave: string
}

export interface Persona {
  id: string
  label: string
  description: string
  voice: string
  /** Цветовая семья фона: blue | green | red (контракт с CSS в index.css) */
  theme: string
  /** Текст подтверждения выхода — своими словами для каждого характера */
  quit: PersonaQuit
  /** Персона с матом: включается только через разовое подтверждение */
  adult?: boolean
  /** Что показать в этом подтверждении (приходит с сервера) */
  warning?: string
}

let personasCache: Persona[] | null = null
let personasInFlight: Promise<Persona[]> | null = null
const personaListeners = new Set<() => void>()

/** Список собеседников с сервера. Кэшируется на сессию: каталог меняется
    только вместе с деплоем. Пустой массив = сервер молчит, экран настроек
    тогда просто не покажет выбор, а разговор пойдёт на персоне по умолчанию. */
export async function fetchPersonas(): Promise<Persona[]> {
  if (personasCache) return personasCache
  // Запрос в полёте переиспользуем: хук вызывается из нескольких компонентов
  // сразу (фон приложения и диалог выхода), дёргать сервер трижды незачем.
  if (personasInFlight) return personasInFlight
  personasInFlight = (async () => {
    try {
      const res = await fetch(`${BACKEND}/personas`)
      if (!res.ok) return []
      const data = (await res.json()) as { personas?: Persona[] }
      personasCache = (data.personas ?? []).filter((p) => p && p.id && p.label)
      personaListeners.forEach((cb) => cb())
      return personasCache
    } catch {
      return []
    } finally {
      personasInFlight = null
    }
  })()
  return personasInFlight
}

/**
 * Выбранный собеседник целиком — из него берут и цвет фона, и текст выхода.
 * До ответа сервера возвращает null: вызывающий подставляет свои умолчания,
 * поэтому первый кадр не мигает пустотой.
 */
export function useCurrentPersona(): Persona | null {
  const settings = useSettings()
  const list = useSyncExternalStore(
    (cb) => {
      personaListeners.add(cb)
      // Первый же подписчик заводит загрузку каталога.
      void fetchPersonas()
      return () => personaListeners.delete(cb)
    },
    () => personasCache,
  )
  if (!list) return null
  return list.find((p) => p.id === settings.persona) ?? list[0] ?? null
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
        corpus_consent: current.corpusConsent,
        persona: current.persona,
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
    noteUnauthorized(res)
    if (!res.ok) return
    const data = (await res.json()) as { settings?: Record<string, unknown> }
    const s = data.settings ?? {}
    current = normalize({
      ...current,
      ...('theme' in s ? { theme: s.theme } : {}),
      ...('volume' in s ? { volume: s.volume } : {}),
      ...('show_text' in s ? { showText: s.show_text } : {}),
      ...('corpus_consent' in s ? { corpusConsent: s.corpus_consent } : {}),
      ...('persona' in s ? { persona: s.persona } : {}),
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
  streak: { days: number; active_today: boolean; freeze_available: boolean; best: number }
  week: Array<{ day: string; xp: number; actions: number }>
  today: string
  active_days: string[]
  totals: { replies: number; tasks: number; xp: number }
}

/** null — сервер недоступен или база лежит: экран покажет прочерки, а не
    выдуманные числа (принцип честности данных из StatsScreen). */
/** Сервер ответил 401: аккаунта с таким id нет (база переехала, аккаунт
    удалён). Держать человека в приложении с прочерками и без выхода нечестно —
    App выходит из аккаунта и показывает вход. Срабатывает один раз (§6.47). */
let unauthorized: (() => void) | null = null
export function onUnauthorized(fn: (() => void) | null) {
  unauthorized = fn
}
function noteUnauthorized(res: Response) {
  if (res.status === 401 && unauthorized) {
    const fn = unauthorized
    unauthorized = null
    fn()
  }
}

export async function fetchMeStats(): Promise<MeStats | null> {
  if (!currentUser()) return null
  try {
    const res = await fetch(`${BACKEND}/me/stats`, { headers: { 'X-Device': identityId() } })
    noteUnauthorized(res)
    if (!res.ok) return null
    return (await res.json()) as MeStats
  } catch {
    return null
  }
}

/* ------------------------------------------------------------- Аналитика */

export interface KindAnalytics {
  attempts: number
  avg_pct: number
  recent_pct: number
  trend: 'up' | 'down' | 'flat'
}

export interface MeAnalytics {
  kinds: Record<string, KindAnalytics>
  /** день, тип, процент; v/s/m — вариант и балл (пусто у старых записей) */
  history: Array<{ d: string; k: string; p: number; v?: string; s?: number; m?: number }>
  mistakes: {
    total: number
    by_cat: Array<{ cat: string; n: number; example: { quote: string; correction: string } | null }>
    repeats: Array<{ quote: string; correction: string; n: number }>
  }
}

/** null — сервер недоступен: экран покажет «нет связи», а не нули,
    которые читались бы как «ошибок нет, ты молодец». */
export async function fetchMeAnalytics(): Promise<MeAnalytics | null> {
  if (!currentUser()) return null
  try {
    const res = await fetch(`${BACKEND}/me/analytics`, { headers: { 'X-Device': identityId() } })
    noteUnauthorized(res)
    if (!res.ok) return null
    return (await res.json()) as MeAnalytics
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
