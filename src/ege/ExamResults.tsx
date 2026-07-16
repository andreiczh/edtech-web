import { ExamFrame, ExamButton } from './ExamKit'
import { TASK_TITLES } from './examFlow'

// Итоги по заданиям (баллы — по критериям устной части: 1 + 4 + 5 + 10 = 20).
// Значения-заглушки: реальную оценку будет считать ИИ.
const SCORES = [
  { task: 1, score: 1, max: 1 },
  { task: 2, score: 3, max: 4 },
  { task: 3, score: 4, max: 5 },
  { task: 4, score: 7, max: 10 },
]
const TOTAL = SCORES.reduce((a, s) => a + s.score, 0)
const TOTAL_MAX = SCORES.reduce((a, s) => a + s.max, 0)

// Классификация ошибок — по критериям оценивания устной части ЕГЭ.
type Cat = 'lex' | 'gram' | 'phon' | 'logic'
const CAT_LABEL: Record<Cat, string> = {
  lex: 'Лексическая ошибка',
  gram: 'Грамматическая ошибка',
  phon: 'Фонетическая ошибка',
  logic: 'Логическая ошибка',
}

const ERRORS: { task: number; cat: Cat; desc: string; fb: string }[] = [
  {
    task: 2,
    cat: 'gram',
    desc: 'Во 2-м вопросе нарушен порядок слов.',
    fb: 'В прямых вопросах вспомогательный глагол идёт перед подлежащим: «How much does it cost?».',
  },
  {
    task: 3,
    cat: 'lex',
    desc: 'Неточное слово в ответе на 3-й вопрос.',
    fb: 'Используйте «take a photo» вместо «make a photo» — это устойчивое сочетание.',
  },
  {
    task: 4,
    cat: 'logic',
    desc: 'Вступление и вывод слабо связаны с основной частью.',
    fb: 'Добавьте связки (however, in addition) и вернитесь к теме монолога в заключении.',
  },
  {
    task: 4,
    cat: 'phon',
    desc: 'Ударение в слове «development».',
    fb: 'Ударение падает на второй слог: de-VE-lop-ment.',
  },
]

export function ExamResults({
  variant,
  onRestart,
  onExit,
}: {
  variant?: number
  onRestart: () => void
  onExit?: () => void
}) {
  return (
    <ExamFrame
      eyebrow={variant != null ? `Ответ в формате ЕГЭ · Вариант ${variant}` : 'Ответ в формате ЕГЭ'}
      title="Результат"
      footer={
        <div className="exam__nav">
          {onExit ? (
            <ExamButton variant="ghost" onClick={onExit}>
              ← К выбору варианта
            </ExamButton>
          ) : (
            <span />
          )}
          <ExamButton onClick={onRestart}>Пройти заново</ExamButton>
        </div>
      }
    >
      <div className="results">
        {/* Короткое саммари от ИИ */}
        <div className="results__ai">
          <span className="ai-badge">ИИ</span>
          <p className="results__summary">
            Хороший ответ: коммуникативные задачи в целом выполнены, виден прогресс — стоит подтянуть
            грамматику во втором задании.
          </p>
        </div>

        {/* Таблица итогов */}
        <div className="results__score glass">
          <div className="score-total">
            {TOTAL} <span>/ {TOTAL_MAX} баллов</span>
          </div>
          <table className="score-table">
            <thead>
              <tr>
                <th>Задание</th>
                <th>Балл</th>
              </tr>
            </thead>
            <tbody>
              {SCORES.map((s) => (
                <tr key={s.task}>
                  <td>
                    Задание {s.task} · {TASK_TITLES[s.task]}
                  </td>
                  <td className="num">
                    {s.score} / {s.max}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Разбор ошибок по заданиям */}
        <div className="results__errors">
          <h3>Разбор ошибок</h3>
          {ERRORS.map((e, idx) => (
            <div className="errcard glass" key={idx}>
              <div className="errcard__head">
                <span className={`errtag errtag--${e.cat}`}>{CAT_LABEL[e.cat]}</span>
                <span className="errcard__task">Задание {e.task}</span>
              </div>
              <p className="errcard__desc">{e.desc}</p>
              <p className="errcard__fb">
                <span className="ai-badge ai-badge--sm">ИИ</span>
                {e.fb}
              </p>
            </div>
          ))}
        </div>
      </div>
    </ExamFrame>
  )
}
