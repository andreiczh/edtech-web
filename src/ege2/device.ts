/**
 * Анонимный идентификатор устройства — «кто этот ученик» до появления аккаунтов.
 *
 * По нему сервер копит профиль ошибок (заголовок X-Device). Никаких личных
 * данных в нём нет — случайный uuid, созданный при первом визите. Честное
 * ограничение: сменил браузер или почистил хранилище — для памяти это новый
 * ученик. При появлении аккаунтов id привяжется к аккаунту, история останется.
 */
const KEY = 'pingo.device.v1'

let cached: string | null = null

export function deviceId(): string {
  if (cached) return cached
  try {
    let v = localStorage.getItem(KEY)
    if (!v) {
      v = crypto.randomUUID()
      localStorage.setItem(KEY, v)
    }
    cached = v
    return v
  } catch {
    // Приватный режим: памяти о себе у ученика не будет, но всё работает.
    cached = 'anon'
    return cached
  }
}
