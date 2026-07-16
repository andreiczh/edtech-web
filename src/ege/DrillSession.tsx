import { useState } from 'react'
import { ExamFrame, ExamButton, Progress, Material } from './ExamKit'
import { PAST_ERRORS, CAT_LABEL } from './trainerData'

const TOTAL = 5

/**
 * Нарешивание: 5 заданий подряд → фидбэк ИИ (структура, контент — заглушки).
 * Используется всеми входами тренажёра (Заполнить вакуум / Работа над ошибками /
 * конкретный тип задания).
 */
export function DrillSession({ title, onExit }: { title: string; onExit: () => void }) {
  const [step, setStep] = useState(0)

  // Финальный экран — фидбэк ИИ
  if (step >= TOTAL) {
    return (
      <ExamFrame
        eyebrow={`Тренажёр · ${title}`}
        title="Фидбэк ИИ"
        footer={
          <div className="exam__nav">
            <ExamButton variant="ghost" onClick={onExit}>
              ← К тренажёру
            </ExamButton>
            <ExamButton onClick={() => setStep(0)}>Пройти заново</ExamButton>
          </div>
        }
      >
        <div className="results">
          <div className="results__ai">
            <span className="ai-badge">ИИ</span>
            <p className="results__summary">
              Хороший прогресс: 4 из 5 заданий выполнены уверенно. Осталось закрепить грамматику в
              вопросах — это твоя частая ошибка.
            </p>
          </div>
          <div className="results__errors">
            <h3>Что улучшить</h3>
            {PAST_ERRORS.slice(0, 2).map((e, i) => (
              <div className="errcard glass" key={i}>
                <div className="errcard__head">
                  <span className={`errtag errtag--${e.cat}`}>{CAT_LABEL[e.cat]}</span>
                </div>
                <p className="errcard__desc">{e.title}</p>
                <p className="errcard__fb">
                  <span className="ai-badge ai-badge--sm">ИИ</span>
                  {e.correct}
                </p>
              </div>
            ))}
          </div>
        </div>
      </ExamFrame>
    )
  }

  // Экран задания
  return (
    <ExamFrame
      eyebrow={title}
      title={`Задание ${step + 1} из ${TOTAL}`}
      footer={
        <>
          <Progress value={step / TOTAL} tone="mint" />
          <div className="exam__nav">
            <ExamButton variant="ghost" onClick={onExit}>
              ← Выйти
            </ExamButton>
            <ExamButton onClick={() => setStep((s) => s + 1)}>
              {step === TOTAL - 1 ? 'Завершить' : 'Далее'}
            </ExamButton>
          </div>
        </>
      }
    >
      <Material kind={step % 2 === 0 ? 'text' : 'ad'} />
      <p className="exam-note">
        Плейсхолдер задания. Здесь появится реальное задание типа «{title}».
      </p>
    </ExamFrame>
  )
}
