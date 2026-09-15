/**
 * Аккаунты: никнейм + пароль, без почты и восстановления.
 *
 * Никнейм генерируется из двух английских слов (прилагательное + существительное)
 * с двумя цифрами на конце — цифры добавлены к макету намеренно: без них
 * комбинаций всего ~900 и «Change» быстро начал бы упираться в занятые имена.
 *
 * После входа id аккаунта становится идентичностью для памяти об ошибках
 * (identityId) — история следует за человеком между устройствами. Без входа
 * остаётся анонимный id браузера.
 */
import { backendUnreachableMessage, httpErrorMessage } from '../backendError'
import { deviceId } from '../ege2/device'
import { randomNickname } from './nickname'

const BACKEND = (import.meta.env.VITE_BACKEND_URL ?? '').replace(/\/+$/, '')
const KEY = 'pingo.auth.v1'

export interface AuthUser {
  id: string
  nickname: string
  exam: string
}

let cached: AuthUser | null | undefined

export function currentUser(): AuthUser | null {
  if (cached !== undefined) return cached
  try {
    const raw = localStorage.getItem(KEY)
    cached = raw ? (JSON.parse(raw) as AuthUser) : null
  } catch {
    cached = null
  }
  return cached
}

function saveUser(u: AuthUser) {
  cached = u
  try {
    localStorage.setItem(KEY, JSON.stringify(u))
  } catch {
    /* приватный режим: сессия проживёт до перезагрузки, и ладно */
  }
}

/** Ник сменился на сервере — обновляем локальную копию аккаунта. */
export function applyNickname(nickname: string) {
  const u = currentUser()
  if (u) saveUser({ ...u, nickname })
}

export function logout() {
  cached = null
  try {
    localStorage.removeItem(KEY)
    // История диалога — часть личной сессии: следующий человек за этим же
    // компьютером не должен унаследовать чужой разговор.
    sessionStorage.removeItem('pingo.dialog.v1')
  } catch {
    /* ignore */
  }
}

/** Идентичность для памяти об ошибках: аккаунт, а без него — анонимный браузер. */
export function identityId(): string {
  return currentUser()?.id ?? deviceId()
}

/* ------------------------------------------------------------- Никнеймы
 *
 * Генерация — в auth/nickname.ts: два слова без цифр и длиннее любого
 * приветствия главной (16.09.2026). Здесь только реэкспорт для прежних
 * импортов; занятые имена register() решает тихим повтором.
 */

export { randomNickname }

/* ------------------------------------------------------------------- API */

class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

async function post(path: string, body: unknown): Promise<AuthUser> {
  let res: Response
  try {
    res = await fetch(`${BACKEND}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new Error(backendUnreachableMessage())
  }
  let data: unknown = null
  try {
    data = await res.json()
  } catch {
    /* не-JSON разберёт httpErrorMessage */
  }
  const detail =
    data && typeof data === 'object' && 'detail' in data
      ? String((data as { detail: unknown }).detail)
      : null
  if (!res.ok) throw new ApiError(httpErrorMessage(res.status, detail), res.status)
  return data as AuthUser
}

export async function register(
  nickname: string,
  password: string,
  exam: string,
  /** Код доступа: регистрация только по приглашению (см. INVITE_CODES на сервере) */
  invite: string,
): Promise<AuthUser> {
  // Занятый ник (409) решаем сами: генерируем другой и пробуем снова — человек
  // ник не выбирает, значит и разруливать коллизию не его работа. Финальное имя
  // он видит на экране «запиши данные».
  let nick = nickname
  for (let attempt = 0; ; attempt++) {
    try {
      const user = await post('/auth/register', { nickname: nick, password, exam, invite })
      saveUser(user)
      return user
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && attempt < 6) {
        nick = randomNickname()
        continue
      }
      throw e
    }
  }
}

export async function login(nickname: string, password: string): Promise<AuthUser> {
  const user = await post('/auth/login', { nickname, password })
  saveUser(user)
  return user
}

/** Вход из мини-приложения MAX: личность подтверждает подпись мессенджера,
    ника с паролем и кода доступа нет. Ник новому аккаунту генерируется здесь
    же — сервер берёт первый свободный из предложенных. */
export async function loginMax(initData: string): Promise<{ user: AuthUser; created: boolean }> {
  const nicknames = Array.from({ length: 5 }, () => randomNickname())
  const data = (await post('/auth/max', { init_data: initData, nicknames })) as AuthUser & {
    created?: boolean
  }
  const user: AuthUser = { id: data.id, nickname: data.nickname, exam: data.exam }
  saveUser(user)
  return { user, created: data.created === true }
}
