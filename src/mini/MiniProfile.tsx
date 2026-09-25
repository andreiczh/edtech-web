/**
 * Аккаунт — открывается из профиля в настройках. Макета нет, собран в языке
 * экрана настроек (карточки, ряды, тумблер). Всё, что делал прежний кабинет
 * (ProfileScreen) и чего нет в настройках: ник с генерацией нового (ник —
 * это логин), уровень и XP с сервера, серия и итоги, согласие на хранение
 * записей со ссылкой на политику, выход из аккаунта.
 */
import { useCallback, useEffect, useState } from 'react'

import { changeNickname, fetchMeStats, updateSettings, useSettings, type MeStats } from '../account/me'
import { applyNickname, currentUser, logout, randomNickname } from '../auth/auth'
import { BackButton, useMaxBack } from './ResultBits'

const days = (n: number) => `${n} ${n % 10 === 1 && n % 100 !== 11 ? 'день' : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? 'дня' : 'дней'}`

export function MiniProfile({ onBack, onLogout }: { onBack: () => void; onLogout: () => void }) {
  useMaxBack(onBack)
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
    onLogout()
  }, [onLogout])

  const level = stats?.level
  const streak = stats?.streak
  const dash = statsFailed ? '—' : stats ? null : '…'

  return (
    <div className="st-page pf-page">
      <BackButton onBack={onBack} />
      <h1 className="st-h1 pf-h1">Аккаунт</h1>
      <div className="pf-list">
        <section className="st-card pf-card" aria-label="Ник">
          <div className="pf-who">
            <span className="st-profile__ava pf-ava" aria-hidden="true" />
            <div className="pf-who__txt">
              <b className="pf-nick">{nick || 'Гость'}</b>
              <span className="pf-sub">ник — это твой логин</span>
            </div>
            <button
              type="button"
              className="m-btn pf-regen"
              onClick={() => void onChangeNick()}
              disabled={nickBusy}
              aria-label="Сгенерировать новый ник"
            >
              {nickBusy ? 'меняю…' : '⟳ новый ник'}
            </button>
          </div>
          {nickChanged && (
            <p className="pf-note">
              Запиши новый ник: <b>{nick}</b>. Пароль прежний.
            </p>
          )}
          {nickError && <p className="pf-note pf-note--err">{nickError}</p>}
        </section>

        <section className="st-card pf-card" aria-label="Уровень">
          <div className="pf-lvl">
            <b>{level ? `Уровень ${level.level} · ${level.name}` : (dash ?? '')}</b>
            {level && (
              <>
                <div className="pf-xpbar" aria-hidden="true">
                  <i style={{ width: `${Math.round(level.progress * 100)}%` }} />
                </div>
                <span className="pf-sub">
                  {level.xp - level.level_start} / {level.next_at - level.level_start} XP до уровня{' '}
                  {level.level + 1}
                </span>
              </>
            )}
          </div>
          <div className="pf-rows">
            <div className="pf-row">
              <span>Серия сейчас</span>
              <b>{streak ? days(streak.days) : dash}</b>
            </div>
            <div className="pf-row">
              <span>Лучшая серия</span>
              <b>{streak ? days(streak.best) : dash}</b>
            </div>
            <div className="pf-row">
              <span>Заморозка</span>
              <b>{streak ? (streak.freeze_available ? 'доступна' : 'потрачена') : dash}</b>
            </div>
            <div className="pf-row">
              <span>Заданий разобрано</span>
              <b>{stats ? stats.totals.tasks : dash}</b>
            </div>
            <div className="pf-row">
              <span>Реплик в разговоре</span>
              <b>{stats ? stats.totals.replies : dash}</b>
            </div>
            <div className="pf-row">
              <span>Экзамен</span>
              <b>{user?.exam === 'oge' ? 'ОГЭ' : 'ЕГЭ'}</b>
            </div>
          </div>
        </section>

        <section className="st-card pf-card" aria-label="Записи">
          <div className="pf-consent">
            <div className="pf-consent__txt">
              <b>Хранить мои записи</b>
              <span className="pf-sub">
                чтобы система училась точнее проверять речь; записи не публикуются и не продаются.{' '}
                <a className="pf-link" href="/privacy.html" target="_blank" rel="noreferrer">
                  Как хранятся данные
                </a>
              </span>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={settings.corpusConsent}
              aria-label="Хранить мои записи"
              className={`m-btn st-tog pf-tog${settings.corpusConsent ? ' st-tog--on' : ''}`}
              onClick={() => updateSettings({ corpusConsent: !settings.corpusConsent })}
            />
          </div>
        </section>

        <button type="button" className="m-btn pf-logout" onClick={doLogout}>
          Выйти из аккаунта
        </button>
      </div>
    </div>
  )
}
