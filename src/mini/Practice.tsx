/**
 * Прохождение задания в мини-приложении — макеты «66 · Redesign» 32/38
 * (отсчёт), 33 (инструкция), 35 (текст и запись), 37 (ожидание), 36 (разбор).
 *
 * Сейчас в этом дизайне живёт только №39 (чтение вслух); остальные номера
 * ждут своих макетов, и этот экран рассчитан на них: шаг «задание» выбирается
 * по kind варианта. Логика та же, что в TaskScreen: подготовка по таймингу
 * экзамена, запись одним куском, разбор через /task_feedback, отметка о
 * пройденном и последний разбор — как в SessionScreen.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

import { requestTaskFeedback, type TaskFeedback } from '../ege2/feedback'
import {
  TASKS,
  feedbackPayload,
  markVariantSolved,
  saveTaskFeedback,
  variantById,
  type TaskId,
  type TaskVariant,
} from '../ege2/tasks'
import { useCountdown } from '../ege2/useCountdown'
import { useRecorder } from '../ege2/useRecorder'
import { Ambient } from './Ambient'
import { ResultScreen } from './ResultScreen'

export interface PracticeItem {
  taskId: TaskId
  variantId: string
}

type Stage = 'countdown' | 'intro' | 'run' | 'analyzing' | 'result'

/** Номер задания устной части по порядку: 39 → «ЗАДАНИЕ 1». */
export function taskNo(id: TaskId): number {
  return id - 38
}

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
const u = (v: number) => `calc(${v} * var(--u))`

/* ------------------------------------------------------------ отсчёт */

function Countdown({ onDone }: { onDone: () => void }) {
  const [n, setN] = useState(5)
  const doneRef = useRef(onDone)
  doneRef.current = onDone
  useEffect(() => {
    if (n <= 0) {
      doneRef.current()
      return
    }
    const id = setTimeout(() => setN((v) => v - 1), 1000)
    return () => clearTimeout(id)
  }, [n])
  return (
    <>
      <div className="cd-word">Preparation</div>
      {n > 0 && (
        <div className="cd-digit" key={n} aria-live="assertive">
          {n}
        </div>
      )}
    </>
  )
}

/* ----------------------------------------------------- таймер снизу */

function TimerBar({
  left,
  total,
  side,
  onButton,
}: {
  left: number
  total: number
  /** skip — кнопка справа (инструкция, макет 33); quit — слева (запись, макет 35) */
  side: 'skip' | 'quit'
  onButton: () => void
}) {
  const pct = total > 0 ? Math.min(100, Math.max(0, ((total - left) / total) * 100)) : 0
  return (
    <div className="m-bar">
      {side === 'quit' && (
        <button type="button" className="m-btn m-round" style={{ left: u(16.5) }} onClick={onButton}>
          QUIT
        </button>
      )}
      <div
        className="m-pill"
        style={side === 'skip' ? { left: u(20.3), width: u(315) } : { left: u(66.3), width: u(319) }}
        role="timer"
        aria-label={`Осталось ${fmt(left)}`}
      >
        <div
          className="m-pill__track"
          style={side === 'skip' ? { left: u(13.6), width: u(262.9) } : { left: u(13.8), width: u(266.2) }}
        >
          <div className="m-pill__fill" style={{ width: `${pct}%` }} />
        </div>
        <span className="m-pill__time" style={{ right: u(side === 'skip' ? 14.9 : 15.2) }}>
          {fmt(left)}
        </span>
      </div>
      {side === 'skip' && (
        <button
          type="button"
          className="m-btn m-round m-round--skip"
          style={{ left: u(338.3) }}
          onClick={onButton}
        >
          SKIP
        </button>
      )}
    </div>
  )
}

/* ------------------------------------------------------ ожидание (37) */

function Analyzing({ no, onQuit }: { no: number; onQuit: () => void }) {
  // Цвета — та же краска #534E89, что в макете, в трёх плотностях (0.36,
  // 0.76, 1), уже смешанных с фоном: «желейный» фильтр работает по альфе,
  // и полупрозрачные круги он бы стёр.
  return (
    <>
      <span className="m-label">ЗАДАНИЕ {no}</span>
      <div className="m-card wait-card" role="status" aria-live="polite">
        <div className="wait-card__title">Анализ ответа</div>
      </div>
      <svg className="wait-dots" viewBox="0 0 282.8 94.3" aria-hidden="true">
        <defs>
          <filter id="mini-goo" x="-20%" y="-40%" width="140%" height="180%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="blur" />
            <feColorMatrix in="blur" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 20 -10" result="goo" />
            <feComposite in="SourceGraphic" in2="goo" operator="atop" />
          </filter>
        </defs>
        <g filter="url(#mini-goo)">
          <circle cx="96.4" cy="47.1" r="15.3" fill="#bdbacc" />
          <circle cx="141.3" cy="47.1" r="15.3" fill="#7b77a2" />
          <circle cx="186.3" cy="47.1" r="15.3" fill="#534e89" />
        </g>
      </svg>
      <div className="m-bar">
        <button type="button" className="m-btn m-round" style={{ left: u(19.1) }} onClick={onQuit}>
          QUIT
        </button>
      </div>
    </>
  )
}

/* ----------------------------------------------------------- задание */

function ReadingTask({
  no,
  variant,
  stage,
  micError,
  onSkipPrep,
  onQuit,
  onPrepDone,
  onRunDone,
}: {
  no: number
  variant: TaskVariant
  stage: 'intro' | 'run'
  micError: string | null
  onSkipPrep: () => void
  onQuit: () => void
  onPrepDone: () => void
  onRunDone: () => void
}) {
  const task = TASKS[39]
  const total = stage === 'intro' ? task.prepSeconds : task.answerSeconds
  const left = useCountdown(total, stage === 'intro' ? onPrepDone : onRunDone, true, stage)
  return (
    <>
      <span className="m-label">ЗАДАНИЕ {no}</span>
      {stage === 'intro' ? (
        <>
          <div className="m-card m-instr">{variant.brief}</div>
          {micError && <p className="m-note">{micError}</p>}
        </>
      ) : (
        <div className="m-card m-read">{variant.readText}</div>
      )}
      <div className="m-pad" />
      <TimerBar
        left={left > 0 ? left : total}
        total={total}
        side={stage === 'intro' ? 'skip' : 'quit'}
        onButton={stage === 'intro' ? onSkipPrep : onQuit}
      />
    </>
  )
}

/* ------------------------------------------------------------- поток */

export function Practice({ items, onExit }: { items: PracticeItem[]; onExit: () => void }) {
  const [index, setIndex] = useState(0)
  const [stage, setStage] = useState<Stage>('countdown')
  const [feedback, setFeedback] = useState<TaskFeedback | null>(null)
  const [transcript, setTranscript] = useState<string | undefined>(undefined)
  const [failure, setFailure] = useState<string | null>(null)
  const [blob, setBlob] = useState<Blob | null>(null)
  const [micError, setMicError] = useState<string | null>(null)
  const { start, stop, error: recError } = useRecorder()

  const item = items[index]
  const variant = item ? variantById(item.taskId, item.variantId) : undefined
  const startedAtRef = useRef(0)
  const finishingRef = useRef(false)
  // Ушли с экрана ожидания — пришедший позже разбор никому не нужен.
  const cancelledRef = useRef(false)

  const stageRef = useRef(stage)
  stageRef.current = stage

  const startRun = useCallback(async () => {
    if (stageRef.current === 'run') return
    setMicError(null)
    if (!(await start())) {
      setMicError(
        'Нет доступа к микрофону — разреши его и нажми SKIP ещё раз. Если запроса не было, микрофон закрыт настройками окна.',
      )
      return
    }
    startedAtRef.current = Date.now()
    finishingRef.current = false
    setStage('run')
  }, [start])

  useEffect(() => {
    if (recError) setMicError(recError)
  }, [recError])

  const finish = useCallback(async () => {
    if (finishingRef.current || !item || !variant) return
    finishingRef.current = true
    cancelledRef.current = false
    setStage('analyzing')
    const rec = await stop()
    setBlob(rec && rec.size ? rec : null)
    if (!rec || !rec.size) {
      setFailure('Запись пустая — микрофон не отдал ни одного кадра. Попробуй ещё раз.')
      setFeedback(null)
      setStage('result')
      return
    }
    const task = TASKS[item.taskId]
    try {
      const res = await requestTaskFeedback(rec, task.kind, feedbackPayload(task, variant), {
        variantId: variant.id,
        durationSec: Math.max(0, Math.round((Date.now() - startedAtRef.current) / 1000)),
        sessionDone: index >= items.length - 1,
      })
      if (cancelledRef.current) return
      setFeedback(res.feedback)
      setTranscript(res.transcript)
      setFailure(null)
      // Как в SessionScreen: пройденным вариант считается только с разбором.
      markVariantSolved(variant.id)
      saveTaskFeedback(item.taskId, {
        when: new Date().toISOString(),
        summary: res.feedback.summary,
        score: res.feedback.score,
        max: res.feedback.max,
        errors: (res.feedback.errors ?? []).map((e) => ({
          quote: e.quote,
          correction: e.correction,
          explanation: e.explanation,
        })),
      })
    } catch (e) {
      if (cancelledRef.current) return
      setFeedback(null)
      setFailure(e instanceof Error ? e.message : String(e))
    }
    setStage('result')
  }, [index, item, items.length, stop, variant])

  const quit = useCallback(() => {
    cancelledRef.current = true
    void stop() // микрофон гаснет сразу
    onExit()
  }, [onExit, stop])

  const next = useCallback(() => {
    if (index + 1 >= items.length) {
      onExit()
      return
    }
    setFeedback(null)
    setTranscript(undefined)
    setFailure(null)
    setBlob(null)
    setMicError(null)
    finishingRef.current = false
    setIndex((i) => i + 1)
    setStage('countdown')
  }, [index, items.length, onExit])

  // Битый id варианта — только при ошибке в коде; белый экран всё равно нельзя.
  useEffect(() => {
    if (!item || !variant) onExit()
  }, [item, onExit, variant])
  if (!item || !variant) return null
  const no = taskNo(item.taskId)

  if (stage === 'result') {
    return (
      <ResultScreen
        no={no}
        taskId={item.taskId}
        variant={variant}
        feedback={feedback}
        transcript={transcript}
        failure={failure}
        blob={blob}
        seconds={Math.max(0, Math.round((Date.now() - startedAtRef.current) / 1000))}
        onQuit={onExit}
        onNext={next}
      />
    )
  }

  return (
    <div className="mini__frame">
      <Ambient />
      <div className="mini__scroll">
        {stage === 'countdown' && <Countdown onDone={() => setStage('intro')} />}
        {(stage === 'intro' || stage === 'run') && (
          <ReadingTask
            no={no}
            variant={variant}
            stage={stage}
            micError={micError}
            onSkipPrep={() => void startRun()}
            onPrepDone={() => void startRun()}
            onRunDone={() => void finish()}
            onQuit={quit}
          />
        )}
        {stage === 'analyzing' && <Analyzing no={no} onQuit={quit} />}
      </div>
    </div>
  )
}
