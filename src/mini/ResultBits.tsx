/**
 * Общие части экранов разбора (макеты 36 и 31): звёздочка избранного в
 * правом верхнем углу и нижняя панель QUIT / «К СЛЕДУЮЩЕМУ ЗАДАНИЮ».
 */
import { isFavorite, toggleFavorite, useFavorites } from '../ege2/favorites'
import type { TaskId } from '../ege2/tasks'
import { Icon } from './Ambient'
import { ICONS } from './icons'

const u = (v: number) => `calc(${v} * var(--u))`

export function StarButton({ taskId, variantId }: { taskId: TaskId; variantId: string }) {
  const favs = useFavorites()
  const fav = isFavorite(favs, variantId)
  return (
    <button
      type="button"
      className={`m-btn r-star${fav ? ' r-star--on' : ''}`}
      aria-pressed={fav}
      aria-label={fav ? 'Убрать задание из избранного' : 'Добавить задание в избранное'}
      onClick={() => void toggleFavorite(taskId, variantId, !fav)}
    >
      <Icon icon={ICONS.star} />
    </button>
  )
}

export function ResultBar({ onQuit, onNext }: { onQuit: () => void; onNext: () => void }) {
  return (
    <div className="m-bar">
      <button type="button" className="m-btn m-round" style={{ left: u(19.7) }} onClick={onQuit}>
        QUIT
      </button>
      <button type="button" className="m-btn r-next-hit" onClick={onNext} aria-label="К следующему заданию">
        <span className="r-next" aria-hidden="true">
          К СЛЕДУЮЩЕМУ ЗАДАНИЮ
        </span>
        <Icon icon={ICONS.arrowNext} className="r-next-arrow" />
      </button>
    </div>
  )
}
