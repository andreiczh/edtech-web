/**
 * Личный кабинет: аккаунт, стрик и XP, настройки.
 *
 * Честность данных — как в статистике: числа приходят с сервера (/me/stats),
 * а пока их нет, экран показывает прочерки, но не выдумывает. Настройки
 * применяются мгновенно (локальный стор) и уезжают на аккаунт дебаунсом.
 */
import { useCallback, useEffect, useState, type CSSProperties } from 'react'

import {
  changeNickname,
  fetchMeStats,
  fetchPersonas,
  resetSettings,
  updateSettings,
  useSettings,
  type MeStats,
  type Persona,
} from '../account/me'
import { applyNickname, currentUser, logout, randomNickname } from '../auth/auth'
import { ConfirmDialog, Pill, SegmentedTabs } from '../design/ui'

const BLOCK: CSSProperties = { width: 'min(100%, 940px)' }

const EXAM_LABEL: Record<string, string> = {
  ege: 'Готовлюсь к ЕГЭ',
  oge: 'Готовлюсь к ОГЭ',
  other: 'Занимаюсь для себя',
}

const WEEKDAY = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб']

/* Огонёк стрика: гаснет (contour), пока сегодня ещё не занимался. */
function Flame({ lit }: { lit: boolean }) {
  return (
    <svg className={`flame${lit ? ' flame--lit' : ''}`} viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M12 2c.6 3.2-.9 4.9-2.6 6.7C7.6 10.6 6 12.4 6 15a6 6 0 0 0 12 0c0-2.2-1-3.9-2.2-5.4-.4 1.1-1 1.9-1.9 2.5.3-2.9-.5-6.6-1.9-8.1z"
        fill="currentColor"
      />
    </svg>
  )
}

/**
 * Выбор собеседника. Список приходит с сервера (GET /personas) и здесь НЕ
 * дублируется: голос и характер — серверная сущность, фронт рисует что дали.
 * Сервер молчит или список пуст — блок просто не показывается, а разговор идёт
 * на персоне по умолчанию.
 */
/* Согласие на «взрослую» персону: разовое, живёт в этом браузере. Намеренно
   НЕ в настройках аккаунта — согласие даёт человек за конкретным экраном, и
   переносить его на телефон, за которым может сидеть кто-то другой, неверно. */
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
    /* приватный режим — спросим ещё раз, это не страшно */
  }
}

function PersonaPicker() {
  const settings = useSettings()
  const [personas, setPersonas] = useState<Persona[]>([])
  /** Персона, которую выбрали, но она требует подтверждения возраста. */
  const [confirming, setConfirming] = useState<Persona | null>(null)

  useEffect(() => {
    let alive = true
    void fetchPersonas().then((p) => alive && setPersonas(p))
    return () => {
      alive = false
    }
  }, [])

  if (personas.length === 0) return null

  /* Признак «взрослой» приходит с СЕРВЕРА: даже если фронт устарел и не знает
     про новую персону с матом, сервер пометит её, и подтверждение появится. */
  const choose = (p: Persona) => {
    if (p.adult && !adultAccepted(p.id)) {
      setConfirming(p)
      return
    }
    updateSettings({ persona: p.id })
  }

  return (
    <div className="card2 card2--ghost glass settings" style={BLOCK}>
      <div className="settings__text" style={{ marginBottom: 12 }}>
        <span className="settings__name">Собеседник</span>
        <span className="settings__hint">
          С кем говоришь в режиме Conversation. Меняется на лету — следующая
          реплика уже прозвучит новым голосом.
        </span>
      </div>

      <div className="personas" role="radiogroup" aria-label="Выбор собеседника">
        {personas.map((p) => {
          const active = settings.persona === p.id
          return (
            <button
              key={p.id}
              type="button"
              role="radio"
              aria-checked={active}
              className={`persona${active ? ' persona--on' : ''}`}
              onClick={() => choose(p)}
            >
              <span className="persona__top">
                <span className="persona__name">{p.label}</span>
                {active ? (
                  <span className="persona__mark">выбран</span>
                ) : (
                  p.adult && <span className="persona__mark persona__mark--adult">18+</span>
                )}
              </span>
              <span className="persona__desc">{p.description}</span>
            </button>
          )
        })}
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
          }}
        />
      )}
    </div>
  )
}

export function ProfileScreen({
  onOpenStats,
  onLogout,
  onClose,
}: {
  onOpenStats: () => void
  onLogout: () => void
  /** Закрыть экран профиля (НЕ выход из аккаунта — тот отдельной кнопкой). */
  onClose: () => void
}) {
  const settings = useSettings()
  const user = currentUser()

  const [stats, setStats] = useState<MeStats | null>(null)
  const [statsFailed, setStatsFailed] = useState(false)
  useEffect(() => {
    let alive = true
    void fetchMeStats().then((s) => {
      if (!alive) return
      setStats(s)
      setStatsFailed(s === null)
    })
    return () => {
      alive = false
    }
  }, [])

  /* Смена ника: имя только генерируется — как при регистрации. После смены
     показываем напоминание: ник это логин, его надо записать. */
  const [nick, setNick] = useState(user?.nickname ?? '')
  const [nickBusy, setNickBusy] = useState(false)
  const [nickChanged, setNickChanged] = useState(false)
  const [nickError, setNickError] = useState<string | null>(null)

  const onChangeNick = useCallback(async () => {
    setNickBusy(true)
    setNickError(null)
    try {
      const fresh = await changeNickname(randomNickname)
      applyNickname(fresh)
      setNick(fresh)
      setNickChanged(true)
    } catch (e) {
      setNickError(e instanceof Error ? e.message : String(e))
    } finally {
      setNickBusy(false)
    }
  }, [])

  const doLogout = useCallback(() => {
    logout()
    resetSettings() // тема и громкость — часть аккаунта, чужим не наследуются
    onLogout()
  }, [onLogout])

  const streak = stats?.streak
  const level = stats?.level
  const week = stats?.week
  const maxWeekXp = week ? Math.max(1, ...week.map((d) => d.xp)) : 1
  const dash = statsFailed ? '—' : stats ? null : '…'

  return (
    <div className="screenbody">
      <div
        className="screen__body scroll-soft scroll-soft--onDark"
        style={{ overflowY: 'auto', justifyContent: 'safe center', padding: '8px 10px' }}
      >
        {/* ------------------------------------------------------ Аккаунт */}
        <div className="card2 card2--ghost glass profilehead" style={BLOCK}>
          <div className="profilehead__id">
            <span className="profilehead__avatar" aria-hidden="true">
              {(nick.match(/[A-Z]/g) ?? ['?']).slice(0, 2).join('')}
            </span>
            <span className="profilehead__names">
              <span className="profilehead__nick">{nick || 'Гость'}</span>
              <span className="profilehead__role">
                {EXAM_LABEL[user?.exam ?? ''] ?? 'Аккаунт'}
                {level && ` · ${level.name}`}
              </span>
            </span>
          </div>
          <div className="profilehead__actions">
            <Pill onClick={onChangeNick} disabled={nickBusy} title="Сгенерировать новый никнейм">
              {nickBusy ? 'Меняю…' : 'Сменить ник'}
            </Pill>
            <Pill onClick={doLogout} quiet>
              Выйти
            </Pill>
          </div>
          {nickChanged && (
            <p className="profilehead__note">
              Ник — это твой логин. Запиши новый: <b>{nick}</b> (пароль прежний).
            </p>
          )}
          {nickError && <p className="profilehead__note profilehead__note--err">{nickError}</p>}
        </div>

        {/* --------------------------------------------------- Стрик и XP */}
        <div className="profilegrid" style={BLOCK}>
          <div className="card2 card2--ghost glass profilecell" title="Дни занятий подряд. Один пропущенный день в неделю стрик не сжигает — это заморозка.">
            <Flame lit={Boolean(streak?.active_today)} />
            <div className="statrow__value">{streak ? streak.days : dash}</div>
            <div className="statrow__label">DAY STREAK</div>
            <span className="profilecell__sub">
              {streak
                ? streak.active_today
                  ? 'сегодня засчитан'
                  : 'позанимайся — день ещё не засчитан'
                : statsFailed
                  ? 'нет связи с сервером'
                  : 'считаем…'}
            </span>
            {streak && (
              <span className="profilecell__sub">
                {streak.freeze_available
                  ? '❄ заморозка на этой неделе цела'
                  : '❄ заморозка недели потрачена'}
              </span>
            )}
          </div>

          <div className="card2 card2--ghost glass profilecell" title="XP даёт сервер: за реплики разговора (первые 30 в день), за решённые варианты (плюс балл разбора) и за законченные серии.">
            <div className="statrow__value">
              {level ? level.level : dash}
              <span className="statrow__unit"> lvl</span>
            </div>
            <div className="statrow__label">{level ? level.name.toUpperCase() : 'УРОВЕНЬ'}</div>
            {level ? (
              <>
                <div className="xpbar" aria-hidden="true">
                  <div className="xpbar__fill" style={{ width: `${Math.round(level.progress * 100)}%` }} />
                </div>
                <span className="profilecell__sub">
                  {level.xp - level.level_start} / {level.next_at - level.level_start} XP до
                  следующего
                </span>
              </>
            ) : (
              <span className="profilecell__sub">
                {statsFailed ? 'нет связи с сервером' : 'считаем…'}
              </span>
            )}
          </div>

          <div className="card2 card2--ghost glass profilecell" title="XP по дням за последнюю неделю.">
            {week ? (
              <div className="weekbars" role="img" aria-label="Занятия за неделю">
                {week.map((d) => (
                  <div className="weekbars__col" key={d.day} title={`${d.day}: ${d.xp} XP`}>
                    <div
                      className={`weekbars__bar${d.actions > 0 ? ' weekbars__bar--on' : ''}`}
                      style={{ height: `${8 + Math.round((d.xp / maxWeekXp) * 64)}%` }}
                    />
                    <span className="weekbars__day">{WEEKDAY[new Date(d.day + 'T12:00:00').getDay()]}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="statrow__value">{dash}</div>
            )}
            <div className="statrow__label">НЕДЕЛЯ</div>
            <span className="profilecell__sub">
              {stats
                ? `всего: ${stats.totals.replies} реплик · ${stats.totals.tasks} заданий · ${stats.totals.xp} XP`
                : statsFailed
                  ? 'нет связи с сервером'
                  : 'считаем…'}
            </span>
          </div>
        </div>

        {/* ------------------------------------------------- Собеседник */}
        <PersonaPicker />

        {/* ---------------------------------------------------- Настройки */}
        <div className="card2 card2--ghost glass settings" style={BLOCK}>
          <div className="settings__row">
            <div className="settings__text">
              <span className="settings__name">Тема</span>
              <span className="settings__hint">
                {settings.theme === 'dark'
                  ? 'Фон в цвет собеседника'
                  : 'Светлый нейтральный фон'}
              </span>
            </div>
            <SegmentedTabs
              tabs={[
                { id: 'dark', label: 'Цветная' },
                { id: 'light', label: 'Стандарт' },
              ]}
              active={settings.theme}
              onTab={(id) => updateSettings({ theme: id as 'dark' | 'light' })}
            />
          </div>

          <div className="settings__row">
            <div className="settings__text">
              <span className="settings__name">Громкость голоса</span>
              <span className="settings__hint">
                {settings.volume === 0 ? 'звук выключен' : `${Math.round(settings.volume * 100)}%`}
              </span>
            </div>
            <input
              className="slider"
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={settings.volume}
              onChange={(e) => updateSettings({ volume: Number(e.target.value) })}
              aria-label="Громкость голоса ИИ"
            />
          </div>

          <div className="settings__row">
            <div className="settings__text">
              <span className="settings__name">Текст ответа в Conversation</span>
              <span className="settings__hint">
                {settings.showText ? 'аудио + текст' : 'чисто аудио, как в живом разговоре'}
              </span>
            </div>
            <button
              type="button"
              className={`switch${settings.showText ? ' switch--on' : ''}`}
              role="switch"
              aria-checked={settings.showText}
              aria-label="Показывать текст ответа"
              onClick={() => updateSettings({ showText: !settings.showText })}
            >
              <span className="switch__thumb" />
            </button>
          </div>
        </div>
      </div>

      {/* «Назад» слева, как во всех экранах второго уровня. Не путать с «Выйти»
          наверху: та кнопка выходит из АККАУНТА, эта — просто закрывает профиль. */}
      <div className="rowbetween">
        <Pill onClick={onClose}>← Назад</Pill>
        <Pill accent onClick={onOpenStats}>
          Статистика ЕГЭ →
        </Pill>
      </div>
    </div>
  )
}
