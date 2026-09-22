/**
 * Оболочка мини-приложения (телефон и MAX): главная по макету 72 с нижней
 * панелью, поток заданий по макетам 66·Redesign (сейчас №39 и №40), а
 * разделы без макетов (календарь, статистика, кабинет, разговор, демо) —
 * прежние экраны внутри той же оболочки, пока не пришёл их дизайн.
 */
import { useCallback, useEffect, useState } from 'react'

import type { TaskFeedback } from '../ege2/feedback'
import { TASKS, pickDemoItems, pickSession, variantById, type TaskId } from '../ege2/tasks'
import { CalendarScreen } from '../screens/CalendarScreen'
import { ConversationScreen } from '../screens/ConversationScreen'
import { ProfileScreen } from '../screens/ProfileScreen'
import { SessionScreen } from '../screens/SessionScreen'
import { StatsScreen } from '../screens/StatsScreen'
import { MiniHome, MiniTabs, type MiniTab } from './MiniHome'
import { Practice, type PracticeItem } from './Practice'
import { ResultScreen } from './ResultScreen'
import { ResultScreen40 } from './ResultScreen40'
import './mini.css'

/** Номера, у которых уже есть мобильные макеты, — в порядке экзамена. */
const MINI_TASKS: TaskId[] = [39, 40]

interface Demo {
  taskId?: number
  variantId: string
  feedback: TaskFeedback
  transcript: string
  audio?: string
}

type View =
  | { name: 'tab'; tab: MiniTab }
  | { name: 'conversation' }
  | { name: 'practice'; items: PracticeItem[]; nonce: number }
  | { name: 'demo'; nonce: number }
  /** Просмотр экрана разбора без микрофона и сервера: пример из sessionStorage
      (ключ gospeak.mini.demo, открывается по #mini-result). Нужен дизайнеру и
      приёмке — прогнать экран с готовым разбором. */
  | { name: 'result-demo'; taskId: TaskId; demo: Demo }

function initialView(): View {
  // #mini-practice=40 — поток заданий только с указанными номерами: приёмка
  // и дизайнер смотрят экраны №40, не проходя перед этим №39 с микрофоном.
  const m = /^#mini-practice=([\d,]+)$/.exec(window.location.hash)
  if (m) {
    const items = m[1]
      .split(',')
      .map(Number)
      .filter((id): id is TaskId => MINI_TASKS.includes(id as TaskId))
      .map((id) => ({ taskId: id, variantId: pickSession(id, 1)[0]?.id }))
      .filter((i): i is PracticeItem => typeof i.variantId === 'string')
    if (items.length) return { name: 'practice', items, nonce: Date.now() }
  }
  if (window.location.hash === '#mini-result') {
    try {
      const raw = sessionStorage.getItem('gospeak.mini.demo')
      const d = raw ? (JSON.parse(raw) as Demo) : null
      const taskId: TaskId = d?.taskId === 40 ? 40 : 39
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

  const startPractice = useCallback(() => {
    // Цепочка заданий, как на экзамене, — по одному варианту каждого номера,
    // у которого уже есть мобильный макет (№41–42 ждут своих).
    const items = MINI_TASKS.filter((id) => !TASKS[id].comingSoon)
      .map((id) => ({ taskId: id, variantId: pickSession(id, 1)[0]?.id }))
      .filter((i): i is PracticeItem => typeof i.variantId === 'string')
    if (items.length) setView({ name: 'practice', items, nonce: Date.now() })
  }, [])

  if (view.name === 'practice') {
    return (
      <div className="mini">
        <Practice key={view.nonce} items={view.items} onExit={home} />
      </div>
    )
  }

  if (view.name === 'result-demo') {
    return <ResultDemo taskId={view.taskId} demo={view.demo} onExit={home} />
  }

  if (view.name === 'demo') {
    return (
      <div className="mini">
        <div className="mini__frame">
          <div className="mini-legacy" style={{ bottom: 0 }} key={view.nonce}>
            <SessionScreen
              items={pickDemoItems()}
              onExit={home}
              onRestart={() => setView({ name: 'demo', nonce: Date.now() })}
            />
          </div>
        </div>
      </div>
    )
  }

  const tab: MiniTab = view.name === 'tab' ? view.tab : 'home'
  const onTab = (t: MiniTab) => setView({ name: 'tab', tab: t })

  return (
    <div className={`mini${tab === 'home' && view.name === 'tab' ? ' mini--home' : ''}`}>
      <div className="mini__frame">
        {view.name === 'tab' && view.tab === 'home' ? (
          <div className="mini__scroll">
            <MiniHome
              onPractice={startPractice}
              onSpeaking={() => setView({ name: 'conversation' })}
              onDemo={() => setView({ name: 'demo', nonce: Date.now() })}
              onErrors={() => setView({ name: 'tab', tab: 'stats' })}
            />
          </div>
        ) : (
          <div className="mini-legacy">
            <div className="screen">
              <div className="swap" key={view.name === 'tab' ? view.tab : view.name}>
                {view.name === 'conversation' && <ConversationScreen onFeedback={onFeedback} />}
                {view.name === 'tab' && view.tab === 'calendar' && <CalendarScreen />}
                {view.name === 'tab' && view.tab === 'stats' && <StatsScreen onBack={home} />}
                {view.name === 'tab' && view.tab === 'settings' && (
                  <ProfileScreen
                    onOpenStats={() => setView({ name: 'tab', tab: 'stats' })}
                    onLogout={onLogout}
                    onClose={home}
                  />
                )}
              </div>
            </div>
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
      {taskId === 40 ? (
        <ResultScreen40 no={2} {...common} />
      ) : (
        <ResultScreen no={1} transcript={demo.transcript} {...common} />
      )}
    </div>
  )
}
