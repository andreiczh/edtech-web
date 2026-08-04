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

import { syncSettingsFromServer, useCurrentPersona, useSettings } from './account/me'
import { currentUser, identityId, type AuthUser } from './auth/auth'
import { DisagreeModal } from './components/Disagree'
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
import { ProfileScreen } from './screens/ProfileScreen'
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
  | { name: 'profile' }
  /** nonce пересоздаёт сессию при «Пройти ещё раз» — иначе React сохранил бы
      состояние старой (индекс, результаты) и итоги не сбросились бы. */
  | { name: 'session'; items: SessionItem[]; nonce: number }

function initialRoute(): Route {
  // /?admin — скрытый вход в админку; сервер всё равно требует ADMIN_KEY.
  if (new URLSearchParams(window.location.search).has('admin')) return { name: 'admin' }
  return currentUser() ? { name: 'conversation' } : { name: 'welcome' }
}

/* Отзыв уходит В КОПИЛКУ на сервере, а не письмом (05.08.2026). Почтовая
   ссылка на телефоне открывает пустой почтовый клиент, до которого доходят
   единицы, и владелец получал ноль отзывов при живых учениках. Теперь та же
   форма, что и у спора с проверкой, — и всё в одном месте админки. */

export default function App() {
  const [route, setRoute] = useState<Route>(initialRoute)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  /* Тема (тёмная/светлая) — настройка кабинета, применяется атрибутом на
     корневом .app: CSS-переменные переопределяются одним селектором. */
  const { theme } = useSettings()
  // Цвет всего приложения задаёт выбранный собеседник: Наставник — прежний
  // фиолетовый, Гондон — красный, Терпеливый — зелёный. Пока каталог не
  // приехал, держим фиолетовый: он же и умолчание, мигания не будет.
  const paint = useCurrentPersona()?.theme ?? 'blue'
  // Дублируем тему на <html>: модалки уходят порталом в body, вне .app, и без
  // этого подтверждение выхода осталось бы фиолетовым посреди зелёного экрана.
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', paint)
  }, [paint])

  // Банк заданий, серверный прогресс и настройки аккаунта подтягиваются при
  // старте и после входа: сессии вычёркивают решённое на любом устройстве,
  // а тема и громкость следуют за аккаунтом.
  useEffect(() => {
    void syncRemoteTasks()
    if (currentUser()) {
      void syncServerProgress(identityId())
      void syncSettingsFromServer()
    }
  }, [])

  const enterApp = useCallback((_u: AuthUser) => {
    void syncServerProgress(identityId())
    void syncSettingsFromServer()
    setRoute({ name: 'conversation' })
  }, [])

  /* В кабинете бегунок вкладок остаётся там, где был до его открытия:
     кабинет — не вкладка, и прыжок бегунка читался бы как смена раздела. */
  const [lastTab, setLastTab] = useState<'conversation' | 'ege'>('conversation')
  const activeTab =
    route.name === 'conversation'
      ? 'conversation'
      : route.name === 'profile'
        ? lastTab
        : 'ege'

  const onTab = useCallback((id: string) => {
    setLastTab(id === 'conversation' ? 'conversation' : 'ege')
    setRoute(id === 'conversation' ? { name: 'conversation' } : { name: 'ege' })
  }, [])

  const onProfile = useCallback(() => {
    setRoute({ name: 'profile' })
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

  const onFeedback = useCallback(() => setFeedbackOpen(true), [])

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
      <div className="app" data-theme={paint} data-mode={theme}>
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
      <div className="app" data-theme={paint} data-mode={theme}>
        <div className="screenwrap" key={`session-${route.nonce}`}>
          <SessionScreen items={route.items} onExit={backToEge} onRestart={restartSession} />
        </div>
      </div>
    )
  }

  return (
    <div className="app" data-theme={paint} data-mode={theme}>
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

          {route.name === 'profile' && (
            <ProfileScreen
              onOpenStats={() => setRoute({ name: 'stats' })}
              onLogout={() => setRoute({ name: 'welcome' })}
              onClose={() => setRoute({ name: 'conversation' })}
            />
          )}
        </div>
      </div>

      {feedbackOpen && (
        <DisagreeModal
          ctx={{ kind: 'app', target: 'app', targetLabel: 'Отзыв о приложении' }}
          onClose={() => setFeedbackOpen(false)}
          onSent={() => undefined}
        />
      )}
    </div>
  )
}
