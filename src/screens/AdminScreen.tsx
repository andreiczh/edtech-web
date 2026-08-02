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

  const shown = list.filter((t) =>
    filter === 'all' ? true : filter === 'active' ? t.active : !t.active,
  )
  const drafts = list.filter((t) => !t.active).length

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
                {t.active ? '🟢' : '📝'} №{t.task_no} · {KIND_LABEL[t.kind as TaskKind] ?? t.kind}
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

        <BankList list={list} adminKey={key} onChanged={() => refresh(key)} />
      </div>
    </div>
  )
}
