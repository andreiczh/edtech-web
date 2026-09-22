/**
 * Оболочка мини-приложения (телефон и MAX): главная по макету 72 с нижней
 * панелью, выбор задания и поток заданий по макетам 66·Redesign (№39, №40;
 * №41 и №42 — прежний экран задания внутри той же оболочки, пока не пришли
 * их макеты), а разделы без макетов (календарь, статистика, кабинет,
 * разговор) — прежние экраны внутри оболочки.
 */
import { useCallback, useEffect, useState } from 'react'

import type { TaskFeedback } from '../ege2/feedback'
import { TASK_ORDER, pickDemoItems, pickSession, variantById, type TaskId } from '../ege2/tasks'
import { CalendarScreen } from '../screens/CalendarScreen'
import { ConversationScreen } from '../screens/ConversationScreen'
import { ProfileScreen } from '../screens/ProfileScreen'
import { StatsScreen } from '../screens/StatsScreen'
import { MiniHome, MiniTabs, type MiniTab } from './MiniHome'
import { Practice, type PracticeItem } from './Practice'
import { ResultScreen } from './ResultScreen'
import { ResultScreen40 } from './ResultScreen40'
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
  | { name: 'conversation' }
  /** Тренажёр: сначала выбор задания 1–4, потом серия выбранного номера. */
  | { name: 'picker' }
  | { name: 'practice'; items: PracticeItem[]; nonce: number }
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

  /** Выбранный номер: серия из пяти ещё не решённых вариантов, как в
      настольном тренажёре; «К следующему заданию» на разборе ведёт к
      следующему варианту той же серии. */
  const startTask = useCallback((id: TaskId) => {
    const items = pickSession(id, 5).map((v) => ({ taskId: id, variantId: v.id }))
    if (items.length) setView({ name: 'practice', items, nonce: Date.now() })
  }, [])

  /** DEMO — полный экзамен: по одному варианту каждого номера по порядку,
      каждый начинается с отсчёта «Preparation 5…1», как и в тренажёре. */
  const startDemo = useCallback(() => {
    const items = pickDemoItems()
    if (items.length) setView({ name: 'practice', items, nonce: Date.now() })
  }, [])

  if (view.name === 'practice') {
    return (
      <div className="mini">
        <Practice key={view.nonce} items={view.items} onExit={home} />
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

  const tab: MiniTab = view.name === 'tab' ? view.tab : 'home'
  const onTab = (t: MiniTab) => setView({ name: 'tab', tab: t })

  return (
    <div className={`mini${tab === 'home' && view.name === 'tab' ? ' mini--home' : ''}`}>
      <div className="mini__frame">
        {view.name === 'tab' && view.tab === 'home' ? (
          <div className="mini__scroll">
            <MiniHome
              onPractice={() => setView({ name: 'picker' })}
              onSpeaking={() => setView({ name: 'conversation' })}
              onDemo={startDemo}
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
