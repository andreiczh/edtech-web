/**
 * Прохождение заданий в мини-приложении — макеты «66 · Redesign»:
 *  №39: 32/38 (отсчёт), 33 (инструкция, SKIP), 35 (текст и запись), 37
 *       (ожидание), 36 (разбор);
 *  №40: 18 (отсчёт), 20 (объявление, подготовка — по файлу без SKIP), 27–30
 *       (четыре вопроса по очереди над фото), 37 (ожидание), 31 (разбор).
 *  №41: 13/24/26 (карточка «Question N», вопрос ЗВУЧИТ), 16 («Be ready to
 *       answer 5…1» перед каждым вопросом); инструкция и разбор — по
 *       образцу 33 и 31, их макетов нет.
 *  №42: 9 (отсчёт), 7 (инструкция и два фото, 2,5 мин), 10 («Be ready to
 *       answer»), 17 (те же инструкция и фото под запись, 3 мин), 6 (разбор).
 * Прежний экран (TaskScreen) остаётся запасным путём на случай номера без
 * макетов.
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
import { askAloud } from '../ege2/askAloud'
import { useCountdown } from '../ege2/useCountdown'
import { TaskScreen, type VariantResult } from '../screens/TaskScreen'
import { useRecorder } from '../ege2/useRecorder'
import { Ambient } from './Ambient'
import { BackButton, useMaxBack } from './ResultBits'
import { ResultScreen } from './ResultScreen'
import { ResultScreen40 } from './ResultScreen40'
import { ResultScreen42 } from './ResultScreen42'

export interface PracticeItem {
  taskId: TaskId
  variantId: string
}

/** ready — второй отсчёт «Preparation 5…1» между подготовкой и записью №39
    (макет 38 рядом с 32; в раскладке владельца от 24.09.2026 он стоит после
    инструкции). У №40 второго отсчёта в раскладке нет. */
type Stage = 'countdown' | 'intro' | 'ready' | 'run' | 'analyzing' | 'result' | 'legacy'

/** Есть ли у номера мобильные макеты; остальные идут прежним экраном. */
const hasMiniScreens = (kind: string) =>
  kind === 'reading' || kind === 'dialogue' || kind === 'interview' || kind === 'monologue'

/** С чего начинается номер: у интервью первого отсчёта в раскладке нет —
    сразу инструкция; у остальных «Preparation 5…1». */
const firstStage = (kind: string): Stage => (kind === 'interview' ? 'intro' : 'countdown')

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

function Countdown({
  onDone,
  word = 'Preparation',
  wordClass = '',
}: {
  onDone: () => void
  word?: string
  /** cd-word--iv (макет 16, №41) / cd-word--mo (макет 10, №42): слово стоит выше */
  wordClass?: string
}) {
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
      <div className={`cd-word${wordClass ? ` ${wordClass}` : ''}`}>{word}</div>
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
  /** SKIP и конец подготовки: у №39 — отсчёт перед записью, потом микрофон */
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


/* -------------------------------------------- №41: интервью (13/16/24/26) */

/** Вопрос интервью ЗВУЧИТ (как в TaskScreen): на карточке только «Question N»,
    микрофон на время вопроса ставится на паузу, время ответа идёт после.
    Не прозвучало — вопрос показывается текстом: задание проще, но выполнимо. */
function InterviewTask({
  no,
  variant,
  stage,
  step,
  micError,
  onStart,
  onStepDone,
  onQuit,
  pause,
  resume,
}: {
  no: number
  variant: TaskVariant
  stage: 'intro' | 'run'
  step: number
  micError: string | null
  /** SKIP и конец подготовки: включить микрофон и перейти к первому отсчёту */
  onStart: () => void
  onStepDone: () => void
  onQuit: () => void
  pause: () => void
  resume: () => void
}) {
  const task = TASKS[41]
  const steps = variant.steps ?? []
  const [asking, setAsking] = useState(false)
  const [showText, setShowText] = useState(false)
  const askingRef = useRef(false)
  askingRef.current = asking

  useEffect(() => {
    if (stage !== 'run') return
    const text = steps[step]
    if (!text) return
    const ac = new AbortController()
    let alive = true
    setAsking(true)
    setShowText(false)
    pause()
    void askAloud(text, ac.signal).then((ok) => {
      if (!alive) return
      if (!ok) setShowText(true)
      resume()
      setAsking(false)
    })
    return () => {
      alive = false
      ac.abort()
      resume()
    }
  }, [pause, resume, stage, step, steps])

  const total = stage === 'intro' ? task.prepSeconds : task.answerSeconds
  const left = useCountdown(
    total,
    stage === 'intro'
      ? onStart
      : () => {
          if (!askingRef.current) onStepDone()
        },
    true,
    `${stage}:${step}:${asking}`,
  )
  return (
    <>
      <span className="m-label">ЗАДАНИЕ {no}</span>
      {stage === 'intro' ? (
        <>
          <div className="m-card m-instr">{cleanBrief(variant.brief)}</div>
          {micError && <MicNote text={micError} onRetry={onStart} />}
        </>
      ) : (
        <div className={`m-card iv-card${showText ? ' iv-card--text' : ''}`} aria-live="polite">
          {showText ? steps[step] : `Question ${step + 1}`}
        </div>
      )}
      <div className="m-pad" />
      <TimerBar
        left={asking || left <= 0 ? total : left}
        total={total}
        side={stage === 'intro' ? 'skip' : 'quit'}
        onButton={stage === 'intro' ? onStart : onQuit}
      />
    </>
  )
}

/* ------------------------------------------- №42: монолог (7/17) */

/** Инструкция и два фото — и на подготовке (2,5 мин), и на записи (3 мин).
    По файлу: подпись «ЗАДАНИЕ N» только на подготовке, и стоит выше обычной;
    на записи карточка начинается с 68.2 пункта. Кнопки SKIP нет ни там, ни там. */
function MonologueTask({
  no,
  variant,
  stage,
  micError,
  onStart,
  onRunDone,
  onQuit,
}: {
  no: number
  variant: TaskVariant
  stage: 'intro' | 'run'
  micError: string | null
  onStart: () => void
  onRunDone: () => void
  onQuit: () => void
}) {
  const task = TASKS[42]
  const total = stage === 'intro' ? task.prepSeconds : task.answerSeconds
  const left = useCountdown(total, stage === 'intro' ? onStart : onRunDone, true, stage)
  const lines = (variant.brief || '').split('\n')
  const blocks: Array<{ kind: 'p' | 'ul'; items: string[] }> = []
  for (const raw of lines) {
    const line = raw.trim()
    if (!line) continue
    if (/^[•\-–]\s*/.test(line)) {
      const li = line.replace(/^[•\-–]\s*/, '')
      const last = blocks[blocks.length - 1]
      if (last && last.kind === 'ul') last.items.push(li)
      else blocks.push({ kind: 'ul', items: [li] })
    } else blocks.push({ kind: 'p', items: [line] })
  }
  return (
    <>
      {stage === 'intro' && <span className="m-label mo-label">ЗАДАНИЕ {no}</span>}
      <div className={`m-card mo-instr${stage === 'run' ? ' mo-instr--run' : ''}`}>
        {blocks.map((b, i) =>
          b.kind === 'ul' ? (
            <ul key={i}>
              {b.items.map((t, j) => (
                <li key={j}>{t}</li>
              ))}
            </ul>
          ) : (
            <p key={i}>{b.items[0]}</p>
          ),
        )}
      </div>
      {micError && stage === 'intro' && <MicNote text={micError} onRetry={onStart} />}
      {(variant.images ?? []).slice(0, 2).map((src, i) => (
        <img key={i} className="mo-photo" src={src} alt={`Фото ${i + 1}`} />
      ))}
      <div className="mo-pad" />
      <TimerBar left={left > 0 ? left : total} total={total} side="quit" onButton={onQuit} />
    </>
  )
}

/* ------------------------------------------------------------- поток */

export function Practice({
  items,
  onExit,
  onBack,
}: {
  items: PracticeItem[]
  onExit: () => void
  /** «Назад»: на экран, с которого пришли; без него — как QUIT */
  onBack?: () => void
}) {
  const [index, setIndex] = useState(0)
  const [stage, setStage] = useState<Stage>(() =>
    items[0] ? firstStage(TASKS[items[0].taskId].kind) : 'countdown',
  )
  const [step, setStep] = useState(0)
  const [feedback, setFeedback] = useState<TaskFeedback | null>(null)
  const [transcript, setTranscript] = useState<string | undefined>(undefined)
  const [failure, setFailure] = useState<string | null>(null)
  const [blob, setBlob] = useState<Blob | null>(null)
  const [micError, setMicError] = useState<string | null>(null)
  const { start, stop, pause, resume, error: recError } = useRecorder()

  const item = items[index]
  const variant = item ? variantById(item.taskId, item.variantId) : undefined
  const task = item ? TASKS[item.taskId] : undefined
  // Шаги ответа: у №40 — по одному на пункт объявления, у чтения — один.
  const stepCount =
    task?.kind === 'dialogue' || task?.kind === 'interview'
      ? Math.max(1, variant?.steps?.length ?? 0)
      : 1

  const startedAtRef = useRef(0)
  const finishingRef = useRef(false)
  // Ушли с экрана ожидания — пришедший позже разбор никому не нужен.
  const cancelledRef = useRef(false)
  const stageRef = useRef(stage)
  stageRef.current = stage
  const stepRef = useRef(step)
  stepRef.current = step

  /** next — куда после микрофона: у интервью сначала отсчёт «Be ready to
      answer» (запись уже идёт, вопрос ещё не прозвучал). */
  const startRun = useCallback(async (next: 'run' | 'ready' = 'run') => {
    if (stageRef.current === 'run') return
    setMicError(null)
    if (!(await start())) {
      setMicError(MIC_NOTE)
      setStage('intro')
      return
    }
    startedAtRef.current = Date.now()
    finishingRef.current = false
    setStep(0)
    setStage(next)
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
    const following = items[index + 1]
    setStage(following ? firstStage(TASKS[following.taskId].kind) : 'countdown')
  }, [index, items, onExit])

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
    if (stepRef.current + 1 < stepCount) {
      setStep((s) => s + 1)
      // интервью: перед каждым вопросом — свой отсчёт (макет 16)
      if (task?.kind === 'interview') setStage('ready')
    } else void finish()
  }, [finish, stepCount, task?.kind])

  const back = useCallback(() => {
    cancelledRef.current = true
    void stop()
    ;(onBack ?? onExit)()
  }, [onBack, onExit, stop])
  useMaxBack(back)

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
    if (task.kind === 'monologue') {
      return (
        <ResultScreen42
          taskId={item.taskId}
          variant={variant}
          feedback={feedback}
          transcript={transcript}
          failure={failure}
          blob={blob}
          seconds={seconds}
          onQuit={onExit}
          onNext={next}
          onBack={back}
        />
      )
    }
    if (task.kind === 'dialogue' || task.kind === 'interview') {
      return (
        <ResultScreen40
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
          onBack={back}
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
        onBack={back}
      />
    )
  }

  if (stage === 'legacy') {
    return (
      <div className="mini__frame">
        <Ambient />
        <BackButton onBack={back} />
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
      <BackButton onBack={back} />
      <div className="mini__scroll">
        {stage === 'countdown' && (
          <Countdown onDone={() => setStage(hasMiniScreens(task.kind) ? 'intro' : 'legacy')} />
        )}
        {(stage === 'intro' || stage === 'run') && task.kind === 'dialogue' && (
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
        )}
        {(stage === 'intro' || stage === 'run') && task.kind === 'interview' && (
          <InterviewTask
            no={no}
            variant={variant}
            stage={stage}
            step={step}
            micError={micError}
            onStart={() => void startRun('ready')}
            onStepDone={onStepDone}
            onQuit={quit}
            pause={pause}
            resume={resume}
          />
        )}
        {(stage === 'intro' || stage === 'run') && task.kind === 'monologue' && (
          <MonologueTask
            no={no}
            variant={variant}
            stage={stage}
            micError={micError}
            onStart={() => setStage('ready')}
            onRunDone={() => void finish()}
            onQuit={quit}
          />
        )}
        {(stage === 'intro' || stage === 'run') && task.kind === 'reading' && (
          <ReadingTask
            no={no}
            variant={variant}
            stage={stage}
            micError={micError}
            onStart={() => setStage('ready')}
            onRunDone={() => void finish()}
            onQuit={quit}
          />
        )}
        {stage === 'ready' && task.kind === 'reading' && <Countdown onDone={() => void startRun()} />}
        {stage === 'ready' && task.kind === 'monologue' && (
          <Countdown word="Be ready to answer" wordClass="cd-word--mo" onDone={() => void startRun()} />
        )}
        {stage === 'ready' && task.kind === 'interview' && (
          <Countdown word="Be ready to answer" wordClass="cd-word--iv" onDone={() => setStage('run')} />
        )}
        {stage === 'analyzing' && <Analyzing no={no} onQuit={quit} />}
      </div>
    </div>
  )
}
