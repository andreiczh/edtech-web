import { useState, useEffect } from 'react'
import { STEPS, TASK_TITLES, fmt, type Step } from './examFlow'
import { useCountdown } from './useCountdown'
import { ExamFrame, ExamButton, Progress, Material, RecordingIndicator } from './ExamKit'
import { ExamResults } from './ExamResults'

/**
 * Тренажёр устного ЕГЭ: пошаговый флоу станции (структура, без контента).
 * Порядок и тайминги — в examFlow.ts. Экраны листаются кнопками; таймеры
 * показывают логику; экран «Be ready» (3 сек) переходит сам. Финал — экран
 * результата (ИИ-разбор). onComplete отмечает вариант пройденным.
 */
export function EgeTrainer({
  variant,
  onExit,
  onComplete,
}: {
  variant?: number
  onExit?: () => void
  onComplete?: () => void
} = {}) {
  const [i, setI] = useState(0)
  const step = STEPS[i]
  const next = () => setI((n) => Math.min(n + 1, STEPS.length - 1))
  const back = () => setI((n) => Math.max(n - 1, 0))
  const restart = () => setI(0)
  const canBack = i > 0

  // Достигли экрана результата → вариант считается пройденным
  useEffect(() => {
    if (step.kind === 'finish') onComplete?.()
    // onComplete намеренно не в зависимостях: вызываем один раз при входе в finish
  }, [step.kind]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="ege">
      {(variant != null || onExit) && (
        <div className="ege__top">
          {onExit ? (
            <button type="button" className="ege__exit" onClick={onExit}>
              ← К выбору варианта
            </button>
          ) : (
            <span />
          )}
          {variant != null && <span className="ege__variant">Вариант {variant}</span>}
        </div>
      )}
      <StepBar index={i} total={STEPS.length} />
      <Screen
        key={i}
        step={step}
        variant={variant}
        onNext={next}
        onBack={canBack ? back : undefined}
        onRestart={restart}
        onExit={onExit}
      />
    </div>
  )
}

function StepBar({ index, total }: { index: number; total: number }) {
  return (
    <div className="stepbar" aria-hidden="true">
      {Array.from({ length: total }).map((_, k) => (
        <span className={`stepbar__seg${k <= index ? ' is-done' : ''}`} key={k} />
      ))}
    </div>
  )
}

function Screen({
  step,
  variant,
  onNext,
  onBack,
  onRestart,
  onExit,
}: {
  step: Step
  variant?: number
  onNext: () => void
  onBack?: () => void
  onRestart: () => void
  onExit?: () => void
}) {
  switch (step.kind) {
    case 'registration':
      return <Registration onNext={onNext} />
    case 'instruction':
      return <Instruction onNext={onNext} onBack={onBack} />
    case 'important':
      return <Important onNext={onNext} onBack={onBack} />
    case 'melody':
      return <Melody onNext={onNext} onBack={onBack} />
    case 'prep':
      return <Prep step={step} onNext={onNext} onBack={onBack} />
    case 'ready':
      return <Ready step={step} onNext={onNext} onBack={onBack} />
    case 'answer':
      return <Answer step={step} onNext={onNext} onBack={onBack} />
    case 'questions':
      return <Questions step={step} onNext={onNext} onBack={onBack} />
    case 'finish':
      return <ExamResults variant={variant} onRestart={onRestart} onExit={onExit} />
  }
}

/* ----------------------------------------------------------------- Nav */

function Nav({
  onBack,
  primary,
  onPrimary,
}: {
  onBack?: () => void
  primary: string
  onPrimary: () => void
}) {
  return (
    <div className="exam__nav">
      {onBack ? (
        <ExamButton variant="ghost" onClick={onBack}>
          Назад
        </ExamButton>
      ) : (
        <span />
      )}
      <ExamButton onClick={onPrimary}>{primary}</ExamButton>
    </div>
  )
}

/* -------------------------------------------------------- Вступление */

function Registration({ onNext }: { onNext: () => void }) {
  return (
    <ExamFrame
      eyebrow="Английский язык · устная часть"
      title="Единый государственный экзамен"
      footer={<Nav primary="Начать" onPrimary={onNext} />}
    >
      <div className="reg">
        <label className="reg__label">Введите номер вашего бланка регистрации</label>
        <div className="reg__fields">
          <input className="reg__in reg__in--s" maxLength={1} aria-label="Регион" />
          <input className="reg__in" maxLength={6} aria-label="Код" />
          <input className="reg__in" maxLength={6} aria-label="Номер" />
        </div>
        <p className="exam-note">Плейсхолдер: поля структурные, без проверки.</p>
      </div>
    </ExamFrame>
  )
}

function Instruction({ onNext, onBack }: { onNext: () => void; onBack?: () => void }) {
  return (
    <ExamFrame title="Инструкция" footer={<Nav onBack={onBack} primary="Далее" onPrimary={onNext} />}>
      <div className="info">
        <MonitorIcon />
        <div className="info__text">
          <p>Устная часть состоит из <b>4 заданий</b>.</p>
          <p>Каждое следующее задание выдаётся после завершения предыдущего.</p>
          <p>В течение всего ответа ведётся аудиозапись.</p>
          <p>Общее время, включая подготовку, — около <b>15 минут</b>.</p>
        </div>
      </div>
    </ExamFrame>
  )
}

function Important({ onNext, onBack }: { onNext: () => void; onBack?: () => void }) {
  return (
    <ExamFrame title="Важно!" footer={<Nav onBack={onBack} primary="Далее" onPrimary={onNext} />}>
      <div className="info">
        <MicIcon />
        <div className="info__text">
          <p>Постарайтесь полностью выполнить поставленные задачи.</p>
          <p>Говорите ясно и чётко, не отходите от темы и следуйте плану ответа.</p>
          <p>Так вы сможете набрать наибольшее количество баллов.</p>
          <p className="info__wish">Желаем успеха!</p>
        </div>
      </div>
    </ExamFrame>
  )
}

const MELODIES = ['Мелодия 1', 'Мелодия 2', 'Мелодия 3', 'Без мелодии']

function Melody({ onNext, onBack }: { onNext: () => void; onBack?: () => void }) {
  const [selected, setSelected] = useState('Без мелодии')
  return (
    <ExamFrame
      title="Выбор фоновой мелодии"
      footer={<Nav onBack={onBack} primary="Далее" onPrimary={onNext} />}
    >
      <ul className="melody">
        {MELODIES.map((m) => {
          const isNone = m === 'Без мелодии'
          const active = selected === m
          return (
            <li key={m}>
              <button
                type="button"
                className={`melody__row${active ? ' is-active' : ''}`}
                onClick={() => setSelected(m)}
                aria-pressed={active}
              >
                <span className="melody__check">{active ? '✓' : ''}</span>
                <span className="melody__name">{m}</span>
                {!isNone && (
                  <>
                    <span className="melody__play" aria-hidden="true">
                      ▶
                    </span>
                    <span className="melody__len">03:00</span>
                  </>
                )}
              </button>
            </li>
          )
        })}
      </ul>
    </ExamFrame>
  )
}

/* ------------------------------------------------------------ Задания */

function Prep({
  step,
  onNext,
  onBack,
}: {
  step: Extract<Step, { kind: 'prep' }>
  onNext: () => void
  onBack?: () => void
}) {
  const left = useCountdown(step.seconds)
  const done = (step.seconds - left) / step.seconds
  return (
    <ExamFrame
      eyebrow={`Задание ${step.task} · подготовка`}
      title={TASK_TITLES[step.task]}
      timer={
        <span>
          Подготовка <b className="num">{fmt(left)}</b>
        </span>
      }
      footer={
        <>
          <Progress value={done} tone="mint" />
          <Nav onBack={onBack} primary="Далее" onPrimary={onNext} />
        </>
      }
    >
      <Material kind={step.material} />
      <p className="exam-note">Идёт время на подготовку. Ознакомьтесь с заданием.</p>
    </ExamFrame>
  )
}

function Ready({
  step,
  onNext,
  onBack,
}: {
  step: Extract<Step, { kind: 'ready' }>
  onNext: () => void
  onBack?: () => void
}) {
  const left = useCountdown(3, onNext, true)
  return (
    <ExamFrame
      eyebrow={`Задание ${step.task}`}
      title="Be ready for the answer"
      footer={<Nav onBack={onBack} primary="Пропустить" onPrimary={onNext} />}
    >
      <div className="ready">
        <span className="ready__num num">{String(Math.max(left, 0)).padStart(2, '0')}</span>
        <span className="ready__label">seconds</span>
      </div>
    </ExamFrame>
  )
}

function Answer({
  step,
  onNext,
  onBack,
}: {
  step: Extract<Step, { kind: 'answer' }>
  onNext: () => void
  onBack?: () => void
}) {
  const left = useCountdown(step.seconds)
  const done = (step.seconds - left) / step.seconds
  return (
    <ExamFrame
      eyebrow={`Задание ${step.task} · ответ`}
      title={TASK_TITLES[step.task]}
      timer={
        <span>
          Ответ <b className="num">{fmt(left)}</b>
        </span>
      }
      footer={
        <>
          <Progress value={done} tone="coral" />
          <Nav onBack={onBack} primary="Завершить ответ" onPrimary={onNext} />
        </>
      }
    >
      <Material kind={step.material} />
      <RecordingIndicator timeLabel={fmt(left)} />
    </ExamFrame>
  )
}

function Questions({
  step,
  onNext,
  onBack,
}: {
  step: Extract<Step, { kind: 'questions' }>
  onNext: () => void
  onBack?: () => void
}) {
  const [q, setQ] = useState(1)
  const left = useCountdown(step.seconds, undefined, false, q)
  const done = (step.seconds - left) / step.seconds
  const isLast = q >= step.count

  const goBack = () => {
    if (q > 1) setQ((n) => n - 1)
    else onBack?.()
  }
  const goNext = () => {
    if (!isLast) setQ((n) => n + 1)
    else onNext()
  }

  return (
    <ExamFrame
      eyebrow={`Задание ${step.task} · ответ`}
      title={TASK_TITLES[step.task]}
      timer={
        <span>
          Ответ <b className="num">{fmt(left)}</b>
        </span>
      }
      footer={
        <>
          <Progress value={done} tone="coral" />
          <Nav onBack={q > 1 || onBack ? goBack : undefined} primary={isLast ? 'Завершить' : 'Следующий вопрос'} onPrimary={goNext} />
        </>
      }
    >
      <Material kind={step.material} />
      <div className="qcount">
        Вопрос <b>{q}</b> из {step.count}
      </div>
      <RecordingIndicator timeLabel={fmt(left)} />
    </ExamFrame>
  )
}

/* -------------------------------------------------------------- Иконки */

function MonitorIcon() {
  return (
    <svg className="info__icon" viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <rect x="6" y="9" width="36" height="24" rx="3" stroke="currentColor" strokeWidth="2.5" />
      <path d="M18 39h12M24 33v6" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  )
}

function MicIcon() {
  return (
    <svg className="info__icon" viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <rect x="19" y="8" width="10" height="20" rx="5" stroke="currentColor" strokeWidth="2.5" />
      <path d="M14 23a10 10 0 0 0 20 0M24 33v7" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  )
}
