/**
 * Личный кабинет — макет из утверждённого прототипа (фото-канон владельца).
 *
 * Вся прежняя логика сохранена: смена ника генерацией, подтверждение 18+ у
 * взрослой персоны, мгновенное применение настроек с дебаунс-отправкой на
 * аккаунт. Числа живые (/me/stats, включая новую «лучшую серию»); пока сервер
 * молчит — прочерки, не выдумки. «Среднего времени занятия» из прототипа нет:
 * система не замеряет длительность, вместо него честные реплики разговора.
 */
import { useCallback, useEffect, useState } from 'react'

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
import { ConfirmDialog } from '../design/ui'

/* Согласие на «взрослую» персону: разовое, живёт в этом браузере. Намеренно
   НЕ в настройках аккаунта — согласие даёт человек за конкретным экраном. */
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

/* Эмодзи персоны — по её цветовой семье (контракт theme: blue/green/red). */
const PERSONA_EMOJI: Record<string, string> = { blue: '😊', green: '🧘', red: '😈' }

export function ProfileScreen({
  onOpenStats: _onOpenStats,
  onLogout,
  onClose: _onClose,
}: {
  onOpenStats?: () => void
  onLogout: () => void
  onClose?: () => void
}) {
  const settings = useSettings()
  const user = currentUser()

  const [stats, setStats] = useState<MeStats | null>(null)
  const [statsFailed, setStatsFailed] = useState(false)
  const [personas, setPersonas] = useState<Persona[]>([])
  const [confirming, setConfirming] = useState<Persona | null>(null)

  useEffect(() => {
    let alive = true
    void fetchMeStats().then((s) => {
      if (!alive) return
      setStats(s)
      setStatsFailed(s === null)
    })
    void fetchPersonas().then((p) => alive && setPersonas(p))
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
    resetSettings()
    onLogout()
  }, [onLogout])

  const choosePersona = (p: Persona) => {
    if (p.adult && !adultAccepted(p.id)) {
      setConfirming(p)
      return
    }
    updateSettings({ persona: p.id })
  }

  const streak = stats?.streak
  const level = stats?.level
  const dash = statsFailed ? '—' : stats ? null : '…'
  const currentPersona = personas.find((p) => p.id === settings.persona)

  return (
    <div className="profpage">
      <h1 className="dash__hello" style={{ marginBottom: 10 }}>
        Личный кабинет
      </h1>

      <div className="profpage__grid">
        <div className="profpage__main">
          {/* --------------------------------------------------- Профиль */}
          <div className="calcard">
            <div className="profhead">
              <span className="profhead__ava" aria-hidden="true">
                {(nick.match(/[A-Z]/g) ?? ['?']).slice(0, 2).join('')}
              </span>
              <div className="profhead__info">
                <div className="profhead__row">
                  <b className="profhead__nick">{nick || 'Гость'}</b>
                  <button
                    type="button"
                    className="profhead__regen"
                    onClick={() => void onChangeNick()}
                    disabled={nickBusy}
                    title="Сгенерировать новый ник"
                  >
                    ⟳ {nickBusy ? 'меняю…' : 'новый ник'}
                  </button>
                </div>
                <span className="profhead__lvl">
                  {level ? `Уровень ${level.level} · ${level.name}` : (dash ?? 'считаю…')}
                </span>
                {level && (
                  <>
                    <div className="profhead__xpbar" aria-hidden="true">
                      <i style={{ width: `${Math.round(level.progress * 100)}%` }} />
                    </div>
                    <span className="profhead__xp">
                      {level.xp - level.level_start} / {level.next_at - level.level_start} XP до
                      уровня {level.level + 1}
                    </span>
                  </>
                )}
              </div>
            </div>
            {nickChanged && (
              <p className="profnote">
                Ник — это твой логин. Запиши новый: <b>{nick}</b> (пароль прежний).
              </p>
            )}
            {nickError && <p className="profnote profnote--err">{nickError}</p>}

            <div className="profstats">
              <div>
                <span>Лучшая серия</span>
                <b>{streak ? `${streak.best} ${streak.best === 1 ? 'день' : 'дней'}` : dash}</b>
              </div>
              <div>
                <span>Занятий</span>
                <b>{stats ? stats.totals.tasks : dash}</b>
              </div>
              <div>
                <span>Реплик</span>
                <b>{stats ? stats.totals.replies : dash}</b>
              </div>
              <div>
                <span>Экзамен</span>
                <b>{user?.exam === 'oge' ? 'ОГЭ' : 'ЕГЭ'}</b>
              </div>
            </div>
          </div>

          {/* -------------------------------------------------- Настройки */}
          <div className="calcard">
            <p className="calcard__title" style={{ marginBottom: 6 }}>
              Настройки
            </p>

            <div className="setrow2">
              <div className="setrow2__t">
                <b>Тема</b>
                <span>следует за аккаунтом на всех устройствах</span>
              </div>
              <div className="calseg">
                {(['light', 'dark', 'auto'] as const).map((t) => (
                  <button
                    key={t}
                    type="button"
                    className={settings.theme === t ? 'calseg--on' : ''}
                    onClick={() => updateSettings({ theme: t })}
                  >
                    {t === 'light' ? 'Светлая' : t === 'dark' ? 'Тёмная' : 'Авто'}
                  </button>
                ))}
              </div>
            </div>

            <div className="setrow2">
              <div className="setrow2__t">
                <b>Громкость голоса</b>
                <span>
                  {settings.volume === 0
                    ? 'звук выключен'
                    : `громкость ответов собеседника и озвучки · ${Math.round(settings.volume * 100)}%`}
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

            <div className="setrow2">
              <div className="setrow2__t">
                <b>Текст в разговоре</b>
                <span>показывать реплики текстом под голосом</span>
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

            {personas.length > 0 && (
              <div className="setrow2">
                <div className="setrow2__t">
                  <b>Собеседник по умолчанию</b>
                  <span>{currentPersona ? currentPersona.label : 'характер в разговорной практике'}</span>
                </div>
                <div className="calseg" role="radiogroup" aria-label="Собеседник">
                  {personas.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      role="radio"
                      aria-checked={settings.persona === p.id}
                      className={settings.persona === p.id ? 'calseg--on' : ''}
                      onClick={() => choosePersona(p)}
                      title={p.label + (p.adult ? ' (18+)' : '')}
                    >
                      {PERSONA_EMOJI[p.theme] ?? '🤖'}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="setrow2">
              <div className="setrow2__t">
                <b>Помогаю улучшать проверку</b>
                <span>
                  {settings.corpusConsent
                    ? 'записи заданий сохраняются и помогают точнее оценивать речь'
                    : 'записи не сохраняются — оценка от этого не меняется'}
                </span>
              </div>
              <button
                type="button"
                className={`switch${settings.corpusConsent ? ' switch--on' : ''}`}
                role="switch"
                aria-checked={settings.corpusConsent}
                aria-label="Сохранять мои записи для улучшения проверки"
                onClick={() => updateSettings({ corpusConsent: !settings.corpusConsent })}
              >
                <span className="switch__thumb" />
              </button>
            </div>

            <div className="setrow2">
              <div className="setrow2__t">
                <b>Экзамен</b>
                <span>набор заданий и шкалы</span>
              </div>
              <div className="calseg">
                <button type="button" className="calseg--on">
                  ЕГЭ
                </button>
                <button type="button" disabled title="Скоро">
                  ОГЭ
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* ------------------------------------------------ Правая колонка */}
        <div className="profpage__side">
          <div className="profstreak">
            <span className="profstreak__ic">🔥</span>
            <b>Стрик {streak ? streak.days : (dash ?? '…')} {streak && streak.days === 1 ? 'день' : 'дней'}</b>
            <p>
              {streak
                ? streak.active_today
                  ? 'Сегодня зачтено — серия живёт. Возвращайся завтра.'
                  : 'Загляни до полуночи по Москве — серия продлится.'
                : statsFailed
                  ? 'Нет связи с сервером.'
                  : 'Считаю…'}
            </p>
          </div>
          <div className="calcard">
            <p className="calside__eyebrow">Аккаунт</p>
            <p className="profnote" style={{ margin: '0 0 12px' }}>
              Ник + пароль, почты нет. Пароль знаешь только ты — потерял, попроси сброс у
              владельца.
            </p>
            <p className="profnote" style={{ margin: '0 0 12px' }}>
              <a href="/privacy.html" target="_blank" rel="noreferrer">
                Как хранятся твои данные
              </a>
            </p>
            <button type="button" className="proflogout" onClick={doLogout}>
              Выйти из аккаунта
            </button>
          </div>
        </div>
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
