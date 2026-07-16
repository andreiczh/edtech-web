import { useState } from 'react'
import { Sidebar } from './components/Sidebar'
import { TrainerScreen } from './components/TrainerScreen'
import { Placeholder } from './components/Placeholder'
import type { Mode, EgeTab } from './types'

const EGE_TABS: { id: EgeTab; label: string }[] = [
  { id: 'trainer', label: 'Тренажёр' },
  { id: 'format', label: 'Ответ в формате ЕГЭ' },
]

// Каждому режиму — свой оттенок фона (одна палитра, разный тон)
const THEME: Record<Mode, 'blue' | 'green' | 'red'> = {
  conversation: 'blue',
  ege: 'green',
  oge: 'red',
}

export default function App() {
  const [mode, setMode] = useState<Mode>('conversation')
  const [tab, setTab] = useState<EgeTab>('trainer')

  return (
    <div className="app" data-theme={THEME[mode]}>
      <Sidebar mode={mode} onSelect={setMode} />

      <main className="main">
        {mode === 'conversation' && (
          <div className="content">
            <TrainerScreen />
          </div>
        )}

        {mode === 'ege' && (
          <>
            <div className="tabs" role="tablist" aria-label="Разделы подготовки к ЕГЭ">
              {EGE_TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={tab === t.id}
                  className={`tab${tab === t.id ? ' tab--active' : ''}`}
                  onClick={() => setTab(t.id)}
                >
                  {t.label}
                </button>
              ))}
            </div>

            <div className="content">
              {tab === 'trainer' ? (
                <TrainerScreen />
              ) : (
                <Placeholder title="Ответ в формате ЕГЭ" note="Скоро — набросаем функционал." />
              )}
            </div>
          </>
        )}

        {mode === 'oge' && (
          <div className="content">
            <Placeholder title="Подготовка к ОГЭ" note="soon…" />
          </div>
        )}
      </main>
    </div>
  )
}
