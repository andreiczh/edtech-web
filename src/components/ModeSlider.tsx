import { useRef, type WheelEvent, type KeyboardEvent } from 'react'
import type { Mode } from '../types'

const MODES: { id: Mode; label: string; dot: string; soon?: boolean }[] = [
  { id: 'conversation', label: 'Разговор с носителем', dot: '#67a2c5' },
  { id: 'ege', label: 'Подготовка к ЕГЭ', dot: '#9bcec1' },
  { id: 'oge', label: 'Подготовка к ОГЭ', dot: '#ffb6a6', soon: true },
]

/**
 * Круговой (зацикленный) слайдер режимов: активный — по центру, соседние —
 * сверху/снизу. Листается прокруткой колеса, стрелками ↑↓ или кликом по соседу.
 */
export function ModeSlider({ mode, onSelect }: { mode: Mode; onSelect: (m: Mode) => void }) {
  const i = MODES.findIndex((m) => m.id === mode)
  const at = (o: number) => MODES[(i + o + MODES.length) % MODES.length]
  const go = (dir: number) => onSelect(at(dir).id)
  const lastWheel = useRef(0)

  const onWheel = (e: WheelEvent) => {
    const now = Date.now()
    if (now - lastWheel.current < 350) return // одна прокрутка = один шаг
    lastWheel.current = now
    go(e.deltaY > 0 ? 1 : -1)
  }
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault()
      go(1)
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault()
      go(-1)
    }
  }

  const cur = at(0)
  const prev = at(-1)
  const next = at(1)

  return (
    <div
      className="wheel"
      onWheel={onWheel}
      onKeyDown={onKeyDown}
      tabIndex={0}
      role="listbox"
      aria-label="Режим подготовки"
    >
      <button className="wheel__arrow" onClick={() => go(-1)} aria-label="Предыдущий режим">
        ←
      </button>

      <div className="wheel__viewport">
        <button className="wheel__item wheel__item--side" onClick={() => go(-1)}>
          {prev.label}
        </button>

        <div className="wheel__item wheel__item--active" role="option" aria-selected="true">
          <span className="wheel__dot" style={{ background: cur.dot }} />
          <span>{cur.label}</span>
          {cur.soon && <span className="badge">soon…</span>}
        </div>

        <button className="wheel__item wheel__item--side" onClick={() => go(1)}>
          {next.label}
        </button>
      </div>

      <button className="wheel__arrow" onClick={() => go(1)} aria-label="Следующий режим">
        →
      </button>
    </div>
  )
}
