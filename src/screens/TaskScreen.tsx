/**
 * Универсальный экран прохождения задания устной части ЕГЭ (39, 40, 41, 42) —
 * фото 4, 5 и 7 макета. Экран один на все четыре номера намеренно: различия между
 * ними целиком описаны данными в `ege2/tasks.ts` (есть ли текст для чтения,
 * картинки, шаги), и ветвиться нужно по этим полям, а не по номеру задания.
 * Добавится задание — хватит строчки в TASKS.
 *
 * Две фазы из макета: intro (текст задания + START) и run (материал + запись +
 * полоса обратного отсчёта). После записи — разбор для 42 и честная заглушка для
 * остальных: оценку, которой бэкенд не считал, показывать нельзя.
 */
import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'

import { backendUnreachableMessage, httpErrorMessage } from '../backendError'
import { CountdownBar, Mascot, Pill } from '../design/ui'
import { useCountdown } from '../ege/useCountdown'
import { TASKS, markSolved, type TaskId } from '../ege2/tasks'
import { useRecorder } from '../ege2/useRecorder'

const BACKEND = (import.meta.env.VITE_BACKEND_URL ?? '').replace(/\/+$/, '')

interface Criterion {
  key: string
  name: string
  score: number
  max: number
  comment: string
}
interface MonoError {
  cat: string
  quote: string
  correction: string
  explanation: string
}
interface MonoResult {
  transcript: string
  feedback: { summary: string; criteria: Criterion[]; errors: MonoError[] }
}

/* Бэкенд может прислать категорию, которой мы не знаем, — тогда показываем её как есть. */
const CAT_LABEL: Record<string, string> = {
  lex: 'Лексика',
  gram: 'Грамматика',
  phon: 'Произношение',
  logic: 'Логика',
}

type Phase = 'intro' | 'run' | 'analyzing' | 'result'

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

/* Центральная область прокручивается сама: на телефоне текст задания и разбор
   заведомо не влезают, а нижняя строка с QUIT/таймером обязана остаться на экране. */
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
 * `brief` приходит одной строкой с \n и маркерами списка. Без разбора это простыня,
 * в которой ученик не находит, о чём именно его просят спросить.
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
  onExit,
  onFinished,
  demoProgress,
}: {
  taskId: TaskId
  onExit: () => void
  onFinished?: (taskId: TaskId) => void
  /** index — номер задания в прогоне DEMO, считая с единицы: именно так его шлёт App.tsx. */
  demoProgress?: { index: number; total: number }
}) {
  const task = TASKS[taskId]
  const steps = task.steps ?? []
  const stepCount = Math.max(1, steps.length)

  const [phase, setPhase] = useState<Phase>('intro')
  const [step, setStep] = useState(0)
  const [duration, setDuration] = useState(0)
  const [result, setResult] = useState<MonoResult | null>(null)
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

  const analyze = useCallback(async (blob: Blob) => {
    setPhase('analyzing')
    setFailure(null)
    try {
      const fd = new FormData()
      fd.append('audio', blob, 'monologue.webm')
      const res = await fetch(`${BACKEND}/monologue`, { method: 'POST', body: fd })
      // Ответ идёт потоком с «сердцебиением»: пока сервер считает, он шлёт переводы
      // строк, иначе туннель рвёт молчащий запрос. Ведущие \n валидны для JSON, их
      // res.json() проглатывает. Но статус уходит ДО результата, поэтому ошибка
      // приезжает полем detail с кодом 200 — проверяем и код, и поле. Сам json()
      // тоже может упасть: страница ошибки туннеля это HTML, и без try человек
      // увидел бы «Unexpected token <» вместо причины.
      let data: unknown = null
      let parsed = true
      try {
        data = await res.json()
      } catch {
        parsed = false
      }
      const detail =
        parsed && data && typeof data === 'object' && 'detail' in data
          ? String((data as { detail: unknown }).detail)
          : null
      if (!res.ok || !parsed || detail) throw new Error(httpErrorMessage(res.status, detail))
      setResult(data as MonoResult)
    } catch (e) {
      setFailure(
        e instanceof TypeError
          ? backendUnreachableMessage()
          : e instanceof Error
            ? e.message
            : String(e),
      )
    } finally {
      setPhase('result')
    }
  }, [])

  const finish = useCallback(async () => {
    // «End task» и истёкший таймер могут прилететь почти одновременно — второй
    // вызов остановил бы уже остановленный рекордер и отправил пустой blob.
    if (finishingRef.current) return
    finishingRef.current = true
    setDuration(Math.max(0, Math.round((Date.now() - startedAtRef.current) / 1000)))
    setPhase(task.hasAiFeedback ? 'analyzing' : 'result')

    const blob = await stop()
    blobRef.current = blob
    markSolved(task.id)
    setAudioUrl(blob && blob.size ? URL.createObjectURL(blob) : null)

    if (task.hasAiFeedback) {
      if (blob && blob.size) await analyze(blob)
      else {
        setFailure('Запись пустая — микрофон не отдал ни одного кадра. Попробуй ещё раз.')
        setPhase('result')
      }
    }
  }, [analyze, stop, task.hasAiFeedback, task.id])

  /**
   * Граница шагов (40: четыре вопроса, 41: пять). Запись НЕ режем на куски и не
   * перезапускаем: MediaRecorder на рестарте теряет заголовок контейнера, а
   * getUserMedia между шагами моргает индикатором микрофона и съедает первые слова
   * следующего ответа. Пишем одним куском на весь прогон, а шаг переключает только
   * таймер и вопрос на экране. Резать по вопросам придётся, когда на бэкенде
   * появится разбор диалога и интервью, — сейчас такого эндпоинта нет.
   */
  const nextStep = useCallback(() => {
    if (phaseRef.current !== 'run') return // хук отсчёта тикает всегда, шаг листаем только в run
    if (step + 1 < stepCount) setStep((s) => s + 1)
    else void finish()
  }, [finish, step, stepCount])

  const left = useCountdown(task.answerSeconds, nextStep, true, `${phase}:${step}`)

  /* Хук нельзя вызвать условно, поэтому отсчёт тикает и на intro: у задания 40 он
     успевает добежать до нуля, пока ученик читает условие. Сброс приходит эффектом,
     то есть уже ПОСЛЕ первой отрисовки run, — без этой строки полоса на кадр
     вспыхивала бы красным 00:00. Настоящий ноль в run не показывается: тот же тик
     таймера переводит фазу, и полоса уже не рисуется. */
  const shown = left > 0 ? left : task.answerSeconds

  const begin = useCallback(async () => {
    setResult(null)
    setFailure(null)
    if (!(await start())) return // причину покажет micError
    startedAtRef.current = Date.now()
    finishingRef.current = false
    setStep(0)
    setPhase('run')
  }, [start])

  const again = useCallback(() => {
    setResult(null)
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

  const question = steps[step]

  return (
    <div className="screen">
      {/* Вкладок здесь нет (экран задания их не получает), но бренд обязан стоять
          слева, как на всех экранах макета: без него экран задания выглядит как
          чужая страница. Номер задания идёт справа от бренда, приглушённым. */}
      <header className="topbar2">
        <span className="topbar2__brand">SPEAKO</span>
        <span className="statrow__label" style={{ marginTop: 0 }}>
          №{task.id} · {task.label}
          {demoProgress && ` · DEMO ${demoProgress.index} из ${demoProgress.total}`}
        </span>
      </header>

      <div className="screen__body">
        {phase === 'intro' && (
          <div style={scrollArea}>
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
                <Brief text={task.brief} />
              </div>

              {task.images ? (
                <div
                  style={{
                    flex: '1 1 280px',
                    minWidth: 0,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 8,
                  }}
                >
                  {task.imageCaption && (
                    <span
                      style={{
                        color: 'var(--text)',
                        fontWeight: 800,
                        textAlign: 'center',
                        fontSize: 'clamp(13px, 1.6vw, 18px)',
                      }}
                    >
                      {task.imageCaption}
                    </span>
                  )}
                  <TaskImages srcs={task.images} alt={task.imageCaption} maxHeight="min(30vh, 260px)" />
                </div>
              ) : (
                <Mascot />
              )}
            </div>

            {micError && <p className="dialog__err">{micError}</p>}
          </div>
        )}

        {phase === 'run' && (
          <div style={scrollArea}>
            <RecBadge recording={state === 'recording'} />
            {stepCount > 1 && (
              <span className="statrow__label" style={{ marginTop: 0 }}>
                Вопрос {step + 1} из {stepCount}
              </span>
            )}

            {task.readText && <div className="readtext">{task.readText}</div>}
            {task.images && (
              <TaskImages srcs={task.images} alt={task.imageCaption} maxHeight="min(38vh, 340px)" />
            )}
            {!task.readText && !task.images && <Mascot />}

            {question && <p style={questionStyle}>{question}</p>}
          </div>
        )}

        {phase === 'analyzing' && (
          <div style={{ textAlign: 'center', color: 'var(--text)' }}>
            <p style={{ fontWeight: 800, fontSize: 'clamp(18px, 2.4vw, 26px)', margin: 0 }}>
              Разбираю ответ…
            </p>
            <p style={{ color: 'var(--text-dim)', marginTop: 8 }}>
              Сначала распознаю речь, потом считаю по критериям ФИПИ. Это 15–25 секунд —
              длинный ответ распознаётся дольше.
            </p>
          </div>
        )}

        {phase === 'result' && (
          <div style={scrollArea}>
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

            {task.hasAiFeedback ? (
              failure ? (
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
                result && <Report result={result} />
              )
            ) : (
              <div className="card2" style={{ width: '100%' }}>
                <p style={{ margin: 0 }}>
                  Автоматического разбора у задания №{task.id} пока нет. Он написан только для
                  задания 42 (монолог), а оценку, которой никто не считал, показывать нельзя —
                  поэтому здесь только сама запись. Послушай себя: уложился ли в тайминг, нет ли
                  долгих пауз.
                </p>
              </div>
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
            {demoProgress && onFinished && (
              <Pill onClick={() => onFinished(task.id)} disabled={phase === 'analyzing'}>
                Дальше
              </Pill>
            )}
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

function Report({ result }: { result: MonoResult }) {
  const criteria = result.feedback?.criteria ?? []
  const errors = result.feedback?.errors ?? []
  const withComment = criteria.filter((c) => c.comment)

  return (
    <>
      {criteria.length > 0 && (
        <div className="statrow" style={{ width: '100%' }}>
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
      )}

      {result.feedback?.summary && (
        <div className="card2" style={{ width: '100%' }}>
          <p style={{ margin: 0 }}>{result.feedback.summary}</p>
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
                {CAT_LABEL[e.cat] ?? e.cat}: {e.explanation}
              </div>
            </div>
          ))}
        </div>
      )}

      {result.transcript && (
        <details className="card2" style={{ width: '100%' }}>
          <summary style={{ cursor: 'pointer', fontWeight: 700 }}>Что услышал сервер</summary>
          <p style={{ margin: '8px 0 0' }}>{result.transcript}</p>
        </details>
      )}
    </>
  )
}
