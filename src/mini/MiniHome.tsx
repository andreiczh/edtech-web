/**
 * Главная мини-приложения — макет «iPhone 16 & 17 Pro - 69» один в один
 * (24.09.2026; сменил макет 72: SPEAKING ушёл во вкладку-микрофон, вместо
 * него «Вариант по ошибкам», вместо «Ошибок» — «Избранное», аватар справа,
 * серии на главной больше нет).
 *
 * Живое: имя из аккаунта, переходы, состояние карточек. Тексты — из макета
 * дословно. Чего в системе нет (раздел теории) — карточка не ведёт никуда
 * и помечена как недоступная, а не притворяется. «По ошибкам» и «Избранное»
 * без данных приглушены, и подпись говорит, откуда данные возьмутся.
 */
import { greeting } from '../account/greeting'
import { currentUser } from '../auth/auth'
import { Icon } from './Ambient'
import { ICONS } from './icons'

export type MiniTab = 'home' | 'talk' | 'stats' | 'settings'

/** Нижняя панель: во втором слоте — разговор (микрофон), как на экране
    разговора макета 39; календарь, нарисованный в трёх других макетах,
    вёл бы в раздел без входа с главной. */
export function MiniTabs({ active, onTab }: { active: MiniTab; onTab: (t: MiniTab) => void }) {
  const tabs: Array<{ id: MiniTab; title: string; icon: keyof typeof ICONS }> = [
    { id: 'home', title: 'Главная', icon: 'home' },
    { id: 'talk', title: 'Разговор', icon: 'micTab' },
    { id: 'stats', title: 'Статистика', icon: 'statsBars' },
    { id: 'settings', title: 'Настройки', icon: 'gear' },
  ]
  return (
    <nav className="h-tabs" aria-label="Разделы">
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          className={`m-btn h-tab h-tab--${t.id}${active === t.id ? ' h-tab--on' : ''}`}
          aria-label={t.title}
          aria-current={active === t.id ? 'page' : undefined}
          onClick={() => onTab(t.id)}
        >
          <Icon icon={ICONS[t.icon]} />
        </button>
      ))}
    </nav>
  )
}

export function MiniHome({
  onPractice,
  onMistakes,
  mistakesReady,
  onDemo,
  onFavorites,
  favoritesReady,
}: {
  onPractice: () => void
  onMistakes: () => void
  /** Есть ли работы с ошибками, из которых собирается вариант */
  mistakesReady: boolean
  onDemo: () => void
  onFavorites: () => void
  favoritesReady: boolean
}) {
  const nick = currentUser()?.nickname ?? ''

  return (
    <div className="h-page">
      <div className="h-bg" aria-hidden="true" />
      <div className="h-sheet" aria-hidden="true" />

      <div className="h-ava" role="img" aria-label="Аватар" />
      <h1 className="h-hi">
        {greeting()},
        <br />
        {nick}!
      </h1>

      <button type="button" className="m-btn h-card h-card--1 h-card--btn" onClick={onPractice}>
        <span className="h-tile h-tile--1" aria-hidden="true" />
        <img className="h-mic" src="/mini/mic.png" alt="" />
        <span className="h-kicker">ТРЕНАЖЁР · 10 МИНУТ</span>
        <span className="h-title1">
          Потренируем
          <br />
          устную часть?
        </span>
        <span className="h-sub h-sub--1">
          Все 4 задания ЕГЭ с подсказками и
          <br />
          мгновенной обратной связью
        </span>
        <span className="h-btn1">Начать практику</span>
      </button>

      <button
        type="button"
        className="m-btn h-card h-card--2 h-card--btn"
        onClick={onMistakes}
        disabled={!mistakesReady}
        aria-label={
          mistakesReady
            ? 'Вариант по ошибкам: отработай ошибки из решённых заданий'
            : 'Вариант по ошибкам появится после первых решённых заданий'
        }
      >
        <span className="h-tile h-tile--2" aria-hidden="true" />
        <Icon icon={ICONS.aa} className="h-aa" />
        <Icon icon={ICONS.retryWord} className="h-retry" />
        <span className="h-title h-title--2">
          ВАРИАНТ ПО
          <br />
          ОШИБКАМ
        </span>
        <span className="h-sub h-sub--2">
          {mistakesReady ? (
            <>
              Отработай ошибки из решенных
              <br />
              заданий
            </>
          ) : (
            <>
              Соберётся из решённых заданий,
              <br />
              где балл ниже максимума
            </>
          )}
        </span>
      </button>

      <button type="button" className="m-btn h-card h-card--3 h-card--btn" onClick={onDemo}>
        <span className="h-tile h-tile--3" aria-hidden="true">
          <img className="h-doc" src="/mini/doc.png" alt="" />
        </span>
        <span className="h-title h-title--3">DEMO</span>
        <span className="h-sub h-sub--3">Полный экзамен в формате ЕГЭ</span>
      </button>

      <div
        className="h-small h-small--theory"
        role="button"
        aria-disabled="true"
        title="Раздел теории появится позже"
      >
        <span className="h-title">ТЕОРИЯ</span>
        <span className="h-sub">
          Чек-листы для подготовки
          <br />к заданиям
        </span>
      </div>
      <button
        type="button"
        className="m-btn h-small h-small--fav h-card--btn"
        onClick={onFavorites}
        disabled={!favoritesReady}
        aria-label={favoritesReady ? 'Избранное: сохранённые задания' : 'Избранное пусто — отмечай ☆ в задании'}
      >
        <span className="h-title">ИЗБРАННОЕ</span>
        <span className="h-sub">{favoritesReady ? 'Сохраненные задания' : 'Отмечай ☆ в задании'}</span>
      </button>
    </div>
  )
}
