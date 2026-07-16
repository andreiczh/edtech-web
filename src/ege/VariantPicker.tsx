import { useState } from 'react'
import { TASK_TITLES } from './examFlow'

// Заглушки вариантов (структура). Реальные КИМы подключим позже.
const VARIANTS = Array.from({ length: 12 }, (_, i) => i + 1)

type Individual = { task: number; from: number }[]

/**
 * «Тренажёр» — витрина вариантов устной части.
 * Даёт: список вариантов, выбор случайного из списка и сборку индивидуального
 * варианта из случайных заданий. Запуск открывает «Ответ в формате ЕГЭ».
 */
export function VariantPicker({ onStart }: { onStart: (label: string) => void }) {
  const [selected, setSelected] = useState<number | null>(null)
  const [individual, setIndividual] = useState<Individual | null>(null)

  const pickRandom = () => {
    setSelected(VARIANTS[Math.floor(Math.random() * VARIANTS.length)])
    setIndividual(null)
  }

  const buildIndividual = () => {
    const composed = [1, 2, 3, 4].map((task) => ({
      task,
      from: VARIANTS[Math.floor(Math.random() * VARIANTS.length)],
    }))
    setIndividual(composed)
    setSelected(null)
  }

  const select = (num: number) => {
    setSelected(num)
    setIndividual(null)
  }

  const hasChoice = selected !== null || individual !== null

  return (
    <div className="variants">
      <div className="variants__inner">
        <header className="variants__head">
          <h2>Выбор варианта</h2>
          <p>Выберите готовый вариант устной части или соберите индивидуальный из случайных заданий, затем приступайте к выполнению.</p>
        </header>

        <div className="variants__actions">
          <button type="button" className="exam-btn exam-btn--primary" onClick={pickRandom}>
            Случайный вариант
          </button>
          <button type="button" className="exam-btn exam-btn--ghost" onClick={buildIndividual}>
            Собрать индивидуальный вариант
          </button>
        </div>

        {hasChoice && (
          <div className="variants__banner">
            <span>
              {individual ? 'Индивидуальный вариант собран' : <>Выбран <b>Вариант {selected}</b></>}
            </span>
            <button
              type="button"
              className="exam-btn exam-btn--primary"
              onClick={() => onStart(individual ? 'Индивидуальный вариант' : `Вариант ${selected}`)}
            >
              Начать →
            </button>
          </div>
        )}

        {individual && (
          <div className="indiv">
            <div className="indiv__title">Индивидуальный вариант</div>
            <div className="indiv__rows">
              {individual.map((row) => (
                <div className="indiv__row" key={row.task}>
                  <span>
                    Задание {row.task} · {TASK_TITLES[row.task]}
                  </span>
                  <span className="indiv__from">из Варианта {row.from}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <ul className="variants__list">
          {VARIANTS.map((num) => (
            <li key={num}>
              <button
                type="button"
                className={`vcard${selected === num ? ' is-active' : ''}`}
                onClick={() => select(num)}
                aria-pressed={selected === num}
              >
                <span className="vcard__num">Вариант {num}</span>
                <span className="vcard__meta">Устная часть · 4 задания · ~15 мин</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
