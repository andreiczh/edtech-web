/**
 * Сессия заданий: пять вариантов одного номера подряд (или DEMO — по одному
 * варианту каждого номера), с общим итогом в конце.
 *
 * Появился по прямой просьбе: клик по №39 должен давать не одно случайное
 * задание, а серию ранее не решённых с фидбэком по проделанной работе.
 *
 * Отметки «пройдено» и последний разбор пишутся здесь, а не в TaskScreen:
 * экран варианта остаётся чистым исполнителем, а всё, что касается прогресса,
 * живёт в одном месте.
 */
import { useCallback, useState, type CSSProperties } from 'react'

import { Pill } from '../design/ui'
import {
  TASKS,
  markVariantSolved,
  saveTaskFeedback,
  variantById,
  type TaskId,
} from '../ege2/tasks'
import { TaskScreen, type VariantResult } from './TaskScreen'

export interface SessionItem {
  taskId: TaskId
  variantId: string
}

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

const BLOCK: CSSProperties = { width: 'min(100%, 940px)' }

export function SessionScreen({
  items,
  onExit,
  onRestart,
}: {
  items: SessionItem[]
  onExit: () => void
  /** «Пройти ещё раз» на итогах: родитель собирает новую сессию (уже с учётом
      только что поставленных отметок) и пересоздаёт экран. */
  onRestart: () => void
}) {
  const [index, setIndex] = useState(0)
  const [results, setResults] = useState<VariantResult[]>([])

  const handleDone = useCallback((r: VariantResult) => {
    markVariantSolved(r.variantId)
    if (r.feedback) {
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
    setResults((prev) => [...prev, r])
    setIndex((i) => i + 1)
  }, [])

  if (index >= items.length) {
    return <SessionSummary results={results} onExit={onExit} onRestart={onRestart} />
  }

  const item = items[index]
  const variant = variantById(item.taskId, item.variantId)
  if (!variant) {
    // Битый id варианта — так бывает только при ошибке в коде, но падать белым
    // экраном из-за этого нельзя.
    onExit()
    return null
  }

  return (
    <TaskScreen
      /* key пересоздаёт экран между вариантами: без него остались бы таймеры,
         запись и результат предыдущего варианта. Заодно каждый вариант получает
         свою анимацию появления. */
      key={variant.id}
      taskId={item.taskId}
      variant={variant}
      progress={{ index: index + 1, total: items.length }}
      onExit={onExit}
      onDone={handleDone}
    />
  )
}

/* ------------------------------------------------------------------ Итоги */

function SessionSummary({
  results,
  onExit,
  onRestart,
}: {
  results: VariantResult[]
  onExit: () => void
  onRestart: () => void
}) {
  const graded = results.filter((r) => r.feedback)
  const score = graded.reduce((s, r) => s + (r.feedback?.score ?? 0), 0)
  const max = graded.reduce((s, r) => s + (r.feedback?.max ?? 0), 0)
  const speech = results.reduce((s, r) => s + r.durationSec, 0)
  const mistakes = results.flatMap((r) =>
    (r.feedback?.errors ?? []).map((e) => ({ ...e, taskId: r.taskId })),
  )

  return (
    <div className="screen">
      <header className="topbar2">
        <span className="topbar2__brand">SPEAKO</span>
        <span className="statrow__label" style={{ marginTop: 0 }}>
          итоги сессии
        </span>
      </header>

      <div
        className="screen__body scroll-soft scroll-soft--onDark"
        style={{ overflowY: 'auto', justifyContent: 'safe center', padding: '6px 10px' }}
      >
        <div className="statrow" style={BLOCK}>
          <div>
            <div className="statrow__value">{results.length}</div>
            <div className="statrow__label">Заданий пройдено</div>
          </div>
          <div>
            <div className="statrow__value">{fmt(speech)}</div>
            <div className="statrow__label">Речи записано</div>
          </div>
          {max > 0 && (
            <div>
              <div className="statrow__value">
                {score}
                <span className="statrow__unit">/{max}</span>
              </div>
              <div className="statrow__label">Баллы разбора</div>
            </div>
          )}
        </div>

        {/* По варианту: что пройдено и с каким счётом */}
        <div
          style={{
            ...BLOCK,
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'center',
            gap: 'clamp(8px, 1.4vw, 14px)',
          }}
        >
          {results.map((r) => (
            <div
              key={r.variantId}
              className="card2"
              style={{ flex: '1 1 150px', maxWidth: 220, padding: '10px 14px', textAlign: 'center' }}
            >
              <div style={{ fontWeight: 800 }}>
                №{r.taskId} · {TASKS[r.taskId].label}
              </div>
              <div className="card2__sub">вариант {r.variantId.split('-')[1]}</div>
              <div className="card2__sub">
                {r.feedback
                  ? `${r.feedback.score}/${r.feedback.max} · ошибок: ${r.feedback.errors?.length ?? 0}`
                  : (r.failure ?? 'разбор не выполнен')}
              </div>
            </div>
          ))}
        </div>

        {mistakes.length > 0 && (
          <div className="card2" style={BLOCK}>
            <p style={{ margin: '0 0 10px', fontWeight: 800 }}>Над чем поработать</p>
            {mistakes.slice(0, 12).map((m, i) => (
              <div className="mistake" key={i}>
                <div>
                  <span className="mistake__wrong">{m.quote}</span>
                  {' → '}
                  <span className="mistake__right">{m.correction}</span>
                </div>
                <div className="mistake__why">
                  №{m.taskId}: {m.explanation}
                </div>
              </div>
            ))}
            {mistakes.length > 12 && (
              <p className="card2__sub" style={{ marginTop: 8 }}>
                Показаны первые 12 из {mistakes.length} — остальные смотри в разборах заданий.
              </p>
            )}
          </div>
        )}

        {mistakes.length === 0 && graded.length > 0 && (
          <div className="card2" style={BLOCK}>
            <p style={{ margin: 0 }}>
              Разбор не нашёл ошибок, которые стоило бы вынести отдельно. Отличная сессия!
            </p>
          </div>
        )}
      </div>

      <div className="rowbetween">
        <Pill onClick={onExit}>В меню</Pill>
        <Pill onClick={onRestart}>Пройти ещё раз</Pill>
      </div>
    </div>
  )
}
