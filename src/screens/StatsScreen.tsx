/**
 * Экран статистики (фото 6 макета): вкладки STATS и MISTAKES.
 *
 * ЧЕСТНОСТЬ ДАННЫХ — главное решение этого файла.
 * Базы нет, логирование сессий не сделано (открытый пункт роадмапа), поэтому
 * настоящих streak, GPA и списка прошлых ошибок взять физически неоткуда.
 * Нарисовать красивые числа как настоящие — значит однажды поверить в них самому
 * и показать другу как факт. Поэтому:
 *   - реальны только две вещи: какие задания отмечены пройденными в этом браузере
 *     (`loadSolved()`) и посчитанный из них процент — они помечены «реальное»;
 *   - всё остальное лежит в константах с приставкой DEMO_, приглушено и подписано
 *     «демо» прямо на экране;
 *   - у заданий 39–41 разбора ошибок на бэкенде нет вообще (`hasAiFeedback`), и
 *     примеров ошибок там не показываем — только объяснение, почему пусто.
 */
import { useEffect, useState, type CSSProperties } from 'react'

import { Pill, TopBar, type TopTab } from '../design/ui'
import { TASKS, TASK_ORDER, loadSolved, type TaskId } from '../ege2/tasks'

/* ------------------------------------------------- Демонстрационные данные */

/** Выдуманные числа макета. Живут отдельной константой с говорящим именем,
 *  чтобы при подключении базы было видно, что именно надо выкинуть. */
const DEMO_STREAK = '4'
const DEMO_GPA = '20'

interface DemoMistake {
  wrong: string
  right: string
  why: string
}

/** Пример разбора для №42: как будет выглядеть панель, когда ответы начнут
 *  сохраняться. Не чей-то реальный ответ — просто типовые ошибки монолога. */
const DEMO_MISTAKES: DemoMistake[] = [
  {
    wrong: 'In the first photo I can see a girl which is knitting.',
    right: 'In the first photo I can see a girl who is knitting.',
    why: 'who — о людях, which — о предметах.',
  },
  {
    wrong: 'Both hobbies has advantages and disadvantages.',
    right: 'Both hobbies have advantages and disadvantages.',
    why: 'both hobbies — множественное число, нужен have.',
  },
  {
    wrong: 'I prefer skateboarding because it more exciting.',
    right: 'I prefer skateboarding because it is more exciting.',
    why: 'В придаточном нельзя терять глагол-связку is.',
  },
]

/* -------------------------------------------------------------- Раскладка */

const NARROW_QUERY = '(max-width: 720px)'

/**
 * На узком экране список заданий в MISTAKES уезжает наверх и становится
 * горизонтальным. Медиазапросы живут в ui.css, а править чужой файл нельзя —
 * поэтому ширину спрашиваем у браузера, а не у CSS.
 */
function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(() => window.matchMedia(NARROW_QUERY).matches)
  useEffect(() => {
    const mq = window.matchMedia(NARROW_QUERY)
    const sync = () => setNarrow(mq.matches)
    sync() // ширина могла измениться между первым рендером и подпиской
    mq.addEventListener('change', sync)
    return () => mq.removeEventListener('change', sync)
  }, [])
  return narrow
}

/* Содержимое выше экрана телефона, а `.app` режет переполнение — прокрутка
   обязана быть внутри тела. 'safe center' вместо center: при переполнении
   обычное центрирование срезает верх и доскроллить до него нечем. */
const BODY: CSSProperties = { overflowY: 'auto', justifyContent: 'safe center' }

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

const CHIP_NUM: CSSProperties = {
  fontSize: 'clamp(17px, 2.2vw, 24px)',
  fontWeight: 800,
  lineHeight: 1.1,
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
      {/* Демо-число дополнительно приглушено: подпись подписью, но глаз должен
          сам видеть, что это число слабее настоящего. */}
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
  solved,
  onOpenMistakes,
}: {
  solved: TaskId[]
  onOpenMistakes: (id: TaskId) => void
}) {
  const pct = Math.round((solved.length / TASK_ORDER.length) * 100)

  return (
    <>
      <div className="card2 card2--ghost glass" style={NOTE}>
        <p style={{ margin: 0 }}>
          Настоящей статистики пока нет: занятия никуда не записываются — базы и
          логирования сессий у продукта ещё не существует.
        </p>
        <p style={{ margin: '4px 0 0' }}>
          Честно известно ровно одно — какие задания отмечены пройденными в этом браузере.
          Остальные числа демонстрационные: они приглушены и подписаны «демо».
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
          title={`Пройдено ${solved.length} из ${TASK_ORDER.length} заданий по отметкам в этом браузере.`}
        />
        <StatItem
          value={DEMO_GPA}
          unit="pts"
          label="GPA"
          demo
          title="Баллы за ответы не считаются и не хранятся — число выдуманное."
        />
      </div>

      <div style={CHIPS}>
        {TASK_ORDER.map((id) => {
          const task = TASKS[id]
          const done = solved.includes(id)
          return (
            <button
              key={id}
              type="button"
              className="card2 card2--button"
              style={CHIP}
              onClick={() => onOpenMistakes(id)}
              title={`Задание ${id} — ${task.label}. Открыть разбор ошибок.`}
            >
              <span style={CHIP_NUM}>№{id}</span>
              <span className="card2__sub">{task.label}</span>
              <span className="card2__sub">{done ? '✓ пройдено' : 'не пройдено'}</span>
              <span className="card2__sub">
                {task.hasAiFeedback ? 'есть разбор ИИ' : 'разбора нет'}
              </span>
            </button>
          )
        })}
      </div>

      <p style={{ ...NOTE, margin: 0, textAlign: 'center' }}>
        Баллов у заданий нет намеренно: ответ разбирается сразу после записи и никуда
        не сохраняется, поэтому оценить «результат по заданию» пока нечем.
      </p>
    </>
  )
}

/* --------------------------------------------------------- Вкладка MISTAKES */

function MistakesTab({
  selected,
  onSelect,
}: {
  selected: TaskId
  onSelect: (id: TaskId) => void
}) {
  const narrow = useNarrow()
  const task = TASKS[selected]

  const layout: CSSProperties = {
    ...BLOCK,
    display: 'flex',
    flexDirection: narrow ? 'column' : 'row',
    alignItems: 'stretch',
    gap: 'clamp(10px, 1.6vw, 18px)',
    minHeight: 0,
  }

  const list: CSSProperties = narrow
    ? { display: 'flex', flexDirection: 'row', gap: 8, overflowX: 'auto', paddingBottom: 4 }
    : {
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        flex: '0 0 clamp(130px, 18vw, 190px)',
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
                /* outline, а не тень: инлайновый box-shadow перебил бы подъём
                   карточки на ховере из .card2--button:hover. */
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
          №{selected} · {task.label}
        </p>

        {task.hasAiFeedback ? (
          <>
            <p
              style={{
                margin: '6px 0 12px',
                fontSize: '0.85em',
                color: 'var(--card-ink-dim)',
              }}
            >
              ПРИМЕР РАЗБОРА, демонстрационные ошибки. Твои настоящие сюда не попадают:
              /monologue показывает разбор сразу после ответа и нигде его не хранит.
            </p>
            {DEMO_MISTAKES.map((m) => (
              <div className="mistake" key={m.wrong}>
                <div>
                  <span className="mistake__wrong">{m.wrong}</span>{' '}
                  <span aria-hidden="true">→</span>{' '}
                  <span className="mistake__right">{m.right}</span>
                </div>
                <div className="mistake__why">{m.why}</div>
              </div>
            ))}
          </>
        ) : (
          <p style={{ margin: '6px 0 0', color: 'var(--card-ink-dim)' }}>
            Разбора у этого задания нет. ИИ проверяет только №42 — там речь длинная и
            есть критерии ФИПИ. Для чтения, диалога и интервью проверка ещё не написана,
            и выдумывать ошибки здесь мы не станем.
          </p>
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ Экран */

type Tab = 'stats' | 'mistakes'

export function StatsScreen({
  tabs,
  activeTab,
  onTab,
  onProfile,
  onBack,
}: {
  tabs: TopTab[]
  activeTab: string
  onTab: (id: string) => void
  onProfile: () => void
  onBack: () => void
}) {
  const [tab, setTab] = useState<Tab>('stats')
  const [selected, setSelected] = useState<TaskId>(42)

  /* Отметки ставит экран задания. Обычно статистика монтируется заново после
     возврата, но если вкладку переключали при живом экране — добираем по фокусу. */
  const [solved, setSolved] = useState<TaskId[]>(loadSolved)
  useEffect(() => {
    const refresh = () => setSolved(loadSolved())
    window.addEventListener('focus', refresh)
    return () => window.removeEventListener('focus', refresh)
  }, [])

  const openMistakes = (id: TaskId) => {
    setSelected(id)
    setTab('mistakes')
  }

  return (
    <div className="screen">
      <TopBar tabs={tabs} active={activeTab} onTab={onTab} onProfile={onProfile} />

      <div style={TABS_ROW}>
        <Pill
          onClick={() => setTab('stats')}
          quiet={tab !== 'stats'}
          active={tab === 'stats'}
        >
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

      <div className="screen__body" style={BODY}>
        {tab === 'stats' ? (
          <StatsTab solved={solved} onOpenMistakes={openMistakes} />
        ) : (
          <MistakesTab selected={selected} onSelect={setSelected} />
        )}
      </div>

      <div className="rowbetween">
        <Pill onClick={onBack}>← Назад</Pill>
        <span style={{ fontSize: 'clamp(10px, 1.1vw, 12px)', color: 'var(--text-dim)' }}>
          Появится база — демо-числа станут настоящими
        </span>
      </div>
    </div>
  )
}
