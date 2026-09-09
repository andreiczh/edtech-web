/**
 * Главный экран — перенос макета «MacBook Air - 15 (2)» один в один.
 *
 * Раскладка (координаты, размеры, кегли, трекинг) не пишется руками: она
 * лежит в homeV2Layout.ts, сгенерированном из откалиброванной копии SVG.
 * Здесь только поведение: те же обработчики, что и раньше — тренажёр,
 * разговор, демо, календарь, статистика, профиль, тема, Telegram.
 *
 * Холст макета 1710×1112 масштабируется под окно целиком (one-pager без
 * скролла), как в утверждённой HTML-версии. Живые данные: имя из аккаунта,
 * серия занятий из /me/stats. Чего в системе нет, то честно не работает:
 * раздел теории (кнопка выключена), уведомления (колокольчик без действия),
 * карусель баннера (стрелки и точки декоративные — баннер один).
 */
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react'

import { fetchMeStats, type MeStats } from '../account/me'
import { currentUser } from '../auth/auth'
import { HOME_LAYOUT, STAGE_H, STAGE_W } from './homeV2Layout'

/* Ссылка на канал приходит из окружения сборки: канала пока нет, и кнопка
   честно выключена. Появится канал — одна переменная, без правки кода. */
const TG_URL = (import.meta.env.VITE_TELEGRAM_URL as string | undefined) ?? ''

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

/* Иконка из макета: SVG-контур вырезан из файла дословно. `strip` убирает
   из группы элемент, который рисуем отдельно (чёрная подложка активного
   пункта, число стрика). */
function Ic({ k, strip, style, className }: { k: string; strip?: RegExp; style?: CSSProperties; className?: string }) {
  const i = icon(k)
  const svg = strip ? i.svg.replace(strip, '') : i.svg
  return (
    <span
      className={`homev2__ic${className ? ` ${className}` : ''}`}
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

function Txt({ k, children, style }: { k: string; children?: string; style?: CSSProperties }) {
  const t = txt(k)
  if (children !== undefined) {
    return (
      <span className="homev2__t" style={{ ...t.style, ...style }}>
        {children}
      </span>
    )
  }
  return <span className="homev2__t" style={{ ...t.style, ...style }} dangerouslySetInnerHTML={{ __html: t.html }} />
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
}: {
  k: string
  label: string
  onClick?: () => void
  disabled?: boolean
  title?: string
  href?: string
}) {
  const style = box(k)
  if (href) {
    return (
      <a className="homev2__btn" style={style} href={href} target="_blank" rel="noreferrer" aria-label={label} title={title} />
    )
  }
  return (
    <button
      type="button"
      className="homev2__btn"
      style={style}
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={title}
    />
  )
}

/* Кнопка рейла: зона нажатия — бокс иконки с полем 8 px. */
function RailBtn({
  k,
  label,
  onClick,
  strip,
  active,
}: {
  k: string
  label: string
  onClick: () => void
  strip?: RegExp
  active?: boolean
}) {
  const i = icon(k)
  const px = (v: unknown) => parseFloat(String(v))
  const pad = 8
  return (
    <button
      type="button"
      className={`homev2__rail${active ? ' homev2__rail--on' : ''}`}
      style={{
        left: px(i.style.left) - pad,
        top: px(i.style.top) - pad,
        width: px(i.style.width) + pad * 2,
        height: px(i.style.height) + pad * 2,
      }}
      aria-label={label}
      title={label}
      onClick={onClick}
    >
      <Ic k={k} strip={strip} style={{ left: pad, top: pad }} />
    </button>
  )
}

export function HomeScreen({
  onTrainer,
  onSpeaking,
  onDemo,
  onStats,
  onCalendar,
  onProfile,
  theme,
  onTheme,
}: {
  onTrainer: () => void
  onSpeaking: () => void
  onDemo: () => void
  onStats: () => void
  onCalendar: () => void
  onProfile: () => void
  theme: 'light' | 'dark' | 'auto'
  onTheme: (t: 'light' | 'dark') => void
}) {
  const [stats, setStats] = useState<MeStats | null>(null)
  useEffect(() => {
    let alive = true
    void fetchMeStats().then((s) => alive && setStats(s))
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
  /* Док темы: чёрный квадрат из макета стоит под активным пунктом. Режим
     «авто» на макете не показан — подсвечиваем то, что сейчас на экране. */
  const darkOn = theme === 'dark' || (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  const sun = icon('navSun')
  const moon = icon('navMoon')
  const px = (v: unknown) => parseFloat(String(v))
  const squareSize = px(sun.style.width) - 3.93
  const square = (i: typeof sun): CSSProperties => ({
    left: px(i.style.left) + px(i.style.width) / 2 - squareSize / 2,
    top: px(i.style.top) + px(i.style.height) / 2 - squareSize / 2,
    width: squareSize,
    height: squareSize,
    borderRadius: 11.3,
    background: '#000',
    border: '1px solid #fff',
  })
  const flameNo = txt('greeting') // стиль числа считаем от иконки, см. ниже
  void flameNo

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

        {/* рейл навигации и док темы */}
        <span className="homev2__box homev2__box--rail" style={box('railNav')} />
        <span className="homev2__box homev2__box--rail" style={box('railTheme')} />
        <RailBtn k="navHome" label="Главная" onClick={() => undefined} active />
        <RailBtn k="navCalendar" label="Календарь" onClick={onCalendar} />
        <RailBtn k="navStats" label="Статистика" onClick={onStats} />
        <RailBtn k="navSettings" label="Настройки" onClick={onProfile} />
        <span className="homev2__box" style={square(darkOn ? moon : sun)} />
        <RailBtn
          k="navSun"
          label="Светлая тема"
          onClick={() => onTheme('light')}
          strip={/<rect[^>]*\/>/}
          active={!darkOn}
        />
        <RailBtn k="navMoon" label="Тёмная тема" onClick={() => onTheme('dark')} active={darkOn} />

        {/* шапка */}
        <Txt k="greeting">{`${greeting()}, ${nick}!`}</Txt>
        <button type="button" className="homev2__streak" style={hit(icon('flame').style)} onClick={onCalendar} title="Серия занятий — открыть календарь" aria-label="Серия занятий">
          <Ic k="flame" strip={/<path[^>]*fill="white"[^>]*\/>/} style={{ left: 0, top: 0 }} />
          <span className="homev2__streakno">{streak ?? '—'}</span>
        </button>
        <span className="homev2__box" style={box('bellBg')} />
        <Ic k="bell" />
        <span className="homev2__box" style={box('avatarBg')} />
        <button type="button" className="homev2__avatar" style={pic('avatar').box} onClick={onProfile} title="Личный кабинет" aria-label="Личный кабинет">
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

        {/* баннер Telegram */}
        <Txt k="tgTitle" />
        <Txt k="tgText" />
        {TG_URL ? (
          <Btn k="btnTelegram" label="Перейти в канал" href={TG_URL} />
        ) : (
          <Btn k="btnTelegram" label="Перейти в канал" disabled title="Канала пока нет" />
        )}
        <Ic k="tgLogo" />
        <Txt k="tgBtn" />
        <Ic k="arrowTelegram" />
        <span className="homev2__box" style={box('prevCircle')} />
        <span className="homev2__box" style={box('nextCircle')} />
        <Ic k="chevPrev" />
        <Ic k="chevNext" />
        <span className="homev2__box" style={box('dot1')} />
        <span className="homev2__box" style={box('dot2')} />
        <span className="homev2__box" style={box('dot3')} />
        <span className="homev2__box" style={box('dot4')} />

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

/* Зона нажатия поверх иконки: тот же бокс, что у иконки. */
function hit(s: CSSProperties): CSSProperties {
  return { left: s.left, top: s.top, width: s.width, height: s.height }
}
