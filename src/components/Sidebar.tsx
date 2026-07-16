import type { Mode } from '../types'

const MODES: { id: Mode; label: string; soon?: boolean }[] = [
  { id: 'conversation', label: 'Разговор с носителем' },
  { id: 'ege', label: 'Подготовка к ЕГЭ' },
  { id: 'oge', label: 'Подготовка к ОГЭ', soon: true },
]

export function Sidebar({
  mode,
  onSelect,
}: {
  mode: Mode
  onSelect: (m: Mode) => void
}) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand__dots" aria-hidden="true">
          <i />
          <i />
          <i />
          <i />
        </span>
        <span className="brand__name">Копилот</span>
      </div>

      <nav className="nav" aria-label="Режим подготовки">
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            className={`nav__item${mode === m.id ? ' nav__item--active' : ''}`}
            onClick={() => onSelect(m.id)}
            aria-current={mode === m.id ? 'page' : undefined}
          >
            <span>{m.label}</span>
            {m.soon && <span className="badge">soon…</span>}
          </button>
        ))}
      </nav>
    </aside>
  )
}
