/**
 * Маршрутизация по макету SPEAKO.
 *
 * Роутера в проекте нет и он не нужен: экранов немного, а адресная строка не
 * участвует в продукте (ссылку дают на корень). Состояние в одном месте — виден
 * весь граф переходов сразу.
 *
 * Клик по номеру задания открывает СЕССИЮ — серию из пяти ранее не решённых
 * вариантов этого типа (см. pickSession). DEMO — по одному варианту каждого
 * номера. Итоги показывает SessionScreen.
 */
import { useCallback, useEffect, useState } from 'react'

import { currentUser, identityId, type AuthUser } from './auth/auth'
import { TopBar, type TopTab } from './design/ui'
import {
  pickDemoItems,
  pickSession,
  syncRemoteTasks,
  syncServerProgress,
  type TaskId,
} from './ege2/tasks'
import { AdminScreen } from './screens/AdminScreen'
import { LoginScreen, RegisterScreen, WelcomeScreen } from './screens/AuthScreens'
import { ConversationScreen } from './screens/ConversationScreen'
import { EgeMenuScreen } from './screens/EgeMenuScreen'
import { SessionScreen, type SessionItem } from './screens/SessionScreen'
import { StatsScreen } from './screens/StatsScreen'

const TABS: TopTab[] = [
  { id: 'conversation', label: 'Conversation' },
  { id: 'ege', label: 'ЕГЭ' },
]

type Route =
  | { name: 'welcome' }
  | { name: 'register' }
  | { name: 'login' }
  | { name: 'admin' }
  | { name: 'conversation' }
  | { name: 'ege' }
  | { name: 'stats' }
  /** nonce пересоздаёт сессию при «Пройти ещё раз» — иначе React сохранил бы
      состояние старой (индекс, результаты) и итоги не сбросились бы. */
  | { name: 'session'; items: SessionItem[]; nonce: number }

function initialRoute(): Route {
  // /?admin — скрытый вход в админку; сервер всё равно требует ADMIN_KEY.
  if (new URLSearchParams(window.location.search).has('admin')) return { name: 'admin' }
  return currentUser() ? { name: 'conversation' } : { name: 'welcome' }
}

/** Отзыв уходит владельцу продукта; адрес виден и так — это его публичная почта. */
const FEEDBACK_MAILTO =
  'mailto:andeich_daddy@icloud.com?subject=' + encodeURIComponent('SPEAKO — отзыв')

export default function App() {
  const [route, setRoute] = useState<Route>(initialRoute)

  // Банк заданий и серверный прогресс подтягиваются при старте и после входа:
  // сессии начинают вычёркивать варианты, решённые на любом устройстве.
  useEffect(() => {
    void syncRemoteTasks()
    if (currentUser()) void syncServerProgress(identityId())
  }, [])

  const enterApp = useCallback((_u: AuthUser) => {
    void syncServerProgress(identityId())
    setRoute({ name: 'conversation' })
  }, [])

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

  const startSession = useCallback((id: TaskId) => {
    setRoute({
      name: 'session',
      items: pickSession(id).map((v) => ({ taskId: id, variantId: v.id })),
      nonce: Date.now(),
    })
  }, [])

  const startDemo = useCallback(() => {
    setRoute({ name: 'session', items: pickDemoItems(), nonce: Date.now() })
  }, [])

  const restartSession = useCallback(() => {
    setRoute((r) => {
      if (r.name !== 'session') return r
      // Пересобираем сессию заново: отметки «пройдено» уже обновились, и
      // pickSession выдаст добор из самых давних вариантов.
      const taskId = r.items[0]?.taskId
      if (taskId === undefined) return { name: 'ege' }
      const sameTask = r.items.every((i) => i.taskId === taskId)
      return {
        name: 'session',
        items: sameTask
          ? pickSession(taskId).map((v) => ({ taskId, variantId: v.id }))
          : pickDemoItems(),
        nonce: Date.now(),
      }
    })
  }, [])

  const onFeedback = useCallback(() => {
    window.location.href = FEEDBACK_MAILTO
  }, [])

  // Экраны входа и админка — отдельные полноэкранные состояния вне каркаса.
  if (route.name === 'welcome') {
    return (
      <WelcomeScreen
        onStart={() => setRoute({ name: 'register' })}
        onLogin={() => setRoute({ name: 'login' })}
      />
    )
  }
  if (route.name === 'register') {
    return <RegisterScreen onDone={enterApp} />
  }
  if (route.name === 'login') {
    return <LoginScreen onDone={enterApp} onRegister={() => setRoute({ name: 'register' })} />
  }
  if (route.name === 'admin') {
    return (
      <div className="app" data-theme="blue">
        <AdminScreen
          onExit={() => {
            window.history.replaceState(null, '', window.location.pathname)
            setRoute(currentUser() ? { name: 'conversation' } : { name: 'welcome' })
          }}
        />
      </div>
    )
  }

  // Верхние экраны живут в общем каркасе: шапка с тумблером НЕ пересоздаётся
  // при переключении вкладок — бегунок плавно едет, «шва» между Conversation и
  // ЕГЭ нет. Кроссфейдом (ключом .swap) меняется только тело. Сессия задания —
  // отдельный полноэкранный поток со своей шапкой и полной анимацией входа.
  if (route.name === 'session') {
    return (
      <div className="app" data-theme="blue">
        <div className="screenwrap" key={`session-${route.nonce}`}>
          <SessionScreen items={route.items} onExit={backToEge} onRestart={restartSession} />
        </div>
      </div>
    )
  }

  return (
    <div className="app" data-theme="blue">
      <div className="screen">
        <TopBar tabs={TABS} active={activeTab} onTab={onTab} onProfile={onProfile} />

        <div className="swap" key={route.name}>
          {route.name === 'conversation' && <ConversationScreen onFeedback={onFeedback} />}

          {route.name === 'ege' && (
            <EgeMenuScreen
              onOpenTask={startSession}
              onDemo={startDemo}
              onStats={() => setRoute({ name: 'stats' })}
            />
          )}

          {route.name === 'stats' && <StatsScreen onBack={backToEge} />}
        </div>
      </div>
    </div>
  )
}
