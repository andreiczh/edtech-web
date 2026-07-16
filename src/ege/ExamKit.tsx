import type { ReactNode } from 'react'
import type { MaterialKind } from './examFlow'
import { VoiceOrbs } from '../components/VoiceOrbs'

/** Рамка «станции»: шапка (надзаголовок + заголовок + таймер), тело, футер. */
export function ExamFrame({
  eyebrow,
  title,
  timer,
  children,
  footer,
}: {
  eyebrow?: string
  title: string
  timer?: ReactNode
  children: ReactNode
  footer?: ReactNode
}) {
  return (
    <div className="exam">
      <div className="exam__frame">
        <header className="exam__head">
          <div className="exam__titles">
            {eyebrow && <span className="exam__eyebrow">{eyebrow}</span>}
            <h2 className="exam__title">{title}</h2>
          </div>
          {timer && <div className="exam__timer">{timer}</div>}
        </header>

        <div className="exam__body">{children}</div>

        {footer && <footer className="exam__foot">{footer}</footer>}
      </div>
    </div>
  )
}

export function ExamButton({
  children,
  onClick,
  variant = 'primary',
  type = 'button',
}: {
  children: ReactNode
  onClick?: () => void
  variant?: 'primary' | 'ghost'
  type?: 'button' | 'submit'
}) {
  return (
    <button type={type} className={`exam-btn exam-btn--${variant}`} onClick={onClick}>
      {children}
    </button>
  )
}

/** Полоса прогресса таймера. tone задаёт цвет (mint — подготовка, coral — запись). */
export function Progress({ value, tone = 'mint' }: { value: number; tone?: 'mint' | 'coral' }) {
  return (
    <div className="exam-progress" role="progressbar" aria-valuenow={Math.round(value * 100)}>
      <span className={`exam-progress__fill exam-progress__fill--${tone}`} style={{ width: `${value * 100}%` }} />
    </div>
  )
}

function Skeleton({ lines = 5 }: { lines?: number }) {
  const widths = ['96%', '88%', '92%', '80%', '85%', '70%', '90%', '76%']
  return (
    <div className="skeleton-lines">
      {Array.from({ length: lines }).map((_, i) => (
        <span className="skeleton" style={{ width: widths[i % widths.length] }} key={i} />
      ))}
    </div>
  )
}

/** «Бумажный» плейсхолдер материала задания — структура без контента. */
export function Material({ kind }: { kind: MaterialKind }) {
  if (kind === 'none') return null

  if (kind === 'text') {
    return (
      <div className="paper">
        <span className="paper__badge">1</span>
        <div className="paper__label">Текст для чтения вслух</div>
        <Skeleton lines={6} />
      </div>
    )
  }

  if (kind === 'ad') {
    return (
      <div className="paper">
        <div className="paper__label">Рекламное объявление</div>
        <div className="paper__row">
          <div className="ph-image" aria-hidden="true" />
          <Skeleton lines={5} />
        </div>
      </div>
    )
  }

  if (kind === 'interview') {
    return (
      <div className="paper paper--interview">
        <div className="ph-avatar" aria-hidden="true" />
        <div>
          <div className="paper__label">Вопрос виртуального собеседника</div>
          <Skeleton lines={2} />
        </div>
      </div>
    )
  }

  // photos
  return (
    <div className="paper">
      <div className="paper__label">Фотографии для сравнения</div>
      <div className="ph-photos">
        <div className="ph-image" aria-hidden="true" />
        <div className="ph-image" aria-hidden="true" />
      </div>
    </div>
  )
}

/** Индикатор записи ответа: наши круги-эквалайзер + «REC» + таймер. */
export function RecordingIndicator({ timeLabel }: { timeLabel: string }) {
  return (
    <div className="rec">
      <div className="exam-orbs">
        <VoiceOrbs state="listening" />
      </div>
      <div className="rec__row">
        <span className="rec__dot" aria-hidden="true" />
        <span className="rec__text">Идёт запись</span>
        <span className="rec__time">{timeLabel}</span>
      </div>
    </div>
  )
}
