import { useState } from 'react'
import { Logo } from './components/Logo'
import { ModeSlider } from './components/ModeSlider'
import { Profile } from './components/Profile'
import { TrainerScreen } from './components/TrainerScreen'
import { Placeholder } from './components/Placeholder'
import { EgeFormat } from './ege/EgeFormat'
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
  const [tab, setTab] = useState<EgeTab>('format')

  return (
    <div className="app" data-theme={THEME[mode]}>
      <header className="topbar">
        <Logo />
      </header>

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
                <Placeholder title="Тренажёр" note="soon…" />
              ) : (
                <EgeFormat />
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

      <footer className="bottombar">
        <ModeSlider mode={mode} onSelect={setMode} />
        <div className="bottombar__profile">
          <Profile />
        </div>
      </footer>
    </div>
  )
}
