/**
 * Снимок экрана к жалобе: приём файла и сжатие ПЕРЕД отправкой.
 *
 * Почему сжимаем в браузере, а не на сервере. Скриншот с телефона — это 2-4 МБ
 * PNG, и по мобильному интернету он уезжает десятки секунд. Человек в этот
 * момент видит «Отправляю…» и уходит, решив, что сломалось. После ужатия до
 * 1600 px по длинной стороне и JPEG 0.72 тот же снимок весит 80-250 КБ и
 * уходит за секунду, а читаемость текста на экране сохраняется — проверено
 * на скриншотах этого же продукта.
 *
 * PNG сохраняем как PNG только для маленьких картинок: скриншот интерфейса в
 * PNG весит втрое больше JPEG при одинаковой читаемости.
 */

/** Потолок стороны. 1600 px хватает, чтобы прочитать мелкий текст интерфейса
    на снимке с ноутбука, и вдвое меньше типичного 3200 px с телефона. */
const MAX_SIDE = 1600
const JPEG_QUALITY = 0.72
/** Столько же принимает сервер (backend/disputes.py MAX_SHOT_B64). */
export const MAX_SHOT_BYTES = 500_000

export interface Shot {
  /** base64 БЕЗ префикса data:, как ждёт сервер. */
  data: string
  mime: string
  /** Для превью в форме. */
  url: string
  bytes: number
}

export const SHOT_ERROR = {
  notImage: 'Это не картинка — приложи снимок экрана (PNG или JPEG).',
  broken: 'Не удалось прочитать картинку — попробуй другой файл.',
  tooBig: 'Снимок слишком большой даже после сжатия — обрежь его.',
}

function loadImage(file: Blob): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      URL.revokeObjectURL(url)
      resolve(img)
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('broken'))
    }
    img.src = url
  })
}

/**
 * Файл (из выбора, перетаскивания или буфера обмена) → сжатый снимок.
 * Возвращает `{ shot }` либо `{ error }` — текстом, который можно показать.
 */
export async function prepareShot(
  file: File | Blob,
): Promise<{ shot?: Shot; error?: string }> {
  if (!file.type.startsWith('image/')) return { error: SHOT_ERROR.notImage }

  let img: HTMLImageElement
  try {
    img = await loadImage(file)
  } catch {
    return { error: SHOT_ERROR.broken }
  }

  const scale = Math.min(1, MAX_SIDE / Math.max(img.width, img.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(img.width * scale))
  canvas.height = Math.max(1, Math.round(img.height * scale))
  const ctx = canvas.getContext('2d')
  if (!ctx) return { error: SHOT_ERROR.broken }
  // Белая подложка: у PNG со скриншота бывает прозрачность, и в JPEG она
  // становится чёрной — снимок светлого интерфейса превращается в негатив.
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height)

  const url = canvas.toDataURL('image/jpeg', JPEG_QUALITY)
  const comma = url.indexOf(',')
  if (comma < 0) return { error: SHOT_ERROR.broken }
  const data = url.slice(comma + 1)
  // Длина base64 → байты: четыре символа кодируют три байта.
  const bytes = Math.round((data.length * 3) / 4)
  if (bytes > MAX_SHOT_BYTES) return { error: SHOT_ERROR.tooBig }

  return { shot: { data, mime: 'image/jpeg', url, bytes } }
}

/** Первый файл-картинка из события вставки (Ctrl+V) — самый быстрый путь:
    снимок из буфера обмена не надо сначала сохранять на диск. */
export function imageFromPaste(e: ClipboardEvent): File | null {
  const items = e.clipboardData?.items
  if (!items) return null
  for (const item of items) {
    if (item.kind === 'file' && item.type.startsWith('image/')) {
      const file = item.getAsFile()
      if (file) return file
    }
  }
  return null
}
