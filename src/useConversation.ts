import { useCallback, useEffect, useRef, useState } from 'react'

import { getSettings } from './account/me'
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
  /* Бесшовное проигрывание фраз (Web Audio).
   *
   * Ответ приезжает ПОФРАЗНО, отдельным mp3 на каждое предложение. Раньше каждый
   * кусок играл свой <audio>, а следующий создавался в onended — и между фразами
   * зияла тишина: замер показал ~200мс подкладки в начале каждого mp3 и ~870мс в
   * конце, то есть около СЕКУНДЫ мёртвого воздуха на каждом стыке, плюс время на
   * создание и декодирование нового элемента. Именно это слышалось как «робот
   * с паузами» — сам голос был ни при чём.
   *
   * Теперь куски декодируются в AudioBuffer и ставятся на таймлайн встык:
   * start(when, offset, duration) отрезает тишину по краям БЕЗ копирования
   * буфера, а `when` считается от конца предыдущей фразы. Обрезка живёт на
   * клиенте намеренно: на сервере это значило бы распаковывать и переупаковывать
   * mp3 на каждую фразу, а процессор на бесплатном Render — самый дефицитный
   * ресурс (см. backend/CLAUDE.md про перекодирование). */
  const ctxRef = useRef<AudioContext | null>(null)
  const nextStartRef = useRef(0)
  const sourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set())
  const decodeChainRef = useRef<Promise<void>>(Promise.resolve())
  const pendingRef = useRef(0)
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
  // Запасной путь: используется, если Web Audio в браузере недоступен.
  const playNext = useCallback(() => {
    const next = queueRef.current.shift()
    if (!next) {
      playingRef.current = false
      if (streamDoneRef.current) setState((s) => (s === 'speaking' ? 'idle' : s))
      return
    }
    playingRef.current = true
    const audio = new Audio(`data:audio/mpeg;base64,${next}`)
    // Громкость из настроек читается на каждом чанке: сдвинул ползунок —
    // уже следующая фраза звучит тише, без перезапуска разговора.
    audio.volume = getSettings().volume
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

  /** Границы собственно речи в буфере, в секундах. Всё, что тише порога по
      краям, — подкладка кодека, её и срезаем. */
  const speechBounds = useCallback((buf: AudioBuffer): [number, number] => {
    const d = buf.getChannelData(0)
    const thr = 0.005
    let a = 0
    let b = d.length - 1
    while (a < d.length && Math.abs(d[a]) <= thr) a++
    while (b > a && Math.abs(d[b]) <= thr) b--
    if (a >= b) return [0, buf.duration] // тишина целиком — не трогаем
    // по 30 мс воздуха с краёв, чтобы не срезать атаку первого звука
    const pad = 0.03 * buf.sampleRate
    return [
      Math.max(0, a - pad) / buf.sampleRate,
      Math.min(d.length, b + pad) / buf.sampleRate,
    ]
  }, [])

  const enqueueAudio = useCallback(
    (b64: string) => {
      const Ctor = window.AudioContext ?? (window as unknown as {
        webkitAudioContext?: typeof AudioContext
      }).webkitAudioContext
      if (!Ctor) {
        // Древний браузер — играем по-старому, с паузами, но играем.
        queueRef.current.push(b64)
        if (!playingRef.current) playNext()
        return
      }
      if (!ctxRef.current || ctxRef.current.state === 'closed') {
        ctxRef.current = new Ctor()
        nextStartRef.current = 0
      }
      const ctx = ctxRef.current
      void ctx.resume().catch(() => {})

      pendingRef.current += 1
      setState('speaking')

      // Декодируем строго по очереди: чанки приходят по порядку, а
      // decodeAudioData асинхронный и без цепочки переставил бы фразы местами.
      decodeChainRef.current = decodeChainRef.current.then(async () => {
        try {
          const bin = atob(b64)
          const bytes = new Uint8Array(bin.length)
          for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
          const buf = await ctx.decodeAudioData(bytes.buffer)

          const [from, to] = speechBounds(buf)
          const dur = Math.max(0, to - from)
          if (dur <= 0) return

          const src = ctx.createBufferSource()
          src.buffer = buf
          const gain = ctx.createGain()
          gain.gain.value = getSettings().volume
          src.connect(gain).connect(ctx.destination)

          // Встык к предыдущей фразе; 0.15с — естественный вдох между
          // предложениями, а не дыра от кодека.
          const when = Math.max(ctx.currentTime + 0.02, nextStartRef.current)
          src.start(when, from, dur)
          nextStartRef.current = when + dur + 0.15

          sourcesRef.current.add(src)
          src.onended = () => {
            sourcesRef.current.delete(src)
            pendingRef.current = Math.max(0, pendingRef.current - 1)
            if (pendingRef.current === 0 && streamDoneRef.current) {
              setState((s) => (s === 'speaking' ? 'idle' : s))
            }
          }
        } catch (e) {
          pendingRef.current = Math.max(0, pendingRef.current - 1)
          setError(
            `Звук не проигрался (${(e as Error)?.name ?? 'ошибка'}). ` +
              'Нажми на страницу и попробуй снова.',
          )
        }
      })
    },
    [playNext, speechBounds],
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
    // Запланированные наперёд фразы: без этого перебивание глохло бы не сразу —
    // уже поставленные на таймлайн куски продолжали бы звучать.
    for (const src of sourcesRef.current) {
      src.onended = null
      try {
        src.stop()
      } catch {
        /* ещё не стартовал — нечего останавливать */
      }
    }
    sourcesRef.current.clear()
    pendingRef.current = 0
    nextStartRef.current = 0
    decodeChainRef.current = Promise.resolve()
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
        // Собеседник: голос и (в будущем) характер. Читаем на каждый запрос,
        // а не при монтировании — сменил персону в настройках, и уже следующая
        // реплика звучит новым голосом, без перезахода в разговор.
        fd.append('persona', getSettings().persona)
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
        // pendingRef — счётчик недоигранных фраз на пути Web Audio, queue/playing
        // — на запасном; в покой уходим, только когда молчат оба.
        if (pendingRef.current === 0 && !playingRef.current && queueRef.current.length === 0) {
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
