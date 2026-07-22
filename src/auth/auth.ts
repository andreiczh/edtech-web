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

export function logout() {
  cached = null
  try {
    localStorage.removeItem(KEY)
  } catch {
    /* ignore */
  }
}

/** Идентичность для памяти об ошибках: аккаунт, а без него — анонимный браузер. */
export function identityId(): string {
  return currentUser()?.id ?? deviceId()
}

/* ------------------------------------------------------------- Никнеймы */

const ADJECTIVES = [
  'Brave', 'Calm', 'Clever', 'Bright', 'Gentle', 'Happy', 'Kind', 'Lucky',
  'Mighty', 'Noble', 'Proud', 'Quick', 'Quiet', 'Royal', 'Shiny', 'Smart',
  'Sunny', 'Swift', 'Warm', 'Wild', 'Witty', 'Bold', 'Cosmic', 'Golden',
  'Silver', 'Velvet', 'Cozy', 'Breezy', 'Merry', 'Frosty',
]
const NOUNS = [
  'Falcon', 'Tiger', 'Panda', 'Dolphin', 'Comet', 'Maple', 'River', 'Meadow',
  'Pearl', 'Cloud', 'Ember', 'Breeze', 'Harbor', 'Willow', 'Aurora', 'Canyon',
  'Coral', 'Fox', 'Owl', 'Lark', 'Otter', 'Pine', 'Star', 'Moon', 'Wave',
  'Stone', 'Leaf', 'Spark', 'Drift', 'Bloom',
]

export function randomNickname(): string {
  const pick = (arr: string[]) => arr[Math.floor(Math.random() * arr.length)]
  const num = String(10 + Math.floor(Math.random() * 90))
  return `${pick(ADJECTIVES)}${pick(NOUNS)}${num}`
}

/* ------------------------------------------------------------------- API */

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
  if (!res.ok) throw new Error(httpErrorMessage(res.status, detail))
  return data as AuthUser
}

export async function register(nickname: string, password: string, exam: string): Promise<AuthUser> {
  const user = await post('/auth/register', { nickname, password, exam })
  saveUser(user)
  return user
}

export async function login(nickname: string, password: string): Promise<AuthUser> {
  const user = await post('/auth/login', { nickname, password })
  saveUser(user)
  return user
}
