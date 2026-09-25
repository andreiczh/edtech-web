/**
 * Общие части экранов задания: звёздочка избранного в правом верхнем углу
 * (макеты 36 и 31), нижняя панель QUIT / «К СЛЕДУЮЩЕМУ ЗАДАНИЮ» и «Назад» в
 * левом верхнем углу (просьба владельца 25.09.2026, макета нет — та же
 * строка и кегль, что у подписи «ЗАДАНИЕ N»).
 */
import { useEffect } from 'react'

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

/** «Назад»: на экран, с которого пришли (выбор задания или главная). */
export function BackButton({ onBack }: { onBack: () => void }) {
  return (
    <button type="button" className="m-btn m-back" onClick={onBack} aria-label="Назад">
      <Icon icon={ICONS.chevron} className="m-back__ic" />
      <span>Назад</span>
    </button>
  )
}

/** Внутри MAX — ещё и родная кнопка «назад» в шапке мессенджера: показать на
    время экрана, по нажатию сделать то же, что «Назад» на экране. */
export function useMaxBack(onBack: () => void) {
  useEffect(() => {
    const bb = window.WebApp?.BackButton
    if (!bb) return
    try {
      bb.onClick(onBack)
      bb.show()
    } catch {
      return
    }
    return () => {
      try {
        bb.offClick(onBack)
        bb.hide()
      } catch {
        /* мост уже отвалился — не страшно */
      }
    }
  }, [onBack])
}
