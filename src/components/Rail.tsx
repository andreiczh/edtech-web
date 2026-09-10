/**
 * Рейл навигации и док темы — ОДИН компонент для всех экранов (10.09.2026).
 *
 * Раньше главная рисовала свой рейл внутри масштабируемого холста, а остальные
 * экраны — рейл каркаса: размеры и отступы расходились, при переходе всё
 * «прыгало». Теперь рейл фиксирован на экране в одном месте (railwrap), а
 * контент под ним — какой угодно.
 *
 * Активный пункт — «жидкое стекло»: стеклянная плашка живёт отдельно от
 * кнопок и переезжает к активной с пружиной. Переключать можно тремя
 * способами: клик, колесо над рейлом (пролистывание по пунктам) и зажать —
 * протащить — отпустить: плашка едет за пальцем/курсором, отпускаешь над
 * пунктом — он открывается.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'

export type IconKind = 'home' | 'calendar' | 'stats' | 'settings' | 'sun' | 'moon'

/* Иконки рейла — один набор, один stroke (правило брифа). */
export function RailIcon({ kind }: { kind: IconKind }) {
  const paths: Record<IconKind, ReactNode> = {
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

export interface RailItem {
  id: string
  icon: IconKind
  title: string
  go: () => void
}

/** Группа кнопок со стеклянной плашкой: клик, колесо, перетаскивание. */
function GlassGroup({
  items,
  activeId,
  className,
  label,
}: {
  items: RailItem[]
  activeId: string
  className: string
  label: string
}) {
  const boxRef = useRef<HTMLDivElement>(null)
  const btnRefs = useRef<Array<HTMLButtonElement | null>>([])
  const [glass, setGlass] = useState<{ x: number; y: number; w: number; h: number } | null>(null)
  const [dragging, setDragging] = useState(false)
  const [underIdx, setUnderIdx] = useState<number | null>(null)
  const suppressClick = useRef(false)
  const wheelAt = useRef(0)

  const activeIdx = Math.max(0, items.findIndex((i) => i.id === activeId))

  /* Геометрия кнопок относительно группы — для плашки и для попадания при
     перетаскивании. Пересчитывается при смене актива и размера окна. */
  const rectOf = useCallback((i: number) => {
    const b = btnRefs.current[i]
    const box = boxRef.current
    if (!b || !box) return null
    const br = b.getBoundingClientRect()
    const xr = box.getBoundingClientRect()
    return { x: br.left - xr.left, y: br.top - xr.top, w: br.width, h: br.height }
  }, [])

  const snapTo = useCallback(
    (i: number) => {
      const r = rectOf(i)
      if (r) setGlass(r)
    },
    [rectOf],
  )

  useLayoutEffect(() => {
    snapTo(activeIdx)
    const box = boxRef.current
    if (!box || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => snapTo(activeIdx))
    ro.observe(box)
    return () => ro.disconnect()
  }, [activeIdx, snapTo])

  useEffect(() => {
    const onResize = () => snapTo(activeIdx)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [activeIdx, snapTo])

  /* Ближайшая кнопка к точке (в координатах группы). */
  const nearest = useCallback(
    (px: number, py: number) => {
      let best = activeIdx
      let bestD = Infinity
      items.forEach((_, i) => {
        const r = rectOf(i)
        if (!r) return
        const d = Math.hypot(px - (r.x + r.w / 2), py - (r.y + r.h / 2))
        if (d < bestD) {
          bestD = d
          best = i
        }
      })
      return best
    },
    [activeIdx, items, rectOf],
  )

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return
    const box = boxRef.current
    if (!box) return
    const start = { x: e.clientX, y: e.clientY }
    const first = rectOf(0)
    const last = rectOf(items.length - 1)
    if (!first || !last) return
    let moved = false
    const onMove = (ev: PointerEvent) => {
      const dx = ev.clientX - start.x
      const dy = ev.clientY - start.y
      if (!moved && Math.hypot(dx, dy) < 6) return
      moved = true
      setDragging(true)
      const xr = box.getBoundingClientRect()
      const px = ev.clientX - xr.left
      const py = ev.clientY - xr.top
      // Плашка едет за курсором, но не выходит за крайние кнопки.
      const cx = Math.min(Math.max(px, first.x + first.w / 2), last.x + last.w / 2)
      const cy = Math.min(Math.max(py, first.y + first.h / 2), last.y + last.h / 2)
      setGlass({ x: cx - first.w / 2, y: cy - first.h / 2, w: first.w, h: first.h })
      setUnderIdx(nearest(cx, cy))
    }
    const onUp = (ev: PointerEvent) => {
      document.removeEventListener('pointermove', onMove)
      document.removeEventListener('pointerup', onUp)
      document.removeEventListener('pointercancel', onUp)
      if (!moved) return
      setDragging(false)
      setUnderIdx(null)
      const xr = box.getBoundingClientRect()
      const target = nearest(ev.clientX - xr.left, ev.clientY - xr.top)
      suppressClick.current = true
      window.setTimeout(() => {
        suppressClick.current = false
      }, 0)
      if (target !== activeIdx) items[target].go()
      else snapTo(activeIdx)
    }
    document.addEventListener('pointermove', onMove)
    document.addEventListener('pointerup', onUp)
    document.addEventListener('pointercancel', onUp)
  }

  const onWheel = (e: React.WheelEvent) => {
    const now = Date.now()
    if (now - wheelAt.current < 420) return
    const delta = Math.abs(e.deltaY) >= Math.abs(e.deltaX) ? e.deltaY : e.deltaX
    if (Math.abs(delta) < 8) return
    wheelAt.current = now
    const next = Math.min(items.length - 1, Math.max(0, activeIdx + (delta > 0 ? 1 : -1)))
    if (next !== activeIdx) items[next].go()
  }

  const onIdx = underIdx ?? activeIdx

  return (
    <div
      ref={boxRef}
      className={className}
      role="group"
      aria-label={label}
      onPointerDown={onPointerDown}
      onWheel={onWheel}
    >
      {glass && (
        <span
          className={`rail__glass${dragging ? ' is-dragging' : ''}`}
          style={{
            transform: `translate(${glass.x}px, ${glass.y}px)${dragging ? ' scale(1.08)' : ''}`,
            width: glass.w,
            height: glass.h,
          }}
          aria-hidden="true"
        />
      )}
      {items.map((it, i) => (
        <button
          key={it.id}
          ref={(el) => {
            btnRefs.current[i] = el
          }}
          type="button"
          className={`rail__btn${i === onIdx ? ' is-on' : ''}`}
          title={it.title}
          aria-label={it.title}
          aria-current={i === activeIdx ? 'page' : undefined}
          onClick={() => {
            if (suppressClick.current) return
            it.go()
          }}
        >
          <RailIcon kind={it.icon} />
        </button>
      ))}
    </div>
  )
}

export function Rail({
  active,
  items,
  theme,
  onTheme,
}: {
  active: string
  items: RailItem[]
  theme: 'light' | 'dark' | 'auto'
  onTheme: (t: 'light' | 'dark') => void
}) {
  const dark =
    theme === 'dark' ||
    (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  const themeItems: RailItem[] = [
    { id: 'light', icon: 'sun', title: 'Светлая тема', go: () => onTheme('light') },
    { id: 'dark', icon: 'moon', title: 'Тёмная тема', go: () => onTheme('dark') },
  ]
  /* Два отдельных блока: меню — по центру колонки, док темы — внизу. */
  return (
    <div className="railwrap">
      <span className="lspacer" />
      <GlassGroup items={items} activeId={active} className="rail" label="Основная навигация" />
      <span className="lspacer" />
      <GlassGroup
        items={themeItems}
        activeId={dark ? 'dark' : 'light'}
        className="themedock"
        label="Тема оформления"
      />
    </div>
  )
}
