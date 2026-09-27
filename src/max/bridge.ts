/**
 * MAX: запуск внутри мессенджера и доступ к MAX Bridge (window.WebApp).
 *
 * Мини-приложение MAX получает данные запуска в фрагменте адреса
 * (#WebAppData=...), а библиотека MAX Bridge раскладывает их в window.WebApp.
 * Библиотеку грузим только при запуске из MAX — в обычном браузере она не нужна.
 *
 * Флаг запуска запоминается в sessionStorage: приложение может сменить адрес,
 * а решение «мы в MAX» должно пережить это до конца сессии.
 */

export interface MaxUser {
  id?: number
  first_name?: string
}

export interface MaxWebApp {
  initData?: string
  initDataUnsafe?: { user?: MaxUser; start_param?: string }
  platform?: string
  version?: string
  ready?: () => void
  BackButton?: {
    show: () => void
    hide: () => void
    onClick: (cb: () => void) => void
    offClick: (cb: () => void) => void
  }
  HapticFeedback?: { impactOccurred: (style: string) => void }
  enableClosingConfirmation?: () => void
  disableClosingConfirmation?: () => void
  shareMaxContent?: (p: { text?: string; link?: string }) => void
}

declare global {
  interface Window {
    WebApp?: MaxWebApp
  }
}

const BRIDGE_SRC = 'https://st.max.ru/js/max-web-app.js'
const FLAG = 'gospeak.max.v1'
const LINK_KEY = 'gospeak.max.link'
/** Запас на случай, если sessionStorage недоступен (приватный режим). */
let memLink: string | null = null

/** Личная ссылка от бота (#mlogin=..., §6.50): забрать токен из адреса ДО первой
    отрисовки, убрать его из адреса (история, скриншоты) и пометить запуск как
    MAX — оболочка телефона и вход без регистрации. */
export function captureLinkLogin(): void {
  const m = /(?:^#|&)mlogin=([^&]+)/.exec(window.location.hash || '')
  if (!m) return
  let tok = m[1]
  try {
    tok = decodeURIComponent(tok)
  } catch {
    /* как есть */
  }
  memLink = tok
  try {
    sessionStorage.setItem(LINK_KEY, tok)
    sessionStorage.setItem(FLAG, '1')
  } catch {
    /* приватный режим — хватит памяти до перезагрузки */
  }
  try {
    window.history.replaceState(null, '', window.location.pathname + window.location.search)
  } catch {
    /* адрес не поменять — не страшно */
  }
}

/** Токен личной ссылки, если приложение открыли по ней и вход ещё не выполнен. */
export function pendingLinkToken(): string | null {
  try {
    return sessionStorage.getItem(LINK_KEY) || memLink
  } catch {
    return memLink
  }
}

export function clearLinkToken(): void {
  memLink = null
  try {
    sessionStorage.removeItem(LINK_KEY)
  } catch {
    /* ignore */
  }
}

/** Данные запуска из фрагмента адреса — есть сразу, без библиотеки. */
export function launchParamsFromHash(): string | null {
  const parts = (window.location.hash || '').replace(/^#/, '').split('&')
  for (const p of parts) {
    if (p.startsWith('WebAppData=')) {
      try {
        return decodeURIComponent(p.slice('WebAppData='.length))
      } catch {
        return p.slice('WebAppData='.length)
      }
    }
  }
  return null
}

/** Запущены ли мы из MAX. Синхронно — нужно для выбора первого экрана. */
export function isMaxLaunch(): boolean {
  if (memLink) return true
  if (launchParamsFromHash() || window.WebApp?.initData) {
    try {
      sessionStorage.setItem(FLAG, '1')
    } catch {
      /* приватный режим */
    }
    return true
  }
  try {
    return sessionStorage.getItem(FLAG) === '1'
  } catch {
    return false
  }
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname
  } catch {
    return ''
  }
}

/** Похоже ли, что нас открыли внутри MAX, ещё ДО загрузки библиотеки:
    данные запуска во фрагменте адреса (мобильный клиент), либо мы во фрейме
    (веб-версия MAX встраивает мини-приложение и данных в адрес не кладёт),
    либо пришли с max.ru. В обычном браузере — false, и библиотека не грузится. */
export function probablyInsideMax(): boolean {
  if (launchParamsFromHash()) return true
  try {
    if (window.self !== window.top) return true
  } catch {
    return true
  }
  return /(^|\.)max\.ru$/.test(hostOf(document.referrer))
}

/** Перед первой отрисовкой: если мы, вероятно, в MAX — дождаться MAX Bridge
    (не дольше 3,5 с), чтобы isMaxLaunch() увидел initData и приложение
    открылось как мини-приложение со входом по подписи, а не как сайт со
    входом по нику. Именно так выглядела веб-версия MAX 25.09.2026:
    «открывается как сторонний сайт». */
export async function bootMax(): Promise<void> {
  if (!probablyInsideMax()) return
  await loadMaxBridge()
  isMaxLaunch()
}

let loading: Promise<MaxWebApp | null> | null = null

/** Подгрузить MAX Bridge. Не загрузился за 3,5 с — работаем без него. */
export function loadMaxBridge(): Promise<MaxWebApp | null> {
  if (window.WebApp) return Promise.resolve(window.WebApp)
  if (loading) return loading
  loading = new Promise((resolve) => {
    let done = false
    const fin = () => {
      if (done) return
      done = true
      resolve(window.WebApp ?? null)
    }
    const s = document.createElement('script')
    s.src = BRIDGE_SRC
    s.onload = () => window.setTimeout(fin, 60)
    s.onerror = fin
    document.head.appendChild(s)
    window.setTimeout(fin, 3500)
  })
  return loading
}

/** Строка данных запуска для входа на сервере. */
export async function maxInitData(): Promise<string | null> {
  const w = await loadMaxBridge()
  try {
    w?.ready?.()
  } catch {
    /* необязательный вызов */
  }
  return w?.initData || launchParamsFromHash()
}

/** Имя из MAX — только для приветствия на экране; на сервере не хранится. */
export function maxFirstName(): string | null {
  return window.WebApp?.initDataUnsafe?.user?.first_name?.trim() || null
}
