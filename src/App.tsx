/**
 * Маршрутизация по новому макету SPEAKO.
 *
 * Роутера в проекте нет и он не нужен: экранов немного, а адресная строка у нас
 * не участвует в продукте (ссылку дают на корень). Держим состояние в одном месте
 * — так видно весь граф переходов сразу, без беготни по файлам.
 *
 * Прежний каркас (слайдер режимов внизу + вкладки ЕГЭ) заменён на верхние вкладки
 * из макета: conversation / ЕГЭ. Режим ОГЭ в макете отсутствует, поэтому он остаётся
 * вкладкой-заглушкой, а не выкинут: продукт его обещает.
 */
import { useCallback, useState } from 'react'

import type { TopTab } from './design/ui'
import { TASK_ORDER, type TaskId } from './ege2/tasks'
import { ConversationScreen } from './screens/ConversationScreen'
import { EgeMenuScreen } from './screens/EgeMenuScreen'
import { StatsScreen } from './screens/StatsScreen'
import { TaskScreen } from './screens/TaskScreen'

const TABS: TopTab[] = [
  { id: 'conversation', label: 'conversation' },
  { id: 'ege', label: 'ЕГЭ' },
]

type Route =
  | { name: 'conversation' }
  | { name: 'ege' }
  | { name: 'stats' }
  | { name: 'task'; id: TaskId }
  /** DEMO — те же экраны заданий, но подряд; index — сколько уже пройдено. */
  | { name: 'demo'; index: number }

export default function App() {
  const [route, setRoute] = useState<Route>({ name: 'conversation' })

  const activeTab = route.name === 'conversation' ? 'conversation' : 'ege'

  const onTab = useCallback((id: string) => {
    setRoute(id === 'conversation' ? { name: 'conversation' } : { name: 'ege' })
  }, [])

  const onProfile = useCallback(() => {
    // Личный кабинет по макету не нарисован. Отправляем в статистику — это
    // ближайшее осмысленное место, а не мёртвая кнопка.
    setRoute({ name: 'stats' })
  }, [])

  const backToEge = useCallback(() => setRoute({ name: 'ege' }), [])

  // В DEMO задания идут подряд: закончилось одно — сразу следующее, а после
  // последнего показываем сводную статистику, ради которой демо и затевалось.
  const onTaskFinished = useCallback(() => {
    setRoute((r) => {
      if (r.name !== 'demo') return { name: 'ege' }
      const next = r.index + 1
      return next >= TASK_ORDER.length ? { name: 'stats' } : { name: 'demo', index: next }
    })
  }, [])

  switch (route.name) {
    case 'conversation':
      return (
        <div className="app" data-theme="blue">
          <ConversationScreen
            tabs={TABS}
            activeTab={activeTab}
            onTab={onTab}
            onProfile={onProfile}
            onQuit={() => setRoute({ name: 'ege' })}
            onFeedback={onProfile}
          />
        </div>
      )

    case 'ege':
      return (
        <div className="app" data-theme="blue">
          <EgeMenuScreen
            tabs={TABS}
            activeTab={activeTab}
            onTab={onTab}
            onProfile={onProfile}
            onOpenTask={(id) => setRoute({ name: 'task', id })}
            onDemo={() => setRoute({ name: 'demo', index: 0 })}
            onStats={() => setRoute({ name: 'stats' })}
          />
        </div>
      )

    case 'stats':
      return (
        <div className="app" data-theme="blue">
          <StatsScreen
            tabs={TABS}
            activeTab={activeTab}
            onTab={onTab}
            onProfile={onProfile}
            onBack={backToEge}
          />
        </div>
      )

    case 'task':
      return (
        <div className="app" data-theme="blue">
          <TaskScreen taskId={route.id} onExit={backToEge} onFinished={onTaskFinished} />
        </div>
      )

    case 'demo':
      return (
        <div className="app" data-theme="blue">
          <TaskScreen
            // key заставляет React пересоздать экран между заданиями демо:
            // без него остались бы таймеры и запись от предыдущего номера.
            key={TASK_ORDER[route.index]}
            taskId={TASK_ORDER[route.index]}
            onExit={backToEge}
            onFinished={onTaskFinished}
            demoProgress={{ index: route.index + 1, total: TASK_ORDER.length }}
          />
        </div>
      )
  }
}
