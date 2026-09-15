/**
 * Избранные задания — чистая часть, без хранилища и сети (её гоняет тест в node).
 *
 * Звёздочка в правом верхнем углу задания кладёт в избранное конкретный
 * ВАРИАНТ (текст, картинки, вопросы), а не номер целиком: из этого списка
 * собирается «избранный вариант» — своя серия, как вариант экзамена.
 */

export interface FavoriteItem {
  taskId: number
  variantId: string
  /** ISO-время добавления: внутри одного номера порядок — по нему */
  at: string
}

/** Поставить или снять звёздочку. Повторная постановка не плодит дублей. */
export function withFavorite(
  list: FavoriteItem[],
  item: { taskId: number; variantId: string },
  on: boolean,
  at: string = new Date().toISOString(),
): FavoriteItem[] {
  const rest = list.filter((f) => f.variantId !== item.variantId)
  return on ? [...rest, { taskId: item.taskId, variantId: item.variantId, at }] : rest
}

/**
 * «Избранный вариант». Берём самые свежие отметки (не больше max), а идут они
 * как в настоящем варианте экзамена — по порядку номеров, внутри номера — в
 * порядке добавления. Варианты, которых больше нет в банке, выпадают молча.
 */
export function favoriteSession(
  list: FavoriteItem[],
  exists: (f: FavoriteItem) => boolean,
  max = 20,
): Array<{ taskId: number; variantId: string }> {
  return list
    .filter(exists)
    .sort((a, b) => b.at.localeCompare(a.at))
    .slice(0, max)
    .sort((a, b) => a.taskId - b.taskId || a.at.localeCompare(b.at))
    .map(({ taskId, variantId }) => ({ taskId, variantId }))
}
