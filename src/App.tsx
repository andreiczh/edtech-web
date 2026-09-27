/**
 * Маршрутизация. Каркас нового дизайна (перенос утверждённого прототипа):
 * слева плавающий рейл навигации (Главная / Календарь / Статистика / Настройки)
 * и отдельный док темы, справа контент. Стартовый экран — дашборд.
 *
 * Роутера в проекте нет и он не нужен: экранов немного, а адресная строка не
 * участвует в продукте (ссылку дают на корень). Состояние в одном месте — виден
 * весь граф переходов сразу.
 *
 * Клик по номеру задания открывает СЕССИЮ — серию из пяти ранее не решённых
 * вариантов этого типа (см. pickSession). DEMO — по одному варианту каждого
 * номера. Итоги показывает SessionScreen.
 *
 * Рейл — ОДИН на все экраны (components/Rail.tsx), фиксирован на экране:
 * главная рисует свой холст под ним, остальные экраны — сетку с пустой
 * левой колонкой той же ширины. Так при переходах ничего не прыгает.
 */
import { useCallback, useEffect, useState } from 'react'

import {
  onUnauthorized,
  resetSettings,
  syncSettingsFromServer,
  updateSettings,
  useCurrentPersona,
  useSettings,
} from './account/me'
import { currentUser, identityId, logout, type AuthUser } from './auth/auth'
import { DisagreeModal } from './components/Disagree'
import { Rail, type RailItem } from './components/Rail'
import {
  pickDemoItems,
  pickSession,
  syncRemoteTasks,
  syncServerProgress,
  type TaskId,
} from './ege2/tasks'
import { favoriteSessionItems, syncFavorites } from './ege2/favorites'
import { isMaxLaunch, pendingLinkToken } from './max/bridge'
import { Ambient } from './mini/Ambient'
import { MiniApp } from './mini/MiniApp'
import { useMobileShell } from './mini/useMobileShell'
import { AdminScreen } from './screens/AdminScreen'
import { CalendarScreen } from './screens/CalendarScreen'
import { IntroScreen, LoginScreen, MaxLoginScreen, RegisterScreen } from './screens/AuthScreens'
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
  /** Запуск из мини-приложения MAX: вход подписью мессенджера. */
  | { name: 'maxlogin' }
  | { name: 'admin' }
  | { name: 'home' }
  | { name: 'calendar' }
  | { name: 'conversation' }
  | { name: 'ege' }
  | { name: 'stats' }
  | { name: 'profile' }
  /** nonce пересоздаёт сессию при «Пройти ещё раз» — иначе React сохранил бы
      состояние старой (индекс, результаты) и итоги не сбросились бы. */
  | { name: 'session'; items: SessionItem[]; nonce: number; fav?: boolean }
  /* fav — серия «Избранный вариант»: «Пройти ещё раз» собирает её заново из
     избранного, а не из банка номера. */

function initialRoute(): Route {
  // /?admin — скрытый вход в админку; сервер всё равно требует ADMIN_KEY.
  if (new URLSearchParams(window.location.search).has('admin')) return { name: 'admin' }
  // Личная ссылка от бота важнее сохранённого входа: по ней человек должен
  // попасть в СВОЙ аккаунт MAX, даже если в этом браузере был чужой (§6.50).
  if (pendingLinkToken()) return { name: 'maxlogin' }
  if (currentUser()) return { name: 'home' }
  // Открыли из MAX — входим подписью мессенджера, без ника, пароля и кода.
  return isMaxLaunch() ? { name: 'maxlogin' } : { name: 'welcome' }
}

export default function App() {
  const [route, setRoute] = useState<Route>(initialRoute)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  // Телефон и MAX — мини-оболочка по мобильным макетам, см. mini/MiniApp.tsx.
  const mobile = useMobileShell()
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
      void syncFavorites()
    }
  }, [])

  // 401 от /me/*: аккаунта с этим id на сервере нет (база переехала или
  // аккаунт удалён). Выходим сами — иначе человек сидит с прочерками и без
  // выхода (аудит 26.09.2026, §6.47).
  useEffect(() => {
    onUnauthorized(() => {
      logout()
      resetSettings()
      setRoute(isMaxLaunch() ? { name: 'maxlogin' } : { name: 'welcome' })
    })
    return () => onUnauthorized(null)
  }, [])

  const enterApp = useCallback((_u: AuthUser) => {
    void syncServerProgress(identityId())
    void syncSettingsFromServer()
    void syncFavorites()
    setRoute({ name: 'home' })
  }, [])

  /* После регистрации — интро «что тебя ждёт внутри» (фото-канон), после
     входа существующего аккаунта — сразу дашборд. */
  const enterAfterRegister = useCallback((_u: AuthUser) => {
    void syncServerProgress(identityId())
    void syncSettingsFromServer()
    void syncFavorites()
    setRoute({ name: 'intro' })
  }, [])

  /* Вход через MAX. Новому аккаунту — интро, как после регистрации. Согласия
     на хранение записей у него НЕ спрашивали, поэтому явное «нет»: иначе
     локальное значение по умолчанию уехало бы на сервер с первой же сменой
     настроек. Включить можно в кабинете. */
  const enterFromMax = useCallback((_u: AuthUser, created: boolean) => {
    if (created) updateSettings({ corpusConsent: false })
    void syncServerProgress(identityId())
    void syncSettingsFromServer()
    void syncFavorites()
    setRoute(created ? { name: 'intro' } : { name: 'home' })
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

  /* «Избранный вариант»: серия из заданий, отмеченных звёздочкой. */
  const startFavorites = useCallback(() => {
    const items = favoriteSessionItems()
    if (items.length) setRoute({ name: 'session', items, nonce: Date.now(), fav: true })
  }, [])

  const restartSession = useCallback(() => {
    setRoute((r) => {
      if (r.name !== 'session') return r
      if (r.fav) {
        const items = favoriteSessionItems()
        return items.length ? { name: 'session', items, nonce: Date.now(), fav: true } : { name: 'ege' }
      }
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
  // На телефоне и в MAX те же экраны одеваются в оболочку мини-приложения
  // (фон, кадр, кегли) — форма и логика входа одни на оба входа.
  const authShell = (node: React.ReactNode) =>
    mobile ? (
      <div className="mini mini--auth">
        <div className="mini__frame">
          <Ambient />
          <div className="mini__scroll mini-auth">{node}</div>
        </div>
      </div>
    ) : (
      node
    )
  if (route.name === 'welcome') {
    return authShell(
      <RegisterScreen onDone={enterAfterRegister} onLogin={() => setRoute({ name: 'login' })} />,
    )
  }
  if (route.name === 'intro') {
    return authShell(<IntroScreen onGo={() => setRoute({ name: 'home' })} />)
  }
  if (route.name === 'login') {
    return authShell(<LoginScreen onDone={enterApp} onRegister={() => setRoute({ name: 'welcome' })} />)
  }
  if (route.name === 'maxlogin') {
    return authShell(
      <MaxLoginScreen onDone={enterFromMax} onFallback={() => setRoute({ name: 'login' })} />,
    )
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

  // Мини-оболочка (телефон, MAX): своя главная, поток задания и панель разделов.
  if (mobile) {
    return (
      <div className="app" data-theme={paint} data-mode={mode}>
        <MiniApp
          onLogout={() => setRoute(isMaxLaunch() ? { name: 'maxlogin' } : { name: 'welcome' })}
          onFeedback={onFeedback}
        />
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

  const RAIL: RailItem[] = [
    { id: 'home', icon: 'home', title: 'Главная', go: goHome },
    { id: 'calendar', icon: 'calendar', title: 'Календарь', go: () => setRoute({ name: 'calendar' }) },
    { id: 'stats', icon: 'stats', title: 'Статистика', go: () => setRoute({ name: 'stats' }) },
    { id: 'settings', icon: 'settings', title: 'Настройки', go: () => setRoute({ name: 'profile' }) },
  ]

  const rail = (
    <Rail
      active={railActive}
      items={RAIL}
      theme={theme}
      onTheme={(t) => updateSettings({ theme: t })}
    />
  )

  const feedback = feedbackOpen && (
    <DisagreeModal
      ctx={{ kind: 'app', target: 'app', targetLabel: 'Отзыв о приложении' }}
      onClose={() => setFeedbackOpen(false)}
      onSent={() => undefined}
    />
  )

  // Главная — макет «MacBook Air - 15 (2)» на своём холсте; общий рейл поверх.
  if (route.name === 'home') {
    return (
      <div className="app" data-theme={paint} data-mode={mode}>
        <HomeScreen
          onTrainer={backToEge}
          onSpeaking={() => setRoute({ name: 'conversation' })}
          onDemo={startDemo}
          onStats={() => setRoute({ name: 'stats' })}
          onCalendar={() => setRoute({ name: 'calendar' })}
          onProfile={() => setRoute({ name: 'profile' })}
        />
        {rail}
        {feedback}
      </div>
    )
  }

  return (
    <div className="app" data-theme={paint} data-mode={mode}>
      {rail}
      <div className="appgrid">
        {/* Пустая колонка держит место под фиксированный рейл. */}
        <div className="leftcol" aria-hidden="true" />

        <div className="screen">
          <div className="swap" key={route.name}>
            {route.name === 'calendar' && <CalendarScreen />}

            {route.name === 'conversation' && <ConversationScreen onFeedback={onFeedback} />}

            {route.name === 'ege' && (
              <EgeMenuScreen
                onOpenTask={startSession}
                onDemo={startDemo}
                onFavorites={startFavorites}
                onStats={() => setRoute({ name: 'stats' })}
              />
            )}

            {route.name === 'stats' && <StatsScreen onBack={backToEge} />}

            {route.name === 'profile' && (
              <ProfileScreen
                onOpenStats={() => setRoute({ name: 'stats' })}
                onLogout={() => setRoute(isMaxLaunch() ? { name: 'maxlogin' } : { name: 'welcome' })}
                onClose={goHome}
              />
            )}
          </div>
        </div>
      </div>

      {feedback}
    </div>
  )
}
