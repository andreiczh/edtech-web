/**
 * Звёздочка «в избранное» в правом верхнем углу задания (16.09.2026).
 *
 * Стоит в шапке TaskScreen, поэтому есть у каждого задания — и в серии
 * тренажёра, и в демо-варианте. Отмеченное собирается в «Избранный вариант»
 * на экране выбора заданий.
 */
import { useState } from 'react'

import { isFavorite, toggleFavorite, useFavorites } from '../ege2/favorites'
import type { TaskId } from '../ege2/tasks'

export function FavoriteStar({ taskId, variantId }: { taskId: TaskId; variantId: string }) {
  const list = useFavorites()
  const on = isFavorite(list, variantId)
  const [failed, setFailed] = useState(false)
  const label = on ? 'Убрать задание из избранного' : 'Добавить задание в избранное'

  return (
    <button
      type="button"
      className={`favstar${on ? ' favstar--on' : ''}`}
      aria-pressed={on}
      aria-label={label}
      title={failed ? 'Не сохранилось: нет связи с сервером. Попробуй ещё раз.' : label}
      onClick={() => {
        void toggleFavorite(taskId, variantId, !on).then((ok) => setFailed(!ok))
      }}
    >
      <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
        <path d="M12 3.2l2.62 5.31 5.86.85-4.24 4.13 1 5.84L12 16.58l-5.24 2.75 1-5.84-4.24-4.13 5.86-.85z" />
      </svg>
    </button>
  )
}
