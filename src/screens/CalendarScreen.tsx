/**
 * Календарь занятий — экран из утверждённого прототипа (фото-канон владельца).
 *
 * Данные живые: /me/stats.active_days — даты с занятиями за последние два
 * месяца (сервер считает их из activity_days). Огонёк — день с занятием,
 * снежинка — пропуск-«мост», который спасла заморозка (вычисляется той же
 * логикой, что серверный стрик: один пропуск на ISO-неделю внутри цепочки).
 * Блок «Напоминание» из прототипа не переносим: механизма напоминаний в
 * системе нет, а мёртвая кнопка хуже отсутствующей.
 */
import { useEffect, useState } from 'react'

import { fetchMeStats, type MeStats } from '../account/me'

const WD = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС']
const MONTHS = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
]

function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function isoWeekKey(d: Date): string {
  // ISO-неделя: та же, которой сервер считает заморозку.
  const t = new Date(d)
  t.setDate(t.getDate() + 3 - ((t.getDay() + 6) % 7))
  const week1 = new Date(t.getFullYear(), 0, 4)
  const week =
    1 + Math.round(((t.getTime() - week1.getTime()) / 86400000 - 3 + ((week1.getDay() + 6) % 7)) / 7)
  return `${t.getFullYear()}-${week}`
}

/** Дни-«мосты»: пропуск ровно в один день между активными, если в этой
    ISO-неделе мост ещё не тратился, — как в серверной логике стрика. */
function bridgeDays(active: string[]): Set<string> {
  const bridges = new Set<string>()
  const usedWeeks = new Set<string>()
  const sorted = [...active].sort()
  for (let i = 1; i < sorted.length; i++) {
    const prev = new Date(sorted[i - 1] + 'T12:00:00')
    const cur = new Date(sorted[i] + 'T12:00:00')
    const gap = Math.round((cur.getTime() - prev.getTime()) / 86400000)
    if (gap === 2) {
      const mid = new Date(prev)
      mid.setDate(mid.getDate() + 1)
      const wk = isoWeekKey(mid)
      if (!usedWeeks.has(wk)) {
        usedWeeks.add(wk)
        bridges.add(isoDate(mid))
      }
    }
  }
  return bridges
}

export function CalendarScreen() {
  const [stats, setStats] = useState<MeStats | null>(null)
  const [shift, setShift] = useState(0) // 0 = текущий месяц, -1 = прошлый

  useEffect(() => {
    let alive = true
    void fetchMeStats().then((s) => alive && setStats(s))
    return () => {
      alive = false
    }
  }, [])

  const todayStr = stats?.today ?? isoDate(new Date())
  const today = new Date(todayStr + 'T12:00:00')
  const shown = new Date(today.getFullYear(), today.getMonth() + shift, 1)
  const active = new Set(stats?.active_days ?? [])
  const bridges = stats ? bridgeDays(stats.active_days) : new Set<string>()

  const daysInMonth = new Date(shown.getFullYear(), shown.getMonth() + 1, 0).getDate()
  const firstDow = (new Date(shown.getFullYear(), shown.getMonth(), 1).getDay() + 6) % 7

  const weekDaysDone = stats
    ? stats.week.filter((d) => d.actions > 0).length
    : null

  const cells: Array<{ n: number; cls: string; mark: string }> = []
  for (let i = 0; i < firstDow; i++) cells.push({ n: 0, cls: 'cal__day cal__day--mute', mark: '' })
  for (let d = 1; d <= daysInMonth; d++) {
    const ds = isoDate(new Date(shown.getFullYear(), shown.getMonth(), d))
    let cls = 'cal__day'
    let mark = ''
    if (active.has(ds)) {
      cls += ' cal__day--did'
      mark = '🔥'
    } else if (bridges.has(ds)) {
      cls += ' cal__day--frz'
      mark = '❄'
    }
    if (ds === todayStr) cls += ' cal__day--today'
    cells.push({ n: d, cls, mark })
  }

  return (
    <div className="calpage">
      <h1 className="dash__hello" style={{ marginBottom: 10 }}>
        Календарь занятий
      </h1>
      <div className="calpage__grid">
        <div className="calcard">
          <div className="calcard__head">
            <p className="calcard__title">
              {MONTHS[shown.getMonth()]} {shown.getFullYear()}
            </p>
            <div className="calseg">
              <button type="button" onClick={() => setShift((s) => Math.max(-1, s - 1))} aria-label="Предыдущий месяц" disabled={shift <= -1}>
                ←
              </button>
              <button type="button" className={shift === 0 ? 'calseg--on' : ''} onClick={() => setShift(0)}>
                Сегодня
              </button>
              <button type="button" onClick={() => setShift((s) => Math.min(0, s + 1))} aria-label="Следующий месяц" disabled={shift >= 0}>
                →
              </button>
            </div>
          </div>
          <div className="cal">
            {WD.map((w) => (
              <div key={w} className="cal__wd">
                {w}
              </div>
            ))}
            {cells.map((c, i) => (
              <div key={i} className={c.cls}>
                {c.n > 0 && <span>{c.n}</span>}
                {c.mark && <i className="cal__mark">{c.mark}</i>}
              </div>
            ))}
          </div>
          <p className="calcard__legend">
            🔥 день с занятием · ❄ заморозка спасла серию · обводка — сегодня
          </p>
        </div>

        <div className="calside">
          <div className="calcard">
            <p className="calside__eyebrow">Эта неделя</p>
            <div className="calside__row">
              <span className="calside__ic calside__ic--fire">🔥</span>
              <div>
                <b>Стрик {stats ? stats.streak.days : '—'} {stats && stats.streak.days === 1 ? 'день' : 'дней'}</b>
                <span>лучшая серия — {stats ? stats.streak.best : '—'}</span>
              </div>
            </div>
            <div className="calside__row">
              <span className="calside__ic calside__ic--frz">❄</span>
              <div>
                <b>{stats?.streak.freeze_available ? 'Заморозка доступна' : 'Заморозка потрачена'}</b>
                <span>1 пропуск в неделю не рвёт серию</span>
              </div>
            </div>
            <div className="calside__row">
              <span className="calside__ic calside__ic--ok">✓</span>
              <div>
                <b>{weekDaysDone ?? '—'} {weekDaysDone === 1 ? 'день' : 'дней'} с занятиями</b>
                <span>на этой неделе</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
