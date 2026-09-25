/**
 * Настройки — макет «settings-exact-editable 1» (24.09.2026): профиль и три
 * раздела. Ряды привязаны к тому, что в системе есть: транскрибирование и
 * громкость — настройки аккаунта (/me/settings), режим общения —
 * выбор собеседника (с тем же подтверждением для грубого, что в кабинете),
 * избранное — серия из отмеченных заданий, «помощь и поддержка» — форма
 * обратной связи. Чего нет (уведомления, язык системы) — ряд нарисован по
 * макету, но выключен и не притворяется работающим. Профиль ведёт в прежний
 * кабинет (ник, согласие на корпус, выход) — макета для него пока нет.
 */
import { useEffect, useState, type CSSProperties } from 'react'

import { fetchPersonas, updateSettings, useSettings, type Persona } from '../account/me'
import { currentUser } from '../auth/auth'
import { ConfirmDialog } from '../design/ui'
import { Icon } from './Ambient'
import { ICONS, type MiniIcon } from './icons'

const u = (v: number) => `calc(${v} * var(--u))`

/* Тот же ключ, что в кабинете (ProfileScreen): согласие на грубого
   собеседника даётся один раз с любого экрана. */
const ADULT_OK_KEY = 'pingo.adultOk.v1'

function adultAccepted(id: string): boolean {
  try {
    return (JSON.parse(localStorage.getItem(ADULT_OK_KEY) || '[]') as string[]).includes(id)
  } catch {
    return false
  }
}

function rememberAdultAccepted(id: string) {
  try {
    const prev = JSON.parse(localStorage.getItem(ADULT_OK_KEY) || '[]') as string[]
    localStorage.setItem(ADULT_OK_KEY, JSON.stringify([...new Set([...prev, id])]))
  } catch {
    /* приватный режим — спросим ещё раз */
  }
}

function RowIcon({ icon }: { icon: MiniIcon }) {
  return (
    <span className="st-row__icon" aria-hidden="true">
      <Icon icon={icon} style={{ width: u(icon.w), height: u(icon.h) } as CSSProperties} />
    </span>
  )
}

function Toggle({
  on,
  label,
  disabled,
  onChange,
}: {
  on: boolean
  label: string
  disabled?: boolean
  onChange: () => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      className={`m-btn st-tog${on ? ' st-tog--on' : ''}`}
      disabled={disabled}
      onClick={onChange}
    />
  )
}

export function MiniSettings({
  onProfile,
  onFavorites,
  favoritesReady,
  onSupport,
}: {
  onProfile: () => void
  onFavorites: () => void
  favoritesReady: boolean
  onSupport: () => void
}) {
  const settings = useSettings()
  const [personas, setPersonas] = useState<Persona[]>([])
  const [choosing, setChoosing] = useState(false)
  const [confirming, setConfirming] = useState<Persona | null>(null)
  useEffect(() => {
    let alive = true
    void fetchPersonas().then((p) => alive && setPersonas(p))
    return () => {
      alive = false
    }
  }, [])

  const current = personas.find((p) => p.id === settings.persona)
  const nick = currentUser()?.nickname ?? ''

  const choose = (p: Persona) => {
    if (p.adult && !adultAccepted(p.id)) {
      setConfirming(p)
      return
    }
    updateSettings({ persona: p.id })
    setChoosing(false)
  }

  return (
    <div className="st-page">
      <h1 className="st-h1">Настройки</h1>

      <button
        type="button"
        className="m-btn st-card st-profile"
        onClick={onProfile}
        aria-label={`Аккаунт ${nick}: ник, согласие на записи, выход`}
      >
        <span className="st-profile__ava" aria-hidden="true" />
        <span className="st-profile__name">{nick}</span>
        <Icon icon={ICONS.chevron} className="st-chev" />
      </button>

      <h2 className="st-sec" style={{ top: u(300) }}>
        Основные
      </h2>
      <div className="st-card st-card--rows" style={{ top: u(322.8) }}>
        <div className="st-row st-row--off" aria-disabled="true" title="Уведомлений в приложении пока нет">
          <RowIcon icon={ICONS.bell} />
          <span className="st-row__l">Уведомления</span>
          <Toggle on={false} disabled label="Уведомления — пока недоступно" onChange={() => undefined} />
        </div>
        {/* Тёмных цветов у мини-экранов пока нет (макеты светлые), а тумблер,
            который ничего не меняет, — обман. Ряд стоит по макету, но выключен,
            как «Уведомления» (аудит 26.09.2026, §6.47). */}
        <div className="st-row st-row--off" aria-disabled="true" title="Тёмная тема на телефоне появится позже">
          <RowIcon icon={ICONS.moon} />
          <span className="st-row__l">Тёмная тема</span>
          <Toggle on={false} disabled label="Тёмная тема — пока недоступно" onChange={() => undefined} />
        </div>
        <div className="st-row st-row--off" aria-disabled="true" title="Пока только русский">
          <RowIcon icon={ICONS.aaSmall} />
          <span className="st-row__l">Язык системы</span>
          <span className="st-row__val">Русский</span>
          <Icon icon={ICONS.chevron} className="st-chev" />
        </div>
      </div>

      <h2 className="st-sec" style={{ top: u(477.8) }}>
        Обучение
      </h2>
      <div className="st-card st-card--rows" style={{ top: u(501.3) }}>
        <button
          type="button"
          className="m-btn st-row"
          onClick={() => setChoosing((v) => !v)}
          aria-expanded={choosing}
          aria-label={`Режим общения: ${current?.label ?? 'загружается'}. Выбрать собеседника`}
        >
          <RowIcon icon={ICONS.micSmall} />
          <span className="st-row__l">Режим общения</span>
          <span className="st-row__val">{current?.label ?? '…'}</span>
          <Icon icon={ICONS.chevron} className="st-chev" />
        </button>
        {choosing && personas.length > 0 && (
          <div className="st-choice" role="radiogroup" aria-label="Собеседник">
            {personas.map((p) => (
              <button
                key={p.id}
                type="button"
                role="radio"
                aria-checked={p.id === settings.persona}
                className={`m-btn st-choice__b${p.id === settings.persona ? ' st-choice__b--on' : ''}`}
                onClick={() => choose(p)}
              >
                {p.label}
                <span className="st-choice__d">{p.description}</span>
              </button>
            ))}
          </div>
        )}
        <div className="st-row">
          <RowIcon icon={ICONS.transcript} />
          <span className="st-row__l">Транскрибирование</span>
          <Toggle
            on={settings.showText}
            label="Показывать текст ответа в разговоре"
            onChange={() => updateSettings({ showText: !settings.showText })}
          />
        </div>
        <div className="st-row">
          <RowIcon icon={ICONS.speaker} />
          <span className="st-row__l">Громкость голоса</span>
          <input
            type="range"
            className="st-slider"
            min={0}
            max={1}
            step={0.05}
            value={settings.volume}
            aria-label={`Громкость голоса: ${Math.round(settings.volume * 100)}%`}
            onChange={(e) => updateSettings({ volume: Number(e.target.value) })}
          />
        </div>
        <button
          type="button"
          className="m-btn st-row"
          onClick={onFavorites}
          disabled={!favoritesReady}
          aria-label={favoritesReady ? 'Избранное: пройти отмеченные задания' : 'Избранное пусто — отмечай ☆ в задании'}
        >
          <RowIcon icon={ICONS.starLine} />
          <span className="st-row__l">Избранное</span>
          {!favoritesReady && <span className="st-row__val">пусто</span>}
          <Icon icon={ICONS.chevron} className="st-chev" />
        </button>
      </div>

      <h2 className="st-sec" style={{ top: u(696.1) }}>
        Другое
      </h2>
      <div className="st-card st-card--rows" style={{ top: u(719.3) }}>
        <button type="button" className="m-btn st-row" onClick={onSupport}>
          <RowIcon icon={ICONS.headset} />
          <span className="st-row__l" style={{ left: u(64.9) }}>
            Помощь и поддержка
          </span>
          <Icon icon={ICONS.chevron} className="st-chev" />
        </button>
      </div>

      {confirming && (
        <ConfirmDialog
          title={`${confirming.label} — точно включаем?`}
          body={confirming.warning || 'Этот собеседник говорит грубо.'}
          stay="Не надо"
          leave="Мне есть 18, включить"
          onStay={() => setConfirming(null)}
          onLeave={() => {
            rememberAdultAccepted(confirming.id)
            updateSettings({ persona: confirming.id })
            setConfirming(null)
            setChoosing(false)
          }}
        />
      )}
    </div>
  )
}
