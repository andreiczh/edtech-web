import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Состояния голосовой сессии.
 *  - idle       — покой, ждём нажатия
 *  - listening  — идёт запись микрофона (эквалайзер)
 *  - processing — аудио ушло на бэкенд, ждём первый звук ответа
 *  - speaking   — играем голос ответа ИИ (пофразно, потоком)
 */
export type ConversationState = 'idle' | 'listening' | 'processing' | 'speaking'

export interface ConversationApi {
  state: ConversationState
  /** Клик по микрофону: старт записи / стоп-и-отправка / barge-in во время ответа. */
  toggle: () => void
  transcript: string // что распознали из речи пользователя
  reply: string // текст ответа ИИ (наполняется по мере стрима)
  error: string | null // текст последней ошибки (или null)
  latency: Record<string, number> | null // { stt, first_audio, total }
}

// Адрес бэкенда. По умолчанию ПУСТОЙ = тот же origin, что отдал страницу
// (бэк раздаёт фронт / туннель). В dev проксируется на :8000 (vite.config).
const BACKEND = (import.meta.env.VITE_BACKEND_URL ?? '').replace(/\/+$/, '')

export function useConversation(): ConversationApi {
  const [state, setState] = useState<ConversationState>('idle')
  const [transcript, setTranscript] = useState('')
  const [reply, setReply] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [latency, setLatency] = useState<Record<string, number> | null>(null)

  const stateRef = useRef(state)
  stateRef.current = state

  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])

  // Потоковое проигрывание: очередь base64-аудио + текущий элемент.
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const queueRef = useRef<string[]>([])
  const playingRef = useRef(false)
  const streamDoneRef = useRef(false)
  const abortRef = useRef<AbortController | null>(null)

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
  }, [])

  // Проиграть следующий чанк из очереди; когда очередь пуста и стрим завершён — в покой.
  const playNext = useCallback(() => {
    const next = queueRef.current.shift()
    if (!next) {
      playingRef.current = false
      if (streamDoneRef.current) setState((s) => (s === 'speaking' ? 'idle' : s))
      return
    }
    playingRef.current = true
    const audio = new Audio(`data:audio/mpeg;base64,${next}`)
    audioRef.current = audio
    audio.onended = () => {
      audioRef.current = null
      playNext()
    }
    setState('speaking')
    audio.play().catch(() => {
      audioRef.current = null
      playNext() // автоплей заблокирован — не застреваем
    })
  }, [])

  const enqueueAudio = useCallback(
    (b64: string) => {
      queueRef.current.push(b64)
      if (!playingRef.current) playNext()
    },
    [playNext],
  )

  // Полностью гасим текущий ответ (barge-in / очистка): обрыв стрима, очередь, звук.
  const stopSpeaking = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    queueRef.current = []
    playingRef.current = false
    streamDoneRef.current = false
    if (audioRef.current) {
      audioRef.current.onended = null
      audioRef.current.pause()
      audioRef.current.src = ''
      audioRef.current = null
    }
  }, [])

  // Отправка записи + потребление NDJSON-потока ответа.
  const streamTalk = useCallback(
    async (blob: Blob) => {
      setState('processing')
      setError(null)
      setReply('')
      setTranscript('')
      setLatency(null)
      queueRef.current = []
      playingRef.current = false
      streamDoneRef.current = false
      const ac = new AbortController()
      abortRef.current = ac

      try {
        const fd = new FormData()
        fd.append('audio', blob, 'speech.webm')
        const res = await fetch(`${BACKEND}/talk_stream`, {
          method: 'POST',
          body: fd,
          signal: ac.signal,
        })
        if (!res.ok || !res.body) {
          let detail = `HTTP ${res.status}`
          try {
            const j = await res.json()
            detail = j.detail || detail
          } catch {
            /* тело не JSON — оставим статус */
          }
          throw new Error(detail)
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })
          let nl: number
          while ((nl = buf.indexOf('\n')) >= 0) {
            const line = buf.slice(0, nl).trim()
            buf = buf.slice(nl + 1)
            if (!line) continue
            let msg: {
              user?: string
              text?: string
              audio_b64?: string
              reply?: string
              error?: string
              done?: boolean
              latency?: Record<string, number>
            }
            try {
              msg = JSON.parse(line)
            } catch {
              continue
            }
            if (msg.error) throw new Error(msg.error)
            if (msg.user != null) setTranscript(msg.user)
            if (msg.text) {
              setReply((r) => (r ? `${r} ${msg.text}` : (msg.text as string)))
              if (msg.audio_b64) enqueueAudio(msg.audio_b64)
            }
            if (msg.done) {
              if (msg.reply) setReply(msg.reply)
              if (msg.latency) setLatency(msg.latency)
            }
          }
        }
        streamDoneRef.current = true
        // Стрим кончился, а звука нет/уже доиграл — вернёмся в покой.
        if (!playingRef.current && queueRef.current.length === 0) {
          setState((s) => (s === 'processing' || s === 'speaking' ? 'idle' : s))
        }
      } catch (e) {
        if (ac.signal.aborted) return // barge-in: состояние уже переведено в listening
        const msg =
          e instanceof TypeError
            ? 'Не достучались до бэкенда. Он запущен на :8000?'
            : e instanceof Error
              ? e.message
              : String(e)
        setError(msg)
        setState('idle')
      } finally {
        if (abortRef.current === ac) abortRef.current = null
      }
    },
    [enqueueAudio],
  )

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
        void streamTalk(new Blob(chunksRef.current, { type: 'audio/webm' }))
      }
      recorderRef.current = recorder
      recorder.start()
      setState('listening')
    } catch {
      setError('Нет доступа к микрофону — разреши его в браузере.')
      setState('idle')
    }
  }, [stopStream, streamTalk])

  const stopRecording = useCallback(() => {
    recorderRef.current?.stop() // → onstop → streamTalk()
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
        stopSpeaking() // barge-in: обрываем ответ ИИ и слушаем снова
        void startRecording()
        break
      case 'processing':
      default:
        break // игнорируем — кнопка disabled
    }
  }, [startRecording, stopRecording, stopSpeaking])

  // Очистка при размонтировании.
  useEffect(() => {
    return () => {
      stopSpeaking()
      stopStream()
      recorderRef.current?.stop()
    }
  }, [stopSpeaking, stopStream])

  return { state, toggle, transcript, reply, error, latency }
}
