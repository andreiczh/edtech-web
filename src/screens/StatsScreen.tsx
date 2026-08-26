/**
 * Прогресс — экран из утверждённого прототипа (фото-канон владельца).
 *
 * Все числа живые:
 *  - тайлы — /me/stats (лучшая серия теперь считает сервер) и /me/analytics;
 *  - график «Успешность по заданиям» — history из /me/analytics: серия на
 *    каждую работу (день, тип, процент), агрегация по периодам на фронте;
 *  - «По заданиям» и «Частые ошибки» — kinds и mistakes из /me/analytics.
 *
 * «Время за неделю» из прототипа не переносим: система не замеряет длительность
 * занятий, а выдуманная цифра хуже отсутствующей. Вместо него — реальный XP.
 */
import { useEffect, useMemo, useState } from 'react'

import {
  fetchMeAnalytics,
  fetchMeStats,
  type MeAnalytics,
  type MeStats,
} from '../account/me'

const CAT_RU: Record<string, string> = {
  gram: 'Грамматика',
  lex: 'Лексика',
  order: 'Структура вопроса',
  missing: 'Нет ответа',
  logic: 'Логика',
  phon: 'Произношение',
  other: 'Прочее',
}

const KIND_RU: Record<string, string> = {
  reading: 'Чтение вслух',
  dialogue: 'Вопросы',
  interview: 'Интервью',
  monologue: 'Голосовое',
}

/* Серии графика — как на макете: чтение / вопросы и интервью / голосовое. */
const SERIES: Array<{ label: string; kinds: string[]; color: string }> = [
  { label: 'Чтение', kinds: ['reading'], color: '#B7A6F0' },
  { label: 'Вопросы и интервью', kinds: ['dialogue', 'interview'], color: '#F0537F' },
  { label: 'Голосовое сообщение', kinds: ['monologue'], color: '#2C97E0' },
]

type Range = 'week' | 'month' | 'year'

/** Агрегация истории по корзинам периода: среднее по работам серии в корзине.
    Возвращает подписи корзин и по значению (или null) на серию. */
function aggregate(history: MeAnalytics['history'], range: Range) {
  const now = new Date()
  const buckets: Array<{ label: string; from: string; to: string }> = []
  if (range === 'week') {
    for (let i = 6; i >= 0; i--) {
      const d = new Date(now)
      d.setDate(d.getDate() - i)
      const iso = d.toISOString().slice(0, 10)
      buckets.push({ label: ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'][d.getDay()], from: iso, to: iso })
    }
  } else {
    const months = range === 'month' ? 6 : 12
    for (let i = months - 1; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
      const from = d.toISOString().slice(0, 7)
      buckets.push({
        label: ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'][d.getMonth()],
        from,
        to: from,
      })
    }
  }
  const series = SERIES.map((s) => ({
    ...s,
    points: buckets.map((b) => {
      const inBucket = history.filter((h) => {
        const key = range === 'week' ? h.d : h.d.slice(0, 7)
        return key >= b.from && key <= b.to && s.kinds.includes(h.k)
      })
      if (inBucket.length === 0) return null
      return Math.round(inBucket.reduce((sum, h) => sum + h.p, 0) / inBucket.length)
    }),
  }))
  return { labels: buckets.map((b) => b.label), series }
}

function AreaChart({ history, range }: { history: MeAnalytics['history']; range: Range }) {
  const { labels, series } = useMemo(() => aggregate(history, range), [history, range])
  const W = 900
  const H = 260
  const padL = 46
  const padR = 16
  const padT = 14
  const padB = 30
  const n = labels.length
  const xs = (i: number) => padL + ((W - padL - padR) * i) / Math.max(1, n - 1)
  const ys = (v: number) => padT + (H - padB - padT) * (1 - v / 100)

  const hasData = series.some((s) => s.points.filter((p) => p !== null).length >= 2)
  if (!hasData) {
    return (
      <p className="statpage__empty">
        График появится после нескольких разборов — реши пару заданий.
      </p>
    )
  }

  return (
    <svg className="statpage__area" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Успешность по заданиям">
      {[0, 1, 2, 3, 4].map((g) => {
        const y = padT + ((H - padB - padT) * g) / 4
        return (
          <g key={g}>
            <line x1={padL} y1={y} x2={W - padR} y2={y} stroke="var(--line)" strokeWidth="1" />
            <text x={padL - 8} y={y + 4} textAnchor="end" fontSize="12" fill="var(--text-dim)" fontWeight="600">
              {100 - 25 * g}%
            </text>
          </g>
        )
      })}
      {labels.map((l, i) => (
        <text key={i} x={xs(i)} y={H - 8} textAnchor="middle" fontSize="12" fill="var(--text-dim)" fontWeight="600">
          {l}
        </text>
      ))}
      {series.map((s) => {
        const pts = s.points
          .map((p, i) => (p === null ? null : `${xs(i)},${ys(p)}`))
          .filter((p): p is string => p !== null)
        if (pts.length === 0) return null
        const lastIdx = s.points.reduce<number>((acc, p, i) => (p !== null ? i : acc), 0)
        const lastVal = s.points[lastIdx] ?? null
        return (
          <g key={s.label}>
            {pts.length >= 2 && (
              <polygon
                points={`${pts[0].split(',')[0]},${H - padB} ${pts.join(' ')} ${pts[pts.length - 1].split(',')[0]},${H - padB}`}
                fill={s.color}
                opacity="0.09"
              />
            )}
            <polyline
              points={pts.join(' ')}
              fill="none"
              stroke={s.color}
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            {lastVal !== null && (
              <circle cx={xs(lastIdx)} cy={ys(lastVal)} r="4" fill={s.color} stroke="var(--card-solid)" strokeWidth="2" />
            )}
          </g>
        )
      })}
    </svg>
  )
}

export function StatsScreen({ onBack: _onBack }: { onBack?: () => void }) {
  const [stats, setStats] = useState<MeStats | null>(null)
  const [analytics, setAnalytics] = useState<MeAnalytics | null>(null)
  const [range, setRange] = useState<Range>('month')

  useEffect(() => {
    let alive = true
    void fetchMeStats().then((s) => alive && setStats(s))
    void fetchMeAnalytics().then((a) => alive && setAnalytics(a))
    return () => {
      alive = false
    }
  }, [])

  const weekXp = stats ? stats.week.reduce((s, d) => s + d.xp, 0) : null

  const kinds = analytics?.kinds ?? {}
  const kindList = Object.entries(kinds)
  const totalAttempts = kindList.reduce((s, [, k]) => s + k.attempts, 0)
  const avgPct =
    totalAttempts > 0
      ? Math.round(kindList.reduce((s, [, k]) => s + k.avg_pct * k.attempts, 0) / totalAttempts)
      : null
  const recentPct =
    totalAttempts > 0
      ? Math.round(
          kindList.reduce((s, [, k]) => s + k.recent_pct * k.attempts, 0) / totalAttempts,
        )
      : null
  const deltaPct = avgPct !== null && recentPct !== null ? recentPct - avgPct : null

  /* «По заданиям»: recent_pct по каждому типу, слабейший подсвечен розовым. */
  const KIND_ORDER = ['reading', 'dialogue', 'interview', 'monologue']
  const kindRows = KIND_ORDER.filter((k) => kinds[k]?.attempts > 0).map((k) => ({
    k,
    pct: kinds[k].recent_pct,
  }))
  const weakest = kindRows.length > 1 ? kindRows.reduce((a, b) => (b.pct < a.pct ? b : a)) : null

  const cats = analytics?.mistakes.by_cat ?? []

  return (
    <div className="statpage">
      <h1 className="dash__hello" style={{ marginBottom: 18 }}>
        Прогресс
      </h1>

      <div className="statpage__tiles">
        <div className="stattile">
          <span>XP за неделю</span>
          <b>{weekXp ?? '—'}</b>
          {stats && stats.streak.active_today && <i className="statchip statchip--good">сегодня зачтено</i>}
        </div>
        <div className="stattile">
          <span>Средний балл</span>
          <b>{avgPct !== null ? `${avgPct}%` : '—'}</b>
          {deltaPct !== null && deltaPct !== 0 && (
            <i className={`statchip ${deltaPct > 0 ? 'statchip--good' : 'statchip--bad'}`}>
              {deltaPct > 0 ? '+' : ''}
              {deltaPct}% последние работы
            </i>
          )}
        </div>
        <div className="stattile">
          <span>Заданий выполнено</span>
          <b>{stats ? stats.totals.tasks : '—'}</b>
          {stats && <i className="statchip statchip--lav">{stats.totals.replies} реплик в разговоре</i>}
        </div>
        <div className="stattile">
          <span>Лучшая серия</span>
          <b>{stats ? `${stats.streak.best} ${stats.streak.best === 1 ? 'день' : 'дней'}` : '—'}</b>
          {stats && <i className="statchip statchip--pink">сейчас {stats.streak.days} 🔥</i>}
        </div>
      </div>

      <div className="calcard statpage__chartcard">
        <div className="statpage__chart-head">
          <div>
            <p className="calcard__title">Успешность по заданиям</p>
            <div className="statpage__legend">
              {SERIES.map((s) => (
                <span key={s.label}>
                  <i style={{ background: s.color }} />
                  {s.label}
                </span>
              ))}
            </div>
          </div>
          <div className="calseg">
            {(['week', 'month', 'year'] as Range[]).map((r) => (
              <button
                key={r}
                type="button"
                className={range === r ? 'calseg--on' : ''}
                onClick={() => setRange(r)}
              >
                {r === 'week' ? 'Неделя' : r === 'month' ? 'Месяц' : 'Год'}
              </button>
            ))}
          </div>
        </div>
        {analytics ? (
          <AreaChart history={analytics.history} range={range} />
        ) : (
          <p className="statpage__empty">Загружаю…</p>
        )}
      </div>

      <div className="statpage__row">
        <div className="calcard">
          <p className="calcard__title" style={{ marginBottom: 12 }}>
            По заданиям
          </p>
          {kindRows.length === 0 && (
            <p className="statpage__empty">Появится после первых разборов — реши любое задание.</p>
          )}
          {kindRows.map(({ k, pct }, i) => (
            <div className="kindrow" key={k}>
              <span className="kindrow__name">
                {i + 1} · {KIND_RU[k] ?? k}
              </span>
              <span className="kindrow__bar">
                <i
                  style={{
                    width: `${pct}%`,
                    background: weakest && weakest.k === k ? '#F0537F' : '#B7A6F0',
                  }}
                />
              </span>
              <b className="kindrow__pct">{pct}%</b>
            </div>
          ))}
          {weakest && (
            <p className="statpage__note">
              {KIND_RU[weakest.k] ?? weakest.k} — твоя точка роста. Вариант на основе ошибок уже
              собран под неё.
            </p>
          )}
        </div>

        <div className="calcard">
          <p className="calcard__title" style={{ marginBottom: 12 }}>
            Частые ошибки
          </p>
          {cats.length === 0 && (
            <p className="statpage__empty">
              Пока пусто — ошибки появятся здесь после разборов и будут повторяться в заданиях.
            </p>
          )}
          {cats.slice(0, 4).map((c) => (
            <div className="mistrow" key={c.cat}>
              <div>
                <b>{CAT_RU[c.cat] ?? c.cat}</b>
                {c.example && (
                  <span>
                    «{c.example.quote}» → «{c.example.correction}»
                  </span>
                )}
              </div>
              <i className="mistrow__n">×{c.n}</i>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
