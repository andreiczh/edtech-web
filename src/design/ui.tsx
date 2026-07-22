/**
 * Общие блоки нового макета. Контракт для всех экранов: чтобы «Liquid Glass» и
 * прожатие кнопки выглядели одинаково везде, их описывают здесь, а не в каждом
 * экране заново.
 */
import { useState, type CSSProperties, type ReactNode } from 'react'

/* ------------------------------------------------------------------ Кнопки */

export function Pill({
  children,
  onClick,
  quiet,
  disabled,
  title,
  active,
}: {
  children: ReactNode
  onClick?: () => void
  quiet?: boolean
  disabled?: boolean
  title?: string
  active?: boolean
}) {
  return (
    <button
      type="button"
      className={`pill pressable${quiet ? ' pill--quiet' : ''}`}
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
}: {
  title: ReactNode
  sub?: ReactNode
  onClick?: () => void
  ghost?: boolean
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      className={`card2 card2--button${ghost ? ' card2--ghost' : ''}`}
      onClick={onClick}
      disabled={disabled}
    >
      <span className="card2__title">{title}</span>
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
  const index = Math.max(
    0,
    tabs.findIndex((t) => t.id === active),
  )
  return (
    <nav
      className="segmented"
      role="tablist"
      style={{ '--i': index, '--n': tabs.length } as CSSProperties}
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
      <span className="topbar2__brand">SPEAKO</span>

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
}: {
  caption?: ReactNode
  onQuit?: () => void
  onFeedback?: () => void
  quitLabel?: string
}) {
  return (
    <footer className="bottombar2">
      {/* Кнопки без обработчика не рисуем: мёртвая кнопка хуже отсутствующей.
          Пустой span сохраняет раскладку space-between, чтобы подпись и
          Feedback не съехали влево. */}
      {onQuit ? (
        <Pill onClick={onQuit}>
          {quitLabel} <ExitIcon />
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

/** Полоса обратного отсчёта из макетов: заполнение + mm:ss + кнопка справа. */
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
  const pct = total > 0 ? Math.max(0, Math.min(100, (left / total) * 100)) : 0
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

/* Настоящего арта маскота в репозитории нет — есть только скриншоты макета,
   а картинку из чата на диск не вытащить. Поэтому компонент сначала пробует
   файл `public/mascot.png` (vite копирует public/ в корень сборки): положи туда
   PNG маскота — он подхватится на всех экранах без правок кода. Пока файла нет,
   рисуется векторная замена, максимально близкая к референсу: лежащий пухлый
   фиолетовый зверёк с крылышками-ушками, подмигивает.
   Флаг на уровне модуля — чтобы не дёргать 404 на каждом монтировании. */
let mascotFileMissing = false

export function Mascot({ style }: { style?: CSSProperties }) {
  const [missing, setMissing] = useState(mascotFileMissing)
  if (!missing) {
    return (
      <img
        className="mascot"
        src="/mascot.png"
        alt=""
        style={style}
        onError={() => {
          mascotFileMissing = true
          setMissing(true)
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
