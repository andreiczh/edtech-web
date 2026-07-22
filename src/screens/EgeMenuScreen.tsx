/**
 * Экран выбора задания ЕГЭ (фото 3 макета).
 *
 * Шесть карточек: четыре задания, DEMO (все подряд) и STATS. Номера ведут сразу
 * в практику — вводный экран задания сам расскажет условие, лишний клик здесь
 * ничего не добавляет.
 *
 * Про «уже решал»: базы нет, `loadSolved()` помнит прогресс в localStorage этого
 * браузера. Поэтому пройденное только ПРИГЛУШАЕМ и подписываем, а не блокируем:
 * блокировка по данным, которых нет на сервере, отняла бы у человека задание
 * из-за очищенного кэша. По той же причине под сеткой честно написано, где
 * лежат отметки и у какого задания реально работает разбор ИИ.
 */
import { useEffect, useState, type CSSProperties } from 'react'
import { CardButton, TopBar, type TopTab } from '../design/ui'
import { TASKS, TASK_ORDER, firstUnsolved, loadSolved, type TaskId } from '../ege2/tasks'

/* Шесть карточек в одну колонку (360px) выше экрана, а `.app` режет переполнение
   (overflow:hidden при height:100dvh) — прокрутка обязана быть внутри тела.
   'safe center' вместо обычного center: при переполнении центрирование срезает
   верхние карточки, и доскроллить до них уже нечем. */
const BODY: CSSProperties = { overflowY: 'auto', justifyContent: 'safe center' }

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
  solved,
  next,
  onOpen,
}: {
  id: TaskId
  solved: boolean
  next: boolean
  onOpen: (id: TaskId) => void
}) {
  const task = TASKS[id]

  const marks: string[] = []
  if (solved) marks.push('✓ пройдено')
  else if (next) marks.push('дальше')
  if (task.hasAiFeedback) marks.push('разбор ИИ')

  const hint = solved
    ? 'Уже пройдено. Можно пройти ещё раз.'
    : next
      ? 'Первое непройденное задание.'
      : 'Ещё не пройдено.'

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
        opacity: solved ? 0.62 : 1,
        /* Именно outline, а не box-shadow: инлайновая тень перебила бы подъём
           карточки на ховере из .card2--button:hover. */
        outline: next ? '2px solid var(--orb-2)' : undefined,
        outlineOffset: next ? '3px' : undefined,
      }}
    >
      <span className="card2__title">№{id}</span>
      <span className="card2__sub">{task.label}</span>
      {marks.length > 0 && <span className="card2__sub">{marks.join(' · ')}</span>}
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
  /* Отметку «пройдено» ставит экран задания, а меню при возврате обычно
     монтируется заново — этого хватает. Слушатель фокуса добирает случай, когда
     вкладку переключали, а меню всё это время висело смонтированным. */
  const [solved, setSolved] = useState<TaskId[]>(loadSolved)
  useEffect(() => {
    const refresh = () => setSolved(loadSolved())
    window.addEventListener('focus', refresh)
    return () => window.removeEventListener('focus', refresh)
  }, [])

  const next = firstUnsolved(solved)

  const progress =
    solved.length === 0
      ? `Пока ничего не отмечено пройденным — начни с №${TASK_ORDER[0]}.`
      : next
        ? `Пройдено ${solved.length} из ${TASK_ORDER.length}, дальше — №${next}.`
        : 'Пройдены все четыре. Ничего не заблокировано — любое можно перерешать.'

  return (
    <div className="screen">
      <TopBar tabs={tabs} active={activeTab} onTab={onTab} onProfile={onProfile} />

      <div className="screen__body" style={BODY}>
        <div className="cardgrid">
          {TASK_ORDER.map((id) => (
            <TaskCard
              key={id}
              id={id}
              solved={solved.includes(id)}
              next={id === next}
              onOpen={onOpenTask}
            />
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
          <p style={{ margin: 0 }}>{progress}</p>
          <p style={{ margin: '4px 0 0' }}>
            Отметки хранятся только в этом браузере — на другом устройстве прогресс будет
            пустой. Разбор ответа ИИ пока работает только у №42.
          </p>
        </div>
      </div>
    </div>
  )
}
