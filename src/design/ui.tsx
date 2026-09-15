/**
 * Общие блоки нового макета. Контракт для всех экранов: чтобы «Liquid Glass» и
 * прожатие кнопки выглядели одинаково везде, их описывают здесь, а не в каждом
 * экране заново.
 */
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

/* --------------------------------------------------------- Подтверждение */

/**
 * Модалка «точно выйти?». Слова приходят снаружи: их диктует выбранный
 * собеседник, и Гондон прощается не так, как Терпеливый.
 *
 * Рендерится порталом в body — то же правило, что у модалки личного кабинета:
 * `backdrop-filter` на панелях делает их контейнером для position:fixed, и
 * вложенная модалка проваливается под них (см. src/CLAUDE.md).
 *
 * Уход — действие необратимое (ответ не разберут), поэтому по умолчанию
 * подсвечена кнопка «остаться», Esc отменяет, а клик по фону НЕ выходит:
 * промахнуться мимо модалки и потерять запись было бы обидно.
 */
export function ConfirmDialog({
  title,
  body,
  stay,
  leave,
  onStay,
  onLeave,
}: {
  title: string
  body: string
  stay: string
  leave: string
  onStay: () => void
  onLeave: () => void
}) {
  const stayRef = useRef<HTMLButtonElement | null>(null)
  // Свежий колбэк в ref: эффект не должен пересоздаваться из-за инлайновой
  // стрелки родителя, иначе фокус перескакивает при каждом чужом рендере
  // (та же поломка, что чинилась в Disagree 05.08.2026).
  const stayCb = useRef(onStay)
  stayCb.current = onStay

  useEffect(() => {
    stayRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') stayCb.current()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return createPortal(
    <div className="modal-backdrop" onClick={onStay}>
      <div
        className="modal card2 glass confirm"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="modal__title" id="confirm-title">
          {title}
        </h2>
        <p className="modal__body">{body}</p>
        <div className="confirm__foot">
          <button type="button" className="pill pressable confirm__leave" onClick={onLeave}>
            {leave}
          </button>
          <button ref={stayRef} type="button" className="pill pressable" onClick={onStay}>
            {stay}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}

/* ------------------------------------------------------------------ Кнопки */

export function Pill({
  children,
  onClick,
  quiet,
  disabled,
  title,
  active,
  accent,
}: {
  children: ReactNode
  onClick?: () => void
  quiet?: boolean
  disabled?: boolean
  title?: string
  active?: boolean
  /** Главное действие экрана. Остаётся фиолетовой во всех темах — на красном и
      зелёном фоне это единственное цветовое пятно, и глаз идёт к нему.
      Ставить не больше одной-двух на экран, иначе акцент перестаёт работать. */
  accent?: boolean
}) {
  return (
    <button
      type="button"
      className={`pill pressable${quiet ? ' pill--quiet' : ''}${accent ? ' pill--accent' : ''}`}
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-pressed={active}
    >
      {children}
    </button>
  )
}

/** Карточка-кнопка меню (задания ЕГЭ, DEMO, STATS). */
export function CardButton({
  title,
  sub,
  onClick,
  ghost,
  disabled,
  fit,
}: {
  title: ReactNode
  sub?: ReactNode
  onClick?: () => void
  ghost?: boolean
  disabled?: boolean
  /** Длинный заголовок: кегль подгоняется под ширину карточки, а не окна */
  fit?: boolean
}) {
  return (
    <button
      type="button"
      className={`card2 card2--button${ghost ? ' card2--ghost' : ''}${fit ? ' card2--fit' : ''}`}
      onClick={onClick}
      disabled={disabled}
    >
      <span className={`card2__title${fit ? ' card2__title--fit' : ''}`}>{title}</span>
      {sub && <span className="card2__sub">{sub}</span>}
    </button>
  )
}

/* ------------------------------------------------------------------ Панели */

export type TopTab = { id: string; label: string; disabled?: boolean }

/**
 * Переключатель вкладок с ПЛАВНО ЕЗДЯЩИМ бегунком (как в присланном референсе
 * с тумблером день/ночь). Раньше активная вкладка просто мгновенно меняла фон —
 * пользователь назвал это некрасивым, и был прав: переключение читалось как
 * подмена, а не как движение.
 *
 * Подложка одна на весь переключатель, её позиция считается из индекса активной
 * вкладки. Поэтому вкладок может быть сколько угодно, ничего не пересчитывая.
 */
export function SegmentedTabs({
  tabs,
  active,
  onTab,
}: {
  tabs: TopTab[]
  active?: string
  onTab?: (id: string) => void
}) {
  const navRef = useRef<HTMLElement>(null)
  const draggingRef = useRef(false)
  /* Во время перетаскивания бегунок следует за пальцем/курсором, а не за
     активной вкладкой — dragIdx временно перебивает индекс из пропсов. */
  const [dragIdx, setDragIdx] = useState<number | null>(null)

  const activeIndex = Math.max(
    0,
    tabs.findIndex((t) => t.id === active),
  )

  const idxFromX = (clientX: number) => {
    const el = navRef.current
    if (!el) return activeIndex
    const r = el.getBoundingClientRect()
    const rel = (clientX - r.left) / Math.max(1, r.width)
    return Math.min(tabs.length - 1, Math.max(0, Math.floor(rel * tabs.length)))
  }

  const commit = (idx: number) => {
    const t = tabs[idx]
    if (t && !t.disabled && t.id !== active) onTab?.(t.id)
  }

  return (
    <nav
      ref={navRef}
      className={`segmented${dragIdx !== null ? ' segmented--drag' : ''}`}
      role="tablist"
      style={{ '--i': dragIdx ?? activeIndex, '--n': tabs.length } as CSSProperties}
      /* Тумблер можно не только кликать, но и ЗАЖАТЬ И ПОТЯНУТЬ, как физический
         переключатель (просьба пользователя, референс — тумблер день/ночь).
         Pointer capture держит перетаскивание, даже когда курсор ушёл с полосы.
         Клик продолжает работать: он превращается в down+up в одной точке. */
      onPointerDown={(e) => {
        draggingRef.current = true
        navRef.current?.setPointerCapture(e.pointerId)
        setDragIdx(idxFromX(e.clientX))
      }}
      onPointerMove={(e) => {
        if (draggingRef.current) setDragIdx(idxFromX(e.clientX))
      }}
      onPointerUp={(e) => {
        if (!draggingRef.current) return
        draggingRef.current = false
        setDragIdx(null)
        commit(idxFromX(e.clientX))
      }}
      onPointerCancel={() => {
        draggingRef.current = false
        setDragIdx(null)
      }}
    >
      <span className="segmented__thumb" aria-hidden="true" />
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          aria-selected={active === t.id}
          disabled={t.disabled}
          className={`tab2${active === t.id ? ' tab2--active' : ''}`}
          onClick={() => onTab?.(t.id)}
          title={t.disabled ? 'Скоро' : undefined}
        >
          {t.label}
        </button>
      ))}
    </nav>
  )
}

export function TopBar({
  tabs,
  active,
  onTab,
  onProfile,
}: {
  tabs?: TopTab[]
  active?: string
  onTab?: (id: string) => void
  onProfile?: () => void
}) {
  return (
    <header className="topbar2">
      <span className="topbar2__brand">GoSpeak</span>

      {tabs && tabs.length > 0 && (
        <SegmentedTabs tabs={tabs} active={active} onTab={onTab} />
      )}

      <Pill onClick={onProfile}>Profile</Pill>
    </header>
  )
}

export function BottomBar({
  caption,
  onQuit,
  onFeedback,
  quitLabel = 'QUIT',
  quitIcon = <ExitIcon />,
}: {
  caption?: ReactNode
  onQuit?: () => void
  onFeedback?: () => void
  quitLabel?: string
  /** Иконка левой кнопки. Отключается (`null`) там, где кнопка не про выход:
      значок «выйти» рядом со словом «Разбор» обещал бы не то действие. */
  quitIcon?: ReactNode
}) {
  return (
    <footer className="bottombar2">
      {/* Кнопки без обработчика не рисуем: мёртвая кнопка хуже отсутствующей.
          Пустой span сохраняет раскладку space-between, чтобы подпись и
          Feedback не съехали влево. */}
      {onQuit ? (
        <Pill onClick={onQuit}>
          {quitLabel}
          {quitIcon ? <> {quitIcon}</> : null}
        </Pill>
      ) : (
        <span />
      )}
      <div className="bottombar2__caption">{caption}</div>
      {onFeedback ? (
        <Pill onClick={onFeedback}>
          Feedback <ExitIcon />
        </Pill>
      ) : (
        <span />
      )}
    </footer>
  )
}

/* ------------------------------------------------------------- Обратный счёт */

/** Полоса обратного отсчёта из макетов: заполнение + mm:ss + кнопка справа.

    Полоса стартует БЕЛОЙ и заливается фиолетовым слева направо по мере хода
    времени (замечание владельца, 23.07.2026): заполнение = прошедшее время,
    а не остаток. Цифра рядом по-прежнему показывает, сколько осталось. */
export function CountdownBar({
  left,
  total,
  onEnd,
  endLabel = 'End task',
}: {
  left: number
  total: number
  onEnd?: () => void
  endLabel?: string
}) {
  const pct = total > 0 ? Math.max(0, Math.min(100, ((total - left) / total) * 100)) : 0
  const mm = String(Math.floor(left / 60)).padStart(2, '0')
  const ss = String(left % 60).padStart(2, '0')
  return (
    <div className={`countdown${left <= 10 ? ' countdown--urgent' : ''}`}>
      <div
        className="countdown__track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={left}
        aria-label="Осталось времени"
      >
        <div className="countdown__fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="countdown__time">
        {mm}:{ss}
      </span>
      {onEnd && <Pill onClick={onEnd}>{endLabel}</Pill>}
    </div>
  )
}

/* ------------------------------------------------------------------ Мелочи */

function ExitIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/* Маскоты. Их два:
 *   /mascot.png     — ОСНОВНОЙ (фиолетовый лежащий), лицо бренда;
 *   /mascot-alt.png — экспериментальный (синий круглый).
 * Файлы кладутся в public/ — vite копирует их в корень сборки.
 *
 * Правило пользователя: «одна линия — один маскот», два зверя не должны
 * встретиться в одной сессии. Поэтому выбор делается ОДИН раз на вкладку
 * (sessionStorage) и дальше не меняется: основной показывается почти всем,
 * экспериментальный — небольшой доле сессий. Принудительно посмотреть вариант:
 * открыть сайт с ?mascot=alt или ?mascot=main.
 *
 * Пока файлов нет, рисуется векторная замена. Флаги 404 — на уровне модуля,
 * чтобы не дёргать сеть на каждом монтировании. */
type MascotVariant = 'main' | 'alt'

const ALT_SHARE = 0.15 // доля сессий с экспериментальным маскотом

function pickMascotVariant(): MascotVariant {
  try {
    const forced = new URLSearchParams(window.location.search).get('mascot')
    if (forced === 'alt' || forced === 'main') {
      sessionStorage.setItem('pingo.mascot', forced)
      return forced
    }
    const saved = sessionStorage.getItem('pingo.mascot')
    if (saved === 'alt' || saved === 'main') return saved
    const v: MascotVariant = Math.random() < ALT_SHARE ? 'alt' : 'main'
    sessionStorage.setItem('pingo.mascot', v)
    return v
  } catch {
    return 'main'
  }
}

const MASCOT_VARIANT = pickMascotVariant()
/* Цепочка файлов: у alt-сессии при отсутствии её файла — откат на основной,
   и только потом на вектор. Основной никогда не откатывается в alt. */
const MASCOT_CHAIN =
  MASCOT_VARIANT === 'alt' ? ['/mascot-alt.png', '/mascot.png'] : ['/mascot.png']
const mascotFileMissing: Record<string, boolean> = {}

export function Mascot({ style }: { style?: CSSProperties }) {
  const [, bump] = useState(0)
  const src = MASCOT_CHAIN.find((f) => !mascotFileMissing[f])
  if (src) {
    return (
      <img
        className="mascot"
        src={src}
        alt=""
        style={style}
        onError={() => {
          mascotFileMissing[src] = true
          bump((n) => n + 1)
        }}
      />
    )
  }
  return (
    <svg className="mascot" viewBox="0 0 230 150" style={style} aria-hidden="true">
      <defs>
        <linearGradient id="m-body" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#cdc5f4" />
          <stop offset="1" stopColor="#8d84d9" />
        </linearGradient>
        <linearGradient id="m-wing" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#b7aeee" />
          <stop offset="1" stopColor="#9a90e0" />
        </linearGradient>
      </defs>

      {/* тельце лежит, как на референсе */}
      <ellipse cx="118" cy="92" rx="86" ry="50" fill="url(#m-body)" />
      <ellipse cx="122" cy="108" rx="58" ry="28" fill="#f1edff" opacity="0.92" />

      {/* крылышки-ушки */}
      <path d="M74 50 C64 26 44 18 32 24 C46 30 56 42 60 58 Z" fill="url(#m-wing)" />
      <path d="M150 48 C158 24 178 16 190 22 C176 28 166 40 162 56 Z" fill="url(#m-wing)" />

      {/* хвостик-крылышко сбоку */}
      <path d="M196 88 q20 -8 26 4 q-12 12 -28 6 z" fill="#b7aeee" />

      {/* открытый глаз + подмигивающий */}
      <circle cx="92" cy="82" r="8" fill="#332e5c" />
      <circle cx="95" cy="79" r="2.6" fill="#fff" />
      <path d="M136 82 q8 -7 16 0" stroke="#332e5c" strokeWidth="4.5" strokeLinecap="round" fill="none" />

      {/* улыбка и румянец */}
      <path d="M106 96 q9 8 18 0" stroke="#332e5c" strokeWidth="4.5" strokeLinecap="round" fill="none" />
      <ellipse cx="78" cy="96" rx="7" ry="4.5" fill="#ffb6a6" opacity="0.8" />
      <ellipse cx="158" cy="96" rx="7" ry="4.5" fill="#ffb6a6" opacity="0.8" />
    </svg>
  )
}
