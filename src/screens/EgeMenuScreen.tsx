/**
 * Экран выбора задания ЕГЭ (фото 3 макета).
 *
 * Шесть карточек: четыре номера, DEMO и STATS. Клик по номеру запускает СЕССИЮ —
 * серию из пяти ранее не решённых вариантов этого типа (пожелание пользователя),
 * поэтому прогресс на карточке считается по вариантам: «3/5».
 *
 * Прогресс живёт в localStorage этого браузера (базы нет), поэтому пройденное
 * только приглушаем, а не блокируем: блокировка по данным, которых нет на
 * сервере, отняла бы задание из-за очищенного кэша.
 */
import { useEffect, useState, type CSSProperties } from 'react'
import { CardButton, TopBar, type TopTab } from '../design/ui'
import { TASKS, TASK_ORDER, taskProgress, type TaskId } from '../ege2/tasks'

/* Прокрутки здесь нет — по прямой просьбе: «всё должно стоять на одном экране».
   Высоту диктует сетка (.cardgrid делит остаток между рядами, 3×2 и 2×3), а
   overflow:hidden ловит случай, если контент всё же окажется выше. Внутренний
   padding нужен подъёму карточек на ховере — без него верх лифта режется краем. */
const BODY: CSSProperties = { overflow: 'hidden', justifyContent: 'center', padding: '8px 10px' }

const NOTE: CSSProperties = {
  width: 'min(100%, 900px)',
  margin: 0,
  textAlign: 'center',
  color: 'var(--text-dim)',
  fontSize: 'clamp(11px, 1.2vw, 13px)',
  lineHeight: 1.45,
}

function TaskCard({
  id,
  progress,
  next,
  onOpen,
}: {
  id: TaskId
  progress: { done: number; total: number }
  next: boolean
  onOpen: (id: TaskId) => void
}) {
  const task = TASKS[id]
  const complete = progress.done >= progress.total

  const hint = complete
    ? 'Все варианты пройдены — сессия соберётся из самых давних.'
    : next
      ? 'Начни отсюда: серия из пяти вариантов подряд.'
      : `Пройдено ${progress.done} из ${progress.total} вариантов.`

  return (
    /* Своя разметка вместо <CardButton>: нужны приглушение пройденного, рамка
       «дальше» и внятный aria-label, а таких пропсов у CardButton нет. Классы
       те же, так что стекло и прожатие берутся из дизайн-системы. */
    <button
      type="button"
      className="card2 card2--button"
      onClick={() => onOpen(id)}
      title={`Задание ${id} — ${task.label}. ${hint}`}
      aria-label={`Задание ${id}, ${task.label}. ${hint}`}
      style={{
        opacity: complete ? 0.62 : 1,
        /* Именно outline, а не box-shadow: инлайновая тень перебила бы подъём
           карточки на ховере из .card2--button:hover. */
        outline: next ? '2px solid var(--orb-2)' : undefined,
        outlineOffset: next ? '3px' : undefined,
      }}
    >
      <span className="card2__title">№{id}</span>
      <span className="card2__sub">{task.label}</span>
      <span className="card2__sub">
        {complete ? '✓ все варианты' : `${progress.done}/${progress.total} вариантов`}
      </span>
    </button>
  )
}

export function EgeMenuScreen({
  tabs,
  activeTab,
  onTab,
  onProfile,
  onOpenTask,
  onDemo,
  onStats,
}: {
  tabs: TopTab[]
  activeTab: string
  onTab: (id: string) => void
  onProfile: () => void
  onOpenTask: (id: TaskId) => void
  onDemo: () => void
  onStats: () => void
}) {
  /* Отметки ставит сессия, а меню при возврате монтируется заново — этого
     хватает. Слушатель фокуса добирает случай, когда вкладку переключали. */
  const [progress, setProgress] = useState(() =>
    TASK_ORDER.map((id) => ({ id, ...taskProgress(id) })),
  )
  useEffect(() => {
    const refresh = () => setProgress(TASK_ORDER.map((id) => ({ id, ...taskProgress(id) })))
    window.addEventListener('focus', refresh)
    return () => window.removeEventListener('focus', refresh)
  }, [])

  const next = progress.find((p) => p.done < p.total)?.id

  return (
    <div className="screen">
      <TopBar tabs={tabs} active={activeTab} onTab={onTab} onProfile={onProfile} />

      <div className="screen__body" style={BODY}>
        <div className="cardgrid">
          {progress.map((p) => (
            <TaskCard key={p.id} id={p.id} progress={p} next={p.id === next} onOpen={onOpenTask} />
          ))}

          <CardButton
            title="DEMO"
            sub={`№${TASK_ORDER[0]}–${TASK_ORDER[TASK_ORDER.length - 1]} подряд`}
            onClick={onDemo}
          />

          <CardButton
            title={
              <>
                STATS <span aria-hidden="true">→</span>
              </>
            }
            sub="сводка по занятиям"
            ghost
            onClick={onStats}
          />
        </div>

        <div style={NOTE}>
          <p style={{ margin: 0 }}>
            Каждый номер — серия из пяти вариантов с общим разбором в конце. Отметки о
            пройденном хранятся только в этом браузере. У №39 разбор сверяет слова с текстом —
            произношение по записи не оценивается.
          </p>
        </div>
      </div>
    </div>
  )
}
