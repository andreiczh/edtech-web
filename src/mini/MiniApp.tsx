/**
 * Оболочка мини-приложения (телефон и MAX): главная по макету 72 с нижней
 * панелью, поток задания по макетам 66·Redesign, а разделы без макетов
 * (календарь, статистика, кабинет, разговор, демо) — прежние экраны внутри
 * той же оболочки, пока не пришёл их дизайн.
 */
import { useCallback, useState } from 'react'

import { pickDemoItems, pickSession, variantById } from '../ege2/tasks'
import type { TaskFeedback } from '../ege2/feedback'
import { CalendarScreen } from '../screens/CalendarScreen'
import { ConversationScreen } from '../screens/ConversationScreen'
import { ProfileScreen } from '../screens/ProfileScreen'
import { SessionScreen } from '../screens/SessionScreen'
import { StatsScreen } from '../screens/StatsScreen'
import { MiniHome, MiniTabs, type MiniTab } from './MiniHome'
import { Practice, type PracticeItem } from './Practice'
import { ResultScreen } from './ResultScreen'
import './mini.css'

type View =
  | { name: 'tab'; tab: MiniTab }
  | { name: 'conversation' }
  | { name: 'practice'; items: PracticeItem[]; nonce: number }
  | { name: 'demo'; nonce: number }
  /** Просмотр экрана разбора без микрофона и сервера: пример из sessionStorage
      (ключ gospeak.mini.demo, открывается по #mini-result). Нужен дизайнеру и
      приёмке — прогнать экран с готовым разбором. */
  | { name: 'result-demo'; variantId: string; feedback: TaskFeedback; transcript: string }

function initialView(): View {
  if (window.location.hash === '#mini-result') {
    try {
      const raw = sessionStorage.getItem('gospeak.mini.demo')
      const d = raw ? (JSON.parse(raw) as { variantId: string; feedback: TaskFeedback; transcript: string }) : null
      if (d && d.feedback && variantById(39, d.variantId)) {
        return { name: 'result-demo', variantId: d.variantId, feedback: d.feedback, transcript: d.transcript }
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
    // Пока в новом дизайне живёт только №39: серия из его вариантов, как в
    // тренажёре. Когда придут макеты остальных номеров — цепочка 39→42.
    const items = pickSession(39).map((v) => ({ taskId: 39 as const, variantId: v.id }))
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
    const variant = variantById(39, view.variantId)!
    return (
      <div className="mini">
        <ResultScreen
          no={1}
          taskId={39}
          variant={variant}
          feedback={view.feedback}
          transcript={view.transcript}
          failure={null}
          blob={null}
          seconds={0}
          onQuit={home}
          onNext={home}
        />
      </div>
    )
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
