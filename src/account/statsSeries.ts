import type { MeAnalytics } from './me'

/* Серии графика — как на макете: чтение / вопросы и интервью / голосовое. */
export const SERIES: Array<{ label: string; kinds: string[]; color: string }> = [
  { label: 'Чтение', kinds: ['reading'], color: '#B7A6F0' },
  { label: 'Вопросы и интервью', kinds: ['dialogue', 'interview'], color: '#F0537F' },
  { label: 'Голосовое сообщение', kinds: ['monologue'], color: '#2C97E0' },
]

export type Range = 'week' | 'month' | 'year'

/** Агрегация истории по корзинам периода: среднее по работам серии в корзине.
    Возвращает подписи корзин и по значению (или null) на серию. */
export function aggregate(history: MeAnalytics['history'], range: Range, today: string) {
  // Use the server's calendar day; ISO conversion of local midnight shifts
  // the first of a month backwards in UTC+ timezones.
  const now = new Date(today + 'T12:00:00Z')
  const buckets: Array<{ label: string; from: string; to: string }> = []
  if (range === 'week' || range === 'month') {
    const days = range === 'week' ? 7 : 30
    for (let i = days - 1; i >= 0; i--) {
      const d = new Date(now)
      d.setUTCDate(d.getUTCDate() - i)
      const iso = d.toISOString().slice(0, 10)
      const label = range === 'week' ? ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'][d.getUTCDay()] : `${d.getUTCDate()}.${d.getUTCMonth()+1}`
      buckets.push({ label, from: iso, to: iso })
    }
  } else {
    for (let i = 11; i >= 0; i--) {
      const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - i, 1, 12))
      const from = d.toISOString().slice(0, 7)
      buckets.push({label: ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'][d.getUTCMonth()], from, to:from})
    }
  }
  const series = SERIES.map((s) => ({
    ...s,
    points: buckets.map((b) => {
      const inBucket = history.filter((h) => {
        const key = range === 'year' ? h.d.slice(0, 7) : h.d
        return key >= b.from && key <= b.to && s.kinds.includes(h.k)
      })
      if (inBucket.length === 0) return null
      return Math.round(inBucket.reduce((sum, h) => sum + h.p, 0) / inBucket.length)
    }),
  }))
  return { labels: buckets.map((b) => b.label), series }
}

