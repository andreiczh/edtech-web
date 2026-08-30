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

/* --------------------------------------------------- 3D-иконки карточек */

function ArtBooks() {
  return (
    <svg viewBox="0 0 96 96" fill="none" aria-hidden="true">
      <rect x="18" y="52" width="60" height="14" rx="4" fill="#F3D9A4" />
      <rect x="22" y="38" width="52" height="14" rx="4" fill="#F7E6C4" />
      <rect x="28" y="24" width="40" height="14" rx="4" fill="#FBF1DC" />
      <rect x="18" y="52" width="60" height="5" rx="2.5" fill="#E8C687" opacity="0.6" />
      <rect x="22" y="38" width="52" height="5" rx="2.5" fill="#EDD5A7" opacity="0.6" />
    </svg>
  )
}

function ArtChecklist() {
  return (
    <svg viewBox="0 0 96 96" fill="none" aria-hidden="true">
      <rect x="26" y="16" width="44" height="62" rx="8" fill="#F9C9DD" />
      <rect x="26" y="16" width="44" height="62" rx="8" fill="url(#chkg)" opacity="0.5" />
      <defs>
        <linearGradient id="chkg" x1="26" y1="16" x2="70" y2="78">
          <stop stopColor="#fff" stopOpacity="0.65" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect x="34" y="28" width="10" height="10" rx="3" fill="#E786AD" />
      <rect x="48" y="30" width="16" height="5" rx="2.5" fill="#E9A8C4" />
      <rect x="34" y="44" width="10" height="10" rx="3" fill="#E786AD" />
      <rect x="48" y="46" width="16" height="5" rx="2.5" fill="#E9A8C4" />
      <path d="M35.5 32.5l2.5 2.5 4-4.5" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
      <path d="M35.5 48.5l2.5 2.5 4-4.5" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

function ArtHeadphones() {
  return (
    <svg viewBox="0 0 96 96" fill="none" aria-hidden="true">
      <path d="M22 58v-8a26 26 0 0 1 52 0v8" stroke="#F1A7C2" strokeWidth="9" strokeLinecap="round" />
      <rect x="14" y="52" width="18" height="26" rx="9" fill="#F786B0" />
      <rect x="64" y="52" width="18" height="26" rx="9" fill="#F786B0" />
      <rect x="17" y="55" width="7" height="20" rx="3.5" fill="#FBB6D0" />
      <rect x="67" y="55" width="7" height="20" rx="3.5" fill="#FBB6D0" />
    </svg>
  )
}

function ArtMic() {
  return (
    <svg viewBox="0 0 96 96" fill="none" aria-hidden="true">
      <rect x="36" y="14" width="24" height="42" rx="12" fill="#A88BEB" />
      <rect x="40" y="18" width="7" height="34" rx="3.5" fill="#C3AEF2" />
      <path d="M26 44a22 22 0 0 0 44 0" stroke="#8C73FF" strokeWidth="7" strokeLinecap="round" />
      <rect x="44" y="66" width="8" height="12" rx="3" fill="#8C73FF" />
      <rect x="34" y="78" width="28" height="6" rx="3" fill="#A88BEB" />
    </svg>
  )
}

function ArtPlay() {
  return (
    <svg viewBox="0 0 96 96" fill="none" aria-hidden="true">
      <rect x="16" y="16" width="64" height="64" rx="20" fill="#F97FA5" />
      <rect x="20" y="20" width="56" height="30" rx="15" fill="#FB9FBC" opacity="0.7" />
      <path d="M42 36v24l20-12-20-12Z" fill="#fff" />
    </svg>
  )
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
          <span className="promo__art">
            <ArtBooks />
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
          <span className="promo__art">
            <ArtChecklist />
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
              <span className="tcard__ic" aria-hidden="true">🤖</span>
              <b>Совет дня</b>
              <span className="tcard__text">{dayTip()}</span>
            </div>
            <button type="button" className="tcard tcard--blue" onClick={onStats}>
              <span className="tcard__ic" aria-hidden="true">📈</span>
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
              <span className="tcard__ic" aria-hidden="true">🎯</span>
              <b>Фокус недели</b>
              <span className="tcard__text">
                {weakest
                  ? `${(KIND_RU[weakest] ?? weakest).replace(/^./, (c) => c.toUpperCase())} — твоя точка роста`
                  : 'Реши пару заданий — подскажем, что подтянуть'}
              </span>
              <span className="tcard__go">Тренировать →</span>
            </button>
            <button type="button" className="tcard tcard--peach" onClick={onCalendar}>
              <span className="tcard__ic" aria-hidden="true">🏆</span>
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
          <span className="actioncard__dot" aria-hidden="true" />
          <h3>ТРЕНАЖЁР</h3>
          <p>Практикуй все 4 задания устной части ЕГЭ</p>
          <button type="button" className="actioncard__go" onClick={onTrainer}>
            Начать <span aria-hidden="true">→</span>
          </button>
          <span className="actioncard__art">
            <ArtHeadphones />
          </span>
        </div>
        <div className="actioncard actioncard--lav">
          <span className="actioncard__dot" aria-hidden="true" />
          <h3>SPEAKING</h3>
          <p>Свободные разговоры с AI-собеседником</p>
          <button type="button" className="actioncard__go" onClick={onSpeaking}>
            Практиковаться <span aria-hidden="true">→</span>
          </button>
          <span className="actioncard__art">
            <ArtMic />
          </span>
        </div>
        <div className="actioncard actioncard--rose">
          <span className="actioncard__dot" aria-hidden="true" />
          <h3>DEMO ВЕРСИЯ</h3>
          <p>Полный экзамен в формате ЕГЭ</p>
          <button type="button" className="actioncard__go" onClick={onDemo}>
            Начать <span aria-hidden="true">→</span>
          </button>
          <span className="actioncard__art">
            <ArtPlay />
          </span>
        </div>
      </div>

      {/* Telegram — заглушка: канала пока НЕТ. Баннер по референсу, кнопка
          оживёт, когда владелец заведёт канал и укажет VITE_TELEGRAM_URL. */}
      <div className="tgbar">
        <span className="tgbar__ic" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
            <circle cx="12" cy="12" r="11" fill="#54A9EB" />
            <path
              d="M5.5 11.7l11.2-4.4c.5-.2 1 .1.8.9l-1.9 9c-.1.6-.5.8-1 .5l-2.9-2.1-1.4 1.3c-.2.2-.4.3-.7.3l.2-3 5.5-5-6.8 4.3-2.9-.9c-.6-.2-.6-.7-.1-.9Z"
              fill="#fff"
            />
          </svg>
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
