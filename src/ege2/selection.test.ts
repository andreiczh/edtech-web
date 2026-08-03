/**
 * Тесты отбора вариантов и слияния прогресса.
 *
 * Запуск: npm run test (обычный node с --experimental-strip-types).
 * Фреймворк не ставим намеренно: npm install в этом проекте запрещён — он
 * переписывает лок-файл (см. CLAUDE.md), а бэкенд-тесты и так живут обычными
 * скриптами (test_ege_scoring.py). Здесь та же конвенция.
 */
import { highlightPieces, mergeSolved, pickVariants } from './selection.ts'

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

/* ------------------------------------------------------- mergeSolved */

eq(mergeSolved([], []), [], 'слияние: обе стороны пусты')

eq(
  mergeSolved(['a', 'b', 'c'], []),
  ['a', 'b', 'c'],
  'слияние: порядок сервера сохраняется как есть',
)

eq(
  mergeSolved([], ['x', 'y']),
  ['x', 'y'],
  'слияние: без сервера остаются локальные отметки',
)

// Главное свойство: сервер задаёт хронологию, а не «доливается» в конец.
// Раньше цикл markVariantSolved давал бы ['c','a','b'] — порядок ломался.
eq(
  mergeSolved(['a', 'b'], ['c', 'a', 'b']),
  ['a', 'b', 'c'],
  'слияние: сервер — источник правды, локальный лишний уходит в конец',
)

eq(
  mergeSolved(['a', 'b'], ['a', 'b']),
  ['a', 'b'],
  'слияние: дублей не появляется',
)

/* ------------------------------------------------------ pickVariants */

const BANK = ['v1', 'v2', 'v3', 'v4', 'v5', 'v6', 'v7']

eq(
  pickVariants(BANK, [], 5),
  ['v1', 'v2', 'v3', 'v4', 'v5'],
  'отбор: ничего не решено — первые пять из банка',
)

eq(
  pickVariants(BANK, ['v1', 'v2'], 5),
  ['v3', 'v4', 'v5', 'v6', 'v7'],
  'отбор: решённые пропускаются, хватает свежих',
)

// Свежих меньше пяти — добор начинается с САМЫХ ДАВНИХ (v1 решён раньше v5).
eq(
  pickVariants(BANK, ['v1', 'v2', 'v3', 'v4', 'v5'], 5),
  ['v6', 'v7', 'v1', 'v2', 'v3'],
  'отбор: добор повторов идёт от самых давних',
)

eq(
  pickVariants(BANK, ['v5', 'v4', 'v3', 'v2', 'v1', 'v6', 'v7'], 5),
  ['v5', 'v4', 'v3', 'v2', 'v1'],
  'отбор: всё решено — повторяем в порядке давности, а не банка',
)

eq(
  pickVariants(['v1', 'v2'], [], 5),
  ['v1', 'v2'],
  'отбор: в банке меньше, чем просят — отдаём сколько есть',
)

// Вариант удалили в админке, а отметка о нём осталась в истории ученика.
eq(
  pickVariants(['v1', 'v2'], ['v9', 'v1'], 5),
  ['v2', 'v1'],
  'отбор: исчезнувший из банка вариант не попадает в сессию',
)

eq(pickVariants([], ['v1'], 5), [], 'отбор: пустой банк — пустая сессия')


/* -------------------------------------------------- highlightPieces (№39) */

const REF = 'A tree is a tall plant with a trunk and branches.'

eq(
  highlightPieces(REF, []),
  [{ text: REF }],
  'подсветка: ошибок нет — текст одним куском',
)

eq(
  highlightPieces(REF, [{ correction: 'trunk', cat: 'missing' }]),
  [
    { text: 'A tree is a tall plant with a ' },
    { text: 'trunk', mark: 'missing' },
    { text: ' and branches.' },
  ],
  'подсветка: пропущенное слово выделено, текст вокруг цел',
)

eq(
  highlightPieces(REF, [
    { correction: 'tree', cat: 'lex' },
    { correction: 'branches', cat: 'missing' },
  ]),
  [
    { text: 'A ' },
    { text: 'tree', mark: 'misread' },
    { text: ' is a tall plant with a trunk and ' },
    { text: 'branches', mark: 'missing' },
    { text: '.' },
  ],
  'подсветка: два куска, порядок по тексту, а не по списку ошибок',
)

// Перекрытие: «tall plant» и «plant» накладываются — второй должен отпасть,
// иначе разметка порвётся и часть текста продублируется.
eq(
  highlightPieces(REF, [
    { correction: 'tall plant', cat: 'lex' },
    { correction: 'plant', cat: 'lex' },
  ]),
  [
    { text: 'A tree is a ' },
    { text: 'tall plant', mark: 'misread' },
    { text: ' with a trunk and branches.' },
  ],
  'подсветка: перекрывающиеся куски не рвут текст',
)

eq(
  highlightPieces(REF, [{ correction: 'слова нет в тексте', cat: 'lex' }]),
  [{ text: REF }],
  'подсветка: фрагмент не найден — текст не трогаем',
)

eq(
  highlightPieces(REF, [{ correction: 'a', cat: 'lex' }]),
  [{ text: REF }],
  'подсветка: слишком короткий фрагмент игнорируется (иначе подсветит все «a»)',
)

// Склейка целого текста из кусков обязана давать исходный текст без потерь.
{
  const pieces = highlightPieces(REF, [
    { correction: 'tree', cat: 'lex' },
    { correction: 'branches', cat: 'missing' },
  ])
  eq(pieces.map((p) => p.text).join(''), REF, 'подсветка: склейка кусков = исходный текст')
}

console.log(
  failed === 0
    ? '\nВсе проверки прошли: отбор, слияние прогресса и подсветка разбора.'
    : `\nПРОВАЛЕНО проверок: ${failed}`,
)
process.exit(failed === 0 ? 0 : 1)
