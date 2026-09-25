/**
 * Разбор задания №40 — макет «66 · Redesign 31» один в один; тем же экраном
 * идёт интервью №41 (пять вопросов, макета разбора у него нет).
 *
 * Сверху карточка: кольцо с баллом (мятное — балл есть, коралловое — ноль),
 * список «ВОПРОС №N засчитан / не засчитан» по критериям сервера, плеер
 * записи. Ниже — по карточке на вопрос: «ваш ответ» — что услышано, «лучше»
 * — для зачтённого «Ваш ответ хорош! Так держать!» (как в макете), для
 * незачтённого — как стоило спросить (correction сервера) и мелко причина
 * отказа. В макете незачтённого состояния нет; причина — единственное
 * добавление: без неё карточка ничему не учит.
 */
import { useCallback, useState } from 'react'

import type { TaskFeedback } from '../ege2/feedback'
import type { TaskId, TaskVariant } from '../ege2/tasks'
import { Ambient } from './Ambient'
import { BackButton, MiniDisagree, ResultBar, StarButton } from './ResultBits'
import { ErrorsCard, SummaryCard, TranscriptCard, disputeBase } from './ResultExtras'
import { Player } from './ResultScreen'

const PRAISE = 'Ваш ответ хорош! Так держать!'

export function ResultScreen40({
  no,
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
  no: number
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
  const criteria = feedback?.criteria ?? []
  const count = Math.max(variant.steps?.length ?? 0, criteria.length, 1)
  const interview = taskId === 41
  const dispute = feedback ? disputeBase(taskId, variant, feedback, transcript) : null
  const score = feedback?.score ?? null
  const max = feedback?.max ?? count
  const ringClass = feedback === null ? 'q-ring--none' : score ? '' : 'q-ring--zero'
  // Плеер двигает ничего: у вопросов нет текста для подсветки. Заглушка нужна
  // самому плееру — он один на оба разбора.
  const [, setProgress] = useState(0)
  const onProgress = useCallback((f: number) => setProgress(f), [])

  return (
    <div className="mini__frame">
      <Ambient />
      {onBack && <BackButton onBack={onBack} />}
      <StarButton taskId={taskId} variantId={variant.id} />
      <div className="mini__scroll">
        <span className="m-label">ЗАДАНИЕ {no}</span>

        <div className="q-summary">
          <div className={`q-ring ${ringClass}`} aria-hidden="true" />
          <div className="q-score" aria-hidden="true">
            {score ?? '—'}
          </div>
          <div className="q-of" aria-hidden="true">
            из {max} {max === 1 ? 'балла' : max >= 2 && max <= 4 ? 'баллов' : 'баллов'}
          </div>
          <span className="m-sr">
            Балл: {score ?? 'нет'} из {max}.
          </span>
          {feedback ? (
            <ol className="q-list">
              {Array.from({ length: count }, (_, i) => {
                const c = criteria[i]
                const ok = !!c && c.score >= c.max
                return (
                  <li key={i}>
                    ВОПРОС №{i + 1}{' '}
                    <span className={ok ? 'ok' : 'no'}>{ok ? 'засчитан' : 'не засчитан'}</span>
                  </li>
                )
              })}
            </ol>
          ) : (
            <div className="q-fail">{failure ?? 'Разбор не выполнен.'}</div>
          )}
          {blob && <Player blob={blob} seconds={seconds} onProgress={onProgress} />}
        </div>

        {feedback &&
          Array.from({ length: count }, (_, i) => {
            const c = criteria[i]
            const ok = !!c && c.score >= c.max
            const heard = c?.quote?.trim() || (interview ? '— ответа не было —' : '— вопрос не прозвучал —')
            // «лучше» — когда есть чем заменить (correction). У интервью сервер
            // даёт только причину отказа: под подписью «лучше» она читалась бы как
            // совет, поэтому подпись честная — «почему не засчитан».
            const correction = c?.correction?.trim() || ''
            const better = ok ? PRAISE : correction || c?.comment?.trim() || (interview ? 'ответ не засчитан' : 'вопрос не засчитан')
            const betterLabel = ok || correction ? 'лучше' : 'почему не засчитан'
            const why = !ok && correction && c?.comment?.trim() ? c.comment.trim() : ''
            return (
              <div className={`q-item${i === 0 ? ' q-item--first' : ''}`} key={i}>
                <div className="q-badge" aria-hidden="true">
                  {i + 1}
                </div>
                <div className="q-card">
                  <span className="q-k">ваш ответ</span>
                  <span className={`q-v${c?.quote?.trim() ? '' : ' q-v--muted'}`}>{heard}</span>
                  <span className="q-k">{betterLabel}</span>
                  <span className="q-v q-v--better">{better}</span>
                  {why && <span className="q-why">{why}</span>}
                  {dispute && (
                    <MiniDisagree
                      ctx={{
                        ...dispute,
                        target: 'item',
                        targetKey: c?.key ?? `q${i + 1}`,
                        targetLabel: `${interview ? 'Ответ' : 'Вопрос'} №${i + 1}`,
                        score: c?.score,
                        max: c?.max,
                      }}
                    />
                  )}
                </div>
              </div>
            )
          })}
        {feedback && dispute && (
          <>
            <SummaryCard feedback={feedback} />
            <ErrorsCard errors={feedback.errors ?? []} dispute={dispute} />
            <TranscriptCard transcript={transcript} />
            <MiniDisagree center label="не согласен с баллом" ctx={dispute} />
          </>
        )}
        <div className="m-pad" />
      </div>

      <ResultBar onQuit={onQuit} onNext={onNext} />
    </div>
  )
}
