/**
 * Приветствие, регистрация и вход — по присланным макетам (светлая тема).
 *
 * Решения из требований:
 *  - никнейм генерируется из двух английских слов, кнопка Change перекидывает
 *    на другой случайный;
 *  - после регистрации — карточка «запиши никнейм и пароль»: восстановления
 *    нет по построению (ни почты, ни телефона), человек обязан это увидеть;
 *  - выбор ОГЭ показывает баннер «soon...» и не пускает дальше; ЕГЭ и «другое»
 *    проходят в приложение.
 */
import { useCallback, useEffect, useState } from 'react'

import { login, randomNickname, register, type AuthUser } from '../auth/auth'
import { Mascot } from '../design/ui'

type Exam = 'ege' | 'oge' | 'other'

export function WelcomeScreen({
  onStart,
  onLogin,
}: {
  onStart: () => void
  onLogin: () => void
}) {
  return (
    <div className="authpage">
      <div className="auth-hero">
        <h1 className="auth-title">PINGO AI</h1>
        <Mascot />
      </div>
      <p className="auth-sub">Just improve your speaking skills for free!</p>

      <div style={{ height: 'clamp(8px, 6vh, 60px)' }} />

      <button type="button" className="auth-btn" onClick={onStart}>
        НАЧАТЬ
      </button>
      <button type="button" className="auth-btn auth-btn--ghost" onClick={onLogin}>
        У МЕНЯ УЖЕ ЕСТЬ АККАУНТ
      </button>
    </div>
  )
}

/* ------------------------------------------------------------ Регистрация */

export function RegisterScreen({ onDone }: { onDone: (u: AuthUser) => void }) {
  const [nickname, setNickname] = useState(randomNickname)
  const [password, setPassword] = useState('')
  const [exam, setExam] = useState<Exam | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [soon, setSoon] = useState(false)
  /** Аккаунт уже создан — показываем «запиши данные» перед входом в приложение */
  const [created, setCreated] = useState<AuthUser | null>(null)

  // Баннер «soon...» гаснет сам — это подсказка, а не тупик.
  useEffect(() => {
    if (!soon) return
    const id = setTimeout(() => setSoon(false), 2200)
    return () => clearTimeout(id)
  }, [soon])

  const pickExam = (e: Exam) => {
    if (e === 'oge') {
      setSoon(true)
      return // выбор не меняем: ОГЭ пока некуда вести
    }
    setExam(e)
  }

  const submit = useCallback(async () => {
    if (!exam || busy) return
    setBusy(true)
    setError(null)
    try {
      setCreated(await register(nickname.trim(), password, exam))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }, [busy, exam, nickname, password])

  if (created) {
    return (
      <div className="authpage">
        <h1 className="auth-title" style={{ fontSize: 'clamp(28px, 5vw, 48px)' }}>
          Запиши свои данные
        </h1>
        <p className="auth-sub" style={{ maxWidth: 'min(92vw, 460px)' }}>
          Восстановить их нельзя: у аккаунта нет ни почты, ни телефона. Потеряешь пару —
          потеряешь прогресс.
        </p>
        <div className="auth-panel" style={{ textAlign: 'center', gap: 8 }}>
          <span style={{ color: '#efeaff', fontWeight: 800, fontSize: 'clamp(18px, 2.6vw, 26px)' }}>
            {created.nickname}
          </span>
          <span style={{ color: '#cfc9f2', fontWeight: 700 }}>{password}</span>
        </div>
        <button type="button" className="auth-btn" onClick={() => onDone(created)}>
          Я ЗАПИСАЛ(А) — НАЧАТЬ
        </button>
      </div>
    )
  }

  return (
    <div className="authpage">
      <h1 className="auth-title" style={{ fontSize: 'clamp(34px, 6vw, 60px)', color: '#574f8e' }}>
        REGISTRATION
      </h1>

      {/* Маскот и на регистрации — как на приветственном референсе. Компонент
          сам решает, какой зверь достался этой сессии. */}
      <Mascot style={{ width: 'clamp(90px, 14vw, 150px)', marginTop: '-8px' }} />

      <div className="auth-panel">
        <div className="auth-inputrow">
          <input
            className="auth-input"
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            placeholder="nickname"
            aria-label="Никнейм"
            maxLength={32}
          />
          <button
            type="button"
            className="auth-chip"
            style={{ flex: '0 0 auto' }}
            onClick={() => setNickname(randomNickname())}
            title="Сгенерировать другой никнейм"
          >
            Change
          </button>
        </div>

        <input
          className="auth-input"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="password"
          aria-label="Пароль"
          maxLength={64}
        />

        <div className="auth-chiprow">
          <button
            type="button"
            className="auth-chip"
            onClick={() => pickExam('oge')}
            title="Скоро"
          >
            огэ
          </button>
          <button
            type="button"
            className={`auth-chip${exam === 'ege' ? ' auth-chip--active' : ''}`}
            onClick={() => pickExam('ege')}
          >
            егэ
          </button>
          <button
            type="button"
            className={`auth-chip${exam === 'other' ? ' auth-chip--active' : ''}`}
            onClick={() => pickExam('other')}
          >
            другое
          </button>
        </div>
      </div>

      {error && <p className="auth-err">{error}</p>}

      <button
        type="button"
        className="auth-btn"
        disabled={busy || !exam || password.length < 4 || nickname.trim().length < 3}
        onClick={() => void submit()}
        title={
          !exam
            ? 'Выбери ЕГЭ или «другое»'
            : password.length < 4
              ? 'Пароль — минимум 4 символа'
              : undefined
        }
      >
        {busy ? '…' : 'CONTINUE'}
      </button>

      {soon && (
        <div className="auth-soon" role="status" onClick={() => setSoon(false)}>
          <div className="auth-soon__card">soon…</div>
        </div>
      )}
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
      <h1 className="auth-title" style={{ fontSize: 'clamp(34px, 6vw, 60px)', color: '#574f8e' }}>
        LOG IN
      </h1>

      <div className="auth-panel">
        <input
          className="auth-input"
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
          placeholder="nickname"
          aria-label="Никнейм"
          maxLength={32}
        />
        <input
          className="auth-input"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="password"
          aria-label="Пароль"
          maxLength={64}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void submit()
          }}
        />
      </div>

      {error && <p className="auth-err">{error}</p>}

      <div style={{ height: 'clamp(4px, 4vh, 40px)' }} />

      <button
        type="button"
        className="auth-btn"
        disabled={busy || !nickname.trim() || !password}
        onClick={() => void submit()}
      >
        {busy ? '…' : 'ENTER'}
      </button>
      <button type="button" className="auth-btn auth-btn--ghost" onClick={onRegister}>
        СОЗДАТЬ АККАУНТ
      </button>
    </div>
  )
}
