/**
 * Маршрутизация. Каркас нового дизайна (перенос утверждённого прототипа):
 * слева плавающий рейл навигации (Главная / Тренажёр / Статистика / Настройки)
 * и отдельный док темы, справа контент. Стартовый экран — дашборд.
 *
 * Роутера в проекте нет и он не нужен: экранов немного, а адресная строка не
 * участвует в продукте (ссылку дают на корень). Состояние в одном месте — виден
 * весь граф переходов сразу.
 *
 * Клик по номеру задания открывает СЕССИЮ — серию из пяти ранее не решённых
 * вариантов этого типа (см. pickSession). DEMO — по одному варианту каждого
 * номера. Итоги показывает SessionScreen.
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react'

import {
  syncSettingsFromServer,
  updateSettings,
  useCurrentPersona,
  useSettings,
} from './account/me'
import { currentUser, identityId, type AuthUser } from './auth/auth'
import { DisagreeModal } from './components/Disagree'
import {
  pickDemoItems,
  pickSession,
  syncRemoteTasks,
  syncServerProgress,
  type TaskId,
} from './ege2/tasks'
import { AdminScreen } from './screens/AdminScreen'
import { CalendarScreen } from './screens/CalendarScreen'
import { IntroScreen, LoginScreen, RegisterScreen } from './screens/AuthScreens'
import { ConversationScreen } from './screens/ConversationScreen'
import { EgeMenuScreen } from './screens/EgeMenuScreen'
import { HomeScreen } from './screens/HomeScreen'
import { ProfileScreen } from './screens/ProfileScreen'
import { SessionScreen, type SessionItem } from './screens/SessionScreen'
import { StatsScreen } from './screens/StatsScreen'

type Route =
  | { name: 'welcome' }
  | { name: 'intro' }
  | { name: 'login' }
  | { name: 'admin' }
  | { name: 'home' }
  | { name: 'calendar' }
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
  return currentUser() ? { name: 'home' } : { name: 'welcome' }
}

/* Иконки рейла — один набор, один stroke (правило брифа). */
function RailIcon({ kind }: { kind: 'home' | 'calendar' | 'stats' | 'settings' | 'sun' | 'moon' }) {
  const paths: Record<string, ReactNode> = {
    home: (
      <>
        <path d="M3 11.5 12 4l9 7.5M5.5 9.7V20h13V9.7" />
        <path d="M10 20v-5.5h4V20" />
      </>
    ),
    calendar: (
      <>
        <rect x="3.5" y="5" width="17" height="16" rx="3" />
        <path d="M8 3v4M16 3v4M3.5 10.5h17" />
      </>
    ),
    stats: <path d="M5 20v-6M12 20V9M19 20V4" />,
    settings: (
      <>
        <circle cx="12" cy="12" r="3.2" />
        <path d="M19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3 1a7 7 0 0 0-2-1.2L14.2 3h-4l-.4 2.5a7 7 0 0 0-2 1.2l-2.3-1-2 3.4 2 1.5a7 7 0 0 0 0 2.4l-2 1.5 2 3.4 2.3-1a7 7 0 0 0 2 1.2l.4 2.5h4l.4-2.5a7 7 0 0 0 2-1.2l2.3 1 2-3.4-2-1.5c.06-.4.1-.8.1-1.2Z" />
      </>
    ),
    sun: (
      <>
        <circle cx="12" cy="12" r="4.2" />
        <path d="M12 2.5v2.6M12 18.9v2.6M2.5 12h2.6M18.9 12h2.6M5 5l1.8 1.8M17.2 17.2 19 19M19 5l-1.8 1.8M6.8 17.2 5 19" />
      </>
    ),
    moon: <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5Z" />,
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[kind]}
    </svg>
  )
}

export default function App() {
  const [route, setRoute] = useState<Route>(initialRoute)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  /* Тема (тёмная/светлая) — настройка кабинета, применяется атрибутом на
     корневом .app: CSS-переменные переопределяются одним селектором. */
  const { theme } = useSettings()
  const [sysDark, setSysDark] = useState(
    () => window.matchMedia('(prefers-color-scheme: dark)').matches,
  )
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const cb = (e: MediaQueryListEvent) => setSysDark(e.matches)
    mq.addEventListener('change', cb)
    return () => mq.removeEventListener('change', cb)
  }, [])
  const mode = theme === 'auto' ? (sysDark ? 'dark' : 'light') : theme
  // Характер собеседника задаёт АКЦЕНТ (бегунок, полоса опыта, главные
  // кнопки) — фон в новом дизайне всегда молочный, см. theme-new.css.
  const paint = useCurrentPersona()?.theme ?? 'blue'
  // Дублируем тему на <html>: модалки уходят порталом в body, вне .app.
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', paint)
  }, [paint])

  // Банк заданий, серверный прогресс и настройки аккаунта подтягиваются при
  // старте и после входа.
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
    setRoute({ name: 'home' })
  }, [])

  /* После регистрации — интро «что тебя ждёт внутри» (фото-канон), после
     входа существующего аккаунта — сразу дашборд. */
  const enterAfterRegister = useCallback((_u: AuthUser) => {
    void syncServerProgress(identityId())
    void syncSettingsFromServer()
    setRoute({ name: 'intro' })
  }, [])

  const goHome = useCallback(() => setRoute({ name: 'home' }), [])
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
      <RegisterScreen onDone={enterAfterRegister} onLogin={() => setRoute({ name: 'login' })} />
    )
  }
  if (route.name === 'intro') {
    return <IntroScreen onGo={() => setRoute({ name: 'home' })} />
  }
  if (route.name === 'login') {
    return <LoginScreen onDone={enterApp} onRegister={() => setRoute({ name: 'welcome' })} />
  }
  if (route.name === 'admin') {
    return (
      <div className="app" data-theme={paint} data-mode={mode}>
        <AdminScreen
          onExit={() => {
            window.history.replaceState(null, '', window.location.pathname)
            setRoute(currentUser() ? { name: 'home' } : { name: 'welcome' })
          }}
        />
      </div>
    )
  }

  // Сессия задания — полноэкранный поток со своей шапкой, рейл не показываем:
  // на экзамене ничто не должно уводить из задания.
  if (route.name === 'session') {
    return (
      <div className="app" data-theme={paint} data-mode={mode}>
        <div className="screenwrap" key={`session-${route.nonce}`}>
          <SessionScreen items={route.items} onExit={backToEge} onRestart={restartSession} />
        </div>
      </div>
    )
  }

  /* Актив рейла: разговор открывается с дашборда и своей кнопки не имеет —
     подсвечиваем «Главную», путь возврата очевиден. */
  const railActive =
    route.name === 'calendar' ? 'calendar'
    : route.name === 'stats' ? 'stats'
    : route.name === 'profile' ? 'settings'
    : 'home'

  const RAIL: Array<{ id: typeof railActive; icon: Parameters<typeof RailIcon>[0]['kind']; title: string; go: () => void }> = [
    { id: 'home', icon: 'home', title: 'Главная', go: goHome },
    { id: 'calendar', icon: 'calendar', title: 'Календарь', go: () => setRoute({ name: 'calendar' }) },
    { id: 'stats', icon: 'stats', title: 'Статистика', go: () => setRoute({ name: 'stats' }) },
    { id: 'settings', icon: 'settings', title: 'Настройки', go: () => setRoute({ name: 'profile' }) },
  ]

  return (
    <div className="app" data-theme={paint} data-mode={mode}>
      <div className="appgrid">
        <aside className="leftcol">
          <span className="lspacer lspacer--top" />
          <nav className="rail" aria-label="Основная навигация">
            {RAIL.map((b) => (
              <button
                key={b.id}
                type="button"
                className={`rail__btn${railActive === b.id ? ' rail__btn--on' : ''}`}
                title={b.title}
                aria-label={b.title}
                onClick={b.go}
              >
                <RailIcon kind={b.icon} />
              </button>
            ))}
          </nav>
          <span className="lspacer" />
          <div className="themedock themedock--joined" role="group" aria-label="Тема оформления">
            <button
              type="button"
              className={`rail__btn${theme === 'light' ? ' rail__btn--on' : ''}`}
              title="Светлая тема"
              aria-label="Светлая тема"
              onClick={() => updateSettings({ theme: 'light' })}
            >
              <RailIcon kind="sun" />
            </button>
            <button
              type="button"
              className={`rail__btn${theme === 'dark' ? ' rail__btn--on' : ''}`}
              title="Тёмная тема"
              aria-label="Тёмная тема"
              onClick={() => updateSettings({ theme: 'dark' })}
            >
              <RailIcon kind="moon" />
            </button>
          </div>
        </aside>

        <div className="screen">
          <div className="swap" key={route.name}>
            {route.name === 'home' && (
              <HomeScreen
                onTrainer={backToEge}
                onSpeaking={() => setRoute({ name: 'conversation' })}
                onDemo={startDemo}
                onStats={() => setRoute({ name: 'stats' })}
                onCalendar={() => setRoute({ name: 'calendar' })}
                onProfile={() => setRoute({ name: 'profile' })}
              />
            )}

            {route.name === 'calendar' && <CalendarScreen />}

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
                onClose={goHome}
              />
            )}
          </div>
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
