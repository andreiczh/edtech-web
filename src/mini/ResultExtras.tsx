/**
 * Блоки разбора, которых нет в мобильных макетах, но которые сервер отдаёт и
 * настольная версия показывает (ResultView): итог словами с честной оговоркой
 * о точности, найденные ошибки с поправками, расшифровка, подача чтения
 * (темп и заминки — измерено, не суждение модели) и спор о балле. Собраны
 * из тех же карточек и кеглей, что макеты 31 и 6, чтобы не выбиваться.
 */
import { useEffect, useState } from 'react'

import { fetchWeakWords, type Delivery, type FeedbackError, type TaskFeedback, type WeakWord } from '../ege2/feedback'
import type { DisputeContext } from '../ege2/dispute'
import { TASKS, type TaskId, type TaskVariant } from '../ege2/tasks'
import { sayWord, speakable } from '../ege2/sayWord'
import { Icon } from './Ambient'
import { ICONS } from './icons'
import { MiniDisagree } from './ResultBits'

/** Общая часть жалобы для всех спорных мест этого разбора — как в ResultView:
    улика, снимок разбора и обстановка задания; место спора дописывает кнопка. */
export function disputeBase(
  taskId: TaskId,
  variant: TaskVariant,
  feedback: TaskFeedback,
  transcript?: string,
): DisputeContext {
  return {
    kind: TASKS[taskId].kind,
    target: 'score',
    score: feedback.score,
    max: feedback.max,
    variant: variant.id,
    transcript: transcript || variant.readText || '',
    feedback,
    context: {
      task: taskId,
      brief: variant.brief,
      readText: variant.readText,
      steps: variant.steps,
      photoFacts: variant.photoFacts,
      imageCaption: variant.imageCaption,
      transcript,
    },
  }
}

const PACE: Record<string, string> = { slow: 'медленно', ok: 'ровный темп', fast: 'быстро' }

/** Подача чтения (№39): приходит только когда замер включён на сервере. */
export function DeliveryCard({ d }: { d?: Delivery }) {
  if (!d) return null
  return (
    <section className="x-card" aria-label="Как это прозвучало">
      <h3 className="x-title">КАК ЭТО ПРОЗВУЧАЛО</h3>
      <div className="x-row">
        <span className="x-k">темп</span>
        <span className={`x-v${d.pace === 'ok' ? ' x-v--ok' : ' x-v--warn'}`}>
          {d.wpm} слов/мин · {PACE[d.pace] ?? d.pace}
        </span>
      </div>
      <div className="x-row">
        <span className="x-k">заминки</span>
        <span className={`x-v${d.pause_count === 0 ? ' x-v--ok' : ' x-v--warn'}`}>
          {d.pause_count === 0 ? 'нет' : d.pause_count}
        </span>
      </div>
      <div className="x-row">
        <span className="x-k">звучало</span>
        <span className="x-v">{d.seconds} с</span>
      </div>
      {d.pauses.length > 0 && (
        <p className="x-why">
          Самые долгие: {d.pauses.map((p) => `${p.sec} с после «${p.after}»`).join(', ')}.
        </p>
      )}
      {d.comment && <p className="x-why">{d.comment}</p>}
    </section>
  )
}

/** Итог словами и оговорка о точности балла (текст — с сервера). */
export function SummaryCard({ feedback }: { feedback: TaskFeedback }) {
  const summary = feedback.summary?.trim()
  const note = feedback.accuracy_note?.trim()
  if (!summary && !note) return null
  return (
    <section className="x-card" aria-label="Итог">
      <h3 className="x-title">ИТОГ</h3>
      {summary && <p className="x-text">{summary}</p>}
      {note && <p className="x-why">{note}</p>}
    </section>
  )
}

/** Найденные ошибки с поправкой и объяснением; у каждой — «это не ошибка». */
export function ErrorsCard({ errors, dispute }: { errors: FeedbackError[]; dispute: DisputeContext }) {
  const list = errors.filter((e) => (e.quote || e.correction || '').trim())
  if (!list.length) return null
  return (
    <section className="x-card" aria-label="Ошибки">
      <h3 className="x-title">ОШИБКИ</h3>
      {list.map((e, i) => (
        <div className="x-err" key={i}>
          <span className="x-err__quote">{e.quote || '—'}</span>
          {e.correction && <span className="x-err__fix">{e.correction}</span>}
          {e.explanation && <p className="x-why">{e.explanation}</p>}
          <MiniDisagree
            label="это не ошибка"
            ctx={{
              ...dispute,
              target: 'error',
              targetKey: (e.quote || e.correction || '').slice(0, 40),
              targetLabel: `«${e.quote || '—'}» → «${e.correction || '—'}»`,
            }}
          />
        </div>
      ))}
    </section>
  )
}

/** Расшифровка — что сервер услышал (№40 и №41; у №42 своя карточка по макету). */
export function TranscriptCard({ transcript }: { transcript?: string }) {
  const t = transcript?.trim()
  if (!t) return null
  return (
    <section className="mr-card x-transcript" aria-label="Расшифровка">
      <h2 className="mr-title">РАСШИФРОВКА</h2>
      <p className="mr-text">{t}</p>
    </section>
  )
}

/**
 * «Переслушай эти слова» — единственное, что фонемный замер показывает
 * ученику (GET /pron/weakest). Замер идёт фоном и приезжает позже балла,
 * поэтому две попытки с паузой; пустой ответ — норма: сервер отдаёт слова
 * только при PRON_SHOW (выключено с 20.08.2026, §6.16), и тогда блока просто
 * нет. НА БАЛЛ НЕ ВЛИЯЕТ — это подсказка, не оценка. Один в один с блоком
 * настольной ResultView, только в карточке мини-экрана.
 */
export function WeakWordsCard({ variantId }: { variantId?: string }) {
  const [words, setWords] = useState<WeakWord[]>([])
  const [saying, setSaying] = useState<string | null>(null)

  useEffect(() => {
    if (!variantId) return
    let alive = true
    const timers = [1500, 12000].map((ms) =>
      setTimeout(() => {
        void fetchWeakWords(variantId).then((w) => {
          if (alive && w.length) setWords(w)
        })
      }, ms),
    )
    return () => {
      alive = false
      timers.forEach(clearTimeout)
    }
  }, [variantId])

  if (!words.length) return null
  const say = (word: string) => {
    if (saying) return
    setSaying(word)
    void sayWord(word, variantId).finally(() => setSaying(null))
  }
  return (
    <section className="x-card" aria-label="Переслушай эти слова">
      <h3 className="x-title">ПЕРЕСЛУШАЙ ЭТИ СЛОВА</h3>
      <div className="x-words">
        {words.map((w) => (
          <span key={`${w.ord}-${w.word}`} className="x-word">
            {w.word}
            <button
              type="button"
              className="m-btn x-word__say"
              onClick={() => say(w.word)}
              disabled={saying !== null || !speakable(w.word)}
              aria-label={`Послушать, как читается ${w.word}`}
            >
              <Icon icon={ICONS.speaker} />
            </button>
          </span>
        ))}
      </div>
      <p className="x-why">
        Здесь звук меньше всего похож на текст. Это подсказка для тренировки, а не
        ошибка — на балл не влияет: отличить неверный звук от акцента система пока
        не умеет.
      </p>
    </section>
  )
}
