/**
 * Общие блоки нового макета. Контракт для всех экранов: чтобы «Liquid Glass» и
 * прожатие кнопки выглядели одинаково везде, их описывают здесь, а не в каждом
 * экране заново.
 */
import type { CSSProperties, ReactNode } from 'react'

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
      <Pill onClick={onQuit}>
        {quitLabel} <ExitIcon />
      </Pill>
      <div className="bottombar2__caption">{caption}</div>
      <Pill onClick={onFeedback}>
        Feedback <ExitIcon />
      </Pill>
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

/**
 * Маскот со скринов 4 и 7. Настоящий арт — растровый и его в репозитории нет,
 * поэтому здесь векторная заглушка в палитре проекта: она не «дырка в макете»,
 * а осмысленный placeholder, который не ломает композицию. Придёт файл — заменить
 * на <img src=...>, размеры и тень задаёт .mascot.
 */
export function Mascot({ style }: { style?: CSSProperties }) {
  return (
    <svg className="mascot" viewBox="0 0 200 160" style={style} aria-hidden="true">
      <defs>
        <linearGradient id="m-body" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#cfc7ff" />
          <stop offset="1" stopColor="#8f86d8" />
        </linearGradient>
      </defs>
      <ellipse cx="100" cy="104" rx="62" ry="44" fill="url(#m-body)" />
      <ellipse cx="100" cy="112" rx="42" ry="28" fill="#f4f1ff" opacity="0.9" />
      <path d="M44 74c-16-16-30-16-34-6 8 2 16 10 22 22z" fill="#a79ee6" />
      <path d="M156 74c16-16 30-16 34-6-8 2-16 10-22 22z" fill="#a79ee6" />
      <circle cx="80" cy="92" r="9" fill="#2f2a52" />
      <circle cx="83" cy="89" r="3" fill="#fff" />
      <path
        d="M112 92c4-4 10-4 14 0"
        stroke="#2f2a52"
        strokeWidth="4"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M92 108c5 5 11 5 16 0"
        stroke="#2f2a52"
        strokeWidth="4"
        strokeLinecap="round"
        fill="none"
      />
      <ellipse cx="66" cy="104" rx="7" ry="5" fill="#ffb6a6" opacity="0.75" />
      <ellipse cx="134" cy="104" rx="7" ry="5" fill="#ffb6a6" opacity="0.75" />
    </svg>
  )
}
