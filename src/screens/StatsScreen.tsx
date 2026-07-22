/**
 * Экран статистики (фото 6 макета): вкладки STATS и MISTAKES.
 *
 * ЧЕСТНОСТЬ ДАННЫХ — главное решение этого файла. Базы нет, поэтому реально
 * только то, что успело осесть в localStorage этого браузера:
 *   - какие варианты пройдены (прогресс) — реальное;
 *   - последний разбор каждого задания (баллы и ошибки) — реальное, пишется
 *     сессией после каждого ответа;
 *   - DAY STREAK — взять неоткуда (дни занятий не логируются), число
 *     демонстрационное, приглушено и подписано «демо».
 */
import { useEffect, useState, type CSSProperties } from 'react'

import { Pill } from '../design/ui'
import {
  TASKS,
  TASK_ORDER,
  loadTaskFeedback,
  taskProgress,
  type StoredFeedback,
  type TaskId,
} from '../ege2/tasks'

/** Выдуманное число макета. Отдельная константа с говорящим именем, чтобы при
 *  подключении базы было видно, что именно выкинуть. */
const DEMO_STREAK = '4'

/* -------------------------------------------------------------- Раскладка */

const NARROW_QUERY = '(max-width: 720px)'

/** На узком экране список заданий в MISTAKES уезжает наверх и становится
 *  горизонтальным. Медиазапросы живут в ui.css, а инлайновым стилям остаётся
 *  только спросить ширину у браузера. */
function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(() => window.matchMedia(NARROW_QUERY).matches)
  useEffect(() => {
    const mq = window.matchMedia(NARROW_QUERY)
    const sync = () => setNarrow(mq.matches)
    sync()
    mq.addEventListener('change', sync)
    return () => mq.removeEventListener('change', sync)
  }, [])
  return narrow
}

/* Содержимое выше экрана телефона, а `.app` режет переполнение — прокрутка
   обязана быть внутри тела. 'safe center': при переполнении обычный center
   срезает верх, и доскроллить до него нечем. padding — чтобы подъём карточек
   на ховере не резался краем контейнера. */
const BODY: CSSProperties = {
  overflowY: 'auto',
  justifyContent: 'safe center',
  padding: '8px 10px',
}

const BLOCK: CSSProperties = { width: 'min(100%, 940px)' }

const NOTE: CSSProperties = {
  ...BLOCK,
  fontSize: 'clamp(11px, 1.2vw, 13px)',
  lineHeight: 1.45,
  color: 'var(--text-dim)',
}

const TABS_ROW: CSSProperties = {
  display: 'flex',
  justifyContent: 'center',
  gap: 8,
  flexShrink: 0,
}

const CHIPS: CSSProperties = {
  ...BLOCK,
  display: 'flex',
  flexWrap: 'wrap',
  justifyContent: 'center',
  gap: 'clamp(8px, 1.4vw, 16px)',
}

const CHIP: CSSProperties = {
  flex: '1 1 150px',
  maxWidth: 220,
  gap: 4,
  padding: 'clamp(10px, 1.4vw, 16px)',
}

const BADGE_BASE: CSSProperties = {
  display: 'inline-block',
  marginTop: 6,
  padding: '1px 8px',
  borderRadius: 999,
  fontSize: 10,
  fontWeight: 800,
  letterSpacing: '0.08em',
}

const BADGE_DEMO: CSSProperties = {
  ...BADGE_BASE,
  border: '1px dashed var(--text-dim)',
  color: 'var(--text-dim)',
}

const BADGE_REAL: CSSProperties = {
  ...BADGE_BASE,
  border: '1px solid var(--orb-2)',
  color: 'var(--text)',
}

/* ------------------------------------------------------------ Вкладка STATS */

function StatItem({
  value,
  unit,
  label,
  demo,
  title,
}: {
  value: string
  unit?: string
  label: string
  demo: boolean
  title: string
}) {
  return (
    <div title={title}>
      <div className="statrow__value" style={demo ? { opacity: 0.5 } : undefined}>
        {value}
        {unit && <span className="statrow__unit"> {unit}</span>}
      </div>
      <div className="statrow__label">{label}</div>
      <span style={demo ? BADGE_DEMO : BADGE_REAL}>{demo ? 'демо' : 'реальное'}</span>
    </div>
  )
}

function StatsTab({
  progress,
  feedback,
  onOpenMistakes,
}: {
  progress: Array<{ id: TaskId; done: number; total: number }>
  feedback: Partial<Record<TaskId, StoredFeedback>>
  onOpenMistakes: (id: TaskId) => void
}) {
  const done = progress.reduce((s, p) => s + p.done, 0)
  const total = progress.reduce((s, p) => s + p.total, 0)
  const pct = total ? Math.round((done / total) * 100) : 0

  // Средний результат — по ПОСЛЕДНЕМУ разбору каждого задания. Это реальное
  // число, но с честной оговоркой в title: истории нет, только последний срез.
  const graded = TASK_ORDER.map((id) => feedback[id]).filter(
    (f): f is StoredFeedback => Boolean(f && f.max > 0),
  )
  const avg = graded.length
    ? Math.round((graded.reduce((s, f) => s + f.score / f.max, 0) / graded.length) * 100)
    : null

  return (
    <>
      <div className="card2 card2--ghost glass" style={NOTE}>
        <p style={{ margin: 0 }}>
          Реальны прогресс по вариантам и последний разбор каждого задания — они хранятся в
          этом браузере. Дни занятий пока никуда не пишутся, поэтому DAY STREAK —
          демонстрационное число.
        </p>
      </div>

      <div className="statrow" style={BLOCK}>
        <StatItem
          value={DEMO_STREAK}
          label="DAY STREAK"
          demo
          title="Дни занятий нигде не сохраняются — число выдуманное."
        />
        <StatItem
          value={`${pct}%`}
          label="PROGRESS"
          demo={false}
          title={`Пройдено ${done} из ${total} вариантов по отметкам в этом браузере.`}
        />
        <StatItem
          value={avg === null ? '—' : `${avg}%`}
          label="СРЕДНИЙ БАЛЛ"
          demo={false}
          title={
            avg === null
              ? 'Появится после первой сессии с разбором.'
              : 'Средний процент баллов по последнему разбору каждого задания.'
          }
        />
      </div>

      <div style={CHIPS}>
        {progress.map(({ id, done: d, total: t }) => {
          const fb = feedback[id]
          return (
            <button
              key={id}
              type="button"
              className="card2 card2--button"
              style={CHIP}
              onClick={() => onOpenMistakes(id)}
              title={`Задание ${id} — ${TASKS[id].label}. Открыть разбор ошибок.`}
            >
              <span style={{ fontSize: 'clamp(17px, 2.2vw, 24px)', fontWeight: 800, lineHeight: 1.1 }}>
                №{id}
              </span>
              <span className="card2__sub">{TASKS[id].label}</span>
              <span className="card2__sub">{`${d}/${t} вариантов`}</span>
              <span className="card2__sub">
                {fb ? `последний разбор: ${fb.score}/${fb.max}` : 'разбора ещё не было'}
              </span>
            </button>
          )
        })}
      </div>
    </>
  )
}

/* --------------------------------------------------------- Вкладка MISTAKES */

function MistakesTab({
  selected,
  onSelect,
  feedback,
}: {
  selected: TaskId
  onSelect: (id: TaskId) => void
  feedback: Partial<Record<TaskId, StoredFeedback>>
}) {
  const narrow = useNarrow()
  const fb = feedback[selected]

  const layout: CSSProperties = {
    ...BLOCK,
    display: 'flex',
    flexDirection: narrow ? 'column' : 'row',
    alignItems: 'stretch',
    gap: 'clamp(10px, 1.6vw, 18px)',
    minHeight: 0,
  }

  const list: CSSProperties = narrow
    ? { display: 'flex', flexDirection: 'row', gap: 8, overflowX: 'auto', padding: '4px 2px 8px' }
    : {
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        flex: '0 0 clamp(130px, 18vw, 190px)',
        padding: 4,
      }

  return (
    <div style={layout}>
      <div style={list} role="tablist" aria-label="Задания">
        {TASK_ORDER.map((id) => {
          const active = id === selected
          return (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={active}
              className="card2 card2--button"
              style={{
                padding: '10px 14px',
                gap: 2,
                flex: narrow ? '0 0 auto' : undefined,
                opacity: active ? 1 : 0.62,
                outline: active ? '2px solid var(--orb-2)' : undefined,
                outlineOffset: active ? '2px' : undefined,
              }}
              onClick={() => onSelect(id)}
            >
              <span style={{ fontWeight: 800 }}>№{id}</span>
              <span className="card2__sub">{TASKS[id].label}</span>
            </button>
          )
        })}
      </div>

      <div className="card2" style={{ flex: '1 1 auto', minWidth: 0 }}>
        <p style={{ margin: 0, fontWeight: 800 }}>
          №{selected} · {TASKS[selected].label}
        </p>

        {fb ? (
          <>
            <p style={{ margin: '6px 0 12px', fontSize: '0.85em', color: 'var(--card-ink-dim)' }}>
              Последний разбор от {new Date(fb.when).toLocaleString('ru-RU')} — {fb.score}/
              {fb.max}. {fb.summary}
            </p>
            {fb.errors.length === 0 && (
              <p style={{ margin: 0, color: 'var(--card-ink-dim)' }}>
                Ошибок, которые стоило бы вынести отдельно, разбор не нашёл.
              </p>
            )}
            {fb.errors.map((m, i) => (
              <div className="mistake" key={i}>
                <div>
                  <span className="mistake__wrong">{m.quote}</span>{' '}
                  <span aria-hidden="true">→</span>{' '}
                  <span className="mistake__right">{m.correction}</span>
                </div>
                <div className="mistake__why">{m.explanation}</div>
              </div>
            ))}
          </>
        ) : (
          <p style={{ margin: '6px 0 0', color: 'var(--card-ink-dim)' }}>
            Разбора этого задания ещё не было. Пройди серию — итог последнего разбора
            сохранится здесь (в этом браузере, базы пока нет).
          </p>
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ Экран */

type Tab = 'stats' | 'mistakes'

export function StatsScreen({ onBack }: { onBack: () => void }) {
  const [tab, setTab] = useState<Tab>('stats')
  const [selected, setSelected] = useState<TaskId>(42)

  /* Отметки и разборы пишет сессия. Обычно статистика монтируется заново после
     возврата, но если вкладку переключали при живом экране — добираем по фокусу. */
  const [progress, setProgress] = useState(() =>
    TASK_ORDER.map((id) => ({ id, ...taskProgress(id) })),
  )
  const [feedback, setFeedback] = useState(loadTaskFeedback)
  useEffect(() => {
    const refresh = () => {
      setProgress(TASK_ORDER.map((id) => ({ id, ...taskProgress(id) })))
      setFeedback(loadTaskFeedback())
    }
    window.addEventListener('focus', refresh)
    return () => window.removeEventListener('focus', refresh)
  }, [])

  const openMistakes = (id: TaskId) => {
    setSelected(id)
    setTab('mistakes')
  }

  /* Шапку рисует App — общий каркас верхних экранов, см. комментарий там. */
  return (
    <div className="screenbody">
      <div style={TABS_ROW}>
        <Pill onClick={() => setTab('stats')} quiet={tab !== 'stats'} active={tab === 'stats'}>
          STATS
        </Pill>
        <Pill
          onClick={() => setTab('mistakes')}
          quiet={tab !== 'mistakes'}
          active={tab === 'mistakes'}
        >
          MISTAKES
        </Pill>
      </div>

      <div className="screen__body scroll-soft scroll-soft--onDark" style={BODY}>
        {tab === 'stats' ? (
          <StatsTab progress={progress} feedback={feedback} onOpenMistakes={openMistakes} />
        ) : (
          <MistakesTab selected={selected} onSelect={setSelected} feedback={feedback} />
        )}
      </div>

      <div className="rowbetween">
        <Pill onClick={onBack}>← Назад</Pill>
        <span style={{ fontSize: 'clamp(10px, 1.1vw, 12px)', color: 'var(--text-dim)' }}>
          Появится база — статистика переедет с этого браузера на аккаунт
        </span>
      </div>
    </div>
  )
}
