import { useCallback, useEffect, useRef, useState } from 'react'

import { backendUnreachableMessage, httpErrorMessage } from './backendError'
import { identityId } from './auth/auth'

const DIALOG_KEY = 'pingo.dialog.v1'

function loadDialogHistory(): Array<{ role: 'user' | 'assistant'; content: string }> {
  try {
    const raw = sessionStorage.getItem(DIALOG_KEY)
    if (!raw) return []
    const items = JSON.parse(raw) as Array<{ role: string; content: string }>
    return items
      .filter((i) => (i.role === 'user' || i.role === 'assistant') && i.content)
      .slice(-10) as Array<{ role: 'user' | 'assistant'; content: string }>
  } catch {
    return []
  }
}

function saveDialogHistory(items: Array<{ role: 'user' | 'assistant'; content: string }>) {
  try {
    sessionStorage.setItem(DIALOG_KEY, JSON.stringify(items))
  } catch {
    /* приватный режим — история проживёт до размонтирования, и ладно */
  }
}

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
  /** Память диалога: последние 10 реплик (5 обменов). Живёт в sessionStorage —
      переживает переключение вкладок ПРИЛОЖЕНИЯ (Conversation → ЕГЭ → назад
      раньше стирало историю: компонент размонтировался, и тьютор всё забывал),
      но умирает вместе со вкладкой БРАУЗЕРА. Сервер историю не хранит
      намеренно: приватность + ноль состояния. */
  const historyRef = useRef<Array<{ role: 'user' | 'assistant'; content: string }>>(
    loadDialogHistory(),
  )

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
    audio.play().catch((e) => {
      // НЕ глотать молча: при заблокированном автоплее или сбое декодирования
      // студент сидит в тишине, а на экране бодрое «пауза до ответа: 1.3s».
      // Замер латентности при этом становится фикцией — показываем причину.
      setError(`Звук не проигрался (${e?.name ?? 'ошибка'}). Нажми на страницу и попробуй снова.`)
      audioRef.current = null
      playNext() // но не застреваем — идём к следующему чанку
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

      // Получили ли мы хоть что-то из потока. Решает, можно ли повторить запрос:
      // после первого чанка повтор проиграл бы часть ответа дважды.
      let gotData = false
      // Итог этой реплики — чтобы по done-чанку дописать её в историю диалога.
      let finalUser = ''
      let finalReply = ''

      const runOnce = async () => {
        const fd = new FormData()
        fd.append('audio', blob, 'speech.webm')
        // Память диалога: последние 10 реплик ЭТОЙ сессии уходят с запросом —
        // тьютор помнит, о чём шла речь. Хранится только в этой вкладке
        // (historyRef): сервер намеренно ничего не запоминает, закрыл вкладку —
        // диалог забыт. Дёшево по построению: ~10 коротких строк.
        fd.append('history', JSON.stringify(historyRef.current))
        const res = await fetch(`${BACKEND}/talk_stream`, {
          method: 'POST',
          body: fd,
          signal: ac.signal,
          // По X-Device сервер узнаёт аккаунт: и входной шлюз, и профиль ошибок.
          headers: { 'X-Device': identityId() },
        })
        if (!res.ok || !res.body) {
          let detail: string | null = null
          try {
            const j = await res.json()
            detail = j.detail ?? null
          } catch {
            /* тело не JSON (например, страница ошибки туннеля) — так и запомним */
          }
          throw new Error(httpErrorMessage(res.status, detail))
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
            gotData = true
            if (msg.user != null) setTranscript(msg.user)
            if (msg.text) {
              setReply((r) => (r ? `${r} ${msg.text}` : (msg.text as string)))
              if (msg.audio_b64) enqueueAudio(msg.audio_b64)
            }
            if (msg.done) {
              if (msg.reply) setReply(msg.reply)
              if (msg.latency) setLatency(msg.latency)
              if (msg.user) finalUser = msg.user
              if (msg.reply) finalReply = msg.reply
            }
          }
        }
        streamDoneRef.current = true
        // Реплика состоялась целиком — дописываем пару в историю и режем до
        // 10 последних записей (5 обменов): больше не нужно ни тьютору, ни
        // токенам. Ошибочные и пустые обмены в историю не попадают.
        if (finalUser && finalReply) {
          historyRef.current = [
            ...historyRef.current,
            { role: 'user' as const, content: finalUser },
            { role: 'assistant' as const, content: finalReply },
          ].slice(-10)
          saveDialogHistory(historyRef.current)
        }
        // Стрим кончился, а звука нет/уже доиграл — вернёмся в покой.
        if (!playingRef.current && queueRef.current.length === 0) {
          setState((s) => (s === 'processing' || s === 'speaking' ? 'idle' : s))
        }
      }

      try {
        try {
          await runOnce()
        } catch (e) {
          // Одна автоматическая повторная попытка на сетевой сбой. Замерено
          // 22.07.2026: соединение через бесплатный туннель рвётся на загрузке
          // аудио примерно раз в несколько попыток, а запись при этом уже
          // сделана — терять её и заставлять человека говорить заново незачем.
          // Повторяем ТОЛЬКО если из потока ещё ничего не пришло, иначе часть
          // ответа проиграется дважды.
          if (!(e instanceof TypeError) || gotData || ac.signal.aborted) throw e
          await runOnce()
        }
      } catch (e) {
        if (ac.signal.aborted) return // barge-in: состояние уже переведено в listening
        const msg =
          e instanceof TypeError
            ? backendUnreachableMessage()
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
