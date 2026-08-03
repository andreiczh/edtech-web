/**
 * Чистая логика выбора вариантов и слияния прогресса.
 *
 * Вынесена из tasks.ts НАМЕРЕННО: там она была сцеплена с localStorage и
 * import.meta.env, и проверить её можно было только руками в браузере. Здесь
 * ни одной зависимости — ни от DOM, ни от Vite, — поэтому selection.test.ts
 * гоняется обычным node (см. npm run test).
 *
 * Регресс именно тут самый тихий: перепутанный порядок повторов не падает и
 * не рисует ошибку, ученик просто получает не тот вариант, а заметить это
 * можно только сверив два списка вручную.
 */

/**
 * Слияние прогресса: сервер — источник правды, локальные отметки — буфер.
 *
 * Сервер знает время каждой сдачи, поэтому его порядок и есть хронология
 * (самые давние первыми). Локальные id, которых у сервера нет, — самые
 * свежие: они появились после последней успешной записи результата (разбор
 * мог не доехать из-за сети), и подсовывать эти варианты заново нечестно.
 */
export function mergeSolved(fromServer: string[], local: string[]): string[] {
  const known = new Set(fromServer)
  return [...fromServer, ...local.filter((id) => !known.has(id))]
}

/**
 * Набор вариантов в сессию: сначала все нерешённые (в порядке банка), затем,
 * если их не хватает, добор из решённых — начиная с САМЫХ ДАВНИХ.
 *
 * @param variantIds  все варианты типа задания, в порядке банка
 * @param solvedOrder решённые в хронологическом порядке (давние первыми)
 * @param want        сколько вариантов нужно в сессию
 */
export function pickVariants(
  variantIds: string[],
  solvedOrder: string[],
  want: number,
): string[] {
  const solved = new Set(solvedOrder)
  const fresh = variantIds.filter((id) => !solved.has(id))
  // Из порядка сдач берём только те, что ещё есть в банке: вариант могли
  // удалить в админке, а отметка о нём в истории осталась.
  const inBank = new Set(variantIds)
  const stale = solvedOrder.filter((id) => inBank.has(id))
  return [...fresh, ...stale].slice(0, Math.min(want, variantIds.length))
}
