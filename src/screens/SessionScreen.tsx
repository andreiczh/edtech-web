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
import { useCallback, useEffect, useState, type CSSProperties } from 'react'

import { fetchMeStats, type MeStats } from '../account/me'
import { Pill } from '../design/ui'
import {
  markVariantSolved,
  saveTaskFeedback,
  variantById,
  type TaskId,
} from '../ege2/tasks'
import { ResultView } from './ResultView'
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
    // Вариант считается пройденным ТОЛЬКО когда разбор состоялся. Раньше
    // отметка ставилась всегда — и вариант, на котором не сработал микрофон,
    // навсегда исчезал из будущих сессий, хотя человек его не решал
    // (05.08.2026: тестировщик молча прошёл серию, все пять записей оказались
    // пустыми, и пять вариантов из банка выбыли ни за что).
    if (r.feedback) markVariantSolved(r.variantId)
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

  // Стрик берём с сервера, а не считаем на глазок: он один на все устройства.
  const [me, setMe] = useState<MeStats | null>(null)
  useEffect(() => {
    let alive = true
    void fetchMeStats().then((s) => alive && setMe(s))
    return () => {
      alive = false
    }
  }, [])

  const [tab, setTab] = useState<'stats' | 'mistakes'>('stats')
  // Открыт всегда ровно один блок: повторный клик по нему же закрывает.
  const [open, setOpen] = useState<number>(0)

  return (
    <div className="screen">
      <header className="topbar2">
        <span className="topbar2__brand">SPEAKO</span>
        <span className="statrow__label" style={{ marginTop: 0 }}>
          итоги варианта
        </span>
      </header>

      <div
        className="screen__body scroll-soft scroll-soft--onDark"
        style={{ overflowY: 'auto', justifyContent: 'safe center', padding: '6px 10px' }}
      >
        <div className="segmented" style={{ alignSelf: 'center' }}>
          <button
            type="button"
            className={`segmented__btn${tab === 'stats' ? ' segmented__btn--on' : ''}`}
            onClick={() => setTab('stats')}
          >
            ИТОГИ
          </button>
          <button
            type="button"
            className={`segmented__btn${tab === 'mistakes' ? ' segmented__btn--on' : ''}`}
            onClick={() => setTab('mistakes')}
          >
            ОШИБКИ
          </button>
        </div>

        {tab === 'stats' && (
          <>
            <div className="statrow" style={BLOCK}>
              <div>
                <div className="statrow__value">{me ? me.streak.days : '—'}</div>
                <div className="statrow__label">DAY STREAK</div>
              </div>
              <div>
                {/* Ноль баллов и ОТСУТСТВИЕ баллов — разные вещи. «0/—» после
                    серии, где ничего не записалось, читается как «ты всё
                    провалил», хотя проверять было нечего. */}
                <div className="statrow__value">
                  {graded.length ? (
                    <>
                      {score}
                      <span className="statrow__unit">/{max}</span>
                    </>
                  ) : (
                    '—'
                  )}
                </div>
                <div className="statrow__label">
                  {graded.length ? 'БАЛЛЫ ЗА ВАРИАНТ' : 'РАЗБОРОВ НЕ БЫЛО'}
                </div>
              </div>
              <div>
                <div className="statrow__value">{fmt(speech)}</div>
                <div className="statrow__label">РЕЧИ ЗАПИСАНО</div>
              </div>
            </div>

            {/* Аккордеон: развёрнут ровно один разбор. */}
            <div className="acc" style={BLOCK}>
              {results.map((r, i) => {
                const isOpen = open === i
                const variant = variantById(r.taskId, r.variantId)
                return (
                  <div className={`acc__item${isOpen ? ' acc__item--open' : ''}`} key={r.variantId}>
                    <button
                      type="button"
                      className="acc__head"
                      aria-expanded={isOpen}
                      onClick={() => setOpen(isOpen ? -1 : i)}
                    >
                      <span className="acc__no">№{r.taskId}</span>
                      <span className="acc__sum">
                        {r.feedback
                          ? `${r.feedback.score} из ${r.feedback.max}`
                          : (r.failure ?? 'разбор не выполнен')}
                      </span>
                      <span className="acc__chev" aria-hidden="true">
                        {isOpen ? '▲' : '▼'}
                      </span>
                    </button>
                    {isOpen && (
                      <div className="acc__body">
                        {r.feedback ? (
                          <ResultView
                            taskId={r.taskId}
                            feedback={r.feedback}
                            transcript={r.transcript}
                            reference={variant?.readText}
                            variantId={r.variantId}
                            variant={variant}
                          />
                        ) : (
                          <p style={{ margin: 0 }}>{r.failure ?? 'Разбор не выполнен.'}</p>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </>
        )}

        {tab === 'mistakes' && (
          <div className="card2" style={BLOCK}>
            {graded.length === 0 ? (
              /* Ни один ответ не разобрался — хвалить не за что. Раньше здесь
                 стояло «Отличный вариант!» на пустой серии: система поздравляла
                 человека с работой, которой не было (жалоба владельца
                 05.08.2026). Похвала без основания обесценивает и настоящую. */
              <p style={{ margin: 0 }}>
                Разбирать было нечего: ни один ответ не записался. Проверь микрофон и
                разрешение на запись в браузере — и пройди вариант заново.
              </p>
            ) : mistakes.length === 0 ? (
              <p style={{ margin: 0 }}>
                Разбор не нашёл ошибок, которые стоило бы вынести отдельно. Отличный вариант!
              </p>
            ) : (
              mistakes.map((m, i) => (
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
              ))
            )}
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
