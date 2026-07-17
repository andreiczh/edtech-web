import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Состояния голосовой сессии.
 *  - idle       — покой, ждём нажатия
 *  - listening  — идёт запись микрофона (эквалайзер)
 *  - processing — аудио ушло на бэкенд, ждём ответ (STT→LLM→TTS)
 *  - speaking   — проигрываем голос ответа ИИ (волна)
 */
export type ConversationState = 'idle' | 'listening' | 'processing' | 'speaking'

export interface ConversationApi {
  state: ConversationState
  /** Клик по микрофону: старт записи / стоп-и-отправка / barge-in во время ответа. */
  toggle: () => void
  transcript: string // что распознали из речи пользователя
  reply: string // текст ответа ИИ
  error: string | null // текст последней ошибки (или null)
  latency: Record<string, number> | null // { stt, llm, tts, total }
}

// Адрес бэкенда. По умолчанию — та же машина (бэк на :8000). Меняется через
// VITE_BACKEND_URL в .env (напр. если бэк за туннелем).
const BACKEND = (import.meta.env.VITE_BACKEND_URL ?? 'http://localhost:8000').replace(/\/+$/, '')

export function useConversation(): ConversationApi {
  const [state, setState] = useState<ConversationState>('idle')
  const [transcript, setTranscript] = useState('')
  const [reply, setReply] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [latency, setLatency] = useState<Record<string, number> | null>(null)

  // Зеркало state в ref — чтобы toggle() читал актуальное состояние без пересоздания.
  const stateRef = useRef(state)
  stateRef.current = state

  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
  }, [])

  const stopAudio = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.onended = null
      audioRef.current.pause()
      audioRef.current.src = ''
      audioRef.current = null
    }
  }, [])

  // Отправка записанного аудио на бэкенд + проигрывание ответа.
  const sendAudio = useCallback(async (blob: Blob) => {
    setState('processing')
    setError(null)
    try {
      const fd = new FormData()
      fd.append('audio', blob, 'speech.webm')
      const res = await fetch(`${BACKEND}/talk`, { method: 'POST', body: fd })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`)

      setTranscript(data.user || '')
      setReply(data.ai || '')
      setLatency(data.latency ?? null)

      if (data.audio_b64) {
        const mime = data.audio_mime || 'audio/mpeg'
        const audio = new Audio(`data:${mime};base64,${data.audio_b64}`)
        audioRef.current = audio
        audio.onended = () => {
          audioRef.current = null
          // Не сбиваем состояние, если пользователь уже начал новую запись (barge-in).
          setState((s) => (s === 'speaking' ? 'idle' : s))
        }
        setState('speaking')
        try {
          await audio.play()
        } catch {
          // Автоплей заблокирован — не застреваем в speaking.
          setState((s) => (s === 'speaking' ? 'idle' : s))
        }
      } else {
        setState('idle')
      }
    } catch (e) {
      const msg = e instanceof TypeError
        ? 'Не достучались до бэкенда. Он запущен на :8000?'
        : e instanceof Error ? e.message : String(e)
      setError(msg)
      setState('idle')
    }
  }, [])

  const startRecording = useCallback(async () => {
    setError(null)
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Микрофон недоступен: нужен https или localhost.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const recorder = new MediaRecorder(stream)
      chunksRef.current = []
      recorder.ondataavailable = (e) => {
        if (e.data.size) chunksRef.current.push(e.data)
      }
      recorder.onstop = () => {
        stopStream()
        void sendAudio(new Blob(chunksRef.current, { type: 'audio/webm' }))
      }
      recorderRef.current = recorder
      recorder.start()
      setState('listening')
    } catch {
      setError('Нет доступа к микрофону — разреши его в браузере.')
      setState('idle')
    }
  }, [sendAudio, stopStream])

  const stopRecording = useCallback(() => {
    recorderRef.current?.stop() // → onstop → sendAudio()
    recorderRef.current = null
  }, [])

  const toggle = useCallback(() => {
    switch (stateRef.current) {
      case 'idle':
        void startRecording()
        break
      case 'listening':
        stopRecording()
        break
      case 'speaking':
        stopAudio() // barge-in: обрываем ответ ИИ и слушаем снова
        void startRecording()
        break
      case 'processing':
      default:
        break // игнорируем — кнопка и так disabled
    }
  }, [startRecording, stopRecording, stopAudio])

  // Очистка при размонтировании.
  useEffect(() => {
    return () => {
      stopAudio()
      stopStream()
      recorderRef.current?.stop()
    }
  }, [stopAudio, stopStream])

  return { state, toggle, transcript, reply, error, latency }
}
