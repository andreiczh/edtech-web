/**
 * Прохождение заданий в мини-приложении — макеты «66 · Redesign»:
 *  №39: 32/38 (отсчёт), 33 (инструкция, SKIP), 35 (текст и запись), 37
 *       (ожидание), 36 (разбор);
 *  №40: 18 (отсчёт), 20 (объявление, подготовка — по файлу без SKIP), 27–30
 *       (четыре вопроса по очереди над фото), 37 (ожидание), 31 (разбор).
 * №41 и №42 ждут своих макетов: после того же отсчёта идёт прежний экран
 * задания (TaskScreen) внутри оболочки — тестировщик 23.09.2026 просил
 * выбор всех четырёх заданий и отсчёт перед каждым, в том числе в DEMO.
 *
 * Логика та же, что в TaskScreen: подготовка по таймингу экзамена, запись
 * одним куском на все шаги (перезапуск рекордера ломает контейнер записи),
 * разбор через /task_feedback, отметка о пройденном и последний разбор — как
 * в SessionScreen.
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
import { TaskScreen, type VariantResult } from '../screens/TaskScreen'
import { useRecorder } from '../ege2/useRecorder'
import { Ambient } from './Ambient'
import { ResultScreen } from './ResultScreen'
import { ResultScreen40 } from './ResultScreen40'

export interface PracticeItem {
  taskId: TaskId
  variantId: string
}

type Stage = 'countdown' | 'intro' | 'run' | 'analyzing' | 'result' | 'legacy'

/** Есть ли у номера мобильные макеты; остальные идут прежним экраном. */
const hasMiniScreens = (kind: string) => kind === 'reading' || kind === 'dialogue'

/** Номер задания устной части по порядку: 39 → «ЗАДАНИЕ 1». */
export function taskNo(id: TaskId): number {
  return id - 38
}

/** Номер уже стоит в подписи «ЗАДАНИЕ N» — «№39:» и «Task 1.» из текста
    банка на экране лишние: тестировщик принял «№39: … a project with your
    friend» за инструкцию монолога (23.09.2026), хотя это дословный текст
    ФИПИ задания 1. */
export function cleanBrief(text: string): string {
  return text.replace(/^\s*(№\s*\d+\s*:|Task\s+\d+\s*\.)\s*/i, '')
}

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
const u = (v: number) => `calc(${v} * var(--u))`

const MIC_NOTE = 'Нет доступа к микрофону — разреши его в браузере и нажми сюда, чтобы начать.'

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
  /** skip — кнопка справа (инструкция №39, макет 33); quit — слева (35, 20, 27–30) */
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

/** Микрофон не дали: объяснение, по нажатию — новая попытка. */
function MicNote({ text, onRetry }: { text: string; onRetry: () => void }) {
  return (
    <button type="button" className="m-btn m-note" onClick={onRetry}>
      {text}
    </button>
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

/* ------------------------------------------------------- №39: чтение */

function ReadingTask({
  no,
  variant,
  stage,
  micError,
  onStart,
  onQuit,
  onRunDone,
}: {
  no: number
  variant: TaskVariant
  stage: 'intro' | 'run'
  micError: string | null
  /** SKIP и конец подготовки: включить микрофон и начать запись */
  onStart: () => void
  onQuit: () => void
  onRunDone: () => void
}) {
  const task = TASKS[39]
  const total = stage === 'intro' ? task.prepSeconds : task.answerSeconds
  const left = useCountdown(total, stage === 'intro' ? onStart : onRunDone, true, stage)
  return (
    <>
      <span className="m-label">ЗАДАНИЕ {no}</span>
      {stage === 'intro' ? (
        <>
          <div className="m-card m-instr">{cleanBrief(variant.brief)}</div>
          {micError && <MicNote text={micError} onRetry={onStart} />}
          {/* На экзамене текст виден все 1,5 минуты подготовки («read the text
              silently, then be ready to read it aloud»). В макете 33 его нет,
              но без текста подготовка теряет смысл — правка тестировщика. */}
          <div className="m-card m-read m-read--prep">{variant.readText}</div>
        </>
      ) : (
        <div className="m-card m-read">{variant.readText}</div>
      )}
      <div className="m-pad" />
      <TimerBar
        left={left > 0 ? left : total}
        total={total}
        side={stage === 'intro' ? 'skip' : 'quit'}
        onButton={stage === 'intro' ? onStart : onQuit}
      />
    </>
  )
}

/* ---------------------------------------------------- №40: вопросы */

/** Текст объявления из банка — на три карточки макета: инструкция, пункты,
    «20 секунд на вопрос». Вариант с сервера может быть сложен иначе —
    тогда пункты берутся из шагов, а чего нет, того и не рисуем. */
function splitBrief(variant: TaskVariant): { head: string; points: string[]; foot: string } {
  const lines = (variant.brief || '').split('\n').map((s) => s.trim()).filter(Boolean)
  let points = lines.filter((l) => /^\d+\.\s/.test(l)).map((l) => l.replace(/^\d+\.\s*/, ''))
  const foot = lines.find((l) => /^you have/i.test(l)) ?? ''
  const head = cleanBrief(lines.filter((l) => !/^\d+\.\s/.test(l) && l !== foot).join(' '))
  if (!points.length) points = (variant.steps ?? []).map((s) => s.replace(/^Question \d+:\s*/i, ''))
  return { head, points, foot }
}

function DialogueTask({
  no,
  variant,
  stage,
  step,
  micError,
  onStart,
  onStepDone,
  onQuit,
}: {
  no: number
  variant: TaskVariant
  stage: 'intro' | 'run'
  step: number
  micError: string | null
  onStart: () => void
  onStepDone: () => void
  onQuit: () => void
}) {
  const task = TASKS[40]
  const total = stage === 'intro' ? task.prepSeconds : task.answerSeconds
  const left = useCountdown(total, stage === 'intro' ? onStart : onStepDone, true, `${stage}:${step}`)
  const { head, points, foot } = splitBrief(variant)
  const photo = variant.images?.[0]
  return (
    <>
      <span className="m-label">ЗАДАНИЕ {no}</span>
      {stage === 'intro' ? (
        <>
          <div className="m-card d-instr">{head}</div>
          {points.length > 0 && (
            <div className="m-card d-points">
              <ol>
                {points.map((p, i) => (
                  <li key={i}>
                    {i + 1}. {p}
                  </li>
                ))}
              </ol>
            </div>
          )}
          {foot && <div className="m-card d-foot">{foot}</div>}
          {micError && <MicNote text={micError} onRetry={onStart} />}
          {variant.imageCaption && <div className="d-caption">{variant.imageCaption}</div>}
          {photo && <img className="d-photo" src={photo} alt="" />}
        </>
      ) : (
        <>
          <div className="d-title" aria-live="polite">
            {step + 1}. {points[step] ?? ''}
          </div>
          {photo && <img className="d-photo" src={photo} alt="" />}
        </>
      )}
      <div className="m-pad" />
      <TimerBar left={left > 0 ? left : total} total={total} side="quit" onButton={onQuit} />
    </>
  )
}

/* ------------------------------------------------------------- поток */

export function Practice({ items, onExit }: { items: PracticeItem[]; onExit: () => void }) {
  const [index, setIndex] = useState(0)
  const [stage, setStage] = useState<Stage>('countdown')
  const [step, setStep] = useState(0)
  const [feedback, setFeedback] = useState<TaskFeedback | null>(null)
  const [transcript, setTranscript] = useState<string | undefined>(undefined)
  const [failure, setFailure] = useState<string | null>(null)
  const [blob, setBlob] = useState<Blob | null>(null)
  const [micError, setMicError] = useState<string | null>(null)
  const { start, stop, error: recError } = useRecorder()

  const item = items[index]
  const variant = item ? variantById(item.taskId, item.variantId) : undefined
  const task = item ? TASKS[item.taskId] : undefined
  // Шаги ответа: у №40 — по одному на пункт объявления, у чтения — один.
  const stepCount = task?.kind === 'dialogue' ? Math.max(1, variant?.steps?.length ?? 0) : 1

  const startedAtRef = useRef(0)
  const finishingRef = useRef(false)
  // Ушли с экрана ожидания — пришедший позже разбор никому не нужен.
  const cancelledRef = useRef(false)
  const stageRef = useRef(stage)
  stageRef.current = stage
  const stepRef = useRef(step)
  stepRef.current = step

  const startRun = useCallback(async () => {
    if (stageRef.current === 'run') return
    setMicError(null)
    if (!(await start())) {
      setMicError(MIC_NOTE)
      return
    }
    startedAtRef.current = Date.now()
    finishingRef.current = false
    setStep(0)
    setStage('run')
  }, [start])

  useEffect(() => {
    if (recError) setMicError(MIC_NOTE)
  }, [recError])

  const finish = useCallback(async () => {
    if (finishingRef.current || !item || !variant || !task) return
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
  }, [index, item, items.length, stop, task, variant])

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
    setStep(0)
    setIndex((i) => i + 1)
    setStage('countdown')
  }, [index, items.length, onExit])

  /** №41/№42 прошли прежним экраном: отметки — те же, что в SessionScreen. */
  const onLegacyDone = useCallback(
    (r: VariantResult) => {
      if (r.feedback) {
        markVariantSolved(r.variantId)
        saveTaskFeedback(r.taskId, {
          when: new Date().toISOString(),
          summary: r.feedback.summary,
          score: r.feedback.score,
          max: r.feedback.max,
          errors: (r.feedback.errors ?? []).map((e) => ({
            quote: e.quote,
            correction: e.correction,
            explanation: e.explanation,
          })),
        })
      }
      next()
    },
    [next],
  )

  /** Конец 20 секунд на вопрос: следующий пункт или разбор. Запись не
      прерывается — шаг переключает только заголовок и таймер. */
  const onStepDone = useCallback(() => {
    if (stageRef.current !== 'run') return
    if (stepRef.current + 1 < stepCount) setStep((s) => s + 1)
    else void finish()
  }, [finish, stepCount])

  const quit = useCallback(() => {
    cancelledRef.current = true
    void stop() // микрофон гаснет сразу
    onExit()
  }, [onExit, stop])

  // Битый id варианта — только при ошибке в коде; белый экран всё равно нельзя.
  useEffect(() => {
    if (!item || !variant || !task) onExit()
  }, [item, onExit, task, variant])
  if (!item || !variant || !task) return null
  const no = taskNo(item.taskId)
  const seconds = Math.max(0, Math.round((Date.now() - startedAtRef.current) / 1000))

  if (stage === 'result') {
    if (task.kind === 'dialogue') {
      return (
        <ResultScreen40
          no={no}
          taskId={item.taskId}
          variant={variant}
          feedback={feedback}
          failure={failure}
          blob={blob}
          seconds={seconds}
          onQuit={onExit}
          onNext={next}
        />
      )
    }
    return (
      <ResultScreen
        no={no}
        taskId={item.taskId}
        variant={variant}
        feedback={feedback}
        transcript={transcript}
        failure={failure}
        blob={blob}
        seconds={seconds}
        onQuit={onExit}
        onNext={next}
      />
    )
  }

  if (stage === 'legacy') {
    return (
      <div className="mini__frame">
        <Ambient />
        <div className="mini-legacy mini-legacy--full">
          <TaskScreen
            key={variant.id}
            taskId={item.taskId}
            variant={variant}
            progress={{ index: index + 1, total: items.length }}
            onExit={quit}
            onDone={onLegacyDone}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="mini__frame">
      <Ambient />
      <div className="mini__scroll">
        {stage === 'countdown' && (
          <Countdown onDone={() => setStage(hasMiniScreens(task.kind) ? 'intro' : 'legacy')} />
        )}
        {(stage === 'intro' || stage === 'run') &&
          (task.kind === 'dialogue' ? (
            <DialogueTask
              no={no}
              variant={variant}
              stage={stage}
              step={step}
              micError={micError}
              onStart={() => void startRun()}
              onStepDone={onStepDone}
              onQuit={quit}
            />
          ) : (
            <ReadingTask
              no={no}
              variant={variant}
              stage={stage}
              micError={micError}
              onStart={() => void startRun()}
              onRunDone={() => void finish()}
              onQuit={quit}
            />
          ))}
        {stage === 'analyzing' && <Analyzing no={no} onQuit={quit} />}
      </div>
    </div>
  )
}
