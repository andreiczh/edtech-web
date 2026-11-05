/** Responsive dashboard. Artwork stays local; content follows normal flow. */
import { useEffect, useState } from 'react'
import { greeting } from '../account/greeting'
import { fetchMeAnalytics, fetchMeStats, type MeAnalytics, type MeStats } from '../account/me'
import { currentUser } from '../auth/auth'
import { mistakesSessionItems } from '../mini/mistakes'
import type { SessionItem } from './SessionScreen'

const TG_URL = (import.meta.env.VITE_TELEGRAM_URL as string | undefined) || 'https://t.me/Go_Speak_AI'
const KIND_RU: Record<string,string> = { reading: 'чтение вслух', dialogue: 'вопросы', interview: 'интервью', monologue: 'монолог' }
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


export function HomeScreen({ onTrainer, onSpeaking, onDemo, onStats, onCalendar, onProfile, onMistakes }: {
  onTrainer: () => void; onSpeaking: () => void; onDemo: () => void;
  onStats: () => void; onCalendar: () => void; onProfile: () => void;
  onMistakes: (items: SessionItem[]) => void;
}) {
  const [stats, setStats] = useState<MeStats | null>(null)
  const [analytics, setAnalytics] = useState<MeAnalytics | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [slide, setSlide] = useState(0)
  useEffect(() => {
    let alive = true
    setLoaded(false)
    void Promise.all([fetchMeStats(), fetchMeAnalytics()]).then(([s,a]) => {
      if (alive) { setStats(s); setAnalytics(a); setLoaded(true) }
    })
    return () => { alive = false }
  }, [refresh])
  const nick = currentUser()?.nickname ?? ''
  const mistakes = mistakesSessionItems(analytics?.history)
  const practiced = Object.entries(analytics?.kinds ?? {}).filter(([,k]) => k.attempts > 0)
  const weakest = practiced.length ? practiced.reduce((a,b) => b[1].recent_pct < a[1].recent_pct ? b : a)[0] : null
  const slides = [
    { title: 'Присоединяйся к Telegram GoSpeak', text: 'Разборы заданий, советы по ЕГЭ и обновления платформы.', button: 'Перейти в канал', href: TG_URL, onClick: undefined },
    { title: 'Совет дня', text: dayTip(), button: 'К тренажёру', href: undefined, onClick: onTrainer },
    { title: 'Твой прогресс', text: stats ? `Выполнено заданий: ${stats.totals.tasks}. Посмотри результаты и частые ошибки.` : 'Результаты появятся после первых занятий.', button: 'Открыть статистику', href: undefined, onClick: onStats },
    { title: 'Фокус недели', text: weakest ? `Удели внимание разделу «${KIND_RU[weakest] ?? weakest}» — здесь есть возможность улучшить результат.` : 'Начни с любого задания: после тренировок здесь появится подсказка.', button: 'К тренажёру', href: undefined, onClick: onTrainer },
  ]
  const cur = slides[slide]
  return <main className="dashboard-home">
    <div className="dashboard-inner">
      <header className="dashboard-header">
        <h1>{greeting()}, <span title={nick}>{nick}</span>!</h1>
        <div className="dashboard-header-actions">
          <button type="button" className="dashboard-round" onClick={onCalendar} aria-label="Серия занятий — открыть календарь">🔥 <span>{stats?.streak.days ?? '—'}</span></button>
          <button type="button" className="dashboard-round dashboard-avatar" onClick={onProfile} aria-label="Личный кабинет"><img src="/mini/avatar.png" alt="" /></button>
        </div>
      </header>
      {loaded && (!stats || !analytics) && <div className="dashboard-status" role="status">Не удалось загрузить часть статистики. <button type="button" onClick={() => setRefresh(v => v + 1)}>Повторить</button></div>}
      <div className="dashboard-grid">
        <div className="dashboard-primary">
          <section className="dashboard-card dashboard-trainer"><h2>ТРЕНАЖЁР</h2><p>Практикуй все четыре задания устной части ЕГЭ</p><button type="button" className="dashboard-action dashboard-action--dark" aria-label="Тренажёр — начать" onClick={onTrainer}>Начать →</button></section>
          <section className="dashboard-card dashboard-speaking"><h2>SPEAKING</h2><p>Свободный разговор с AI-собеседником</p><button type="button" className="dashboard-action dashboard-action--dark" aria-label="Speaking — начать" onClick={onSpeaking}>Начать →</button></section>
          <section className="dashboard-card dashboard-demo"><img src="/mini/doc.png" alt="" /><h2>DEMO</h2><p>Полный экзамен в формате ЕГЭ</p><button type="button" className="dashboard-action dashboard-action--dark" aria-label="Демо-экзамен — начать" onClick={onDemo}>Начать →</button></section>
        </div>
        <div className="dashboard-secondary">
          <section className="dashboard-card dashboard-theory">
            <span className="dashboard-kicker">ТЕОРИЯ · СКОРО</span><h2>Повтори теорию по заданиям</h2>
            <p>Готовим краткие конспекты и примеры ответов.</p>
            <button type="button" className="dashboard-action" disabled>Скоро появится</button>
          </section>
          <section className="dashboard-card dashboard-mistakes">
            <span className="dashboard-kicker">ПРАКТИКА ПО РЕЗУЛЬТАТАМ</span><h2>Вариант по ошибкам</h2>
            <p>{mistakes.length ? 'Повтори решённые задания, где балл был ниже максимума.' : 'Появится после первых решённых заданий с ошибками.'}</p>
            <button type="button" className="dashboard-action" disabled={!mistakes.length} onClick={() => onMistakes(mistakes)}>Повторить задания <span aria-hidden="true">→</span></button>
          </section>
          <section className="dashboard-card dashboard-banner" aria-roledescription="карусель" aria-label="Подсказки и новости">
            <div aria-live="polite" aria-atomic="true"><h2>{cur.title}</h2><p>{cur.text}</p></div>
            {cur.href ? <a className="dashboard-action dashboard-action--dark" href={cur.href} target="_blank" rel="noreferrer">{cur.button} <span aria-hidden="true">↗</span></a> : <button type="button" className="dashboard-action dashboard-action--dark" onClick={cur.onClick}>{cur.button} <span aria-hidden="true">→</span></button>}
            <div className="dashboard-slider"><button type="button" onClick={() => setSlide(s => (s+3)%4)} aria-label="Предыдущий слайд">←</button>
              {slides.map((s,i) => <button key={s.title} type="button" className="dashboard-dot" aria-label={`Слайд ${i+1}: ${s.title}`} aria-current={i===slide ? 'true' : undefined} onClick={() => setSlide(i)}><span /></button>)}
              <button type="button" onClick={() => setSlide(s => (s+1)%4)} aria-label="Следующий слайд">→</button>
            </div>
          </section>
        </div>

      </div>
    </div>
  </main>
}
