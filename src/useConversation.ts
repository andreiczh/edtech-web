import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Состояния голосовой сессии.
 *  - idle       — покой, ждём нажатия
 *  - listening  — пользователь говорит (эквалайзер)
 *  - processing — ИИ «думает» (короткая пауза)
 *  - speaking   — ИИ отвечает (волна)
 */
export type ConversationState = 'idle' | 'listening' | 'processing' | 'speaking'

// Длительности замоканы. Когда подключим реальный пайплайн (Pipecat/STT/LLM/TTS),
// переходами будут управлять события с бэкенда, а не таймеры.
const PROCESSING_MS = 900
const SPEAKING_MS = 3800

export function useConversation() {
  const [state, setState] = useState<ConversationState>('idle')
  const timers = useRef<ReturnType<typeof setTimeout>[]>([])

  const clearTimers = useCallback(() => {
    timers.current.forEach(clearTimeout)
    timers.current = []
  }, [])

  const later = useCallback((fn: () => void, ms: number) => {
    timers.current.push(setTimeout(fn, ms))
  }, [])

  // Симуляция ответа ИИ: думает → говорит → снова покой.
  const runAiReply = useCallback(() => {
    setState('processing')
    later(() => {
      setState('speaking')
      later(() => setState('idle'), SPEAKING_MS)
    }, PROCESSING_MS)
  }, [later])

  const toggle = useCallback(() => {
    clearTimers()
    setState((prev) => {
      switch (prev) {
        case 'idle':
          return 'listening'
        case 'listening':
          // Закончили говорить → ИИ отвечает.
          later(runAiReply, 0)
          return 'processing'
        case 'speaking':
          // Barge-in: перебиваем ИИ и снова слушаем.
          return 'listening'
        case 'processing':
        default:
          return prev
      }
    })
  }, [clearTimers, later, runAiReply])

  useEffect(() => clearTimers, [clearTimers])

  return { state, toggle }
}
