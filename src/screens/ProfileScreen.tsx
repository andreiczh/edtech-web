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
  resetSettings,
  updateSettings,
  useSettings,
  type MeStats,
} from '../account/me'
import { applyNickname, currentUser, logout, randomNickname } from '../auth/auth'
import { Pill, SegmentedTabs } from '../design/ui'

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

export function ProfileScreen({
  onOpenStats,
  onLogout,
}: {
  onOpenStats: () => void
  onLogout: () => void
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

        {/* ---------------------------------------------------- Настройки */}
        <div className="card2 card2--ghost glass settings" style={BLOCK}>
          <div className="settings__row">
            <div className="settings__text">
              <span className="settings__name">Тема</span>
              <span className="settings__hint">Оформление всего приложения</span>
            </div>
            <SegmentedTabs
              tabs={[
                { id: 'dark', label: 'Тёмная' },
                { id: 'light', label: 'Светлая' },
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

      <div className="rowbetween">
        <Pill onClick={onOpenStats}>Статистика ЕГЭ →</Pill>
        <span style={{ fontSize: 'clamp(10px, 1.1vw, 12px)', color: 'var(--text-dim)' }}>
          Стрик и XP считает сервер — они одни на все твои устройства
        </span>
      </div>
    </div>
  )
}
