/**
 * Тесты избранного (16.09.2026): постановка и снятие звёздочки и сборка
 * «избранного варианта».
 *
 * Запуск: npm run test.
 */
import { favoriteSession, withFavorite, type FavoriteItem } from './favoritesCore.ts'

let failed = 0

function eq(actual: unknown, expected: unknown, name: string): void {
  const a = JSON.stringify(actual)
  const e = JSON.stringify(expected)
  if (a === e) {
    console.log(`OK   ${name}`)
  } else {
    failed += 1
    console.log(`FAIL ${name}\n     ожидалось: ${e}\n     получено:  ${a}`)
  }
}

let list: FavoriteItem[] = []
list = withFavorite(list, { taskId: 40, variantId: '40-2' }, true, '2026-09-16T10:00:00Z')
list = withFavorite(list, { taskId: 42, variantId: '42-1' }, true, '2026-09-16T10:01:00Z')
eq(list.map((f) => f.variantId), ['40-2', '42-1'], 'звёздочка добавляет вариант')

list = withFavorite(list, { taskId: 40, variantId: '40-2' }, true, '2026-09-16T10:02:00Z')
eq(list.length, 2, 'повторная звёздочка не плодит дублей')

list = withFavorite(list, { taskId: 42, variantId: '42-1' }, false)
eq(list.map((f) => f.variantId), ['40-2'], 'снятая звёздочка убирает вариант')

const mixed: FavoriteItem[] = [
  { taskId: 42, variantId: '42-1', at: '2026-09-16T10:00:00Z' },
  { taskId: 40, variantId: '40-5', at: '2026-09-16T10:03:00Z' },
  { taskId: 40, variantId: '40-1', at: '2026-09-16T09:00:00Z' },
  { taskId: 39, variantId: 'gone', at: '2026-09-16T11:00:00Z' },
]
eq(
  favoriteSession(mixed, (f) => f.variantId !== 'gone').map((f) => f.variantId),
  ['40-1', '40-5', '42-1'],
  'избранный вариант идёт по номерам, внутри номера — по времени, удалённое выпадает',
)

const many: FavoriteItem[] = Array.from({ length: 25 }, (_, i) => ({
  taskId: 40 + (i % 3),
  variantId: `v${i}`,
  at: `2026-09-16T10:${String(i).padStart(2, '0')}:00Z`,
}))
const picked = favoriteSession(many, () => true, 20)
eq(picked.length, 20, 'в избранный вариант идёт не больше двадцати заданий')
eq(
  picked.some((f) => f.variantId === 'v0' || f.variantId === 'v4'),
  false,
  'при переполнении берутся самые свежие отметки',
)

if (failed) throw new Error(`ПРОВАЛОВ: ${failed}`)
console.log('\nВСЁ ЗЕЛЁНОЕ')
