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

import { useCurrentPersona } from '../account/me'
import { ConfirmDialog, CountdownBar, Mascot, Pill } from '../design/ui'
import { askAloud } from '../ege2/askAloud'
import { requestTaskFeedback, type TaskFeedback } from '../ege2/feedback'
import { TASKS, feedbackPayload, type TaskId, type TaskVariant } from '../ege2/tasks'
import { useCountdown } from '../ege2/useCountdown'
import { ResultView } from './ResultView'
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

/** prep — подготовка по таймингу экзамена: видно задание и материал, идёт
    отсчёт, микрофон ещё НЕ пишет. Запись стартует сама по концу подготовки. */
type Phase = 'intro' | 'prep' | 'run' | 'analyzing' | 'result'


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

  /* Интервью (№41) слушают, а не читают: вопрос ЗВУЧИТ, на экране его нет.
     Показываем текст только если озвучить не удалось — задание без вопроса
     хуже, чем задание в упрощённом виде. */
  const spoken = task.kind === 'interview'
  const [asking, setAsking] = useState(false)
  const [showQuestion, setShowQuestion] = useState(!spoken)

  const { state, error: micError, start, stop, pause, resume } = useRecorder()

  const phaseRef = useRef(phase)
  phaseRef.current = phase
  const askingRef = useRef(false)
  askingRef.current = asking
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
          sessionDone: !progress || progress.index >= progress.total,
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

  /** Запуск ЗАПИСИ — по концу подготовки (таймером) или кнопкой «Отвечать». */
  const startRun = useCallback(async () => {
    if (phaseRef.current === 'run') return
    if (!(await start())) {
      // Микрофон не дали — возвращаемся на intro, где micError объяснит причину.
      setPhase('intro')
      return
    }
    startedAtRef.current = Date.now()
    finishingRef.current = false
    setStep(0)
    setPhase('run')
  }, [start])

  /**
   * Граница шагов (40: четыре вопроса, 41: пять). Запись НЕ режем на куски и не
   * перезапускаем: MediaRecorder на рестарте теряет заголовок контейнера, а
   * getUserMedia между шагами моргает индикатором микрофона и съедает первые
   * слова следующего ответа. Пишем одним куском, шаг переключает только таймер
   * и вопрос на экране — разбор на бэкенде так и рассчитан: он получает один
   * транскрипт всех ответов подряд.
   */
  const onTimerDone = useCallback(() => {
    if (phaseRef.current === 'prep') {
      // Подготовка кончилась — экзаменационная логика: ответ начинается сам.
      void startRun()
      return
    }
    if (phaseRef.current !== 'run') return
    if (askingRef.current) return // вопрос ещё звучит — время ответа не пошло
    if (step + 1 < stepCount) setStep((s) => s + 1)
    else void finish()
  }, [finish, startRun, step, stepCount])

  /** Закончил отвечать раньше срока — не сиди в тишине.
   *
   * Просьба тестировщика: «я завершил этот вопрос, а время осталось». Раньше
   * единственная кнопка на этом экране завершала ЗАДАНИЕ целиком, и досрочно
   * ответивший должен был либо молчать в микрофон двадцать секунд, либо
   * оборвать себе оставшиеся вопросы. Делаем то же, что делает таймер, только
   * по кнопке: на последнем шаге — завершение, до него — следующий вопрос.
   *
   * Пока ЗВУЧИТ вопрос (интервью), кнопка не работает: перескок в этот момент
   * означал бы ответ на невыслушанный вопрос. */
  const nextStep = useCallback(() => {
    if (askingRef.current) return
    if (step + 1 < stepCount) setStep((s) => s + 1)
    else void finish()
  }, [finish, step, stepCount])

  /* На подготовке тикает prepSeconds, на ответе — answerSeconds на каждый шаг.
     `asking` в ключе сброса не для красоты: пока звучит вопрос, время ответа
     идти не должно, а по концу вопроса отсчёт обязан начаться заново с полных
     сорока секунд — иначе аудирование съедало бы время самого ответа. */
  const phaseSeconds = phase === 'prep' ? task.prepSeconds : task.answerSeconds
  const left = useCountdown(phaseSeconds, onTimerDone, true, `${phase}:${step}:${asking}`)

  /* Хук нельзя вызвать условно, поэтому отсчёт тикает и на intro. Сброс приходит
     эффектом, уже после первой отрисовки prep/run, — без этой строки полоса на
     кадр вспыхивала бы красным 00:00. */
  const shown = left > 0 ? left : phaseSeconds

  /* Вопрос интервью звучит вслух перед каждым ответом.
   *
   * Микрофон на это время СТАВИТСЯ НА ПАУЗУ: иначе голос экзаменатора попадёт
   * в ту же запись, а значит и в расшифровку, и его посчитают ответом ученика.
   * Пауза, а не перезапуск: перезапуск ломает контейнер записи (см. useRecorder).
   */
  useEffect(() => {
    if (!spoken || phase !== 'run') return
    const text = steps[step]
    if (!text) return
    const ac = new AbortController()
    let alive = true
    setAsking(true)
    pause()
    void askAloud(text, ac.signal).then((ok) => {
      if (!alive) return
      // Не прозвучало — показываем текстом. Задание станет проще, чем на
      // экзамене, но останется выполнимым; молчащий экран не оставляет шансов.
      if (!ok) setShowQuestion(true)
      resume()
      setAsking(false)
    })
    return () => {
      alive = false
      ac.abort()
      resume()
    }
  }, [pause, phase, resume, spoken, step, steps])

  const begin = useCallback(async () => {
    setFeedback(null)
    setFailure(null)
    // Сначала подготовка по таймингу экзамена; если её нет — сразу запись.
    if (task.prepSeconds > 0) setPhase('prep')
    else await startRun()
  }, [startRun, task.prepSeconds])

  const again = useCallback(() => {
    setFeedback(null)
    setTranscript(undefined)
    setFailure(null)
    setDuration(0)
    setAudioUrl(null) // старый URL отзовёт эффект
    blobRef.current = null
    finishingRef.current = false
    setStep(0)
    setShowQuestion(!spoken) // новая попытка — снова слушаем, а не читаем
    setPhase('intro')
  }, [spoken])

  /* Выход спрашиваем ТОЛЬКО когда есть что терять: на вводном экране и на
     разборе терять нечего, и лишнее окно там просто раздражает. */
  const [askQuit, setAskQuit] = useState(false)
  const persona = useCurrentPersona()

  const quitNow = useCallback(() => {
    void stop() // уходим — микрофон обязан погаснуть сразу, а не по размонтированию
    onExit()
  }, [onExit, stop])

  const quit = useCallback(() => {
    if (phaseRef.current === 'prep' || phaseRef.current === 'run') setAskQuit(true)
    else quitNow()
  }, [quitNow])

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
      {askQuit && (
        <ConfirmDialog
          title={persona?.quit.title ?? 'Выйти из задания?'}
          body={
            persona?.quit.body ??
            'Ответ не будет разобран, а прогресс по этому варианту не засчитается.'
          }
          stay={persona?.quit.stay ?? 'Продолжить'}
          leave={persona?.quit.leave ?? 'Выйти'}
          onStay={() => setAskQuit(false)}
          onLeave={() => {
            setAskQuit(false)
            quitNow()
          }}
        />
      )}

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

        {phase === 'prep' && (
          <div className="scroll-soft scroll-soft--onDark" style={scrollArea}>
            <span className="statrow__label" style={{ marginTop: 0 }}>
              Подготовка — запись ещё не идёт
            </span>
            <div className="card2 taskcard" style={{ width: '100%' }}>
              <Brief text={variant.brief} />
            </div>
            {variant.readText && <div className="readtext">{variant.readText}</div>}
            {variant.images && (
              <TaskImages srcs={variant.images} alt={variant.imageCaption} maxHeight="min(30vh, 280px)" />
            )}
            <Mascot />
          </div>
        )}

        {phase === 'run' && (
          <div className="scroll-soft scroll-soft--onDark" style={scrollArea}>
            <RecBadge recording={state === 'recording' && !asking} />
            {stepCount > 1 && (
              <span className="statrow__label" style={{ marginTop: 0 }}>
                Вопрос {step + 1} из {stepCount}
              </span>
            )}
            {asking && (
              <span className="statrow__label" style={{ marginTop: 0 }}>
                Слушай вопрос — запись начнётся сразу после него
              </span>
            )}

            {variant.readText && <div className="readtext">{variant.readText}</div>}
            {variant.images && (
              <TaskImages srcs={variant.images} alt={variant.imageCaption} maxHeight="min(38vh, 340px)" />
            )}
            {!variant.readText && !variant.images && <Mascot />}

            {/* Пункты плана обязаны быть перед глазами ВО ВРЕМЯ ответа, а не
                только на подготовке: по ним человек и говорит, и по ним же его
                оценивают. Раньше они пропадали вместе с экраном подготовки —
                жалоба тестировщика («пропадают пункты, по которым нужно
                рассказывать»). Показываем там, где нет пошаговых вопросов:
                у монолога и чтения. У 40 и 41 шаг задаёт вопрос сам. */}
            {!steps.length && task.kind !== 'reading' && (
              <div className="card2 taskcard" style={{ width: '100%' }}>
                <Brief text={variant.brief} />
              </div>
            )}

            {/* У интервью вопрос на экране НЕ печатается: по формату его
                воспринимают на слух. Текст появится только если озвучка
                отказала (showQuestion). */}
            {question && showQuestion && <p style={questionStyle}>{question}</p>}
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

            {failure ? (
              <div className="card2" style={{ width: '100%' }}>
                <p style={{ margin: 0 }}>{failure}</p>
                {blobRef.current && (
                  <>
                    {/* Кнопка шлёт ТУ ЖЕ САМУЮ запись, и об этом надо сказать
                        прямо. Тестировщик жал её и считал, что «ничего не
                        происходит»: разбор честно повторялся и упирался в ту
                        же причину, а выход был в соседней кнопке. */}
                    <p style={{ margin: '8px 0 0', fontSize: 13, color: 'var(--card-ink-dim)' }}>
                      «Разобрать заново» отправит ту же запись ещё раз — помогает,
                      когда виноват был сервер. Если дело в самой записи, жми
                      «Ещё раз» внизу: он даст записать ответ заново.
                    </p>
                    <div className="rowend" style={{ marginTop: 12 }}>
                      <Pill
                        onClick={() => {
                          const b = blobRef.current
                          if (b) void analyze(b)
                        }}
                      >
                        Разобрать заново
                      </Pill>
                    </div>
                  </>
                )}
              </div>
            ) : (
              feedback && (
                <ResultView
                  taskId={task.id}
                  feedback={feedback}
                  transcript={transcript}
                  reference={variant.readText}
                  audioUrl={audioUrl}
                  variantId={variant.id}
                  variant={variant}
                />
              )
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

      {phase === 'prep' && (
        <div className="rowbetween">
          <Pill onClick={quit}>QUIT</Pill>
          <div style={{ flex: 1, minWidth: 0 }}>
            <CountdownBar
              left={shown}
              total={task.prepSeconds}
              onEnd={() => void startRun()}
              endLabel="Отвечать"
            />
          </div>
        </div>
      )}

      {phase === 'run' && (
        <div className="rowbetween">
          <Pill onClick={quit}>QUIT</Pill>
          <div style={{ flex: 1, minWidth: 0 }}>
            <CountdownBar
              left={shown}
              total={task.answerSeconds}
              onEnd={nextStep}
              endLabel={
                asking
                  ? 'Слушай вопрос'
                  : step + 1 < stepCount
                    ? 'Следующий вопрос'
                    : 'Завершить'
              }
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
