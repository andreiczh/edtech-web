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
 * Строго два английских слова, прилагательное + существительное, БЕЗ цифр
 * (требование владельца, 23.07.2026). Руками ник не вводится вовсе — только
 * генерация, поэтому занятые имена решаются не человеком, а тихим повтором
 * в register(). Списки расширены: без цифр комбинаций меньше, чем было.
 */

const ADJECTIVES = [
  'Brave', 'Calm', 'Clever', 'Bright', 'Gentle', 'Happy', 'Kind', 'Lucky',
  'Mighty', 'Noble', 'Proud', 'Quick', 'Quiet', 'Royal', 'Shiny', 'Smart',
  'Sunny', 'Swift', 'Warm', 'Wild', 'Witty', 'Bold', 'Cosmic', 'Golden',
  'Silver', 'Velvet', 'Cozy', 'Breezy', 'Merry', 'Frosty', 'Amber', 'Azure',
  'Coral', 'Crimson', 'Daring', 'Dreamy', 'Eager', 'Fluffy', 'Gleaming',
  'Humble', 'Jolly', 'Lively', 'Misty', 'Peachy', 'Rosy', 'Sleek', 'Tender',
  'Vivid', 'Zesty', 'Snowy',
]
const NOUNS = [
  'Falcon', 'Tiger', 'Panda', 'Dolphin', 'Comet', 'Maple', 'River', 'Meadow',
  'Pearl', 'Cloud', 'Ember', 'Breeze', 'Harbor', 'Willow', 'Aurora', 'Canyon',
  'Fox', 'Owl', 'Lark', 'Otter', 'Pine', 'Star', 'Moon', 'Wave', 'Stone',
  'Leaf', 'Spark', 'Drift', 'Bloom', 'Badger', 'Beacon', 'Cedar', 'Clover',
  'Coyote', 'Crane', 'Fern', 'Glacier', 'Heron', 'Lagoon', 'Lynx', 'Orchid',
  'Osprey', 'Puffin', 'Raven', 'Sequoia', 'Sparrow', 'Thistle', 'Tundra',
  'Walrus', 'Zephyr',
]

export function randomNickname(): string {
  const pick = (arr: string[]) => arr[Math.floor(Math.random() * arr.length)]
  return `${pick(ADJECTIVES)}${pick(NOUNS)}`
}

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

export async function register(nickname: string, password: string, exam: string): Promise<AuthUser> {
  // Занятый ник (409) решаем сами: генерируем другой и пробуем снова — человек
  // ник не выбирает, значит и разруливать коллизию не его работа. Финальное имя
  // он видит на экране «запиши данные».
  let nick = nickname
  for (let attempt = 0; ; attempt++) {
    try {
      const user = await post('/auth/register', { nickname: nick, password, exam })
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
