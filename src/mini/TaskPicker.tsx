/**
 * Выбор задания в тренажёре: «тренажёр → задания 1–4 на выбор → выбранное
 * задание» — правка тестировщика 23.09.2026. Макета у экрана нет, поэтому
 * он собран из элементов соседних макетов: подпись как «ЗАДАНИЕ N» (33),
 * карточки-градиенты (33/35), круглая кнопка внизу (35). Тайминги в подписях
 * считаются из TASKS, а не набраны руками — разойтись с экзаменом не могут.
 */
import { TASKS, TASK_ORDER, taskProgress, type TaskId, type TaskDef } from '../ege2/tasks'
import { Ambient } from './Ambient'
import { BackButton, useMaxBack } from './ResultBits'
import { taskNo } from './Practice'

const u = (v: number) => `calc(${v} * var(--u))`

const NAMES: Record<TaskId, string> = {
  39: 'Чтение текста вслух',
  40: 'Вопросы к объявлению',
  41: 'Интервью',
  42: 'Монолог по фотографиям',
}

const plural = (n: number, one: string, few: string, many: string) => {
  const d = n % 10
  const dd = n % 100
  if (d === 1 && dd !== 11) return one
  if (d >= 2 && d <= 4 && (dd < 10 || dd >= 20)) return few
  return many
}

const mins = (s: number) => `${(s / 60).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} мин`

/** «1,5 мин подготовка · 4 вопроса по 20 с» — по формату задания. */
export function timing(task: TaskDef): string {
  const steps = task.variants[0]?.steps?.length ?? 1
  const prep =
    task.prepSeconds >= 60
      ? `${mins(task.prepSeconds)} подготовка`
      : task.prepSeconds > 0
        ? `${task.prepSeconds} с подготовка`
        : ''
  const answer =
    task.kind === 'reading'
      ? `${mins(task.answerSeconds)} чтение`
      : task.kind === 'monologue'
        ? `${mins(task.answerSeconds)} ответ`
        : `${steps} ${plural(steps, 'вопрос', 'вопроса', 'вопросов')} по ${task.answerSeconds} с`
  return [prep, answer].filter(Boolean).join(' · ')
}

export function TaskPicker({ onPick, onQuit }: { onPick: (id: TaskId) => void; onQuit: () => void }) {
  useMaxBack(onQuit)
  return (
    <div className="mini__frame">
      <Ambient />
      <BackButton onBack={onQuit} />
      <div className="mini__scroll">
        <span className="m-label">ТРЕНАЖЁР</span>
        <div className="tp-list">
          {TASK_ORDER.map((id) => {
            const task = TASKS[id]
            const soon = !!task.comingSoon
            const p = taskProgress(id)
            return (
              <button
                key={id}
                type="button"
                className="m-btn m-card tp-card"
                disabled={soon}
                aria-label={`Задание ${taskNo(id)}, ${NAMES[id]}${soon ? ', скоро' : ''}`}
                onClick={() => !soon && onPick(id)}
              >
                <span className="tp-kicker">ЗАДАНИЕ {taskNo(id)}</span>
                <span className="tp-title">{NAMES[id]}</span>
                <span className="tp-meta">{soon ? 'скоро' : timing(task)}</span>
                {!soon && (
                  <span className="tp-meta">
                    {p.done >= p.total ? 'все варианты пройдены' : `решено ${p.done} из ${p.total}`}
                  </span>
                )}
              </button>
            )
          })}
        </div>
        <div className="m-pad" />
        <div className="m-bar">
          <button type="button" className="m-btn m-round" style={{ left: u(19.1) }} onClick={onQuit}>
            QUIT
          </button>
        </div>
      </div>
    </div>
  )
}
