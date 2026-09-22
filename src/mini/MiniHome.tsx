/**
 * Главная мини-приложения — макет «iPhone 16 & 17 Pro - 72» один в один.
 *
 * Живое: имя из аккаунта, серия из /me/stats, переходы. Тексты карточек — из
 * макета дословно (в нём подписи «Теория»/«Ошибки» повторяют текст SPEAKING;
 * так в файле). Чего в системе нет — раздела теории — карточка не ведёт
 * никуда и помечена как недоступная, а не притворяется.
 */
import { useEffect, useState } from 'react'

import { greeting } from '../account/greeting'
import { fetchMeStats } from '../account/me'
import { currentUser } from '../auth/auth'
import { Icon } from './Ambient'
import { ICONS } from './icons'

export type MiniTab = 'home' | 'calendar' | 'stats' | 'settings'

export function MiniTabs({ active, onTab }: { active: MiniTab; onTab: (t: MiniTab) => void }) {
  const tabs: Array<{ id: MiniTab; title: string; icon: keyof typeof ICONS }> = [
    { id: 'home', title: 'Главная', icon: 'home' },
    { id: 'calendar', title: 'Календарь', icon: 'calendarGlyph' },
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
  onSpeaking,
  onDemo,
  onErrors,
}: {
  onPractice: () => void
  onSpeaking: () => void
  onDemo: () => void
  onErrors: () => void
}) {
  const nick = currentUser()?.nickname ?? ''
  const [streak, setStreak] = useState<number | null>(null)
  useEffect(() => {
    let alive = true
    void fetchMeStats().then((s) => alive && s && setStreak(s.streak.days))
    return () => {
      alive = false
    }
  }, [])

  return (
    <div className="h-page">
      <div className="h-bg" aria-hidden="true" />
      <div className="h-sheet" aria-hidden="true" />

      <div className="h-ava" role="img" aria-label="Аватар" />
      <Icon icon={ICONS.flame} className="h-flame" />
      <span className="h-streak" aria-label={`Серия: ${streak ?? 0} дней`}>
        {streak ?? '·'}
      </span>
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
          мгновенной обратной связью.
        </span>
        <span className="h-btn1">Начать практику</span>
      </button>

      <button type="button" className="m-btn h-card h-card--2 h-card--btn" onClick={onSpeaking}>
        <span className="h-tile h-tile--2" aria-hidden="true" />
        <Icon icon={ICONS.aa} className="h-aa" />
        <Icon icon={ICONS.speakWord} className="h-speak" />
        <span className="h-title h-title--2">SPEAKING</span>
        <span className="h-sub h-sub--2">
          Свободные разговоры с AI-
          <br />
          собеседником
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
          Свободные разговоры с AI-
          <br />
          собеседником
        </span>
      </div>
      <button type="button" className="m-btn h-small h-small--errors h-card--btn" onClick={onErrors}>
        <span className="h-title">ОШИБКИ</span>
        <span className="h-sub">
          Свободные разговоры с AI-
          <br />
          собеседником
        </span>
      </button>
    </div>
  )
}
