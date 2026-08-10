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
import { REASONS } from '../ege2/dispute'
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

interface Overview {
  users: { total: number; active_today: number; active_month: number }
  last_backup: { at: string; what: string } | null
  month: string
  days_with_traffic: number
  llm_requests: number
  llm_tokens: number
  stt_requests: number
  stt_audio_seconds: number
  tts_chars: number
  latency: Record<string, { avg_sec: number; n: number } | null>
  results: Record<string, { attempts: number; avg_pct: number }>
  budget: {
    limit: number | null
    used: number
    remaining: number | null
    pct: number | null
    per_day_avg: number | null
    per_active_user_avg: number | null
    days_left_estimate: number | null
    mode: string
  }
}

const KIND_RU: Record<string, string> = {
  reading: '№39 чтение',
  dialogue: '№40 вопросы',
  interview: '№41 интервью',
  monologue: '№42 монолог',
}

/* Первые четыре — РАЗЛОЖЕНИЕ паузы до звука: распознал → дождался первого
   токена → набрал первую фразу → озвучил. Сумма первых трёх плюс генерация и
   есть «пауза до звука»; по одному итоговому числу решить, что ускорять,
   невозможно. */
const STAGE_RU: Record<string, string> = {
  conv_stt: '1. распознавание речи',
  conv_ttft: '2. ожидание первого токена',
  conv_tts: '3. озвучка первой фразы',
  conv_answer: '= пауза до звука (итог)',
  task_stt: 'задания: распознавание',
  task_llm: 'задания: разбор LLM',
  talk_review: 'разговор: разбор в конце',
}

/** Число или «нет данных» — ноль вместо отсутствия здесь ЗАПРЕЩЁН: ноль
    в скорости читался бы как «мгновенно», а в расходе — как «не тратим». */
const fmt = (v: number | null | undefined, unit = ''): string =>
  v === null || v === undefined ? 'нет данных' : `${v}${unit}`

/**
 * Когда базу последний раз забирали на ноут.
 *
 * Ночная задача проваливается молча: она может быть отключена, ноут мог спать,
 * файл скрипта мог исчезнуть с диска (наблюдалось 05.08.2026). Снаружи всё это
 * неотличимо от «бэкап работает» — до дня, когда база понадобится. Сервер же
 * точно знает, когда его последний раз выгружали, поэтому цифра приходит от
 * него, а не из папки на ноуте.
 */
function BackupCell({
  last,
  cell,
  label,
  value,
}: {
  last: Overview['last_backup']
  cell: CSSProperties
  label: CSSProperties
  value: CSSProperties
}) {
  const hours = last ? (Date.now() - new Date(last.at).getTime()) / 3_600_000 : null
  // Сутки с запасом: бэкап ночной, и «26 часов назад» ещё норма, а вот двое
  // суток означают, что как минимум одна ночь пропущена.
  const stale = hours === null || hours > 48
  const ago =
    hours === null
      ? 'ни разу'
      : hours < 1
        ? 'только что'
        : hours < 24
          ? `${Math.round(hours)} ч назад`
          : `${Math.round(hours / 24)} дн назад`
  return (
    <div style={{ ...cell, ...(stale ? { background: 'rgba(180,72,92,0.16)' } : {}) }}>
      <div style={label}>последний бэкап базы</div>
      <div style={{ ...value, color: stale ? '#b4485c' : undefined }}>{ago}</div>
      <div style={label}>
        {stale ? 'ночная задача не отработала — проверь backup.log' : last?.what}
      </div>
    </div>
  )
}

/**
 * Сводка о работе системы. Все числа приходят ОДНИМ снимком из базы
 * (/admin/overview) — тут ничего не считается, только рисуется: арифметика
 * на двух сторонах разошлась бы при первом же изменении формулы.
 */
function OverviewCard({ adminKey }: { adminKey: string }) {
  const [o, setO] = useState<Overview | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api('/admin/overview', adminKey)
      .then((d) => setO(d as Overview))
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
  }, [adminKey])

  if (err)
    return (
      <div className="card2" style={{ width: 'min(100%, 760px)' }}>
        <p style={{ margin: 0, color: '#b4485c' }}>Сводка недоступна: {err}</p>
      </div>
    )
  if (!o) return null

  const b = o.budget
  const cell: React.CSSProperties = {
    flex: '1 1 150px',
    padding: '8px 12px',
    borderRadius: 12,
    background: 'rgba(0,0,0,0.05)',
  }
  const label: React.CSSProperties = { fontSize: 12, color: 'var(--card-ink-dim)' }
  const value: React.CSSProperties = { fontWeight: 800, fontSize: 18 }

  return (
    <div className="card2" style={{ width: 'min(100%, 760px)' }}>
      <p style={{ margin: '0 0 10px', fontWeight: 800 }}>
        Сводка за {o.month}{' '}
        <span style={{ fontWeight: 600, fontSize: 12, color: 'var(--card-ink-dim)' }}>
          все числа из базы, обновляются при открытии
        </span>
      </p>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
        <div style={cell}>
          <div style={label}>учеников всего</div>
          <div style={value}>{o.users.total}</div>
          <div style={label}>
            активных: {o.users.active_month} за месяц · {o.users.active_today} сегодня
          </div>
        </div>
        <div style={cell}>
          <div style={label}>запросы LLM за месяц</div>
          <div style={value}>
            {b.used}
            {b.limit ? ` / ${b.limit}` : ''}
          </div>
          <div style={label}>
            {b.pct !== null ? `${b.pct}% бюджета` : 'бюджет выключен'} · режим {b.mode}
          </div>
        </div>
        <div style={cell}>
          <div style={label}>хватит ещё примерно</div>
          <div style={value}>{fmt(b.days_left_estimate, ' дн')}</div>
          <div style={label}>при расходе как сейчас</div>
        </div>
        <BackupCell last={o.last_backup} cell={cell} label={label} value={value} />
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
        <div style={cell}>
          <div style={label}>в день (дни с трафиком: {o.days_with_traffic})</div>
          <div style={value}>{fmt(b.per_day_avg)}</div>
        </div>
        <div style={cell}>
          <div style={label}>на активного ученика</div>
          <div style={value}>{fmt(b.per_active_user_avg)}</div>
        </div>
        <div style={cell}>
          <div style={label}>токены · STT · TTS</div>
          <div style={{ fontWeight: 700, fontSize: 13 }}>
            {o.llm_tokens.toLocaleString('ru')} ток · {o.stt_requests} расп ·{' '}
            {o.tts_chars.toLocaleString('ru')} симв
          </div>
        </div>
      </div>

      <p style={{ margin: '4px 0', fontWeight: 800, fontSize: 13 }}>
        СКОРОСТЬ{' '}
        <span style={{ fontWeight: 600, fontSize: 11, color: 'var(--card-ink-dim)' }}>
          точное среднее по всем запросам месяца (сумма/число)
        </span>
      </p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
        {Object.entries(STAGE_RU).map(([k, name]) => {
          const l = o.latency[k]
          return (
            <div key={k} style={cell}>
              <div style={label}>{name}</div>
              <div style={value}>{l ? `${l.avg_sec} с` : 'нет данных'}</div>
              {l && <div style={label}>{l.n} замеров</div>}
            </div>
          )
        })}
      </div>

      <p style={{ margin: '4px 0', fontWeight: 800, fontSize: 13 }}>
        РЕЗУЛЬТАТЫ УЧЕНИКОВ{' '}
        <span style={{ fontWeight: 600, fontSize: 11, color: 'var(--card-ink-dim)' }}>
          средний % от максимума за месяц
        </span>
      </p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {Object.keys(o.results).length === 0 && (
          <span style={label}>разборов в этом месяце ещё не было</span>
        )}
        {Object.entries(o.results).map(([k, r]) => (
          <div key={k} style={cell}>
            <div style={label}>{KIND_RU[k] ?? k}</div>
            <div style={value}>{r.avg_pct}%</div>
            <div style={label}>{r.attempts} разб.</div>
          </div>
        ))}
      </div>
    </div>
  )
}

interface PronStats {
  total: number
  students: number
  variants: number
  percentiles: Record<string, number>
  below: Record<string, { words: number; pct: number }>
  worst: Array<{ word: string; p_norm: number; variant: string | null }>
}

/**
 * Копилка замеров произношения — экран подбора порога.
 *
 * Показатель считается по каждому слову чтения вслух: насколько звук
 * подтверждает ИМЕННО ТО слово, что написано в тексте (backend/gop.py).
 * Ученику пока не показывается ничего — сначала надо увидеть, как показатель
 * распределён на живой речи. Порог, снятый с синтезированного голоса, на
 * школьнике с акцентом почти наверняка окажется другим, а выдуманная точность
 * тут хуже отсутствия функции.
 *
 * Голос НЕ хранится: в базе только слово из задания и число рядом с ним.
 */
function Pronunciation({ adminKey }: { adminKey: string }) {
  const [d, setD] = useState<{
    stats: PronStats
    collecting: boolean
    model: string
    done_this_process: number
  } | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api('/admin/pronunciation', adminKey)
      .then((x) => setD(x as typeof d))
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
  }, [adminKey])

  if (err)
    return (
      <div className="card2" style={{ width: 'min(100%, 760px)' }}>
        <p style={{ margin: 0, color: '#b4485c' }}>Замеры произношения: {err}</p>
      </div>
    )
  if (!d) return null
  const s = d.stats

  return (
    <div className="card2" style={{ width: 'min(100%, 760px)' }}>
      <div className="rowbetween" style={{ marginBottom: 4 }}>
        <p style={{ margin: 0, fontWeight: 800 }}>
          Произношение: копилка для калибровки{' '}
          <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--card-ink-dim)' }}>
            — {s.total} слов от {s.students} учеников
          </span>
        </p>
        <span style={{ fontSize: 12, color: 'var(--card-ink-dim)' }}>
          {d.collecting ? `собирается · ${d.model}` : 'сбор выключен'}
        </span>
      </div>

      {s.total === 0 ? (
        <p style={{ margin: 0, fontSize: 13 }}>
          Пока пусто. Числа появятся, когда кто-нибудь прочитает вслух задание 39:
          замер идёт фоном, ученик его не ждёт и ничего о нём не видит.
        </p>
      ) : (
        <>
          <p style={{ margin: '0 0 10px', fontSize: 13, color: 'var(--card-ink-dim)' }}>
            Показатель нормирован на собственный уровень говорящего: 1.0 — как
            остальные его слова, ниже 0.5 — звук плохо подтверждает написанное.
            Порог выбирается по этой таблице, а не из головы.
          </p>

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
            {Object.entries(s.percentiles).map(([k, v]) => (
              <div
                key={k}
                style={{
                  flex: '1 1 90px',
                  padding: '6px 10px',
                  borderRadius: 10,
                  background: 'rgba(0,0,0,0.05)',
                }}
              >
                <div style={{ fontSize: 11, color: 'var(--card-ink-dim)' }}>{k}</div>
                <div style={{ fontWeight: 800 }}>{v}</div>
              </div>
            ))}
          </div>

          <p style={{ margin: '0 0 4px', fontWeight: 800, fontSize: 12 }}>
            СКОЛЬКО СЛОВ СТАНЕТ «ОШИБКОЙ» ПРИ ПОРОГЕ
          </p>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
            {Object.entries(s.below).map(([thr, v]) => (
              <span
                key={thr}
                style={{
                  fontSize: 13,
                  padding: '4px 10px',
                  borderRadius: 999,
                  background: 'rgba(0,0,0,0.06)',
                }}
              >
                {thr} → <b>{v.words}</b> слов ({v.pct}%)
              </span>
            ))}
          </div>

          <p style={{ margin: '0 0 4px', fontWeight: 800, fontSize: 12 }}>
            САМЫЕ СЛАБЫЕ МЕСТА
          </p>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {s.worst.map((w, i) => (
              <span
                key={i}
                style={{
                  fontSize: 13,
                  padding: '3px 9px',
                  borderRadius: 8,
                  background: 'rgba(180,72,92,0.12)',
                }}
              >
                {w.word} · <b>{w.p_norm}</b>
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

/* ------------------------------------------- Обратная связь и споры об оценке */

interface Dispute {
  id: string
  student_id: string
  kind: string
  variant: string | null
  persona: string | null
  target: string | null
  target_key: string | null
  target_label: string | null
  reason: string | null
  comment: string | null
  said: string | null
  score: number | null
  max_score: number | null
  claim_score: number | null
  transcript: string | null
  feedback: string | null
  context: string | null
  status: string
  verdict: string | null
  verdict_score: number | null
  verdict_note: string | null
  created_at: string
  resolved_at: string | null
  /** Признак снимка: id и размер. Сама картинка приезжает по /admin/shot. */
  shots?: Array<{ id: string; mime: string; bytes: number }>
}

interface DisputeStats {
  total: number
  pending: number
  with_shot: number
  by_kind: Record<string, number>
  by_reason: Record<string, number>
  by_target: Record<string, number>
  by_verdict: Record<string, number>
}

const TARGET_RU: Record<string, string> = {
  score: 'работа целиком',
  item: 'вопрос / ответ',
  criterion: 'критерий ФИПИ',
  error: 'найденная ошибка',
  talk_review: 'разбор беседы',
  talk_reply: 'реплика собеседника',
  app: 'приложение',
}

const KIND_ALL: Record<string, string> = {
  ...KIND_RU,
  talk: 'разговор',
  app: 'приложение',
}

const VERDICT_RU: Record<string, string> = {
  ours: 'наш балл верен',
  student: 'прав ученик',
  partial: 'частично прав',
}

/* Жалобы, поданные ДО появления формы, лежат в той же таблице с пустыми
   полями. Их нельзя показывать так, будто человек выбрал «дело не в балле» или
   «без причины» осознанно: это разные вещи, и по ним принимаются разные
   решения. Поэтому пустое место называется пустым. */
const reasonLabel = (code: string | null): string =>
  REASONS.find((r) => r.code === code)?.label ??
  (!code || code === '?' ? 'причина не указана (старая жалоба)' : code)

const claimLabel = (claim: number | null): string =>
  claim === null || claim === undefined
    ? 'не указано'
    : claim >= 0
      ? String(claim)
      : 'дело не в балле'

/** Разобрать JSON, не роняя экран. Жалобы копятся годами, формат снимка
    разбора будет меняться — старая запись обязана открываться и потом. */
function parseSafe(raw: string | null): unknown {
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

const dim: CSSProperties = { fontSize: 12, color: 'var(--card-ink-dim)' }
const blockTitle: CSSProperties = {
  fontSize: 11,
  fontWeight: 800,
  letterSpacing: '0.06em',
  color: 'var(--card-ink-dim)',
  margin: '10px 0 2px',
}
const quoteBox: CSSProperties = {
  margin: 0,
  padding: '6px 8px',
  borderRadius: 8,
  background: 'rgba(0,0,0,0.05)',
  fontSize: 13,
  whiteSpace: 'pre-wrap',
  maxHeight: 220,
  overflowY: 'auto',
}

/**
 * Снимки экрана из жалобы. Ключ уходит ПАРАМЕТРОМ: тег <img> заголовков не
 * шлёт, а ключ и так лежит в этой вкладке — админка по нему и открыта.
 */
function Shots({ shots, adminKey }: { shots?: Dispute['shots']; adminKey: string }) {
  if (!shots?.length) return null
  return (
    <>
      <p style={blockTitle}>СНИМОК ЭКРАНА</p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {shots.map((s) => {
          const src = `${BACKEND}/admin/shot/${s.id}?key=${encodeURIComponent(adminKey)}`
          return (
            /* Открывается в новой вкладке: разглядывать мелкий текст на
               превью в 240 px бессмысленно, а ради этого и прикладывали. */
            <a key={s.id} href={src} target="_blank" rel="noreferrer" title="Открыть целиком">
              <img
                src={src}
                alt="Снимок экрана от ученика"
                style={{
                  maxWidth: 240,
                  maxHeight: 180,
                  borderRadius: 8,
                  border: '1px solid rgba(0,0,0,0.15)',
                  display: 'block',
                }}
              />
            </a>
          )
        })}
      </div>
    </>
  )
}

/** Обстановка спора: текст задания либо кусок беседы — что приложил экран. */
function ContextView({ raw }: { raw: string | null }) {
  const ctx = parseSafe(raw) as Record<string, unknown> | null
  if (!ctx) return null
  const turns = ctx.turns as Array<{ role: string; content: string }> | undefined
  const steps = ctx.steps as string[] | undefined
  const facts = ctx.photoFacts as string[] | undefined
  return (
    <>
      <p style={blockTitle}>НА ФОНЕ ЧЕГО</p>
      <div style={quoteBox}>
        {typeof ctx.brief === 'string' && <div>{ctx.brief}</div>}
        {typeof ctx.readText === 'string' && (
          <div style={{ fontStyle: 'italic', marginTop: 6 }}>{ctx.readText}</div>
        )}
        {steps && steps.length > 0 && (
          <ol style={{ margin: '6px 0 0', paddingLeft: 18 }}>
            {steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        )}
        {facts && facts.length > 0 && (
          <div style={{ marginTop: 6, ...dim }}>на фото: {facts.join(' | ')}</div>
        )}
        {turns && turns.length > 0 && (
          <div style={{ display: 'grid', gap: 3 }}>
            {turns.map((t, i) => (
              <div key={i}>
                <b>{t.role === 'user' ? 'ученик' : 'ИИ'}:</b> {t.content}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}

/** Что выдал разбор — то, с чем спорят. Показываем разобранным, а сырой JSON
    оставляем по кнопке: ничего не прячем, но и не заставляем читать скобки. */
function VerdictView({ raw }: { raw: string | null }) {
  const [rawOpen, setRawOpen] = useState(false)
  const fb = parseSafe(raw) as
    | {
        summary?: string
        score?: number
        max?: number
        criteria?: Array<{ name?: string; score?: number; max?: number; comment?: string }>
        errors?: Array<{ quote?: string; correction?: string; explanation?: string }>
        mistakes?: Array<{ quote?: string; correction?: string; why?: string }>
      }
    | null
  if (!raw) return null
  return (
    <>
      <p style={blockTitle}>ЧТО ВЫДАЛ РАЗБОР</p>
      {fb ? (
        <div style={quoteBox}>
          {fb.summary && <div>{fb.summary}</div>}
          {(fb.criteria ?? []).map((c, i) => (
            <div key={i}>
              • {c.name}: <b>{c.score}</b> из {c.max}
              {c.comment ? ` — ${c.comment}` : ''}
            </div>
          ))}
          {[...(fb.errors ?? []), ...(fb.mistakes ?? [])].map((e, i) => (
            <div key={`e${i}`}>
              — «{e.quote}» → «{e.correction}»
              {'explanation' in e && e.explanation ? ` (${e.explanation})` : ''}
              {'why' in e && e.why ? ` (${e.why})` : ''}
            </div>
          ))}
        </div>
      ) : (
        <p style={dim}>снимок разбора не разобрался — смотри сырые данные</p>
      )}
      <button type="button" className="dsg__link" onClick={() => setRawOpen(!rawOpen)}>
        {rawOpen ? 'скрыть сырые данные' : 'сырые данные'}
      </button>
      {rawOpen && <pre style={{ ...quoteBox, fontSize: 11 }}>{raw}</pre>}
    </>
  )
}

/** Форма вердикта. Это и есть разметка золотого набора: строка «наш балл 3,
    верный 5, потому что аспект 2 раскрыт» — готовый калибровочный случай. */
function Resolve({
  d,
  adminKey,
  onDone,
}: {
  d: Dispute
  adminKey: string
  onDone: () => void
}) {
  const [verdict, setVerdict] = useState(d.verdict ?? '')
  const [score, setScore] = useState<number>(d.verdict_score ?? -1)
  const [note, setNote] = useState(d.verdict_note ?? '')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const max = d.max_score ?? 0

  const save = (status: 'done' | 'skip') => {
    setBusy(true)
    setErr(null)
    void api(`/admin/disputes/${d.id}`, adminKey, {
      method: 'POST',
      body: JSON.stringify({ status, verdict, verdict_score: score, verdict_note: note }),
    })
      .then(onDone)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false))
  }

  return (
    <div style={{ marginTop: 10, borderTop: '1px solid rgba(0,0,0,0.08)', paddingTop: 8 }}>
      <p style={blockTitle}>ТВОЙ ВЕРДИКТ</p>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
        {Object.entries(VERDICT_RU).map(([code, label]) => (
          <button
            key={code}
            type="button"
            className={`dsg__chip${verdict === code ? ' dsg__chip--on' : ''}`}
            onClick={() => setVerdict(code)}
          >
            {label}
          </button>
        ))}
      </div>
      {max > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
          <span style={{ ...dim, alignSelf: 'center' }}>верный балл:</span>
          {Array.from({ length: max + 1 }, (_, n) => (
            <button
              key={n}
              type="button"
              className={`dsg__score${score === n ? ' dsg__chip--on' : ''}`}
              onClick={() => setScore(n)}
            >
              {n}
            </button>
          ))}
          <button
            type="button"
            className={`dsg__chip${score === -1 ? ' dsg__chip--on' : ''}`}
            onClick={() => setScore(-1)}
          >
            не в балле
          </button>
        </div>
      )}
      <input
        className="auth-input"
        style={{ width: '100%', textAlign: 'left' }}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="почему так — эта строка и станет правилом для калибровки"
      />
      <div className="rowend" style={{ gap: 8, marginTop: 8 }}>
        <Pill quiet disabled={busy} onClick={() => save('skip')}>
          Отложить
        </Pill>
        <Pill disabled={busy || !verdict} onClick={() => save('done')}>
          Разобрано
        </Pill>
      </div>
      {err && <p style={{ color: '#b4485c', fontWeight: 700, margin: '6px 0 0' }}>{err}</p>}
    </div>
  )
}

/**
 * Копилка обратной связи — очередь разбора, а не витрина.
 *
 * Зачем она в таком виде. Жалоба ученика это ЕДИНСТВЕННЫЙ источник размеченных
 * работ, который растёт сам: шесть работ ФИПИ конечны, а споров будет столько,
 * сколько ошибается проверка. Чтобы спор стал калибровочным случаем, не хватает
 * ровно одного — вердикта человека, поэтому он ставится здесь в три нажатия,
 * а не выносится в отдельный документ, который никто не заполнит.
 *
 * Сверху разрезы: по типу задания (что чинить первым), по причине (что именно
 * чинить) и по вердиктам (какая доля жалоб оказалась справедливой — то есть
 * настоящая частота ошибок проверки, а не жалоб на неё).
 */
function Disputes({ adminKey }: { adminKey: string }) {
  const [list, setList] = useState<Dispute[]>([])
  const [stats, setStats] = useState<DisputeStats | null>(null)
  const [status, setStatus] = useState<'new' | 'all'>('new')
  const [kind, setKind] = useState<string>('all')
  // Жалобы со снимком разбираются в разы быстрее — их логично разгребать
  // первыми, поэтому это отдельный фильтр, а не колонка в таблице.
  const [onlyShots, setOnlyShots] = useState(false)
  const [open, setOpen] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const d = (await api(
        `/admin/disputes${status === 'new' ? '?status=new' : ''}`,
        adminKey,
      )) as { disputes: Dispute[]; stats: DisputeStats }
      setList(d.disputes ?? [])
      setStats(d.stats ?? null)
      setErr(null)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }, [adminKey, status])

  useEffect(() => {
    void load()
  }, [load])

  const shown = list.filter(
    (d) => (kind === 'all' || d.kind === kind) && (!onlyShots || (d.shots?.length ?? 0) > 0),
  )

  const download = () => {
    const blob = new Blob([JSON.stringify(list, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `pingo-disputes-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  /* Названия берём из ТОГО ЖЕ каталога, что и форма ученика: свой словарь в
     админке разъехался бы с формой при первой же правке причин. */
  const REASON_RU = Object.fromEntries(REASONS.map((r) => [r.code, r.label]))

  const chips = (title: string, data: Record<string, number>, ru: Record<string, string>) => {
    const items = Object.entries(data).sort((a, b) => b[1] - a[1])
    if (!items.length) return null
    return (
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ ...dim, fontWeight: 800 }}>{title}</span>
        {items.map(([k, n]) => (
          <span
            key={k}
            style={{
              fontSize: 12,
              padding: '3px 9px',
              borderRadius: 999,
              background: 'rgba(0,0,0,0.06)',
            }}
          >
            {ru[k] ?? (k === '?' ? 'не указано (старые жалобы)' : k)} · <b>{n}</b>
          </span>
        ))}
      </div>
    )
  }

  return (
    <div className="card2" style={{ width: 'min(100%, 760px)' }}>
      <div className="rowbetween" style={{ marginBottom: 4 }}>
        <p style={{ margin: 0, fontWeight: 800 }}>
          Обратная связь учеников
          {stats && (
            <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--card-ink-dim)' }}>
              {' '}
              — {stats.total} всего, {stats.pending} ждут разбора
              {stats.with_shot > 0 ? `, ${stats.with_shot} со снимком` : ''}
            </span>
          )}
        </p>
        <span style={{ display: 'flex', gap: 6 }}>
          <Pill quiet onClick={() => setOnlyShots(!onlyShots)}>
            {onlyShots ? '🖼 только со снимком' : '🖼 все'}
          </Pill>
          <select value={status} onChange={(e) => setStatus(e.target.value as typeof status)}>
            <option value="new">ждут разбора</option>
            <option value="all">все</option>
          </select>
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="all">все разделы</option>
            {Object.entries(KIND_ALL).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        </span>
      </div>

      <p style={{ margin: '0 0 8px', fontSize: 13, color: 'var(--card-ink-dim)' }}>
        Каждая разобранная жалоба — случай в калибровочном наборе: «наш балл N,
        верный M, потому что…». Именно из них проверка учится не ошибаться дважды.
      </p>

      {stats && (
        <div style={{ display: 'grid', gap: 6, marginBottom: 10 }}>
          {chips('РАЗДЕЛЫ', stats.by_kind, KIND_ALL)}
          {chips('ПРИЧИНЫ', stats.by_reason, REASON_RU)}
          {chips('ГДЕ ИМЕННО', stats.by_target, TARGET_RU)}
          {chips('ВЕРДИКТЫ', stats.by_verdict, VERDICT_RU)}
        </div>
      )}

      {err && <p style={{ color: '#b4485c', fontWeight: 700 }}>{err}</p>}
      {shown.length === 0 && (
        <p style={{ margin: 0 }}>
          {status === 'new' ? 'Неразобранных жалоб нет.' : 'Жалоб пока нет.'}
        </p>
      )}

      {shown.map((d) => {
        const isOpen = open === d.id
        const where = TARGET_RU[d.target ?? ''] ?? d.target ?? 'место не указано'
        return (
          <div key={d.id} style={{ borderTop: '1px solid rgba(0,0,0,0.08)', padding: '8px 0' }}>
            <button
              type="button"
              onClick={() => setOpen(isOpen ? null : d.id)}
              style={{ all: 'unset', cursor: 'pointer', display: 'block', width: '100%' }}
            >
              <div className="rowbetween">
                <span style={{ fontWeight: 700, minWidth: 0 }}>
                  {d.status === 'new' ? '🟡' : d.status === 'skip' ? '⏸' : '✅'}{' '}
                  {KIND_ALL[d.kind] ?? d.kind} · {where}
                  {d.max_score ? (
                    <>
                      {' '}
                      · балл <b>{d.score}</b> → просят <b>{claimLabel(d.claim_score)}</b>
                    </>
                  ) : null}
                </span>
                <span style={{ ...dim, flexShrink: 0 }}>{d.created_at?.slice(0, 16).replace('T', ' ')}</span>
              </div>
              <div style={{ ...dim, marginTop: 2 }}>
                {reasonLabel(d.reason)}
                {d.target_label ? ` · ${d.target_label}` : ''}
              </div>
              {!isOpen && d.comment && (
                <div style={{ fontSize: 13, marginTop: 2 }}>
                  {(d.shots?.length ?? 0) > 0 && '🖼 '}«{d.comment.slice(0, 110)}»
                </div>
              )}
            </button>

            {isOpen && (
              <div style={{ paddingTop: 4 }}>
                <p style={blockTitle}>УЧЕНИК ПИШЕТ</p>
                <p style={{ margin: 0, fontSize: 14 }}>{d.comment}</p>
                {d.said && (
                  <p style={{ margin: '4px 0 0', fontSize: 13 }}>
                    <span style={dim}>сказал на самом деле: </span>«{d.said}»
                  </p>
                )}

                {d.transcript && (
                  <>
                    <p style={blockTitle}>ЧТО РАСПОЗНАЛОСЬ</p>
                    <p style={quoteBox}>{d.transcript}</p>
                  </>
                )}

                <Shots shots={d.shots} adminKey={adminKey} />
                <ContextView raw={d.context} />
                <VerdictView raw={d.feedback} />

                <p style={{ ...dim, marginTop: 8 }}>
                  ученик {d.student_id?.slice(0, 8)} · вариант {d.variant || '—'} · собеседник{' '}
                  {d.persona || '—'}
                  {d.resolved_at ? ` · разобрано ${d.resolved_at.slice(0, 16).replace('T', ' ')}` : ''}
                </p>

                <Resolve d={d} adminKey={adminKey} onDone={load} />
              </div>
            )}
          </div>
        )
      })}

      {list.length > 0 && (
        <div className="rowend" style={{ marginTop: 10 }}>
          <Pill quiet onClick={download}>
            Скачать JSON
          </Pill>
        </div>
      )}
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

interface TgState {
  token_set: boolean
  chat_set: boolean
  ready: boolean
  chat_id_hint?: string | null
  hint_error?: string | null
}

/**
 * Настройка алертов пошагово. Сделано мастером, а не одной кнопкой, потому что
 * половину шагов может выполнить только владелец (BotFather, переменные
 * Render), и ему важно видеть, какие уже закрыты. Всё, что можно было снять с
 * человека, снято: chat_id ищет сервер, канал проверяется кнопкой.
 */
function AlertCheck({ adminKey }: { adminKey: string }) {
  const [tg, setTg] = useState<TgState | null>(null)
  const [state, setState] = useState<'idle' | 'busy' | 'ok'>('idle')
  const [err, setErr] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setTg((await api('/admin/telegram', adminKey)) as TgState)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }, [adminKey])

  useEffect(() => {
    void load()
  }, [load])

  const step = (done: boolean, text: string) => (
    <p style={{ margin: '2px 0', color: done ? '#2f7d63' : 'var(--card-ink-dim)' }}>
      {done ? '✅' : '⬜'} {text}
    </p>
  )

  return (
    <div className="card2" style={{ width: 'min(100%, 760px)' }}>
      <p style={{ margin: '0 0 8px', fontWeight: 800 }}>
        Алерты в Telegram{' '}
        <span style={{ fontWeight: 600, color: 'var(--card-ink-dim)', fontSize: 13 }}>
          — чтобы о падении узнать не от учеников
        </span>
      </p>

      {tg && (
        <>
          {step(tg.token_set, 'TELEGRAM_BOT_TOKEN задан в переменных Render (бот из @BotFather)')}
          {step(tg.chat_set, 'TELEGRAM_CHAT_ID задан там же')}

          {tg.token_set && !tg.chat_set && (
            <div
              style={{
                margin: '8px 0',
                padding: '8px 10px',
                borderRadius: 10,
                background: 'rgba(0,0,0,0.05)',
              }}
            >
              {tg.chat_id_hint ? (
                <>
                  <b>Твой chat_id: {tg.chat_id_hint}</b>
                  <br />
                  Скопируй число в переменную <code>TELEGRAM_CHAT_ID</code> на Render
                  и передеплой.
                </>
              ) : (
                <>
                  {tg.hint_error}
                  <br />
                  <Pill quiet onClick={() => void load()}>
                    Искать ещё раз
                  </Pill>
                </>
              )}
            </div>
          )}
        </>
      )}

      <div className="rowbetween" style={{ marginTop: 8 }}>
        <span style={{ fontSize: 13, color: 'var(--card-ink-dim)' }}>
          {tg?.ready ? 'Всё задано — проверь, что сообщение дойдёт.' : 'Инструкция: docs/MONITORING.md'}
        </span>
        <Pill
          disabled={state === 'busy' || !tg?.ready}
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
        <OverviewCard adminKey={key} />

        {/* Копилка стоит ВТОРОЙ сверху, сразу под сводкой: это рабочая очередь
            владельца, а банк заданий и коды — обслуживание. */}
        <Disputes adminKey={key} />

        <Pronunciation adminKey={key} />

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
