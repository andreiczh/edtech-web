/**
 * Формат записи с микрофона и имя файла для отправки.
 *
 * iPhone (Safari и любой WebView на WebKit, включая MAX) не пишет webm — только
 * mp4/aac. Раньше запись всегда подписывалась как webm, и быстрый путь
 * распознавания отправлял mp4 под видом webm. Теперь формат берём у самого
 * MediaRecorder, а сервер вдобавок определяет его по содержимому файла.
 */

const CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']

export function pickRecorderMime(): string | undefined {
  if (typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') {
    return undefined
  }
  return CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m))
}

/** MediaRecorder с лучшим поддержанным форматом; не вышло — формат браузера. */
export function makeRecorder(stream: MediaStream): MediaRecorder {
  const mime = pickRecorderMime()
  if (mime) {
    try {
      return new MediaRecorder(stream, { mimeType: mime })
    } catch {
      /* ниже — формат по умолчанию */
    }
  }
  return new MediaRecorder(stream)
}

/** Тип готовой записи: что реально выдал MediaRecorder. */
export function recordedType(rec: MediaRecorder): string {
  return rec.mimeType || pickRecorderMime() || 'audio/webm'
}

export function audioFileName(base: string, blob: Blob): string {
  const t = blob.type
  const ext = t.includes('mp4')
    ? '.m4a'
    : t.includes('aac')
      ? '.aac'
      : t.includes('ogg')
        ? '.ogg'
        : t.includes('wav')
          ? '.wav'
          : t.includes('mpeg')
            ? '.mp3'
            : '.webm'
  return `${base}${ext}`
}
