import { useEffect, useRef, useState } from 'react'

/**
 * Обратный отсчёт в секундах. Возвращает оставшееся время.
 * Если autoAdvance=true — по достижении 0 вызывает onDone.
 * resetKey перезапускает отсчёт (смена фазы или шага).
 *
 * Переехал из src/ege/ при чистке старого экзаменационного флоу — это
 * единственное, что оттуда пригодилось новым экранам.
 */
export function useCountdown(
  seconds: number,
  onDone?: () => void,
  autoAdvance = false,
  resetKey?: unknown,
) {
  const [left, setLeft] = useState(seconds)
  const doneRef = useRef(onDone)
  doneRef.current = onDone

  useEffect(() => {
    setLeft(seconds)
    const start = Date.now()
    const id = setInterval(() => {
      const rem = seconds - Math.floor((Date.now() - start) / 1000)
      if (rem <= 0) {
        clearInterval(id)
        setLeft(0)
        if (autoAdvance) doneRef.current?.()
      } else {
        setLeft(rem)
      }
    }, 250)
    return () => clearInterval(id)
  }, [seconds, autoAdvance, resetKey])

  return left
}
