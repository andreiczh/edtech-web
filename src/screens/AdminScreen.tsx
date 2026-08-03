/**
 * Админка банка заданий. Открывается по адресу /?admin — обычные ученики её не
 * видят, а сервер в любом случае требует ADMIN_KEY (заголовок X-Admin-Key),
 * так что спрятанность — удобство, а не защита.
 *
 * «В два клика»: выбрал раздел и номер → появились ровно нужные поля → Сохранить.
 * Текст задания (brief) собирается сам из шаблонов банка — вводить надо только
 * содержимое: текст для чтения, пункты вопросов, ссылки на картинки.
 */
import { useCallback, useEffect, useState, type CSSProperties } from 'react'

import { httpErrorMessage } from '../backendError'
import { Pill } from '../design/ui'
import { BRIEF_39, BRIEF_41, ad, monologueBrief, type TaskKind } from '../ege2/tasks'

const BACKEND = (import.meta.env.VITE_BACKEND_URL ?? '').replace(/\/+$/, '')
const KEY_STORE = 'pingo.adminKey'

const KIND_BY_EGE_NO: Record<number, TaskKind> = {
  39: 'reading',
  40: 'dialogue',
  41: 'interview',
  42: 'monologue',
}

const KIND_LABEL: Record<TaskKind, string> = {
  reading: 'чтение вслух',
  dialogue: 'вопросы к объявлению',
  interview: 'интервью',
  monologue: 'монолог по фото',
}

interface AdminTask {
  id: string
  exam: string
  task_no: number
  kind: string
  active: boolean
  payload: Record<string, unknown>
  /** Замечания от детерминированных проверок: пусто — заметных дефектов нет */
  problems?: string[]
}

const FIELD: CSSProperties = { width: '100%' }
const AREA: CSSProperties = { ...FIELD, minHeight: 110, resize: 'vertical', textAlign: 'left' }
const LABEL: CSSProperties = {
  fontSize: 12,
  fontWeight: 700,
  color: 'var(--text-dim)',
  letterSpacing: '0.06em',
}

async function api(path: string, key: string, init?: RequestInit) {
  const res = await fetch(`${BACKEND}${path}`, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      'X-Admin-Key': key,
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
    },
  })
  let data: unknown = null
  try {
    data = await res.json()
  } catch {
    /* httpErrorMessage разберёт */
  }
  const detail =
    data && typeof data === 'object' && 'detail' in data
      ? String((data as { detail: unknown }).detail)
      : null
  if (!res.ok) throw new Error(httpErrorMessage(res.status, detail))
  return data
}

/**
 * Разборочный стол банка. Построен под реальную задачу: 94 черновика импорта
 * ФИПИ, каждый нужно ГЛАЗАМИ проверить (OCR мог наврать, картинка может быть
 * не о том) и опубликовать либо удалить. Отсюда предпросмотр целиком —
 * полный текст, картинки, пункты — а не обрезка в 48 символов.
 */
function BankList({
  list,
  adminKey,
  onChanged,
}: {
  list: AdminTask[]
  adminKey: string
  onChanged: () => void
}) {
  const [filter, setFilter] = useState<'drafts' | 'active' | 'all'>('drafts')
  const [open, setOpen] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  const shown = list
    .filter((t) => (filter === 'all' ? true : filter === 'active' ? t.active : !t.active))
    // Проблемные — наверх: это рабочая очередь, а не витрина.
    .sort((a, b) => (b.problems?.length ?? 0) - (a.problems?.length ?? 0))
  const drafts = list.filter((t) => !t.active).length
  const cleanDrafts = list.filter((t) => !t.active && !(t.problems?.length ?? 0)).length

  const act = async (path: string, method: string, id: string) => {
    setBusyId(id)
    try {
      await api(path, adminKey, { method })
      onChanged()
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="card2" style={{ width: 'min(100%, 760px)' }}>
      <div className="rowbetween" style={{ marginBottom: 10 }}>
        <p style={{ margin: 0, fontWeight: 800 }}>
          Банк: {list.length} всего, черновиков {drafts}
        </p>
        <select value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)}>
          <option value="drafts">черновики</option>
          <option value="active">опубликованные</option>
          <option value="all">все</option>
        </select>
      </div>

      {cleanDrafts > 0 && (
        <div className="rowbetween" style={{ marginBottom: 10 }}>
          <span style={{ fontSize: 13, color: 'var(--card-ink-dim)' }}>
            Без замечаний: {cleanDrafts} из {drafts}. Остальные ждут твоих глаз.
          </span>
          <Pill
            onClick={() => {
              if (
                window.confirm(
                  `Опубликовать ${cleanDrafts} черновиков без замечаний? ` +
                    'Они сразу станут видны ученикам.',
                )
              )
                void api('/admin/tasks/publish_clean', adminKey, {
                  method: 'POST',
                  body: JSON.stringify({}),
                }).then(onChanged)
            }}
          >
            Опубликовать чистые
          </Pill>
        </div>
      )}
      {shown.length === 0 && <p style={{ margin: 0 }}>Здесь пусто.</p>}

      {shown.map((t) => {
        const p = t.payload
        const title =
          (p.imageCaption as string) ||
          (p.readText as string)?.slice(0, 60) ||
          (Array.isArray(p.steps) ? String(p.steps[0]) : '') ||
          t.id.slice(0, 8)
        const isOpen = open === t.id
        return (
          <div key={t.id} style={{ borderTop: '1px solid rgba(0,0,0,0.08)', padding: '8px 0' }}>
            <div className="rowbetween">
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : t.id)}
                style={{
                  all: 'unset',
                  cursor: 'pointer',
                  opacity: t.active ? 1 : 0.75,
                  fontWeight: 700,
                  minWidth: 0,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
                title="Показать задание целиком"
              >
                {t.active ? '🟢' : t.problems?.length ? '⚠️' : '📝'} №{t.task_no} ·{' '}
                {KIND_LABEL[t.kind as TaskKind] ?? t.kind}
                {' — '}
                {title}
              </button>
              <span style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                <Pill
                  quiet
                  disabled={busyId === t.id}
                  onClick={() => void act(`/admin/tasks/${t.id}/toggle`, 'POST', t.id)}
                >
                  {t.active ? 'снять' : 'опубликовать'}
                </Pill>
                <Pill
                  quiet
                  disabled={busyId === t.id}
                  onClick={() => {
                    // confirm достаточно: это админка владельца, не ученики
                    if (window.confirm('Удалить задание насовсем?'))
                      void act(`/admin/tasks/${t.id}`, 'DELETE', t.id)
                  }}
                >
                  ✕
                </Pill>
              </span>
            </div>

            {(t.problems?.length ?? 0) > 0 && (
              <p style={{ margin: '4px 0 0', fontSize: 13, color: '#b4485c', fontWeight: 700 }}>
                {t.problems!.join(' · ')}
              </p>
            )}

            {isOpen && (
              <div style={{ padding: '8px 4px', fontSize: 14 }}>
                {typeof p.brief === 'string' && (
                  <p style={{ whiteSpace: 'pre-wrap', margin: '0 0 8px' }}>{p.brief}</p>
                )}
                {typeof p.readText === 'string' && (
                  <p style={{ whiteSpace: 'pre-wrap', margin: '0 0 8px', fontStyle: 'italic' }}>
                    {p.readText}
                  </p>
                )}
                {Array.isArray(p.steps) && (
                  <ol style={{ margin: '0 0 8px', paddingLeft: 20 }}>
                    {(p.steps as string[]).map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ol>
                )}
                {Array.isArray(p.photoFacts) && (p.photoFacts as string[]).length > 0 && (
                  <p style={{ margin: '0 0 8px', color: 'var(--card-ink-dim)' }}>
                    факты для разбора: {(p.photoFacts as string[]).join(' | ')}
                  </p>
                )}
                {Array.isArray(p.images) && (
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {(p.images as string[]).map((src) => (
                      <img
                        key={src}
                        src={src}
                        alt=""
                        style={{ maxWidth: 220, maxHeight: 160, borderRadius: 8 }}
                      />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

interface Invite {
  code: string
  note: string
  uses: number
  max_uses: number
  active: boolean
}

/**
 * Коды доступа. Живут в базе, а не в переменной Render: выдать код классу,
 * исчерпать лимит или отключить один — всё отсюда, без редеплоя.
 * Пока активных кодов нет, регистрация на проде ЗАКРЫТА (fail-closed).
 */
function Invites({ adminKey }: { adminKey: string }) {
  const [list, setList] = useState<Invite[]>([])
  const [note, setNote] = useState('')
  const [maxUses, setMaxUses] = useState('')
  const [err, setErr] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const d = (await api('/admin/invites', adminKey)) as { invites: Invite[] }
      setList(d.invites ?? [])
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }, [adminKey])

  useEffect(() => {
    void load()
  }, [load])

  const create = async () => {
    setErr(null)
    try {
      await api('/admin/invites', adminKey, {
        method: 'POST',
        // Пустой код — сервер придумает сам: короче и безопаснее наспех
        // сочинённого «qwerty».
        body: JSON.stringify({ note, max_uses: Number(maxUses) || 0 }),
      })
      setNote('')
      setMaxUses('')
      await load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }

  const active = list.filter((i) => i.active).length

  return (
    <div className="card2" style={{ width: 'min(100%, 760px)' }}>
      <p style={{ margin: '0 0 4px', fontWeight: 800 }}>Коды доступа</p>
      <p style={{ margin: '0 0 10px', fontSize: 13, color: 'var(--card-ink-dim)' }}>
        {active > 0
          ? `Регистрация открыта: ${active} активных кода.`
          : 'Активных кодов нет — регистрация закрыта для всех новых.'}
      </p>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
        <input
          className="auth-input"
          style={{ flex: 1, minWidth: 160 }}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="для кого (например: 11А)"
        />
        <input
          className="auth-input"
          style={{ width: 130 }}
          value={maxUses}
          onChange={(e) => setMaxUses(e.target.value.replace(/\D/g, ''))}
          placeholder="лимит (0 = ∞)"
        />
        <Pill onClick={() => void create()}>Создать код</Pill>
      </div>

      {list.map((i) => (
        <div className="rowbetween" key={i.code} style={{ padding: '5px 0' }}>
          <span style={{ opacity: i.active ? 1 : 0.5 }}>
            <b style={{ fontFamily: 'monospace' }}>{i.code}</b>
            {i.note && ` — ${i.note}`}
            <span style={{ color: 'var(--card-ink-dim)' }}>
              {' '}
              · использован {i.uses}
              {i.max_uses > 0 ? ` из ${i.max_uses}` : ' раз'}
            </span>
          </span>
          <Pill
            quiet
            onClick={() =>
              void api(`/admin/invites/${i.code}/toggle`, adminKey, {
                method: 'POST',
                body: JSON.stringify({ active: !i.active }),
              }).then(load)
            }
          >
            {i.active ? 'отключить' : 'включить'}
          </Pill>
        </div>
      ))}
      {err && <p style={{ color: '#b4485c', fontWeight: 700, margin: '8px 0 0' }}>{err}</p>}
    </div>
  )
}

/** Проверка канала алертов. Без неё владелец узнаёт, что Telegram настроен
    неверно, ровно тогда, когда что-то упало — то есть слишком поздно. */
function AlertCheck({ adminKey }: { adminKey: string }) {
  const [state, setState] = useState<'idle' | 'busy' | 'ok'>('idle')
  const [err, setErr] = useState<string | null>(null)
  return (
    <div className="card2" style={{ width: 'min(100%, 760px)' }}>
      <div className="rowbetween">
        <span>
          <b>Алерты в Telegram</b>
          <span style={{ color: 'var(--card-ink-dim)' }}>
            {' '}
            — проверь, что сообщения доходят
          </span>
        </span>
        <Pill
          disabled={state === 'busy'}
          onClick={() => {
            setState('busy')
            setErr(null)
            void api('/admin/test_alert', adminKey, { method: 'POST' })
              .then(() => setState('ok'))
              .catch((e) => {
                setState('idle')
                setErr(e instanceof Error ? e.message : String(e))
              })
          }}
        >
          {state === 'busy' ? 'Отправляю…' : 'Отправить тест'}
        </Pill>
      </div>
      {state === 'ok' && (
        <p style={{ color: '#2f7d63', fontWeight: 700, margin: '8px 0 0' }}>
          Отправлено — проверь Telegram.
        </p>
      )}
      {err && <p style={{ color: '#b4485c', fontWeight: 700, margin: '8px 0 0' }}>{err}</p>}
    </div>
  )
}

/** «Забыл пароль» без почты и телефона решает владелец: вводит ник, сервер
    генерирует новый пароль и показывает его ОДИН раз — продиктуй ученику. */
function ResetPassword({ adminKey }: { adminKey: string }) {
  const [nick, setNick] = useState('')
  const [result, setResult] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const run = async () => {
    setErr(null)
    setResult(null)
    try {
      const data = (await api('/admin/reset_password', adminKey, {
        method: 'POST',
        body: JSON.stringify({ nickname: nick.trim() }),
      })) as { nickname: string; password: string }
      setResult(`${data.nickname} → новый пароль: ${data.password}`)
      setNick('')
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="card2" style={{ width: 'min(100%, 760px)' }}>
      <p style={{ margin: '0 0 8px', fontWeight: 800 }}>Сброс пароля ученика</p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <input
          className="auth-input"
          style={{ flex: 1, minWidth: 180 }}
          value={nick}
          onChange={(e) => setNick(e.target.value)}
          placeholder="ник ученика (точно как в аккаунте)"
        />
        <Pill disabled={!nick.trim()} onClick={() => void run()}>
          Сбросить
        </Pill>
      </div>
      {result && (
        <p style={{ color: '#2f7d63', fontWeight: 800, margin: '8px 0 0' }}>
          {result} — покажи его ученику, второй раз не увидишь.
        </p>
      )}
      {err && <p style={{ color: '#b4485c', fontWeight: 700, margin: '8px 0 0' }}>{err}</p>}
    </div>
  )
}

export function AdminScreen({ onExit }: { onExit: () => void }) {
  const [key, setKey] = useState(() => sessionStorage.getItem(KEY_STORE) ?? '')
  const [authed, setAuthed] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [list, setList] = useState<AdminTask[]>([])

  const [exam, setExam] = useState('ege')
  const [taskNo, setTaskNo] = useState(39)
  const [kind, setKind] = useState<TaskKind>('reading')

  // Поля содержимого — общий пул, каждый тип берёт свои.
  const [readText, setReadText] = useState('')
  const [intro, setIntro] = useState('')
  const [caption, setCaption] = useState('')
  const [img1, setImg1] = useState('')
  const [img2, setImg2] = useState('')
  const [points, setPoints] = useState(['', '', '', ''])
  const [questions, setQuestions] = useState(['', '', '', '', ''])
  const [topic, setTopic] = useState('')

  const effKind: TaskKind = exam === 'ege' ? (KIND_BY_EGE_NO[taskNo] ?? 'reading') : kind

  const refresh = useCallback(async (k: string) => {
    const data = (await api('/admin/tasks', k)) as { tasks: AdminTask[] }
    setList(data.tasks ?? [])
  }, [])

  const enter = useCallback(async () => {
    setError(null)
    try {
      await refresh(key)
      sessionStorage.setItem(KEY_STORE, key)
      setAuthed(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [key, refresh])

  // Ключ уже лежит в sessionStorage — входим молча.
  useEffect(() => {
    if (key && !authed) void enter()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const buildPayload = (): Record<string, unknown> | string => {
    switch (effKind) {
      case 'reading':
        if (readText.trim().length < 100) return 'Текст для чтения слишком короткий.'
        return { brief: BRIEF_39, readText: readText.trim() }
      case 'dialogue': {
        const pts = points.map((p) => p.trim()).filter(Boolean)
        if (pts.length !== 4) return 'Нужно ровно 4 пункта вопросов.'
        if (!intro.trim()) return 'Нужно вступление (You are considering…).'
        return {
          brief: ad(intro.trim(), pts),
          images: img1.trim() ? [img1.trim()] : undefined,
          imageCaption: caption.trim() || undefined,
          steps: pts.map((p, i) => `Question ${i + 1}: ${p}`),
        }
      }
      case 'interview': {
        const qs = questions.map((q) => q.trim()).filter(Boolean)
        if (qs.length !== 5) return 'Нужно ровно 5 вопросов.'
        return { brief: BRIEF_41, steps: qs }
      }
      case 'monologue': {
        if (!topic.trim()) return 'Нужна тема проекта.'
        if (!img1.trim() || !img2.trim()) return 'Нужны две ссылки на фото.'
        return {
          brief: monologueBrief(topic.trim(), 'the two options', 'the two options'),
          images: [img1.trim(), img2.trim()],
          imageCaption: topic.trim(),
        }
      }
    }
  }

  const save = useCallback(async () => {
    setError(null)
    setNotice(null)
    const payload = buildPayload()
    if (typeof payload === 'string') {
      setError(payload)
      return
    }
    try {
      await api('/admin/tasks', key, {
        method: 'POST',
        body: JSON.stringify({ exam, task_no: taskNo, kind: effKind, payload }),
      })
      setNotice(`Вариант добавлен: ${exam} №${taskNo} (${KIND_LABEL[effKind]}). Он уже в выдаче.`)
      setReadText('')
      setIntro('')
      setCaption('')
      setImg1('')
      setImg2('')
      setPoints(['', '', '', ''])
      setQuestions(['', '', '', '', ''])
      setTopic('')
      await refresh(key)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, exam, taskNo, effKind, readText, intro, caption, img1, img2, points, questions, topic, refresh])

  if (!authed) {
    return (
      <div className="authpage">
        <h1 className="auth-title" style={{ fontSize: 'clamp(28px, 5vw, 44px)', color: '#574f8e' }}>
          ADMIN
        </h1>
        <div className="auth-panel">
          <input
            className="auth-input"
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="admin key"
            onKeyDown={(e) => {
              if (e.key === 'Enter') void enter()
            }}
          />
        </div>
        {error && <p className="auth-err">{error}</p>}
        <button type="button" className="auth-btn" disabled={!key} onClick={() => void enter()}>
          ВОЙТИ
        </button>
        <button type="button" className="auth-btn auth-btn--ghost" onClick={onExit}>
          НАЗАД
        </button>
      </div>
    )
  }

  return (
    <div className="screen">
      <header className="topbar2">
        <span className="topbar2__brand">SPEAKO · ADMIN</span>
        <Pill onClick={onExit}>Выйти из админки</Pill>
      </header>

      <div
        className="screen__body scroll-soft scroll-soft--onDark"
        style={{ overflowY: 'auto', justifyContent: 'safe center', padding: '8px 10px' }}
      >
        <div className="card2" style={{ width: 'min(100%, 760px)' }}>
          <p style={{ margin: '0 0 10px', fontWeight: 800 }}>Добавить вариант</p>

          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
            <label style={LABEL}>
              РАЗДЕЛ{' '}
              <select value={exam} onChange={(e) => setExam(e.target.value)}>
                <option value="ege">ЕГЭ</option>
                <option value="oge">ОГЭ (в банк, раздел скоро)</option>
                <option value="other">другое</option>
              </select>
            </label>
            <label style={LABEL}>
              НОМЕР{' '}
              {exam === 'ege' ? (
                <select value={taskNo} onChange={(e) => setTaskNo(Number(e.target.value))}>
                  {[39, 40, 41, 42].map((n) => (
                    <option key={n} value={n}>
                      №{n} — {KIND_LABEL[KIND_BY_EGE_NO[n]]}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="number"
                  min={1}
                  max={99}
                  value={taskNo}
                  onChange={(e) => setTaskNo(Number(e.target.value))}
                  style={{ width: 70 }}
                />
              )}
            </label>
            {exam !== 'ege' && (
              <label style={LABEL}>
                ТИП{' '}
                <select value={kind} onChange={(e) => setKind(e.target.value as TaskKind)}>
                  {(Object.keys(KIND_LABEL) as TaskKind[]).map((k) => (
                    <option key={k} value={k}>
                      {KIND_LABEL[k]}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          {effKind === 'reading' && (
            <label style={LABEL}>
              ТЕКСТ ДЛЯ ЧТЕНИЯ (100–150 слов)
              <textarea
                className="auth-input"
                style={AREA}
                value={readText}
                onChange={(e) => setReadText(e.target.value)}
              />
            </label>
          )}

          {effKind === 'dialogue' && (
            <>
              <label style={LABEL}>
                ВСТУПЛЕНИЕ (You are considering…)
                <input className="auth-input" style={FIELD} value={intro} onChange={(e) => setIntro(e.target.value)} />
              </label>
              <label style={LABEL}>
                ПОДПИСЬ НАД КАРТИНКОЙ
                <input className="auth-input" style={FIELD} value={caption} onChange={(e) => setCaption(e.target.value)} />
              </label>
              <label style={LABEL}>
                ССЫЛКА НА КАРТИНКУ
                <input className="auth-input" style={FIELD} value={img1} onChange={(e) => setImg1(e.target.value)} />
              </label>
              {points.map((p, i) => (
                <label key={i} style={LABEL}>
                  ПУНКТ {i + 1}
                  <input
                    className="auth-input"
                    style={FIELD}
                    value={p}
                    onChange={(e) => setPoints(points.map((x, j) => (j === i ? e.target.value : x)))}
                  />
                </label>
              ))}
            </>
          )}

          {effKind === 'interview' && (
            <>
              {questions.map((q, i) => (
                <label key={i} style={LABEL}>
                  ВОПРОС {i + 1}
                  <input
                    className="auth-input"
                    style={FIELD}
                    value={q}
                    onChange={(e) =>
                      setQuestions(questions.map((x, j) => (j === i ? e.target.value : x)))
                    }
                  />
                </label>
              ))}
            </>
          )}

          {effKind === 'monologue' && (
            <>
              <label style={LABEL}>
                ТЕМА ПРОЕКТА (например, The world of hobbies)
                <input className="auth-input" style={FIELD} value={topic} onChange={(e) => setTopic(e.target.value)} />
              </label>
              <label style={LABEL}>
                ФОТО 1 — ССЫЛКА
                <input className="auth-input" style={FIELD} value={img1} onChange={(e) => setImg1(e.target.value)} />
              </label>
              <label style={LABEL}>
                ФОТО 2 — ССЫЛКА
                <input className="auth-input" style={FIELD} value={img2} onChange={(e) => setImg2(e.target.value)} />
              </label>
            </>
          )}

          {error && <p style={{ color: '#b4485c', fontWeight: 700 }}>{error}</p>}
          {notice && <p style={{ color: '#2f7d63', fontWeight: 700 }}>{notice}</p>}

          <div className="rowend" style={{ marginTop: 8 }}>
            <Pill onClick={() => void save()}>Сохранить вариант</Pill>
          </div>
        </div>

        <Invites adminKey={key} />

        <BankList list={list} adminKey={key} onChanged={() => refresh(key)} />

        <ResetPassword adminKey={key} />

        <AlertCheck adminKey={key} />
      </div>
    </div>
  )
}
