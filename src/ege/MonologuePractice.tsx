import { useCallback, useEffect, useRef, useState } from 'react'

import { backendUnreachableMessage } from '../backendError'

/**
 * Практика монолога (ЕГЭ Задание 4) с реальным ИИ-разбором.
 * Записал ответ → POST /monologue (STT→LLM) → структурный фидбэк по 3 критериям
 * ФИПИ + карточки ошибок. Фаза 1: batch, без стриминга.
 *
 * Здесь раньше стояло «замер показал, что STT длинного ответа быстрый — стриминг
 * не нужен». Замер был неверный: 82 с речи это 16.8-18.1 с распознавания, а не 7 с
 * на всё (docs/DECISIONS.md §3, опровержение от 22.07.2026). Распознавание кусками
 * во время записи снимает здесь 11-13 с и остаётся самой крупной незакрытой
 * оптимизацией.
 */

const BACKEND = (import.meta.env.VITE_BACKEND_URL ?? '').replace(/\/+$/, '')

type Cat = 'lex' | 'gram' | 'phon' | 'logic'
const CAT_LABEL: Record<Cat, string> = {
  lex: 'Лексическая ошибка',
  gram: 'Грамматическая ошибка',
  phon: 'Фонетическая ошибка',
  logic: 'Логическая ошибка',
}

interface Criterion {
  key: string
  name: string
  score: number
  max: number
  comment: string
}
interface MonoError {
  cat: Cat
  quote: string
  correction: string
  explanation: string
}
interface Feedback {
  summary: string
  criteria: Criterion[]
  errors: MonoError[]
}
interface MonoResult {
  transcript: string
  feedback: Feedback
  latency?: Record<string, number>
}

type Phase = 'intro' | 'recording' | 'analyzing' | 'done'

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

export function MonologuePractice({ onExit }: { onExit?: () => void }) {
  const [phase, setPhase] = useState<Phase>('intro')
  const [result, setResult] = useState<MonoResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [elapsed, setElapsed] = useState(0)

  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
  }, [])
  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const analyze = useCallback(async (blob: Blob) => {
    setPhase('analyzing')
    setError(null)
    try {
      const fd = new FormData()
      fd.append('audio', blob, 'monologue.webm')
      const res = await fetch(`${BACKEND}/monologue`, { method: 'POST', body: fd })
      // Ответ приходит потоком с «сердцебиением»: бэкенд шлёт переводы строк,
      // пока считает, иначе туннели рвут молчащий запрос (serveo — на 5.1с).
      // Ведущие переводы строк валидны для JSON, res.json() их проглатывает.
      // Но статус уходит ДО результата, поэтому ошибка приезжает полем detail
      // с кодом 200 — проверяем и код, и поле.
      const data = await res.json()
      if (!res.ok || data.detail) throw new Error(data.detail || `HTTP ${res.status}`)
      setResult(data as MonoResult)
      setPhase('done')
    } catch (e) {
      const msg =
        e instanceof TypeError
          ? backendUnreachableMessage()
          : e instanceof Error
            ? e.message
            : String(e)
      setError(msg)
      setPhase('intro')
    }
  }, [])

  const start = useCallback(async () => {
    setError(null)
    setResult(null)
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
        clearTimer()
        stopStream()
        void analyze(new Blob(chunksRef.current, { type: 'audio/webm' }))
      }
      recorderRef.current = recorder
      recorder.start()
      setElapsed(0)
      timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000)
      setPhase('recording')
    } catch {
      setError('Нет доступа к микрофону — разреши его в браузере.')
    }
  }, [analyze, clearTimer, stopStream])

  const stop = useCallback(() => {
    recorderRef.current?.stop() // → onstop → analyze()
    recorderRef.current = null
  }, [])

  useEffect(
    () => () => {
      clearTimer()
      stopStream()
      recorderRef.current?.stop()
    },
    [clearTimer, stopStream],
  )

  return (
    <div className="hub">
      <div className="hub__inner mono">
        <div className="mono__top">
          {onExit ? (
            <button type="button" className="ege__exit" onClick={onExit}>
              ← В тренажёр
            </button>
          ) : (
            <span />
          )}
          <span className="ege__variant">Задание 4 · Монолог</span>
        </div>

        {phase === 'intro' && (
          <div className="mono__center">
            <h2>Монолог по фотографиям</h2>
            <p className="mono__hint">
              Запиши устный монолог на английском (~1.5–2 минуты): сравни две картинки и объясни
              выбор — как в Задании 4. ИИ разберёт ответ по критериям ЕГЭ и покажет ошибки.
              <br />
              <small>(Пока без картинок-материалов — говори на свободную тему. Оценка произношения появится позже.)</small>
            </p>
            {error && <p className="dialog__err">{error}</p>}
            <button type="button" className="exam-btn exam-btn--hero" onClick={start}>
              🎤 Записать ответ
            </button>
          </div>
        )}

        {phase === 'recording' && (
          <div className="mono__center">
            <span className="mono__rec">
              <span className="mono__dot" /> Идёт запись
            </span>
            <span className="mono__time num">{fmt(elapsed)}</span>
            <p className="mono__hint">Говори свой монолог. Как закончишь — нажми «Завершить».</p>
            <button type="button" className="exam-btn exam-btn--hero" onClick={stop}>
              Завершить и разобрать
            </button>
          </div>
        )}

        {phase === 'analyzing' && (
          <div className="mono__center">
            <span className="mono__spinner" aria-hidden="true" />
            <h2>Проверяю ответ…</h2>
            <p className="mono__hint">Распознаю речь и разбираю по критериям. Обычно ~10 секунд.</p>
          </div>
        )}

        {phase === 'done' && result && <Report result={result} onAgain={start} />}
      </div>
    </div>
  )
}

function Report({ result, onAgain }: { result: MonoResult; onAgain: () => void }) {
  const criteria = result.feedback?.criteria ?? []
  const errors = result.feedback?.errors ?? []
  const total = criteria.reduce((a, c) => a + (c.score || 0), 0)
  const max = criteria.reduce((a, c) => a + (c.max || 0), 0)

  return (
    <div className="results">
      <div className="results__ai">
        <span className="ai-badge">ИИ</span>
        <p className="results__summary">{result.feedback?.summary || 'Разбор готов.'}</p>
      </div>

      <div className="results__score glass">
        <div className="score-total">
          {total} <span>/ {max} баллов</span>
        </div>
        <table className="score-table">
          <thead>
            <tr>
              <th>Критерий</th>
              <th>Балл</th>
            </tr>
          </thead>
          <tbody>
            {criteria.map((c) => (
              <tr key={c.key}>
                <td>{c.name}</td>
                <td className="num">
                  {c.score} / {c.max}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {criteria.some((c) => c.comment) && (
        <div className="results__errors">
          <h3>По критериям</h3>
          {criteria
            .filter((c) => c.comment)
            .map((c) => (
              <div className="errcard glass" key={c.key}>
                <div className="errcard__head">
                  <span className="errcard__task">{c.name}</span>
                </div>
                <p className="errcard__desc">{c.comment}</p>
              </div>
            ))}
        </div>
      )}

      {errors.length > 0 && (
        <div className="results__errors">
          <h3>Разбор ошибок</h3>
          {errors.map((e, idx) => (
            <div className="errcard glass" key={idx}>
              <div className="errcard__head">
                <span className={`errtag errtag--${e.cat}`}>{CAT_LABEL[e.cat] ?? e.cat}</span>
              </div>
              {e.quote && (
                <p className="errcard__desc">
                  «{e.quote}» → <b>{e.correction}</b>
                </p>
              )}
              <p className="errcard__fb">
                <span className="ai-badge ai-badge--sm">ИИ</span>
                {e.explanation}
              </p>
            </div>
          ))}
        </div>
      )}

      {result.transcript && (
        <details className="mono__transcript">
          <summary>Показать расшифровку</summary>
          <p>{result.transcript}</p>
        </details>
      )}

      <div className="mono__center">
        <button type="button" className="exam-btn exam-btn--hero" onClick={onAgain}>
          Записать ещё раз
        </button>
      </div>
    </div>
  )
}
