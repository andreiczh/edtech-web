import { useState } from 'react'
import { DrillSession } from './DrillSession'
import { PAST_ERRORS, CAT_LABEL, TASK_TYPES } from './trainerData'

/**
 * «Тренажёр»: адаптивная тренировка.
 * — «Заполнить вакуум» — главная яркая кнопка: индивидуальный набор из 5 блоков
 *   по слабым местам и частым ошибкам ученика.
 * — «Работа над ошибками» — список прошлых ошибок (раскрываются) + кнопка нарешать
 *   задания на их исправление (акцентная, но менее яркая).
 * — Кнопки по типам заданий — нарешивание 5 подряд с фидбэком ИИ.
 */
export function TrainerHub() {
  const [drill, setDrill] = useState<string | null>(null)
  const [openError, setOpenError] = useState<number | null>(null)

  if (drill !== null) {
    return <DrillSession title={drill} onExit={() => setDrill(null)} />
  }

  return (
    <div className="hub">
      <div className="hub__inner">
        {/* Заполнить вакуум */}
        <section className="hub__hero glass">
          <div className="hub__herotext">
            <h2>Заполнить вакуум</h2>
            <p>
              Индивидуальный набор из 5 блоков по твоим слабым местам и частым ошибкам — чтобы
              закрыть пробелы и нарешать задания, где ты чаще ошибаешься.
            </p>
          </div>
          <button
            type="button"
            className="exam-btn exam-btn--hero"
            onClick={() => setDrill('Заполнить вакуум')}
          >
            Начать
          </button>
        </section>

        {/* Работа над ошибками */}
        <section className="hub__section">
          <div className="hub__sechead">
            <h3>Работа над ошибками</h3>
            <button
              type="button"
              className="exam-btn exam-btn--accent"
              onClick={() => setDrill('Работа над ошибками')}
            >
              Пройти работу над ошибками
            </button>
          </div>

          <ul className="errlist">
            {PAST_ERRORS.map((e, i) => {
              const open = openError === i
              return (
                <li key={i} className="errlist__item glass">
                  <button
                    type="button"
                    className="errrow"
                    onClick={() => setOpenError(open ? null : i)}
                    aria-expanded={open}
                  >
                    <span className={`errtag errtag--${e.cat}`}>{CAT_LABEL[e.cat]}</span>
                    <span className="errrow__title">{e.title}</span>
                    <span className="errrow__chev">{open ? '▲' : '▼'}</span>
                  </button>
                  {open && (
                    <div className="errrow__body">
                      <p>
                        <b>Контекст:</b> {e.context}
                      </p>
                      <p>
                        <b>Как правильно:</b> {e.correct}
                      </p>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        </section>

        {/* Нарешивание по типам заданий */}
        <section className="hub__section">
          <h3>Нарешать по типам заданий</h3>
          <div className="hub__taskgrid">
            {TASK_TYPES.map((t) => (
              <button
                key={t.id}
                type="button"
                className="taskbtn glass"
                onClick={() => setDrill(t.label)}
              >
                <span className="taskbtn__title">{t.label}</span>
                <span className="taskbtn__meta">5 заданий подряд · фидбэк ИИ</span>
              </button>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
