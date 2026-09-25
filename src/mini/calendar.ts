/**
 * Календарь занятий для мини-статистики: та же логика, что у настольного
 * `CalendarScreen` — активные дни из /me/stats.active_days, «мосты»
 * заморозки считаются как серверный стрик (один пропуск на ISO-неделю
 * внутри цепочки). Чистые функции, без DOM.
 */

export const WEEKDAYS = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС']
export const MONTHS = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
]

export function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function isoWeekKey(d: Date): string {
  const t = new Date(d)
  t.setDate(t.getDate() + 3 - ((t.getDay() + 6) % 7))
  const week1 = new Date(t.getFullYear(), 0, 4)
  const week =
    1 + Math.round(((t.getTime() - week1.getTime()) / 86400000 - 3 + ((week1.getDay() + 6) % 7)) / 7)
  return `${t.getFullYear()}-${week}`
}

/** Дни-«мосты»: пропуск ровно в один день между активными, если в этой
    ISO-неделе мост ещё не тратился — как в серверной логике стрика. */
export function bridgeDays(active: string[]): Set<string> {
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

export interface CalCell {
  n: number
  mark: 'did' | 'frz' | ''
  today: boolean
}

/** Сетка месяца: пустые ячейки до первого дня (понедельник — первый). */
export function monthCells(shown: Date, todayStr: string, active: Set<string>, bridges: Set<string>): CalCell[] {
  const daysInMonth = new Date(shown.getFullYear(), shown.getMonth() + 1, 0).getDate()
  const firstDow = (new Date(shown.getFullYear(), shown.getMonth(), 1).getDay() + 6) % 7
  const cells: CalCell[] = []
  for (let i = 0; i < firstDow; i++) cells.push({ n: 0, mark: '', today: false })
  for (let d = 1; d <= daysInMonth; d++) {
    const ds = isoDate(new Date(shown.getFullYear(), shown.getMonth(), d))
    cells.push({ n: d, mark: active.has(ds) ? 'did' : bridges.has(ds) ? 'frz' : '', today: ds === todayStr })
  }
  return cells
}
