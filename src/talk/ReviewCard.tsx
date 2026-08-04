/**
 * Итог разговора на экране.
 *
 * Что и почему показано именно так:
 *  - сверху ИТОГ словами, а не баллом. Разговор не экзамен, и цифра здесь
 *    была бы выдуманной: официальной шкалы для свободной беседы не существует;
 *  - ошибки — тремя строками: что сказал, как надо, почему. «Как надо» выделено
 *    сильнее всего: именно это ученик должен унести с собой;
 *  - «получилось» идёт ДО ошибок не из вежливости: человек, начавший разбор со
 *    списка провалов, закрывает его и не читает дальше;
 *  - «пригодится в следующий раз» — то, чего в речи НЕ было. Это единственная
 *    часть, которая работает на будущее, а не на прошлое.
 *
 * Модалка, а не карточка в потоке: разбор — конец занятия, он должен занять
 * всё внимание, а под ним остаётся экран разговора, к которому можно вернуться.
 */
import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'

import type { TalkReview } from './review'

export function ReviewCard({
  review,
  onClose,
  onNewTopic,
}: {
  review: TalkReview
  onClose: () => void
  onNewTopic: () => void
}) {
  const closeRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const { mistakes, good, phrases, stats } = review

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      {/* Три части, а не одна прокручиваемая простыня: шапка и кнопки стоят
          на месте, ездит только середина. Раньше кнопки «прилипали» внутри
          прокрутки и ложились поверх последней ошибки — текст читался
          из-под них. */}
      <div
        className="modal review"
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="review__head">
          <h2 className="review__title" id="review-title">
            Разбор разговора
          </h2>
          <span className="review__stats">
            {stats.turns} реплик · {stats.words} слов
          </span>
        </header>

        <div className="review__scroll scroll-soft">
          {review.summary && <p className="review__summary">{review.summary}</p>}

          {good.length > 0 && (
            <section className="review__block">
              <h3 className="review__h">Получилось</h3>
              <ul className="review__good">
                {good.map((g, i) => (
                  <li key={i}>{g}</li>
                ))}
              </ul>
            </section>
          )}

          <section className="review__block">
            <h3 className="review__h">
              {mistakes.length ? 'Над чем поработать' : 'Ошибки'}
            </h3>
            {mistakes.length === 0 ? (
              /* Пустой список — не повод для пустого места: без объяснения он
                 читается как «разбор не сработал», а не как «ошибок не нашлось». */
              <p className="review__none">
                Грубых ошибок в этот раз не нашлось. Дальше — длиннее фразы и
                сложнее конструкции.
              </p>
            ) : (
              <ul className="review__list">
                {mistakes.map((m, i) => (
                  <li key={i} className="review__item">
                    <span className="review__was">{m.quote}</span>
                    <span className="review__fix">{m.correction}</span>
                    {m.why && <span className="review__why">{m.why}</span>}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {phrases.length > 0 && (
            <section className="review__block">
              <h3 className="review__h">Пригодится в следующий раз</h3>
              <ul className="review__list">
                {phrases.map((p, i) => (
                  <li key={i} className="review__item review__item--phrase">
                    <span className="review__fix">{p.en}</span>
                    {p.ru && <span className="review__why">{p.ru}</span>}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        <footer className="review__foot">
          <button type="button" className="pill pressable review__ghost" onClick={onNewTopic}>
            Новая тема
          </button>
          <button ref={closeRef} type="button" className="pill pressable" onClick={onClose}>
            Продолжить разговор
          </button>
        </footer>
      </div>
    </div>,
    document.body,
  )
}
