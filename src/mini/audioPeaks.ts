/**
 * Волна записи для плеера разбора (макет 36: 58 белых штрихов).
 *
 * Считается из самой записи через WebAudio: файл декодируется в отсчёты, на
 * каждый штрих берётся среднеквадратичная громкость своего куска. Заодно
 * отсюда берётся длительность: у webm с MediaRecorder тег <audio> честно
 * отдаёт Infinity вместо длины (известная особенность Chrome), а декодер —
 * настоящие секунды.
 */
export interface Peaks {
  bars: number[]
  seconds: number
}

export async function audioPeaks(blob: Blob, count: number): Promise<Peaks | null> {
  const AC = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!AC) return null
  const ac = new AC()
  try {
    const buf = await ac.decodeAudioData(await blob.arrayBuffer())
    const data = buf.getChannelData(0)
    const step = Math.max(1, Math.floor(data.length / count))
    const rms: number[] = []
    for (let i = 0; i < count; i++) {
      let sum = 0
      const from = i * step
      const to = Math.min(data.length, from + step)
      for (let j = from; j < to; j++) sum += data[j] * data[j]
      rms.push(Math.sqrt(sum / Math.max(1, to - from)))
    }
    const top = Math.max(...rms, 1e-6)
    return { bars: rms.map((v) => Math.min(1, v / top)), seconds: buf.duration }
  } catch {
    return null
  } finally {
    void ac.close().catch(() => undefined)
  }
}
