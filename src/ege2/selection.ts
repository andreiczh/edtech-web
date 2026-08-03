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

/* --------------------------------------- Подсветка эталона в разборе №39 */

export interface Piece {
  text: string
  mark?: 'missing' | 'misread'
}

export interface HighlightError {
  correction: string
  cat?: string
}

/**
 * Режет эталонный текст на куски и помечает те, что ученик пропустил или
 * прочитал иначе. Ищем по фрагменту из разбора (correction) — это ровно тот
 * кусок эталона, к которому у проверяющего возникли вопросы.
 *
 * Вынесено из ResultView вместе с остальной чистой логикой: тут легко
 * посадить тихий баг (перекрывающиеся куски, порядок, обрезка хвоста), а
 * увидеть его можно только глазами на конкретном тексте.
 */
export function highlightPieces(
  reference: string,
  errors: HighlightError[],
): Piece[] {
  const marks: Array<{ from: number; to: number; mark: 'missing' | 'misread' }> = []
  for (const e of errors ?? []) {
    const needle = (e.correction || '').trim()
    if (needle.length < 2) continue
    const at = reference.toLowerCase().indexOf(needle.toLowerCase())
    if (at < 0) continue
    const mark = e.cat === 'missing' ? 'missing' : 'misread'
    // Перекрытия отбрасываем: два куска на одном месте дали бы рваную разметку.
    if (marks.some((m) => at < m.to && at + needle.length > m.from)) continue
    marks.push({ from: at, to: at + needle.length, mark })
  }
  marks.sort((a, b) => a.from - b.from)

  const out: Piece[] = []
  let cursor = 0
  for (const m of marks) {
    if (m.from > cursor) out.push({ text: reference.slice(cursor, m.from) })
    out.push({ text: reference.slice(m.from, m.to), mark: m.mark })
    cursor = m.to
  }
  if (cursor < reference.length) out.push({ text: reference.slice(cursor) })
  return out
}
