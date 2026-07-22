/**
 * Экран прохождения ОДНОГО варианта задания устной части (39, 40, 41, 42).
 * Экран один на все номера намеренно: различия целиком описаны данными варианта
 * (есть ли текст для чтения, картинки, шаги), ветвимся по полям, а не по номеру.
 *
 * Сессиями из пяти вариантов управляет SessionScreen: этот экран прогоняет один
 * вариант и отдаёт результат через onDone. Разбор ИИ теперь есть у ВСЕХ типов —
 * бэкенд /task_feedback появился 22.07.2026; у №39 он сравнивает слова с текстом
 * (произношение по транскрипту оценить нельзя, и мы этого не изображаем).
 */
import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'

import { CountdownBar, Mascot, Pill } from '../design/ui'
import { requestTaskFeedback, type TaskFeedback } from '../ege2/feedback'
import { TASKS, feedbackPayload, type TaskId, type TaskVariant } from '../ege2/tasks'
import { useCountdown } from '../ege2/useCountdown'
import { useRecorder } from '../ege2/useRecorder'

export interface VariantResult {
  taskId: TaskId
  variantId: string
  durationSec: number
  feedback: TaskFeedback | null
  transcript?: string
  /** Причина, по которой разбор не получился (сеть, пустая запись) */
  failure?: string
}

/* Бэкенд может прислать категорию, которой мы не знаем, — покажем как есть. */
const CAT_LABEL: Record<string, string> = {
  lex: 'Лексика',
  gram: 'Грамматика',
  phon: 'Произношение',
  logic: 'Логика',
}

type Phase = 'intro' | 'run' | 'analyzing' | 'result'

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

/* Центральная область прокручивается сама: на телефоне текст задания и разбор
   заведомо не влезают, а нижняя строка с QUIT/таймером обязана остаться на экране.
   Внутренний padding — чтобы подъём карточек на ховере не резался краем контейнера
   (замечание пользователя: «кнопки вылезают за поля и обрезаются»). */
const scrollArea: CSSProperties = {
  flex: '0 1 auto',
  minHeight: 0,
  maxHeight: '100%',
  overflowY: 'auto',
  overscrollBehavior: 'contain',
  width: 'min(100%, 960px)',
  display: 'flex',
  flexDirection: 'column',
  gap: 'clamp(10px, 1.8vh, 18px)',
  alignItems: 'center',
  padding: '6px 10px',
}

const questionStyle: CSSProperties = {
  margin: 0,
  maxWidth: '900px',
  textAlign: 'center',
  color: 'var(--text)',
  fontWeight: 800,
  fontSize: 'clamp(17px, 2.6vw, 28px)',
  lineHeight: 1.25,
}

/* --------------------------------------------------------- Текст задания */

const MARKER = /^(?:[•·*–—-]|\d+[.)])\s+/

/**
 * `brief` приходит одной строкой с \n и маркерами списка. Без разбора это
 * простыня, в которой ученик не находит, о чём именно его просят спросить.
 */
function Brief({ text }: { text: string }) {
  const blocks: ReactNode[] = []
  let items: string[] = []
  let ordered = false

  const flush = () => {
    if (!items.length) return
    const li = items.map((s, i) => <li key={i}>{s}</li>)
    blocks.push(
      ordered ? <ol key={blocks.length}>{li}</ol> : <ul key={blocks.length}>{li}</ul>,
    )
    items = []
  }

  for (const raw of text.split('\n')) {
    const line = raw.trim()
    if (!line) {
      flush()
      continue
    }
    const m = MARKER.exec(line)
    if (m) {
      const isOrdered = /^\d/.test(line)
      if (items.length && isOrdered !== ordered) flush()
      ordered = isOrdered
      items.push(line.slice(m[0].length))
    } else {
      flush()
      blocks.push(
        <p key={blocks.length} style={{ margin: '0 0 0.6em' }}>
          {line}
        </p>,
      )
    }
  }
  flush()
  return <>{blocks}</>
}

/* ------------------------------------------------------------------ Экран */

export function TaskScreen({
  taskId,
  variant,
  progress,
  onExit,
  onDone,
}: {
  taskId: TaskId
  variant: TaskVariant
  /** Позиция в сессии, счёт с единицы: «2 из 5» в шапке и подпись кнопки */
  progress?: { index: number; total: number }
  onExit: () => void
  onDone: (result: VariantResult) => void
}) {
  const task = TASKS[taskId]
  const steps = variant.steps ?? []
  const stepCount = Math.max(1, steps.length)

  const [phase, setPhase] = useState<Phase>('intro')
  const [step, setStep] = useState(0)
  const [duration, setDuration] = useState(0)
  const [feedback, setFeedback] = useState<TaskFeedback | null>(null)
  const [transcript, setTranscript] = useState<string | undefined>(undefined)
  const [failure, setFailure] = useState<string | null>(null)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)

  const { state, error: micError, start, stop } = useRecorder()

  const phaseRef = useRef(phase)
  phaseRef.current = phase
  const startedAtRef = useRef(0)
  const finishingRef = useRef(false)
  const blobRef = useRef<Blob | null>(null)

  // Ссылку на blob надо отзывать, иначе запись висит в памяти вкладки до перезагрузки.
  useEffect(
    () => () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl)
    },
    [audioUrl],
  )

  const analyze = useCallback(
    async (blob: Blob) => {
      setPhase('analyzing')
      setFailure(null)
      try {
        const res = await requestTaskFeedback(blob, task.kind, feedbackPayload(task, variant), {
          variantId: variant.id,
          durationSec: Math.max(0, Math.round((Date.now() - startedAtRef.current) / 1000)),
        })
        setFeedback(res.feedback)
        setTranscript(res.transcript)
      } catch (e) {
        setFailure(e instanceof Error ? e.message : String(e))
      } finally {
        setPhase('result')
      }
    },
    [task, variant],
  )

  const finish = useCallback(async () => {
    // «End task» и истёкший таймер могут прилететь почти одновременно — второй
    // вызов остановил бы уже остановленный рекордер и отправил пустой blob.
    if (finishingRef.current) return
    finishingRef.current = true
    setDuration(Math.max(0, Math.round((Date.now() - startedAtRef.current) / 1000)))
    setPhase('analyzing')

    const blob = await stop()
    blobRef.current = blob
    setAudioUrl(blob && blob.size ? URL.createObjectURL(blob) : null)

    if (blob && blob.size) await analyze(blob)
    else {
      setFailure('Запись пустая — микрофон не отдал ни одного кадра. Попробуй ещё раз.')
      setPhase('result')
    }
  }, [analyze, stop])

  /**
   * Граница шагов (40: четыре вопроса, 41: пять). Запись НЕ режем на куски и не
   * перезапускаем: MediaRecorder на рестарте теряет заголовок контейнера, а
   * getUserMedia между шагами моргает индикатором микрофона и съедает первые
   * слова следующего ответа. Пишем одним куском, шаг переключает только таймер
   * и вопрос на экране — разбор на бэкенде так и рассчитан: он получает один
   * транскрипт всех ответов подряд.
   */
  const nextStep = useCallback(() => {
    if (phaseRef.current !== 'run') return
    if (step + 1 < stepCount) setStep((s) => s + 1)
    else void finish()
  }, [finish, step, stepCount])

  const left = useCountdown(task.answerSeconds, nextStep, true, `${phase}:${step}`)

  /* Хук нельзя вызвать условно, поэтому отсчёт тикает и на intro. Сброс приходит
     эффектом, уже после первой отрисовки run, — без этой строки полоса на кадр
     вспыхивала бы красным 00:00. */
  const shown = left > 0 ? left : task.answerSeconds

  const begin = useCallback(async () => {
    setFeedback(null)
    setFailure(null)
    if (!(await start())) return // причину покажет micError
    startedAtRef.current = Date.now()
    finishingRef.current = false
    setStep(0)
    setPhase('run')
  }, [start])

  const again = useCallback(() => {
    setFeedback(null)
    setTranscript(undefined)
    setFailure(null)
    setDuration(0)
    setAudioUrl(null) // старый URL отзовёт эффект
    blobRef.current = null
    finishingRef.current = false
    setStep(0)
    setPhase('intro')
  }, [])

  const quit = useCallback(() => {
    void stop() // уходим — микрофон обязан погаснуть сразу, а не по размонтированию
    onExit()
  }, [onExit, stop])

  const proceed = useCallback(() => {
    onDone({
      taskId,
      variantId: variant.id,
      durationSec: duration,
      feedback,
      transcript,
      failure: failure ?? undefined,
    })
  }, [duration, failure, feedback, onDone, taskId, transcript, variant.id])

  const question = steps[step]
  const isLast = !progress || progress.index >= progress.total

  return (
    <div className="screen">
      <header className="topbar2">
        <span className="topbar2__brand">SPEAKO</span>
        <span className="statrow__label" style={{ marginTop: 0 }}>
          №{task.id} · {task.label}
          {progress && ` · ${progress.index} из ${progress.total}`}
        </span>
      </header>

      <div className="screen__body">
        {phase === 'intro' && (
          <div className="scroll-soft scroll-soft--onDark" style={scrollArea}>
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 'clamp(12px, 1.8vw, 22px)',
                alignItems: 'flex-start',
                justifyContent: 'center',
                width: '100%',
              }}
            >
              <div className="card2 taskcard" style={{ flex: '1 1 340px', minWidth: 0 }}>
                <Brief text={variant.brief} />
              </div>

              {variant.images ? (
                <div
                  style={{
                    flex: '1 1 280px',
                    minWidth: 0,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 8,
                  }}
                >
                  {variant.imageCaption && (
                    <span
                      style={{
                        color: 'var(--text)',
                        fontWeight: 800,
                        textAlign: 'center',
                        fontSize: 'clamp(13px, 1.6vw, 18px)',
                      }}
                    >
                      {variant.imageCaption}
                    </span>
                  )}
                  <TaskImages srcs={variant.images} alt={variant.imageCaption} maxHeight="min(30vh, 260px)" />
                </div>
              ) : (
                <Mascot />
              )}
            </div>

            {micError && <p className="dialog__err">{micError}</p>}
          </div>
        )}

        {phase === 'run' && (
          <div className="scroll-soft scroll-soft--onDark" style={scrollArea}>
            <RecBadge recording={state === 'recording'} />
            {stepCount > 1 && (
              <span className="statrow__label" style={{ marginTop: 0 }}>
                Вопрос {step + 1} из {stepCount}
              </span>
            )}

            {variant.readText && <div className="readtext">{variant.readText}</div>}
            {variant.images && (
              <TaskImages srcs={variant.images} alt={variant.imageCaption} maxHeight="min(38vh, 340px)" />
            )}
            {!variant.readText && !variant.images && <Mascot />}

            {question && <p style={questionStyle}>{question}</p>}
          </div>
        )}

        {phase === 'analyzing' && (
          <div style={{ textAlign: 'center', color: 'var(--text)' }}>
            <p style={{ fontWeight: 800, fontSize: 'clamp(18px, 2.4vw, 26px)', margin: 0 }}>
              Разбираю ответ…
            </p>
            <p style={{ color: 'var(--text-dim)', marginTop: 8 }}>
              {task.kind === 'monologue'
                ? 'Распознаю речь и считаю по критериям ФИПИ — обычно 5–15 секунд.'
                : 'Распознаю речь и сверяю с заданием — обычно 5–15 секунд.'}
            </p>
          </div>
        )}

        {phase === 'result' && (
          <div className="scroll-soft scroll-soft--onDark" style={scrollArea}>
            <div className="card2" style={{ width: '100%' }}>
              <b>Запись сделана — {fmt(duration)}</b>
              {audioUrl && (
                <audio
                  controls
                  src={audioUrl}
                  style={{ width: '100%', marginTop: 10 }}
                  aria-label="Твоя запись"
                />
              )}
            </div>

            {failure ? (
              <div className="card2" style={{ width: '100%' }}>
                <p style={{ margin: 0 }}>{failure}</p>
                {blobRef.current && (
                  <div className="rowend" style={{ marginTop: 12 }}>
                    <Pill
                      onClick={() => {
                        const b = blobRef.current
                        if (b) void analyze(b)
                      }}
                    >
                      Повторить разбор
                    </Pill>
                  </div>
                )}
              </div>
            ) : (
              feedback && <Report feedback={feedback} transcript={transcript} />
            )}
          </div>
        )}
      </div>

      {phase === 'intro' && (
        <div className="rowbetween">
          <Pill onClick={quit}>QUIT</Pill>
          <Pill onClick={() => void begin()}>START</Pill>
        </div>
      )}

      {phase === 'run' && (
        <div className="rowbetween">
          <Pill onClick={quit}>QUIT</Pill>
          <div style={{ flex: 1, minWidth: 0 }}>
            <CountdownBar
              left={shown}
              total={task.answerSeconds}
              onEnd={() => void finish()}
              endLabel="End task"
            />
          </div>
        </div>
      )}

      {(phase === 'analyzing' || phase === 'result') && (
        <div className="rowbetween">
          <Pill onClick={quit}>В меню</Pill>
          <div style={{ display: 'flex', gap: 10 }}>
            <Pill onClick={again} disabled={phase === 'analyzing'}>
              Ещё раз
            </Pill>
            <Pill onClick={proceed} disabled={phase === 'analyzing'}>
              {isLast ? 'К итогам' : 'Дальше'}
            </Pill>
          </div>
        </div>
      )}
    </div>
  )
}

/* --------------------------------------------------------------- Кусочки */

function TaskImages({
  srcs,
  alt,
  maxHeight,
}: {
  srcs: string[]
  alt?: string
  maxHeight: string
}) {
  return (
    <div className="taskmedia">
      {srcs.map((src) => (
        <img
          key={src}
          src={src}
          alt={alt ?? 'Фотография к заданию'}
          /* flex-basis + minWidth:0: на узком экране картинки переносятся по одной
             на строку, вместо того чтобы распирать контейнер своей шириной. */
          style={{ flex: '1 1 220px', minWidth: 0, maxHeight }}
        />
      ))}
    </div>
  )
}

function RecBadge({ recording }: { recording: boolean }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        color: 'var(--text)',
        fontWeight: 700,
        fontSize: 'clamp(12px, 1.4vw, 15px)',
      }}
      aria-live="polite"
    >
      <span
        style={{
          width: 10,
          height: 10,
          borderRadius: '50%',
          background: recording ? '#ff8f78' : 'rgba(255,255,255,0.35)',
        }}
      />
      {recording ? 'Идёт запись' : 'Микрофон молчит'}
    </span>
  )
}

export function Report({
  feedback,
  transcript,
}: {
  feedback: TaskFeedback
  transcript?: string
}) {
  const criteria = feedback.criteria ?? []
  const errors = feedback.errors ?? []
  const withComment = criteria.filter((c) => c.comment)

  return (
    <>
      <div className="statrow" style={{ width: '100%' }}>
        <div>
          <div className="statrow__value">
            {feedback.score}
            <span className="statrow__unit">/{feedback.max}</span>
          </div>
          <div className="statrow__label">Баллы</div>
        </div>
        {criteria.map((c, i) => (
          <div key={c.key || i}>
            <div className="statrow__value">
              {c.score}
              <span className="statrow__unit">/{c.max}</span>
            </div>
            <div className="statrow__label">{c.name}</div>
          </div>
        ))}
      </div>

      {feedback.summary && (
        <div className="card2" style={{ width: '100%' }}>
          <p style={{ margin: 0 }}>{feedback.summary}</p>
        </div>
      )}

      {withComment.length > 0 && (
        <div className="card2" style={{ width: '100%' }}>
          {withComment.map((c, i) => (
            <p key={c.key || i} style={{ margin: i ? '10px 0 0' : 0 }}>
              <b>{c.name}.</b> {c.comment}
            </p>
          ))}
        </div>
      )}

      {errors.length > 0 && (
        <div className="card2" style={{ width: '100%' }}>
          {errors.map((e, i) => (
            <div className="mistake" key={i}>
              <div>
                <span className="mistake__wrong">{e.quote}</span>
                {' → '}
                <span className="mistake__right">{e.correction}</span>
              </div>
              <div className="mistake__why">
                {e.cat ? `${CAT_LABEL[e.cat] ?? e.cat}: ` : ''}
                {e.explanation}
              </div>
            </div>
          ))}
        </div>
      )}

      {transcript && (
        <details className="card2" style={{ width: '100%' }}>
          <summary style={{ cursor: 'pointer', fontWeight: 700 }}>Что услышал сервер</summary>
          <p style={{ margin: '8px 0 0' }}>{transcript}</p>
        </details>
      )}
    </>
  )
}
