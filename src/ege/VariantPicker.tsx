// Заглушки вариантов (структура). Реальные КИМы подключим позже.
const VARIANTS = Array.from({ length: 12 }, (_, i) => i + 1)

/**
 * Экран выбора варианта для «Ответ в формате ЕГЭ».
 * — «Решить случайный вариант» (акцентная белая кнопка): случайный из ещё не пройденных.
 * — Ниже — список вариантов; пройденные отмечены галочкой.
 */
export function VariantPicker({
  onStart,
  solved,
}: {
  onStart: (num: number) => void
  solved: number[]
}) {
  const solveRandom = () => {
    const pool = VARIANTS.filter((n) => !solved.includes(n))
    const src = pool.length ? pool : VARIANTS
    onStart(src[Math.floor(Math.random() * src.length)])
  }

  return (
    <div className="variants">
      <div className="variants__inner">
        <header className="variants__head">
          <h2>Выбор варианта</h2>
          <p>Решайте случайные варианты устной части или выбирайте из списка. Пройденные отмечены галочкой.</p>
        </header>

        <div className="variants__actions">
          <button type="button" className="exam-btn exam-btn--hero" onClick={solveRandom}>
            Решить случайный вариант
          </button>
        </div>

        <ul className="variants__list">
          {VARIANTS.map((num) => {
            const done = solved.includes(num)
            return (
              <li key={num}>
                <button
                  type="button"
                  className={`vcard${done ? ' is-done' : ''}`}
                  onClick={() => onStart(num)}
                >
                  <span className="vcard__top">
                    <span className="vcard__num">Вариант {num}</span>
                    {done && (
                      <span className="vcard__check" aria-label="Пройдено">
                        ✓
                      </span>
                    )}
                  </span>
                  <span className="vcard__meta">Устная часть · 4 задания · ~15 мин</span>
                  {done && <span className="vcard__done">Пройдено</span>}
                </button>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
