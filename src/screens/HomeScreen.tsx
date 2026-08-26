/**
 * Главный экран нового дизайна — дашборд из утверждённого прототипа,
 * но с ЖИВЫМИ данными системы:
 *   - стрик и неделя — /me/stats (activity_days считает сервер);
 *   - персональный CTA — /me/analytics (реальные частые ошибки ученика);
 *   - правая колонка — три настоящих раздела: Тренажёр, Разговор, Демо.
 *
 * Чего в системе нет — того нет на экране: «лучшей серии» сервер не хранит,
 * поэтому в бэйдже у огня живёт уровень; «готовность к экзамену» никем не
 * считается — кольцо показывает прогресс уровня. Принцип честности данных
 * из StatsScreen: null от сервера — прочерки, а не выдуманные числа.
 */
import { useEffect, useRef, useState } from 'react'

import {
  fetchMeAnalytics,
  fetchMeStats,
  type MeAnalytics,
  type MeStats,
} from '../account/me'
import { currentUser } from '../auth/auth'

const CAT_RU: Record<string, string> = {
  gram: 'грамматика',
  lex: 'лексика',
  order: 'структура вопроса',
  missing: 'нет ответа',
  logic: 'логика',
  phon: 'произношение',
  other: 'прочее',
}

const WD_RU = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб']

function greeting(): string {
  const h = new Date().getHours()
  if (h < 5) return 'Доброй ночи'
  if (h < 12) return 'Доброе утро'
  if (h < 18) return 'Добрый день'
  return 'Добрый вечер'
}

/* Liquid glass огонь: цифра стрика ВНУТРИ SVG — при любом масштабе текст
   остаётся в теле пламени (урок итераций прототипа). */
function Flame({ days }: { days: number | null }) {
  return (
    <svg viewBox="0 0 150 170" aria-hidden="true">
      <defs>
        <linearGradient id="dashF" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#FFC178" />
          <stop offset=".5" stopColor="#FFA062" />
          <stop offset="1" stopColor="#FF8A5C" />
        </linearGradient>
        <linearGradient id="dashF2" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#FFF6E9" />
          <stop offset="1" stopColor="#FFD9AE" />
        </linearGradient>
        <filter id="dashBlur" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="6" />
        </filter>
      </defs>
      <path
        d="M75 8 C82 40 122 52 122 100 A47 47 0 0 1 28 100 C28 66 52 56 58 26 C64 40 72 42 75 8 Z"
        fill="url(#dashF)"
        stroke="rgba(255,255,255,.7)"
        strokeWidth="2"
      />
      <path
        d="M58 30 C48 52 38 64 38 96 A37 37 0 0 0 46 118 C38 94 50 68 62 50 Z"
        fill="#fff"
        opacity=".5"
        filter="url(#dashBlur)"
      />
      <path
        d="M75 50 C80 72 106 78 106 112 A31 31 0 0 1 44 112 C44 90 62 82 66 62 C70 72 73 70 75 50 Z"
        fill="url(#dashF2)"
      />
      <text
        x="75"
        y="112"
        textAnchor="middle"
        fontSize="34"
        fontWeight="800"
        fill="#121214"
        style={{ letterSpacing: '-1px' }}
      >
        {days ?? '—'}
      </text>
      <text x="75" y="130" textAnchor="middle" fontSize="10.5" fontWeight="600" fill="#77768A">
        {days === 1 ? 'день подряд' : 'дней подряд'}
      </text>
    </svg>
  )
}

/* 3D-иконки правой колонки — из прототипа. */
function ArtHeadphones() {
  return (
    <svg className="actioncard__art" viewBox="0 0 130 130" aria-hidden="true">
      <defs>
        <linearGradient id="dhpB" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#FFCBDD" />
          <stop offset="1" stopColor="#E9799F" />
        </linearGradient>
        <radialGradient id="dhpC" cx=".35" cy=".28" r="1.1">
          <stop offset="0" stopColor="#FFE4EE" />
          <stop offset=".5" stopColor="#F291B4" />
          <stop offset="1" stopColor="#D36A93" />
        </radialGradient>
        <filter id="dsoftb" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="5" />
        </filter>
      </defs>
      <ellipse cx="65" cy="112" rx="38" ry="8" fill="rgba(30,30,50,.13)" filter="url(#dsoftb)" />
      <path
        d="M25 78 v-6 a40 40 0 0 1 80 0 v6"
        fill="none"
        stroke="url(#dhpB)"
        strokeWidth="13"
        strokeLinecap="round"
      />
      <rect x="16" y="72" width="26" height="38" rx="12" fill="url(#dhpC)" />
      <rect x="88" y="72" width="26" height="38" rx="12" fill="url(#dhpC)" />
      <ellipse cx="24.5" cy="82" rx="6" ry="9" fill="#FFEBF1" opacity=".8" />
      <ellipse cx="96.5" cy="82" rx="6" ry="9" fill="#FFEBF1" opacity=".8" />
    </svg>
  )
}

function ArtMic() {
  return (
    <svg className="actioncard__art" viewBox="0 0 130 130" aria-hidden="true">
      <defs>
        <radialGradient id="dmcB" cx=".35" cy=".25" r="1.15">
          <stop offset="0" stopColor="#EAE2FE" />
          <stop offset=".5" stopColor="#A78FE8" />
          <stop offset="1" stopColor="#7E62CF" />
        </radialGradient>
        <linearGradient id="dmcS" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#CCBDF3" />
          <stop offset="1" stopColor="#9F8ADF" />
        </linearGradient>
      </defs>
      <ellipse cx="65" cy="114" rx="34" ry="7" fill="rgba(30,30,50,.13)" filter="url(#dsoftb)" />
      <rect x="44" y="14" width="42" height="64" rx="21" fill="url(#dmcB)" />
      <ellipse cx="56" cy="30" rx="7" ry="12" fill="#F2EDFE" opacity=".85" />
      <path
        d="M50 36h30M50 46h30M50 56h30"
        stroke="#7A63C4"
        strokeWidth="2.6"
        strokeLinecap="round"
        opacity=".5"
      />
      <path
        d="M32 62 v6 a33 33 0 0 0 66 0 v-6"
        fill="none"
        stroke="url(#dmcS)"
        strokeWidth="9"
        strokeLinecap="round"
      />
      <rect x="61" y="99" width="8" height="12" rx="4" fill="url(#dmcS)" />
      <rect x="46" y="108" width="38" height="8" rx="4" fill="url(#dmcS)" />
    </svg>
  )
}

function ArtPlay() {
  return (
    <svg className="actioncard__art" viewBox="0 0 130 130" aria-hidden="true">
      <defs>
        <radialGradient id="dplB" cx=".32" cy=".25" r="1.15">
          <stop offset="0" stopColor="#FFDDE7" />
          <stop offset=".55" stopColor="#F2A2BB" />
          <stop offset="1" stopColor="#DE7C9E" />
        </radialGradient>
      </defs>
      <ellipse cx="65" cy="112" rx="36" ry="8" fill="rgba(30,30,50,.13)" filter="url(#dsoftb)" />
      <rect x="22" y="18" width="86" height="86" rx="26" fill="url(#dplB)" transform="rotate(-6 65 61)" />
      <ellipse cx="43" cy="38" rx="12" ry="18" fill="#FFF0F4" opacity=".75" transform="rotate(-6 65 61)" />
      <path d="M56 44 84 61 56 78 Z" fill="#fff" transform="rotate(-6 65 61)" />
    </svg>
  )
}

const Arrow = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" aria-hidden="true">
    <path d="M4 12h15M13 5.5 19.5 12 13 18.5" />
  </svg>
)

/* График недели: бары XP по дням из /me/stats. Одна серия — легенда не нужна.
   Потолок оси — круглое число из четырёх делений (урок прототипа). */
function WeekChart({ week }: { week: MeStats['week'] }) {
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const ttRef = useRef<HTMLDivElement | null>(null)
  const [hover, setHover] = useState<number | null>(null)

  const vals = week.map((d) => d.xp)
  const rawMax = Math.max(...vals, 1)
  const steps = [5, 10, 15, 20, 25, 50, 75, 100, 150, 200, 250, 500]
  const step = steps.find((s) => s * 4 >= rawMax) ?? Math.ceil(rawMax / 4)
  const max = step * 4

  const W = 640
  const H = 210
  const padL = 40
  const padR = 14
  const padT = 12
  const padB = 26
  const slot = (W - padL - padR) / week.length
  const bw = Math.min(34, slot * 0.5)

  const move = (e: React.MouseEvent, i: number) => {
    setHover(i)
    const tt = ttRef.current
    if (!tt) return
    const d = week[i]
    const wd = WD_RU[new Date(d.day + 'T00:00:00').getDay()]
    tt.innerHTML = `<div class="d">${wd} · ${d.day.slice(8)}.${d.day.slice(5, 7)}</div><b>${d.xp} XP</b><div>${d.actions} действий</div>`
    tt.style.display = 'block'
    tt.style.left = Math.min(e.clientX + 14, window.innerWidth - 130) + 'px'
    tt.style.top = e.clientY - 64 + 'px'
  }
  const leave = () => {
    setHover(null)
    if (ttRef.current) ttRef.current.style.display = 'none'
  }

  return (
    <div className="dash__chartwrap" ref={wrapRef}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Опыт по дням недели">
        {[0, 1, 2, 3, 4].map((g) => {
          const y = padT + ((H - padB - padT) * g) / 4
          return (
            <g key={g}>
              <line x1={padL} y1={y} x2={W - padR} y2={y} stroke="var(--line)" strokeWidth="1" />
              <text x={padL - 8} y={y + 4} textAnchor="end" fontSize="11" fill="var(--card-ink-dim)" fontWeight="600">
                {Math.round(max * (1 - g / 4))}
              </text>
            </g>
          )
        })}
        {week.map((d, i) => {
          const x = padL + slot * i + (slot - bw) / 2
          const h = ((H - padB - padT) * d.xp) / max
          const y = H - padB - h
          const wd = WD_RU[new Date(d.day + 'T00:00:00').getDay()]
          return (
            <g key={d.day} onMouseMove={(e) => move(e, i)} onMouseLeave={leave} style={{ cursor: 'pointer' }}>
              <rect
                x={x}
                y={y}
                width={bw}
                height={Math.max(h, d.xp > 0 ? 3 : 0)}
                rx="6"
                fill="#D9D0F3"
                opacity={hover === null || hover === i ? 1 : 0.4}
              />
              <rect x={x - 8} y={padT} width={bw + 16} height={H - padB - padT} fill="transparent" />
              <text x={x + bw / 2} y={H - 8} textAnchor="middle" fontSize="12" fill="var(--card-ink-dim)" fontWeight="600">
                {wd}
              </text>
            </g>
          )
        })}
      </svg>
      <div className="dashtt" ref={ttRef} />
    </div>
  )
}

export function HomeScreen({
  onTrainer,
  onSpeaking,
  onDemo,
}: {
  onTrainer: () => void
  onSpeaking: () => void
  onDemo: () => void
}) {
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

  const nick = currentUser()?.nickname ?? ''
  const weekActions = stats ? stats.week.reduce((s, d) => s + d.actions, 0) : null
  const level = stats?.level ?? null
  const levelPct = level ? Math.round(level.progress * 100) : null

  const cats = analytics?.mistakes.by_cat ?? []
  const ctaTitle =
    cats.length > 0 ? 'Собери тренировку по своим ошибкам' : 'Начни первую тренировку'
  const ctaSub =
    cats.length > 0
      ? cats
          .slice(0, 2)
          .map((c) => `${CAT_RU[c.cat] ?? c.cat} — ${c.n}`)
          .join(', ') + ' за последние разборы'
      : 'Разбор покажет, что подтянуть — дальше система будет помнить твои ошибки'

  const ringDash = 2 * Math.PI * 21
  const ringOff = level ? ringDash * (1 - Math.min(1, level.progress)) : ringDash

  return (
    <div className="dash">
      <div className="dash__greet">
        <div>
          <h1 className="dash__hello">
            {greeting()}, {nick}! 👋
          </h1>
          <p className="dash__sub">Готовься к устной части ЕГЭ и говори уверенно.</p>
        </div>
      </div>

      <div className="dash__streak">
        <div className="flamebig">
          <Flame days={stats ? stats.streak.days : null} />
          <span className="streakbadge">
            <span className="sp">✨</span>
            <span>
              Лучшая серия
              <b>
                {stats
                  ? `${stats.streak.best} ${stats.streak.best === 1 ? 'день' : 'дней'}`
                  : '—'}
              </b>
            </span>
          </span>
        </div>

        <div className="bigstat">
          <span className="bigstat__slot">
            <span className="bigstat__ic">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round">
                <rect x="9" y="2.5" width="6" height="12" rx="3" />
                <path d="M5 11a7 7 0 0 0 14 0M12 18v3.5" />
              </svg>
            </span>
          </span>
          <b>{weekActions ?? '—'}</b>
          <span className="bigstat__l1">действий</span>
          <span className="bigstat__l2">за неделю</span>
        </div>

        <div className="bigstat">
          <span className="bigstat__slot">
            <span className="bigstat__ic">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round">
                <circle cx="12" cy="12" r="9" />
                <path d="m8.5 12.5 2.5 2.5 5-5.5" />
              </svg>
            </span>
          </span>
          <b>{stats ? stats.totals.tasks : '—'}</b>
          <span className="bigstat__l1">заданий</span>
          <span className="bigstat__l2">выполнено</span>
        </div>

        <div className="bigstat">
          <span className="bigstat__slot">
            <span className="readyring">
              <svg width="52" height="52" viewBox="0 0 52 52">
                <circle cx="26" cy="26" r="21" fill="none" stroke="#EFEAFF" strokeWidth="6" />
                <circle
                  cx="26"
                  cy="26"
                  r="21"
                  fill="none"
                  stroke="#8C73FF"
                  strokeWidth="6"
                  strokeLinecap="round"
                  strokeDasharray={ringDash}
                  strokeDashoffset={ringOff}
                />
              </svg>
              <b>{levelPct !== null ? `${levelPct}%` : '—'}</b>
            </span>
          </span>
          <b style={{ fontSize: 'clamp(16px, 1.6vw, 22px)' }}>{level ? level.name : '—'}</b>
          <span className="bigstat__l1">уровень {level ? level.level : '—'}</span>
          <span className="bigstat__l2">до следующего {levelPct !== null ? `${100 - levelPct}%` : '—'}</span>
        </div>
      </div>

      <div className="dash__cta">
        <span className="sparkle">✨</span>
        <div className="dash__cta-t">
          <b>{ctaTitle}</b>
          <span>{ctaSub}</span>
        </div>
        <button type="button" className="dash__ctabtn" onClick={onTrainer}>
          Открыть <Arrow />
        </button>
      </div>

      <div className="dash__chart">
        <p className="dash__chart-title">Твоя неделя</p>
        <p className="dash__chart-sub">опыт за занятия по дням · наведись на столбик</p>
        {stats ? (
          <WeekChart week={stats.week} />
        ) : (
          <p className="dash__chart-sub" style={{ marginTop: 24 }}>
            Статистика появится после первого занятия — сервер считает дни сам.
          </p>
        )}
      </div>

      <div className="dash__side">
        <button type="button" className="actioncard" onClick={onTrainer}>
          <span className="actioncard__dot" />
          <h3>ТРЕНАЖЁР</h3>
          <p>Все 4 задания устной части ЕГЭ</p>
          <span className="actioncard__go">
            Начать <Arrow />
          </span>
          <ArtHeadphones />
        </button>
        <button type="button" className="actioncard actioncard--lav" onClick={onSpeaking}>
          <span className="actioncard__dot" />
          <h3>SPEAKING</h3>
          <p>Свободный разговор с AI-собеседником</p>
          <span className="actioncard__go">
            Практиковаться <Arrow />
          </span>
          <ArtMic />
        </button>
        <button type="button" className="actioncard actioncard--blush" onClick={onDemo}>
          <span className="actioncard__dot" />
          <h3>DEMO</h3>
          <p>Полный экзамен в формате ЕГЭ</p>
          <span className="actioncard__go">
            Попробовать <Arrow />
          </span>
          <ArtPlay />
        </button>
      </div>
    </div>
  )
}
