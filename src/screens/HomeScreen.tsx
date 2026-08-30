/**
 * Главный экран — по референсу владельца от 31.08.2026.
 *
 * Слева: ТЕОРИЯ (заглушка — раздела в системе нет), «Вариант по ошибкам»
 * (живой: собирается из копилки ошибок), лента «Сегодня» из четырёх мини-
 * карточек. Справа: ТРЕНАЖЁР / SPEAKING / DEMO. Сверху: мини-стрик и
 * профиль-пилюля. Снизу: Telegram-баннер (заглушка — канала пока нет).
 *
 * Принцип честности прежний: живые числа — из /me/stats и /me/analytics,
 * чего система не меряет — того на экране нет; у заглушек прямо написано,
 * чего не хватает. «Совет дня» — ротация написанного руками банка советов
 * по дате: это контент, а не выдуманные данные.
 */
import { useEffect, useState } from 'react'

import { fetchMeAnalytics, fetchMeStats, type MeAnalytics, type MeStats } from '../account/me'
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

const KIND_RU: Record<string, string> = {
  reading: 'чтение вслух',
  dialogue: 'вопросы (№40)',
  interview: 'интервью (№41)',
  monologue: 'монолог (№42)',
}

/* Советы дня — написанный руками банк, ротация по дате. Именно банк, а не
   вызов LLM: совет не стоит запроса из месячного бюджета, а ротация даёт
   «новое каждый день» без единого обращения к сети. */
const TIPS = [
  'Не бойся пауз — они нормальны и в разговоре, и на экзамене.',
  'Отвечай на вопрос, который задали, а не на тот, что готовил.',
  'Две короткие фразы лучше одной длинной и запутанной.',
  'В монологе называй, ЧТО на фото, а не что ты об этом думаешь — мнение только в конце.',
  'Стяжения (I’m, don’t, it’s) делают речь живее — используй их.',
  'Начни ответ с обращения к другу — за его отсутствие снимают балл.',
  'Следи за формой глагола в задании: «you prefer» — отвечай «I prefer».',
  'Проговаривай окончания -s и -ed: их потеря — самая частая ошибка.',
  'Лучше простое слово к месту, чем сложное наугад.',
  'Заверши монолог выводом — «That’s all» тоже считается.',
  'Перечитай план задания за 10 секунд до записи — пункты легко потерять.',
  'Говори в среднем темпе: торопливость съедает окончания слов.',
  'Один день пропуска в неделю не рвёт серию — заморозка спасёт.',
  'Отвечай полными предложениями: обрывок фразой не считается.',
]

function dayTip(): string {
  const now = new Date()
  const day = Math.floor(now.getTime() / 86400000)
  return TIPS[day % TIPS.length]
}

function greeting(): string {
  const h = new Date().getHours()
  if (h < 5) return 'Доброй ночи'
  if (h < 12) return 'Доброе утро'
  if (h < 18) return 'Добрый день'
  return 'Добрый вечер'
}

/* ------------------------------------------------- Иконки (line, 24px) */

function Ic({ d, boxes }: { d?: string; boxes?: Array<[number, number, number, number, number?]> }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {d && <path d={d} />}
      {boxes?.map(([x, y, w, h, r], i) => (
        <rect key={i} x={x} y={y} width={w} height={h} rx={r ?? 2} />
      ))}
    </svg>
  )
}

const IC = {
  book: 'M4 19.5A2.5 2.5 0 0 1 6.5 17H20M4 19.5A2.5 2.5 0 0 0 6.5 22H20V2H6.5A2.5 2.5 0 0 0 4 4.5v15Z',
  sparkles: 'M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9L12 3ZM19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9L19 15Z',
  bulb: 'M9 18h6M10 21h4M12 3a6 6 0 0 1 3.6 10.8c-.5.4-.6 1-.6 1.7V16h-6v-.5c0-.7-.1-1.3-.6-1.7A6 6 0 0 1 12 3Z',
  chart: 'M4 20V4M4 17c4-1.5 5.5 1 9-1s6-7 7-8M20 20H4',
  target: 'M12 12m-9 0a9 9 0 1 0 18 0 9 9 0 1 0-18 0M12 12m-5 0a5 5 0 1 0 10 0 5 5 0 1 0-10 0M12 12m-1 0a1 1 0 1 0 2 0 1 1 0 1 0-2 0',
  trophy: 'M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4ZM7 6H4a3 3 0 0 0 3 4M17 6h3a3 3 0 0 1-3 4',
  headphones: 'M4 14v-2a8 8 0 0 1 16 0v2M4 14a2 2 0 0 1 2-2h1v6H6a2 2 0 0 1-2-2v-2Zm16 0a2 2 0 0 0-2-2h-1v6h1a2 2 0 0 0 2-2v-2Z',
  mic: 'M12 2a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3ZM6 11a6 6 0 0 0 12 0M12 17v4M9 21h6',
  play: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM10 8.5l5.5 3.5-5.5 3.5v-7Z',
  send: 'M21.5 3.5 10 12M21.5 3.5 14 21l-4-9-9-4 20.5-4.5Z',
}

/* ------------------------------------------------------------- Экран */

export function HomeScreen({
  onTrainer,
  onSpeaking,
  onDemo,
  onStats,
  onCalendar,
  onProfile,
}: {
  onTrainer: () => void
  onSpeaking: () => void
  onDemo: () => void
  onStats: () => void
  onCalendar: () => void
  onProfile: () => void
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
  const initials = (nick.match(/[A-Z]/g) ?? ['?']).slice(0, 1).join('')

  /* «Вариант по ошибкам»: подпись из настоящей копилки. */
  const cats = analytics?.mistakes.by_cat ?? []
  const recoSub =
    cats.length > 0
      ? 'Частое у тебя: ' + cats.slice(0, 2).map((c) => CAT_RU[c.cat] ?? c.cat).join(', ')
      : 'Появится после первых разборов — система запомнит твои ошибки'

  /* «Твой прогресс»: последние работы против среднего — из /me/analytics. */
  const kinds = analytics?.kinds ?? {}
  const kindList = Object.entries(kinds)
  const attempts = kindList.reduce((s, [, k]) => s + k.attempts, 0)
  const delta =
    attempts > 0
      ? Math.round(
          kindList.reduce((s, [, k]) => s + (k.recent_pct - k.avg_pct) * k.attempts, 0) / attempts,
        )
      : null

  /* «Фокус недели»: слабейший тип задания по последним работам. */
  const rows = Object.entries(kinds).filter(([, k]) => k.attempts > 0)
  const weakest =
    rows.length > 1
      ? rows.reduce((a, b) => (b[1].recent_pct < a[1].recent_pct ? b : a))[0]
      : null

  const streakDays = stats?.streak.days ?? null

  return (
    <div className="dash2">
      <div className="dash2__top">
        <h1 className="dash__hello">
          {greeting()}, {nick}! <span aria-hidden="true">👋</span>
        </h1>
        <div className="dash2__topright">
          <button
            type="button"
            className="streakpill"
            onClick={onCalendar}
            title="Серия занятий — открыть календарь"
          >
            <span aria-hidden="true">🔥</span>
            <b>{streakDays ?? '—'}</b>
          </button>
          <button type="button" className="userpill" onClick={onProfile} title="Личный кабинет">
            <span className="userpill__ava">{initials}</span>
            <span className="userpill__nick">{nick}</span>
            <span aria-hidden="true" className="userpill__chev">▾</span>
          </button>
        </div>
      </div>

      <div className="dash2__left">
        {/* ТЕОРИЯ — заглушка: раздела теории в системе пока НЕТ. Карточка
            стоит по референсу, а вместо обещаний — честное «скоро». */}
        <div className="promo promo--cream">
          <div className="promo__body">
            <span className="promo__eyebrow">Теория</span>
            <b className="promo__title">Повтори теорию по заданиям</b>
            <span className="promo__sub">
              Раздела пока нет — конспекты по заданиям 40–42 в работе
            </span>
            <button type="button" className="promo__btn" disabled title="Раздел теории ещё не готов">
              Скоро…
            </button>
          </div>
          <span className="promo__chip promo__chip--amber">
            <Ic d={IC.book} />
          </span>
        </div>

        {/* Вариант по ошибкам — живой: подпись из копилки, кнопка в тренажёр. */}
        <div className="promo promo--pink">
          <div className="promo__body">
            <span className="promo__eyebrow">
              <span aria-hidden="true">✨</span> AI рекомендация
            </span>
            <b className="promo__title">Вариант по ошибкам</b>
            <span className="promo__sub">{recoSub}</span>
            <button type="button" className="promo__btn" onClick={onTrainer}>
              Начать тренировку <span aria-hidden="true">→</span>
            </button>
          </div>
          <span className="promo__chip promo__chip--pink">
            <Ic d={IC.sparkles} />
          </span>
        </div>

        {/* Сегодня: четыре мини-карточки. Стрелки листают ленту на узких
            экранах; на широком видны все четыре. */}
        <div className="today">
          <div className="today__head">
            <b>Сегодня в Pingo</b>
            <div className="today__nav">
              <button
                type="button"
                aria-label="Назад"
                onClick={(e) => {
                  const row = e.currentTarget.closest('.today')?.querySelector('.today__row')
                  row?.scrollBy({ left: -180, behavior: 'smooth' })
                }}
              >
                ←
              </button>
              <button
                type="button"
                aria-label="Вперёд"
                onClick={(e) => {
                  const row = e.currentTarget.closest('.today')?.querySelector('.today__row')
                  row?.scrollBy({ left: 180, behavior: 'smooth' })
                }}
              >
                →
              </button>
            </div>
          </div>
          <div className="today__row">
            <div className="tcard tcard--lav">
              <span className="tcard__ic tcard__ic--lav"><Ic d={IC.bulb} /></span>
              <b>Совет дня</b>
              <span className="tcard__text">{dayTip()}</span>
            </div>
            <button type="button" className="tcard tcard--blue" onClick={onStats}>
              <span className="tcard__ic tcard__ic--blue"><Ic d={IC.chart} /></span>
              <b>Твой прогресс</b>
              <span className="tcard__text">
                {delta === null
                  ? 'Появится после первых занятий'
                  : delta > 0
                    ? `Последние работы на ${delta}% лучше твоего среднего`
                    : delta < 0
                      ? `Последние работы на ${-delta}% ниже среднего — бывает`
                      : 'Держишься ровно на своём среднем'}
              </span>
              <span className="tcard__go">Смотреть →</span>
            </button>
            <button type="button" className="tcard tcard--mint" onClick={onTrainer}>
              <span className="tcard__ic tcard__ic--mint"><Ic d={IC.target} /></span>
              <b>Фокус недели</b>
              <span className="tcard__text">
                {weakest
                  ? `${(KIND_RU[weakest] ?? weakest).replace(/^./, (c) => c.toUpperCase())} — твоя точка роста`
                  : 'Реши пару заданий — подскажем, что подтянуть'}
              </span>
              <span className="tcard__go">Тренировать →</span>
            </button>
            <button type="button" className="tcard tcard--peach" onClick={onCalendar}>
              <span className="tcard__ic tcard__ic--peach"><Ic d={IC.trophy} /></span>
              <b>Достижение</b>
              <span className="tcard__text">
                {streakDays && streakDays > 0
                  ? `${streakDays} ${streakDays === 1 ? 'день' : streakDays < 5 ? 'дня' : 'дней'} подряд! Так держать 🔥`
                  : 'Начни серию сегодня — одно занятие уже засчитается'}
              </span>
              <span className="tcard__go">Смотреть →</span>
            </button>
          </div>
        </div>
      </div>

      <div className="dash2__right">
        <div className="actioncard actioncard--pink">
          <h3>ТРЕНАЖЁР</h3>
          <p>Практикуй все 4 задания устной части ЕГЭ</p>
          <button type="button" className="actioncard__go" onClick={onTrainer}>
            Начать <span aria-hidden="true">→</span>
          </button>
          <span className="actioncard__chip actioncard__chip--pink">
            <Ic d={IC.headphones} />
          </span>
        </div>
        <div className="actioncard actioncard--lav">
          <h3>SPEAKING</h3>
          <p>Свободные разговоры с AI-собеседником</p>
          <button type="button" className="actioncard__go" onClick={onSpeaking}>
            Практиковаться <span aria-hidden="true">→</span>
          </button>
          <span className="actioncard__chip actioncard__chip--lav">
            <Ic d={IC.mic} />
          </span>
        </div>
        <div className="actioncard actioncard--rose">
          <h3>DEMO ВЕРСИЯ</h3>
          <p>Полный экзамен в формате ЕГЭ</p>
          <button type="button" className="actioncard__go" onClick={onDemo}>
            Начать <span aria-hidden="true">→</span>
          </button>
          <span className="actioncard__chip actioncard__chip--rose">
            <Ic d={IC.play} />
          </span>
        </div>
      </div>

      {/* Telegram — заглушка: канала пока НЕТ. Баннер по референсу, кнопка
          оживёт, когда владелец заведёт канал и укажет VITE_TELEGRAM_URL. */}
      <div className="tgbar">
        <span className="tgbar__ic" aria-hidden="true">
          <Ic d={IC.send} />
        </span>
        <div className="tgbar__t">
          <b>Присоединяйся к нашему Telegram-каналу</b>
          <span>
            {TG_URL
              ? 'Полезные материалы, разборы заданий и мотивация каждый день'
              : 'Канал скоро откроется — ссылки пока нет'}
          </span>
        </div>
        {TG_URL ? (
          <a className="tgbar__btn" href={TG_URL} target="_blank" rel="noreferrer">
            Перейти в канал <span aria-hidden="true">→</span>
          </a>
        ) : (
          <button type="button" className="tgbar__btn" disabled title="Канала пока нет">
            Скоро…
          </button>
        )}
      </div>
    </div>
  )
}

/* Ссылка на канал приходит из окружения сборки: канала пока нет, и кнопка
   честно выключена. Появится канал — одна переменная, без правки кода. */
const TG_URL = (import.meta.env.VITE_TELEGRAM_URL as string | undefined) ?? ''
