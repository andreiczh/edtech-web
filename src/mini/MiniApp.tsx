/**
 * Оболочка мини-приложения (телефон и MAX). Четыре вкладки по макетам от
 * 24.09.2026: главная (69), разговор (66·Redesign 39), статистика и
 * настройки; выбор задания и поток всех четырёх заданий по макетам
 * 66·Redesign. Кабинет (ник, согласие, выход) — прежний экран из настроек.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'

import { fetchMeAnalytics, type MeAnalytics } from '../account/me'
import { favoriteSessionItems, useFavorites } from '../ege2/favorites'
import type { TaskFeedback } from '../ege2/feedback'
import { TASK_ORDER, pickDemoItems, pickSession, variantById, type TaskId } from '../ege2/tasks'
import { ProfileScreen } from '../screens/ProfileScreen'
import { MiniHome, MiniTabs, type MiniTab } from './MiniHome'
import { MiniSettings } from './MiniSettings'
import { MiniStats } from './MiniStats'
import { MiniTalk } from './MiniTalk'
import { mistakesSessionItems } from './mistakes'
import { Practice, type PracticeItem } from './Practice'
import { ResultScreen } from './ResultScreen'
import { ResultScreen40 } from './ResultScreen40'
import { ResultScreen42 } from './ResultScreen42'
import { TaskPicker } from './TaskPicker'
import './mini.css'

interface Demo {
  taskId?: number
  variantId: string
  feedback: TaskFeedback
  transcript: string
  audio?: string
}

type View =
  | { name: 'tab'; tab: MiniTab }
  /** Тренажёр: сначала выбор задания 1–4, потом серия выбранного номера. */
  | { name: 'picker' }
  | { name: 'practice'; items: PracticeItem[]; nonce: number; from: 'picker' | 'home' }
  /** Прежний кабинет из настроек: ник, согласие, выход — макета нет. */
  | { name: 'profile' }
  /** Просмотр экрана разбора без микрофона и сервера: пример из sessionStorage
      (ключ gospeak.mini.demo, открывается по #mini-result). Нужен дизайнеру и
      приёмке — прогнать экран с готовым разбором. */
  | { name: 'result-demo'; taskId: TaskId; demo: Demo }

const isTaskId = (n: number): n is TaskId => TASK_ORDER.includes(n as TaskId)

function initialView(): View {
  // #mini-practice=40 — поток заданий только с указанными номерами: приёмка
  // и дизайнер смотрят экраны №40, не проходя перед этим №39 с микрофоном.
  const m = /^#mini-practice=([\d,]+)$/.exec(window.location.hash)
  if (m) {
    const items = m[1]
      .split(',')
      .map(Number)
      .filter(isTaskId)
      .map((id) => ({ taskId: id, variantId: pickSession(id, 1)[0]?.id }))
      .filter((i): i is PracticeItem => typeof i.variantId === 'string')
    if (items.length) return { name: 'practice', items, nonce: Date.now(), from: 'home' }
  }
  // #mini-tab=stats — открыть сразу вкладку (приёмка экранов без кликов)
  const t = /^#mini-tab=(home|talk|stats|settings)$/.exec(window.location.hash)
  if (t) return { name: 'tab', tab: t[1] as MiniTab }
  if (window.location.hash === '#mini-result') {
    try {
      const raw = sessionStorage.getItem('gospeak.mini.demo')
      const d = raw ? (JSON.parse(raw) as Demo) : null
      const taskId: TaskId = d && isTaskId(Number(d.taskId)) ? (Number(d.taskId) as TaskId) : 39
      if (d && d.feedback && variantById(taskId, d.variantId)) {
        return { name: 'result-demo', taskId, demo: d }
      }
    } catch {
      /* нет примера — обычная главная */
    }
  }
  return { name: 'tab', tab: 'home' }
}

export function MiniApp({ onLogout, onFeedback }: { onLogout: () => void; onFeedback: () => void }) {
  const [view, setView] = useState<View>(initialView)
  const home = useCallback(() => setView({ name: 'tab', tab: 'home' }), [])

  // Главная: карточкам «по ошибкам» и «избранное» нужно знать, есть ли данные.
  // История работ подтягивается при каждом возвращении на главную — после
  // серии заданий она уже другая.
  const homeShown = view.name === 'tab' && view.tab === 'home'
  const [analytics, setAnalytics] = useState<MeAnalytics | null>(null)
  useEffect(() => {
    if (!homeShown) return
    let alive = true
    void fetchMeAnalytics().then((a) => alive && setAnalytics(a))
    return () => {
      alive = false
    }
  }, [homeShown])
  const mistakeItems = useMemo(() => mistakesSessionItems(analytics?.history), [analytics])
  const favorites = useFavorites()
  const favoritesReady = favorites.length > 0

  const startItems = useCallback((items: PracticeItem[], from: 'picker' | 'home' = 'home') => {
    if (items.length) setView({ name: 'practice', items, nonce: Date.now(), from })
  }, [])

  /** Выбранный номер: серия из пяти ещё не решённых вариантов, как в
      настольном тренажёре; «К следующему заданию» на разборе ведёт к
      следующему варианту той же серии. */
  const startTask = useCallback(
    (id: TaskId) => startItems(pickSession(id, 5).map((v) => ({ taskId: id, variantId: v.id })), 'picker'),
    [startItems],
  )

  if (view.name === 'practice') {
    return (
      <div className="mini">
        <Practice
          key={view.nonce}
          items={view.items}
          onExit={home}
          onBack={view.from === 'picker' ? () => setView({ name: 'picker' }) : home}
        />
      </div>
    )
  }

  if (view.name === 'picker') {
    return (
      <div className="mini">
        <TaskPicker onPick={startTask} onQuit={home} />
      </div>
    )
  }

  if (view.name === 'result-demo') {
    return <ResultDemo taskId={view.taskId} demo={view.demo} onExit={home} />
  }

  const tab: MiniTab = view.name === 'tab' ? view.tab : 'settings'
  const onTab = (t: MiniTab) => setView({ name: 'tab', tab: t })
  const shell = view.name === 'profile' ? 'settings' : tab

  return (
    <div className={`mini mini--${shell}`}>
      <div className="mini__frame">
        {view.name === 'profile' ? (
          <div className="mini-legacy">
            <div className="screen">
              <ProfileScreen
                onOpenStats={() => setView({ name: 'tab', tab: 'stats' })}
                onLogout={onLogout}
                onClose={() => setView({ name: 'tab', tab: 'settings' })}
              />
            </div>
          </div>
        ) : tab === 'home' ? (
          <div className="mini__scroll">
            <MiniHome
              onPractice={() => setView({ name: 'picker' })}
              onMistakes={() => startItems(mistakeItems)}
              mistakesReady={mistakeItems.length > 0}
              onDemo={() => startItems(pickDemoItems())}
              onFavorites={() => startItems(favoriteSessionItems())}
              favoritesReady={favoritesReady}
            />
          </div>
        ) : tab === 'talk' ? (
          <MiniTalk />
        ) : tab === 'stats' ? (
          <div className="mini__scroll">
            <MiniStats />
          </div>
        ) : (
          <div className="mini__scroll">
            <MiniSettings
              onProfile={() => setView({ name: 'profile' })}
              onFavorites={() => startItems(favoriteSessionItems())}
              favoritesReady={favoritesReady}
              onSupport={onFeedback}
            />
          </div>
        )}
        <MiniTabs active={tab} onTab={onTab} />
      </div>
    </div>
  )
}

/** Экран разбора с примером: запись (если в примере есть адрес) подтягивается
    файлом, чтобы плеер и волна были видны без микрофона. */
function ResultDemo({ taskId, demo, onExit }: { taskId: TaskId; demo: Demo; onExit: () => void }) {
  const [blob, setBlob] = useState<Blob | null>(null)
  useEffect(() => {
    if (!demo.audio) return
    let alive = true
    void fetch(demo.audio)
      .then((r) => (r.ok ? r.blob() : null))
      .then((b) => alive && b && setBlob(b))
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [demo.audio])
  const variant = variantById(taskId, demo.variantId)!
  const common = { taskId, variant, feedback: demo.feedback, failure: null, blob, seconds: 0, onQuit: onExit, onNext: onExit }
  return (
    <div className="mini">
      {taskId === 42 ? (
        <ResultScreen42 transcript={demo.transcript} {...common} />
      ) : taskId === 40 || taskId === 41 ? (
        <ResultScreen40 no={taskId - 38} {...common} />
      ) : (
        <ResultScreen no={1} transcript={demo.transcript} {...common} />
      )}
    </div>
  )
}
