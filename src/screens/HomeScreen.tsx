/**
 * Главный экран — перенос макета «MacBook Air - 15 (2)» один в один.
 *
 * Раскладка (координаты, размеры, кегли, трекинг) не пишется руками: она
 * лежит в homeV2Layout.ts, сгенерированном из откалиброванной копии SVG.
 * Здесь только поведение: те же обработчики, что и раньше — тренажёр,
 * разговор, демо, календарь, статистика, профиль, Telegram.
 *
 * Рейл и док темы у главной общие со всеми экранами (components/Rail.tsx,
 * фиксированы поверх холста) — в холсте их нет. Холст 1710×1112
 * масштабируется под окно целиком (one-pager без скролла).
 *
 * Баннер — слайдер из четырёх карточек: канал Telegram и три живые плитки
 * прежней главной («Совет дня», «Твой прогресс», «Фокус недели»). Живые
 * данные: имя из аккаунта, серия из /me/stats, прогресс и слабое место из
 * /me/analytics. Чего в системе нет, то честно не работает: раздел теории
 * (кнопка выключена), уведомления (колокольчик без действия).
 */
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react'

import { fetchMeAnalytics, fetchMeStats, type MeAnalytics, type MeStats } from '../account/me'
import { currentUser } from '../auth/auth'
import { HOME_LAYOUT, STAGE_H, STAGE_W } from './homeV2Layout'

/* Канал: ссылка владельца, переменная окружения может её переопределить. */
const TG_URL = (import.meta.env.VITE_TELEGRAM_URL as string | undefined) || 'https://t.me/Go_Speak_AI'

const KIND_RU: Record<string, string> = {
  reading: 'чтение вслух',
  dialogue: 'вопросы (№40)',
  interview: 'интервью (№41)',
  monologue: 'монолог (№42)',
}

/* Советы дня — написанный руками банк, ротация по дате. Именно банк, а не
   вызов LLM: совет не стоит запроса из месячного бюджета. */
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
  const day = Math.floor(Date.now() / 86400000)
  return TIPS[day % TIPS.length]
}

function greeting(): string {
  const h = new Date().getHours()
  if (h < 5) return 'Good night'
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

const pic = (key: string) => HOME_LAYOUT.pics.find((p) => p.key === key)!
const box = (key: string) => HOME_LAYOUT.boxes.find((b) => b.key === key)!.style
const icon = (key: string) => HOME_LAYOUT.icons.find((i) => i.key === key)!
const txt = (key: string) => HOME_LAYOUT.texts[key]
const px = (v: unknown) => parseFloat(String(v))

/* Иконка из макета: SVG-контур вырезан из файла дословно. `strip` убирает
   из группы элемент, который рисуем отдельно (число стрика). */
function Ic({ k, strip, style }: { k: string; strip?: RegExp; style?: CSSProperties }) {
  const i = icon(k)
  const svg = strip ? i.svg.replace(strip, '') : i.svg
  return (
    <span
      className="homev2__ic"
      style={{ ...i.style, ...style }}
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}

function Pic({ k }: { k: string }) {
  const p = pic(k)
  const { file, ...img } = p.img
  return (
    <span className="homev2__pic" style={p.box}>
      <img src={`/home/${file}`} alt="" style={img} draggable={false} />
    </span>
  )
}

function Txt({ k, children, style, html }: { k: string; children?: string; style?: CSSProperties; html?: string }) {
  const t = txt(k)
  if (children !== undefined) {
    return (
      <span className="homev2__t" style={{ ...t.style, ...style }}>
        {children}
      </span>
    )
  }
  return (
    <span
      className="homev2__t"
      style={{ ...t.style, ...style }}
      dangerouslySetInnerHTML={{ __html: html ?? t.html }}
    />
  )
}

/* Кнопка макета: чёрная/белая плашка из файла — сама и есть кнопка,
   подпись и стрелка лежат поверх и клики пропускают. */
function Btn({
  k,
  label,
  onClick,
  disabled,
  title,
  href,
  style,
}: {
  k: string
  label: string
  onClick?: () => void
  disabled?: boolean
  title?: string
  href?: string
  style?: CSSProperties
}) {
  const s = { ...box(k), ...style }
  if (href) {
    return (
      <a className="homev2__btn" style={s} href={href} target="_blank" rel="noreferrer" aria-label={label} title={title} />
    )
  }
  return (
    <button
      type="button"
      className="homev2__btn"
      style={s}
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={title}
    />
  )
}

/* Зона нажатия поверх иконки: тот же бокс, что у иконки. */
function hit(s: CSSProperties): CSSProperties {
  return { left: s.left, top: s.top, width: s.width, height: s.height }
}

interface Slide {
  title: string
  titleHtml?: string
  text: string
  btn: string
  href?: string
  onClick?: () => void
  logo?: boolean
}

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

  /* Масштаб холста под окно: целиком, по центру, без скролла. */
  const stageRef = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = stageRef.current
    if (!el) return
    const fit = () => {
      const w = window.innerWidth || document.documentElement.clientWidth
      const h = window.innerHeight || document.documentElement.clientHeight
      if (!w || !h) return // окно ещё без размера (скрытая вкладка) — ждём resize
      const k = Math.min(w / STAGE_W, h / STAGE_H)
      const dx = (w - STAGE_W * k) / 2
      const dy = (h - STAGE_H * k) / 2
      el.style.transform = `translate(${dx}px, ${dy}px) scale(${k})`
    }
    fit()
    window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  }, [])

  const nick = currentUser()?.nickname ?? ''
  const streak = stats?.streak.days ?? null

  /* Слайды баннера: канал + три живые плитки прежней главной. */
  const kinds = analytics?.kinds ?? {}
  const kindList = Object.entries(kinds)
  const attempts = kindList.reduce((s, [, k]) => s + k.attempts, 0)
  const delta =
    attempts > 0
      ? Math.round(kindList.reduce((s, [, k]) => s + (k.recent_pct - k.avg_pct) * k.attempts, 0) / attempts)
      : null
  const rows = kindList.filter(([, k]) => k.attempts > 0)
  const weakest = rows.length > 1 ? rows.reduce((a, b) => (b[1].recent_pct < a[1].recent_pct ? b : a))[0] : null

  const slides: Slide[] = [
    {
      title: 'Присоединяйся к Telegram GoSpeak',
      titleHtml: txt('tgTitle').html,
      text: 'Разборы заданий, новый вариант, советы по ЕГЭ и обновления платформы',
      btn: 'Перейти в канал',
      href: TG_URL,
      logo: true,
    },
    { title: 'Совет дня', text: dayTip(), btn: 'К тренажёру', onClick: onTrainer },
    {
      title: 'Твой прогресс',
      text:
        delta === null
          ? 'Появится после первых занятий — сравним последние работы с твоим средним.'
          : delta > 0
            ? `Последние работы на ${delta}% лучше твоего среднего. Так держать.`
            : delta < 0
              ? `Последние работы на ${-delta}% ниже среднего — бывает, разберём.`
              : 'Держишься ровно на своём среднем.',
      btn: 'Смотреть',
      onClick: onStats,
    },
    {
      title: 'Фокус недели',
      text: weakest
        ? `${(KIND_RU[weakest] ?? weakest).replace(/^./, (c) => c.toUpperCase())} — твоя точка роста на этой неделе.`
        : 'Реши пару заданий — подскажем, что подтянуть.',
      btn: 'Тренировать',
      onClick: onTrainer,
    },
  ]
  const [slide, setSlide] = useState(0)
  const cur = slides[slide]
  const go = (d: number) => setSlide((s) => (s + d + slides.length) % slides.length)
  const btnBox = box('btnTelegram')

  return (
    <div className="homev2">
      <div className="homev2__stage" ref={stageRef} style={{ width: STAGE_W, height: STAGE_H }}>
        {/* фон-картинки карточек */}
        <Pic k="theory" />
        <Pic k="ai" />
        <Pic k="telegram" />
        <Pic k="trainer" />
        <Pic k="speaking" />
        <Pic k="demo" />

        {/* шапка */}
        <Txt k="greeting">{`${greeting()}, ${nick}!`}</Txt>
        <button
          type="button"
          className="homev2__streak"
          style={hit(icon('flame').style)}
          onClick={onCalendar}
          title="Серия занятий — открыть календарь"
          aria-label="Серия занятий"
        >
          <Ic k="flame" strip={/<path[^>]*fill="white"[^>]*\/>/} style={{ left: 0, top: 0 }} />
          <span className="homev2__streakno">{streak ?? '—'}</span>
        </button>
        <span className="homev2__box" style={box('bellBg')} />
        <Ic k="bell" />
        <span className="homev2__box" style={box('avatarBg')} />
        <button
          type="button"
          className="homev2__avatar"
          style={pic('avatar').box}
          onClick={onProfile}
          title="Личный кабинет"
          aria-label="Личный кабинет"
        >
          <Pic k="avatar" />
        </button>

        {/* карточка ТЕОРИЯ — раздела в системе пока нет, кнопка выключена */}
        <Txt k="theoryLabel" />
        <Txt k="theoryTitle" />
        <Txt k="theoryText" />
        <Btn k="btnTheory" label="Читать теорию" disabled title="Раздел теории ещё не готов" />
        <Txt k="theoryBtn" />
        <Ic k="arrowTheory" />

        {/* карточка AI РЕКОМЕНДАЦИИ — вариант по ошибкам открывает тренажёр */}
        <Txt k="aiLabel" />
        <Txt k="aiTitle" />
        <Txt k="aiText" />
        <Btn k="btnAi" label="Вариант по ошибкам" onClick={onTrainer} />
        <Txt k="aiBtn" />
        <Ic k="arrowAi" />

        {/* баннер-слайдер */}
        <div className="homev2__slide" key={slide}>
          {cur.titleHtml ? (
            <Txt k="tgTitle" html={cur.titleHtml} />
          ) : (
            <Txt k="tgTitle">{cur.title}</Txt>
          )}
          <Txt k="tgText" style={{ whiteSpace: 'normal', width: 310 }}>
            {cur.text}
          </Txt>
          {cur.href ? (
            <Btn k="btnTelegram" label={cur.btn} href={cur.href} />
          ) : (
            <Btn k="btnTelegram" label={cur.btn} onClick={cur.onClick} />
          )}
          {cur.logo && <Ic k="tgLogo" />}
          <Txt
            k="tgBtn"
            style={cur.logo ? undefined : { left: px(btnBox.left) + 28 }}
          >
            {cur.btn}
          </Txt>
          <Ic k="arrowTelegram" />
        </div>
        <button
          type="button"
          className="homev2__box homev2__arrow"
          style={box('prevCircle')}
          onClick={() => go(-1)}
          aria-label="Предыдущий слайд"
        />
        <button
          type="button"
          className="homev2__box homev2__arrow"
          style={box('nextCircle')}
          onClick={() => go(1)}
          aria-label="Следующий слайд"
        />
        <Ic k="chevPrev" />
        <Ic k="chevNext" />
        {(['dot1', 'dot2', 'dot3', 'dot4'] as const).map((k, i) => (
          <button
            key={k}
            type="button"
            className="homev2__box homev2__dot"
            style={{ ...box(k), background: i === slide ? '#9169EE' : '#D6D2EB' }}
            onClick={() => setSlide(i)}
            aria-label={`Слайд ${i + 1}: ${slides[i].title}`}
            aria-current={i === slide ? 'true' : undefined}
          />
        ))}
        {/* правая колонка */}
        <Txt k="trainerTitle" />
        <Txt k="trainerText" />
        <Btn k="btnTrainer" label="Тренажёр — начать" onClick={onTrainer} />
        <Txt k="trainerBtn" />
        <Ic k="arrowTrainer" />

        <Txt k="speakingTitle" />
        <Txt k="speakingText" />
        <Btn k="btnSpeaking" label="Speaking — начать" onClick={onSpeaking} />
        <Txt k="speakingBtn" />
        <Ic k="arrowSpeaking" />

        <Txt k="demoTitle" />
        <Txt k="demoText" />
        <Btn k="btnDemo" label="Демо-экзамен — начать" onClick={onDemo} />
        <Txt k="demoBtn" />
        <Ic k="arrowDemo" />
      </div>
    </div>
  )
}
