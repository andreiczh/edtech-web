/**
 * Статистика — макет «statistics-settings-style-editable 1» (24.09.2026).
 * Три карточки: интенсивность (решённые задания по дням текущей недели),
 * серия занятий (дни недели с отметками) и средние баллы за задания.
 *
 * Данные — только то, что система реально меряет: /me/stats (серия,
 * активные дни) и /me/analytics (работы по дням, средний процент по типам).
 * Цифры макета (25…70, 12 дней, 10/10) — заглушки дизайнера, на экране их
 * нет: пока данных нет, стоят прочерки.
 */
import { useEffect, useMemo, useState } from 'react'

import { fetchMeAnalytics, fetchMeStats, type MeAnalytics, type MeStats } from '../account/me'
import { TASKS, TASK_ORDER } from '../ege2/tasks'
import { Icon } from './Ambient'
import { ICONS } from './icons'
import { taskNo } from './Practice'

const DAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
const u = (v: number) => `calc(${v} * var(--u))`

/* Геометрия графика из макета (пункты): центры семи колонок, верх и низ
   шкалы. Шкала в макете — по размаху данных: минимум недели лежит внизу,
   максимум — вверху. */
const COL_X = [45.9, 96.75, 147.6, 198.4, 249.25, 300.05, 350.9]
const CHART_TOP = 143.6
const Y_MAX = 226.4 - CHART_TOP
const Y_MIN = 290.6 - CHART_TOP

const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/** Понедельник–воскресенье текущей недели по местному времени. */
export function weekDates(now = new Date()): string[] {
  const start = new Date(now)
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7))
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    return iso(d)
  })
}

const plural = (n: number, one: string, few: string, many: string) => {
  const d = n % 10
  const dd = n % 100
  if (d === 1 && dd !== 11) return one
  if (d >= 2 && d <= 4 && (dd < 10 || dd >= 20)) return few
  return many
}

/** «4/4», «3,2/4» или «—/4»: средний балл по типу из среднего процента. */
function avgLabel(analytics: MeAnalytics | null, kind: string, max: number): string {
  const k = analytics?.kinds?.[kind]
  if (!k || !k.attempts) return `—/${max}`
  const v = (k.avg_pct / 100) * max
  const s = Math.abs(v - Math.round(v)) < 0.05 ? String(Math.round(v)) : v.toFixed(1).replace('.', ',')
  return `${s}/${max}`
}

export function MiniStats() {
  const [stats, setStats] = useState<MeStats | null>(null)
  const [analytics, setAnalytics] = useState<MeAnalytics | null>(null)
  useEffect(() => {
    let alive = true
    void fetchMeStats().then((s) => alive && setStats(s))
    void fetchMeAnalytics().then((a) => alive && setAnalytics(a))
    return () => {
      alive = false
    }
  }, [])

  const week = useMemo(() => weekDates(), [])
  const today = iso(new Date())
  const counts = useMemo(() => {
    const byDay = new Map<string, number>()
    for (const h of analytics?.history ?? []) byDay.set(h.d, (byDay.get(h.d) ?? 0) + 1)
    return week.map((d) => byDay.get(d) ?? 0)
  }, [analytics, week])
  const solvedToday = analytics ? counts[week.indexOf(today)] ?? 0 : null

  const lo = Math.min(...counts)
  const hi = Math.max(...counts)
  const yOf = (v: number) => (hi === lo ? (Y_MAX + Y_MIN) / 2 : Y_MIN - ((v - lo) / (hi - lo)) * (Y_MIN - Y_MAX))
  const points = counts.map((v, i) => [COL_X[i], yOf(v)] as const)

  const active = new Set(stats?.active_days ?? [])
  const streak = stats?.streak.days ?? null

  return (
    <div className="s-page">
      <div className="s-glow s-glow--top" aria-hidden="true" />
      <div className="s-glow s-glow--bottom" aria-hidden="true" />
      <h1 className="s-h1">Статистика</h1>
      <div className="s-ava" role="img" aria-label="Аватар" />

      {/* --------------------------------------------- интенсивность */}
      <section className="s-card s-card--1" aria-label="Интенсивность обучения">
        <h2 className="s-title" style={{ left: u(38.3 - 20), top: u(157.9 - CHART_TOP) }}>
          Интенсивность обучения
        </h2>
        <p className="s-sub" style={{ left: u(39.1 - 20), top: u(182.0 - CHART_TOP) }}>
          Решено сегодня: {solvedToday === null ? '—' : solvedToday}
        </p>
        <svg
          className="s-chart"
          viewBox="0 0 402 216"
          style={{ left: u(-20), top: 0, width: u(402), height: u(216) }}
          aria-hidden="true"
        >
          {COL_X.map((x) => (
            <line key={x} x1={x} y1={83} x2={x} y2={161} stroke="#E5E6EA" strokeWidth="1" strokeDasharray="3 3" />
          ))}
          {analytics && (
            <>
              <polyline
                points={points.map(([x, y]) => `${x},${y}`).join(' ')}
                fill="none"
                stroke="#6D68E8"
                strokeWidth="2.4"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
              {points.map(([x, y], i) => (
                <g key={i}>
                  <circle cx={x} cy={y} r="4.3" fill="#6D68E8" />
                  <text x={x} y={y - 10.2} textAnchor="middle" className="s-chart__v">
                    {counts[i]}
                  </text>
                </g>
              ))}
            </>
          )}
          {DAYS.map((d, i) => (
            <text key={d} x={COL_X[i]} y={324.6 + 8.2 - CHART_TOP} textAnchor="middle" className="s-chart__d">
              {d}
            </text>
          ))}
        </svg>
      </section>

      {/* ------------------------------------------------ серия занятий */}
      <section className="s-card s-card--2" aria-label="Серия занятий">
        <h2 className="s-title" style={{ left: u(38.8 - 20), top: u(398.4 - 382.1) }}>
          Серия занятий
        </h2>
        <img className="s-flame" src="/mini/flame-stats.png" alt="" />
        <span className="s-streak">
          {streak === null ? '—' : `${streak} ${plural(streak, 'день', 'дня', 'дней')}`}
        </span>
        <div className="s-days">
          {week.map((d, i) => {
            const done = active.has(d)
            return (
              <div key={d} className="s-day" aria-label={`${DAYS[i]}: ${done ? 'занятие было' : 'без занятия'}`}>
                <span className="s-day__l">{DAYS[i]}</span>
                {done ? (
                  <span className="s-day__ok">
                    <Icon icon={ICONS.check} />
                  </span>
                ) : (
                  <span className="s-day__no" />
                )}
              </div>
            )
          })}
        </div>
      </section>

      {/* ------------------------------------------- средние баллы */}
      <section className="s-card s-card--3" aria-label="Средние баллы за задания">
        <h2 className="s-title" style={{ left: u(38.9 - 20.8), top: u(550.0 - 533.1) }}>
          Средние баллы за задания
        </h2>
        {TASK_ORDER.map((id, i) => (
          <div key={id} className="s-row" style={{ top: u(581.7 - 533.1 + i * 49.2) }}>
            <span className="s-row__l">Задание {taskNo(id)}</span>
            <span className="s-row__v">{avgLabel(analytics, TASKS[id].kind, TASKS[id].maxScore)}</span>
          </div>
        ))}
      </section>
    </div>
  )
}
