/**
 * Запись с микрофона — одна на все экраны.
 *
 * Раньше эта логика была скопирована в двух местах (`useConversation.ts` и
 * `ege/MonologuePractice.tsx`), и любая правка делалась дважды либо забывалась.
 * Здесь она одна, и экраны заданий пользуются ею.
 *
 * Держим ссылку на MediaStream и глушим дорожки в `onstop`: без этого в браузере
 * остаётся гореть индикатор микрофона после конца задания, и человек справедливо
 * решает, что его пишут дальше.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

export type RecorderState = 'idle' | 'recording'

export function useRecorder() {
  const [state, setState] = useState<RecorderState>('idle')
  const [error, setError] = useState<string | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const resolveRef = useRef<((b: Blob) => void) | null>(null)

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
  }, [])

  const start = useCallback(async () => {
    setError(null)
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Микрофон недоступен: нужен https или localhost.')
      return false
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const rec = new MediaRecorder(stream)
      chunksRef.current = []
      rec.ondataavailable = (e) => {
        if (e.data.size) chunksRef.current.push(e.data)
      }
      rec.onstop = () => {
        stopStream()
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        resolveRef.current?.(blob)
        resolveRef.current = null
        setState('idle')
      }
      recorderRef.current = rec
      rec.start()
      setState('recording')
      return true
    } catch {
      setError('Нет доступа к микрофону — разреши его в браузере.')
      return false
    }
  }, [stopStream])

  /** Останавливает запись и отдаёт готовый blob. */
  const stop = useCallback(() => {
    return new Promise<Blob | null>((resolve) => {
      const rec = recorderRef.current
      if (!rec || rec.state === 'inactive') {
        resolve(null)
        return
      }
      resolveRef.current = (b) => resolve(b)
      rec.stop()
      recorderRef.current = null
    })
  }, [])

  // Ушли со страницы посреди записи — микрофон обязан погаснуть.
  useEffect(
    () => () => {
      try {
        recorderRef.current?.stop()
      } catch {
        /* уже остановлен */
      }
      stopStream()
    },
    [stopStream],
  )

  return { state, error, start, stop }
}
