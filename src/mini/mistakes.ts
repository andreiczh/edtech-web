/**
 * «Вариант по ошибкам» (карточка главной, макет 69): по одному варианту
 * каждого номера — последняя работа, где балл ниже максимума. Источник —
 * история работ с сервера (/me/analytics, поля v/s/m); варианты, которых
 * в банке уже нет, пропускаются. Пусто — значит ошибок ещё нет, и карточка
 * честно говорит об этом, а не подсовывает случайные задания.
 */
import type { MeAnalytics } from '../account/me'
import { TASKS, TASK_ORDER, variantById, type TaskId } from '../ege2/tasks'

export function mistakesSessionItems(
  history: MeAnalytics['history'] | undefined,
): Array<{ taskId: TaskId; variantId: string }> {
  if (!history?.length) return []
  const out: Array<{ taskId: TaskId; variantId: string }> = []
  for (const id of TASK_ORDER) {
    const kind = TASKS[id].kind
    // история идёт от старых к новым — берём последнюю неидеальную работу
    for (let i = history.length - 1; i >= 0; i--) {
      const h = history[i]
      if (h.k !== kind || !h.v || typeof h.m !== 'number' || !h.m) continue
      if ((h.s ?? 0) >= h.m) continue
      if (!variantById(id, h.v)) continue
      out.push({ taskId: id, variantId: h.v })
      break
    }
  }
  return out
}
