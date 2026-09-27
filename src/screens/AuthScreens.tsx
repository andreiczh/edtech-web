/**
 * Регистрация, вход и интро — по фото-канону владельца (26.08.2026).
 * Маскота на этих экранах больше нет — решение владельца.
 *
 * Сохранённые требования прежних версий:
 *  - никнейм только генерируется, кнопка ⟳ перекидывает на другой случайный;
 *  - код доступа — только если его требует сервер (INVITE_REQUIRED=1,
 *    GET /auth/config); с 27.09.2026 регистрация открыта и поля нет (§6.48);
 *  - после регистрации — карточка «запиши данные»: восстановления нет
 *    по построению; затем интро «что тебя ждёт внутри» (фото 8);
 *  - ОГЭ показывает «скоро…» и выбор не меняет.
 *
 * Из мини-приложения MAX вход свой (MaxLoginScreen): без ника и кода —
 * личность подтверждает подпись мессенджера (15.09.2026).
 */
import { useCallback, useEffect, useState } from 'react'

import { updateSettings } from '../account/me'
import { login, loginMax, randomNickname, register, type AuthUser, fetchInviteRequired } from '../auth/auth'
import { maxInitData } from '../max/bridge'

/* ------------------------------------------------------------ Регистрация */

export function RegisterScreen({
  onDone,
  onLogin,
}: {
  onDone: (u: AuthUser) => void
  onLogin: () => void
}) {
  const [nickname, setNickname] = useState(randomNickname)
  const [password, setPassword] = useState('')
  const [invite, setInvite] = useState('')
  /* Поле кода — только если сервер его требует (INVITE_REQUIRED=1). */
  const [inviteRequired, setInviteRequired] = useState(false)
  useEffect(() => {
    let alive = true
    void fetchInviteRequired().then((need) => alive && setInviteRequired(need))
    return () => {
      alive = false
    }
  }, [])
  const [exam, setExam] = useState<'ege' | 'oge'>('ege')
  /* Согласие на хранение записей. Спрашивается ЗДЕСЬ, а не прячется в условиях:
     голос — персональные данные, и человек должен видеть вопрос, а не узнавать
     о нём потом. Снять можно в кабинете в любой момент. */
  const [consent, setConsent] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [soon, setSoon] = useState(false)
  /** Аккаунт создан — показываем «запиши данные» перед интро */
  const [created, setCreated] = useState<AuthUser | null>(null)

  useEffect(() => {
    if (!soon) return
    const id = setTimeout(() => setSoon(false), 2200)
    return () => clearTimeout(id)
  }, [soon])

  const submit = useCallback(async () => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const user = await register(nickname.trim(), password, 'ege', invite.trim())
      // Ответ ученика уезжает на сервер сразу: до первой же записи в корпус
      // сервер обязан знать, разрешили ему или нет.
      updateSettings({ corpusConsent: consent })
      setCreated(user)
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      // Сервер всё-таки требует код (включили, пока экран был открыт) — покажем поле.
      if (/код доступа|регистрация пока закрыта/i.test(msg)) setInviteRequired(true)
      setError(msg)
    } finally {
      setBusy(false)
    }
  }, [busy, nickname, password, invite])

  if (created) {
    return (
      <div className="authpage">
        <div className="authcol">
          <h1 className="auth2-title" style={{ fontSize: 'clamp(26px, 4vw, 40px)' }}>
            Запиши свои данные
          </h1>
          <p className="auth2-sub">
            Восстановить их нельзя: у аккаунта нет ни почты, ни телефона. Потеряешь пару —
            потеряешь прогресс.
          </p>
          <div className="auth2-keep">
            <b>{created.nickname}</b>
            <span>{password}</span>
          </div>
          <button type="button" className="auth2-btn" onClick={() => onDone(created)}>
            Я записал(а) — дальше
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="authpage">
      <div className="authcol">
        <h1 className="auth2-title">GoSpeak</h1>
        <p className="auth2-sub">
          Голосовой тренажёр устной части ЕГЭ.
          <br />
          Говоришь — ИИ отвечает голосом и разбирает
          <br />
          по критериям ФИПИ.
        </p>

        <label className="auth2-label">Твой ник</label>
        <div className="auth2-field auth2-field--row">
          <span className="auth2-nick" title="Ник генерируется — руками не вводится">
            {nickname}
          </span>
          <button
            type="button"
            className="auth2-regen"
            onClick={() => setNickname(randomNickname())}
            title="Сгенерировать другой ник"
            aria-label="Сгенерировать другой ник"
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
              <path d="M21 12a9 9 0 1 1-2.6-6.4M21 3v6h-6" />
            </svg>
          </button>
        </div>

        <label className="auth2-label">Пароль</label>
        <input
          className="auth2-field"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="минимум 8 символов"
          aria-label="Пароль"
          maxLength={64}
        />

        {inviteRequired && (
          <>
            <label className="auth2-label">Код доступа</label>
            <input
              className="auth2-field"
              value={invite}
              onChange={(e) => setInvite(e.target.value)}
              placeholder="выдаёт владелец"
              aria-label="Код доступа"
              maxLength={64}
              autoCapitalize="off"
              autoCorrect="off"
            />
          </>
        )}

        <label className="auth2-label">Готовлюсь к</label>
        <div className="auth2-seg" role="group" aria-label="Экзамен">
          <button
            type="button"
            className={exam === 'ege' ? 'auth2-seg--on' : ''}
            onClick={() => setExam('ege')}
          >
            ЕГЭ
          </button>
          <button type="button" onClick={() => setSoon(true)} title="Скоро">
            ОГЭ
          </button>
        </div>

        <label className="auth2-consent">
          <input
            type="checkbox"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
          />
          <span>
            Разрешаю сохранять мои записи, чтобы система училась точнее проверять речь.
            Записи не публикуются и не продаются; речь распознаёт сервис Mistral AI.
            Отключить можно в кабинете.{' '}
            <a className="auth2-link" href="/privacy.html">
              Как хранятся данные
            </a>
          </span>
        </label>

        {error && <p className="auth2-err">{error}</p>}

        <button
          type="button"
          className="auth2-btn"
          disabled={busy || password.length < 8 || (inviteRequired && !invite.trim())}
          onClick={() => void submit()}
          title={
            password.length < 8
              ? 'Пароль — минимум 8 символов'
              : inviteRequired && !invite.trim()
                ? 'Нужен код доступа'
                : undefined
          }
        >
          {busy ? '…' : 'Создать аккаунт'}
        </button>
        <p className="auth2-foot">
          Уже занимался?{' '}
          <button type="button" className="auth2-link" onClick={onLogin}>
            Войти
          </button>
        </p>
      </div>

      {soon && (
        <div className="auth-soon" role="status" onClick={() => setSoon(false)}>
          <div className="auth-soon__card">скоро…</div>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ Интро */

export function IntroScreen({ onGo }: { onGo: () => void }) {
  return (
    <div className="authpage">
      <div className="authcol authcol--card">
        <h1 className="auth2-title" style={{ fontSize: 'clamp(24px, 3.4vw, 34px)' }}>
          Привет! 👋
        </h1>
        <p className="auth2-sub">Вот что тебя ждёт внутри:</p>

        <div className="intro-list">
          <div className="intro-item">
            <span className="intro-ic intro-ic--pink">
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                <rect x="9" y="2.5" width="6" height="12" rx="3" />
                <path d="M5 11a7 7 0 0 0 14 0M12 18v3.5" />
              </svg>
            </span>
            <div>
              <b>Экзамен голосом, как на ЕГЭ</b>
              <span>Все 4 задания устной части с таймерами и живым разбором.</span>
            </div>
          </div>
          <div className="intro-item">
            <span className="intro-ic intro-ic--lav">
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                <path d="M21 12a8 8 0 1 0-3 6.2L21 19l-.6-3.3A8 8 0 0 0 21 12Z" />
              </svg>
            </span>
            <div>
              <b>Разговор с собеседником</b>
              <span>Свободная беседа с ИИ: три характера на выбор, тему задаёшь ты.</span>
            </div>
          </div>
          <div className="intro-item">
            <span className="intro-ic intro-ic--mint">
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                <path d="M4 19V5M4 17c5-2 7 1 11-1s5-8 5-8" />
              </svg>
            </span>
            <div>
              <b>Балл по шкалам ФИПИ</b>
              <span>Оценка как у эксперта, ошибки с цитатами и объяснением.</span>
            </div>
          </div>
        </div>

        <button type="button" className="auth2-btn" onClick={onGo}>
          Поехали
        </button>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------- Вход */

export function LoginScreen({
  onDone,
  onRegister,
}: {
  onDone: (u: AuthUser) => void
  onRegister: () => void
}) {
  const [nickname, setNickname] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = useCallback(async () => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      onDone(await login(nickname.trim(), password))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }, [busy, nickname, onDone, password])

  return (
    <div className="authpage">
      <div className="authcol">
        <h1 className="auth2-title">GoSpeak</h1>
        <p className="auth2-sub">С возвращением — введи свои данные.</p>

        <label className="auth2-label">Твой ник</label>
        <input
          className="auth2-field"
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
          placeholder="CheerfulHummingbird"
          aria-label="Никнейм"
          maxLength={32}
        />
        <label className="auth2-label">Пароль</label>
        <input
          className="auth2-field"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="пароль"
          aria-label="Пароль"
          maxLength={64}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void submit()
          }}
        />

        {error && <p className="auth2-err">{error}</p>}

        <button
          type="button"
          className="auth2-btn"
          disabled={busy || !nickname.trim() || !password}
          onClick={() => void submit()}
        >
          {busy ? '…' : 'Войти'}
        </button>
        <p className="auth2-foot">
          Нет аккаунта?{' '}
          <button type="button" className="auth2-link" onClick={onRegister}>
            Создать
          </button>
        </p>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------- Вход из MAX
 *
 * Мини-приложение в MAX входит само: подпись данных запуска проверяет сервер
 * (/auth/max), ник, пароль и код доступа не нужны. Экран виден, только пока
 * идёт вход, а при ошибке — с повтором и запасным входом по нику.
 */

export function MaxLoginScreen({
  onDone,
  onFallback,
}: {
  onDone: (u: AuthUser, created: boolean) => void
  onFallback: () => void
}) {
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let alive = true
    setError(null)
    void (async () => {
      try {
        const initData = await maxInitData()
        if (!initData) {
          throw new Error(
            'MAX не передал данные для входа. Закрой мини-приложение и открой его снова из чата бота.',
          )
        }
        const { user, created } = await loginMax(initData)
        if (alive) onDone(user, created)
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e))
      }
    })()
    return () => {
      alive = false
    }
  }, [attempt, onDone])

  return (
    <div className="authpage">
      <div className="authcol">
        <h1 className="auth2-title">GoSpeak</h1>
        {error === null ? (
          <p className="auth2-sub" role="status">
            Входим через MAX…
          </p>
        ) : (
          <>
            <p className="auth2-err" role="alert">
              {error}
            </p>
            <button type="button" className="auth2-btn" onClick={() => setAttempt((a) => a + 1)}>
              Попробовать ещё раз
            </button>
            <p className="auth2-foot">
              Есть аккаунт с ником и паролем?{' '}
              <button type="button" className="auth2-link" onClick={onFallback}>
                Войти
              </button>
            </p>
          </>
        )}
      </div>
    </div>
  )
}
