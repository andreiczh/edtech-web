/**
 * Разбор задания №42 — макет «66 · Redesign 6» один в один.
 *
 * Сверху карточка: кольцо с баллом из 10, три критерия ФИПИ строками
 * («Содержание 4 балла из 4»), плеер записи. Ниже — РАСШИФРОВКА (что
 * услышал сервер) и КОММЕНТАРИЙ: по карточке на критерий, первая раскрыта,
 * остальные свёрнуты в «Развернуть комментарий», как в макете. Подписи
 * критериев — названия ФИПИ; балл и текст — с сервера (ege_scoring: 4+3+3).
 * Подписи «ЗАДАНИЕ N» на этом экране в макете нет.
 */
import { useCallback, useState } from 'react'

import type { TaskFeedback } from '../ege2/feedback'
import type { TaskId, TaskVariant } from '../ege2/tasks'
import { Ambient } from './Ambient'
import { BackButton, MiniDisagree, ResultBar, StarButton } from './ResultBits'
import { ErrorsCard, SummaryCard, disputeBase } from './ResultExtras'
import { Player } from './ResultScreen'

const SHORT = ['Содержание', 'Организация', 'Лексика']
const LONG = [
  'Решение коммуникативной задачи (содержание)',
  'Организация высказывания',
  'Языковое оформление высказывания',
]

const pts = (n: number) => (n === 1 ? 'балл' : n >= 2 && n <= 4 ? 'балла' : 'баллов')

export function ResultScreen42({
  taskId,
  variant,
  feedback,
  transcript,
  failure,
  blob,
  seconds,
  onQuit,
  onNext,
  onBack,
}: {
  taskId: TaskId
  variant: TaskVariant
  feedback: TaskFeedback | null
  transcript?: string
  failure: string | null
  blob: Blob | null
  seconds: number
  onQuit: () => void
  onNext: () => void
  onBack?: () => void
}) {
  const criteria = (feedback?.criteria ?? []).slice(0, 3)
  const score = feedback?.score ?? null
  const max = feedback?.max ?? 10
  const ringClass = feedback === null ? 'q-ring--none' : score ? '' : 'q-ring--zero'
  const [open, setOpen] = useState(0)
  const dispute = feedback ? disputeBase(taskId, variant, feedback, transcript) : null
  const [, setProgress] = useState(0)
  const onProgress = useCallback((f: number) => setProgress(f), [])

  return (
    <div className="mini__frame">
      <Ambient />
      {onBack && <BackButton onBack={onBack} />}
      <StarButton taskId={taskId} variantId={variant.id} />
      <div className="mini__scroll">
        <div className="q-summary mr-summary">
          <div className={`q-ring ${ringClass}`} aria-hidden="true" />
          <div className="q-score" aria-hidden="true">
            {score ?? '—'}
          </div>
          <div className="q-of" aria-hidden="true">
            из {max} {pts(max)}
          </div>
          <span className="m-sr">
            Балл: {score ?? 'нет'} из {max}.
          </span>
          {feedback ? (
            <ul className="mr-crit">
              {criteria.map((c, i) => (
                <li key={i}>
                  <b>{SHORT[i] ?? c.name}</b>
                  <span>
                    {c.score} {pts(c.score)} из {c.max}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="q-fail">{failure ?? 'Разбор не выполнен.'}</div>
          )}
          {blob && <Player blob={blob} seconds={seconds} onProgress={onProgress} />}
        </div>

        {feedback && (
          <>
            <section className="mr-card" aria-label="Расшифровка">
              <h2 className="mr-title">РАСШИФРОВКА</h2>
              <p className="mr-text">{transcript?.trim() || '— расшифровка не получена —'}</p>
            </section>

            <h2 className="mr-h2">КОММЕНТАРИЙ</h2>
            {criteria.map((c, i) => (
              <div className="mr-item" key={i}>
                <div className="mr-head">
                  <span className="mr-badge" aria-hidden="true">
                    {i + 1}
                  </span>
                  <span className="mr-name">{LONG[i] ?? c.name}</span>
                  <span className="mr-val">
                    {c.score} {pts(c.score)} из {c.max}
                  </span>
                </div>
                {open === i ? (
                  <div className="mr-comment">
                    {c.comment?.trim() || 'Без замечаний.'}
                    {dispute && (
                      <MiniDisagree
                        ctx={{
                          ...dispute,
                          target: 'criterion',
                          targetKey: c.key,
                          targetLabel: `${LONG[i] ?? c.name} — ${c.score} из ${c.max}`,
                          score: c.score,
                          max: c.max,
                        }}
                      />
                    )}
                  </div>
                ) : (
                  <button
                    type="button"
                    className="m-btn mr-comment mr-comment--toggle"
                    onClick={() => setOpen(i)}
                    aria-expanded={false}
                    aria-label={`Развернуть комментарий: ${LONG[i] ?? c.name}`}
                  >
                    Развернуть комментарий
                  </button>
                )}
              </div>
            ))}
            {dispute && (
              <>
                <SummaryCard feedback={feedback} />
                <ErrorsCard errors={feedback.errors ?? []} dispute={dispute} />
                <MiniDisagree center label="не согласен с баллом" ctx={dispute} />
              </>
            )}
          </>
        )}
        <div className="m-pad" />
      </div>

      <ResultBar onQuit={onQuit} onNext={onNext} />
    </div>
  )
}
