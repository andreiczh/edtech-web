/**
 * Тесты формы несогласия: набор причин и проверка полноты.
 *
 * Запуск: npm run test (обычный node с --experimental-strip-types).
 *
 * Проверяем ровно то, что делает жалобу пригодной для калибровки. Ошибка здесь
 * не роняет приложение — она тихо портит данные: форма отпускает полупустую
 * жалобу, та ложится в базу, и через месяц копилка полна записей, по которым
 * ничего нельзя решить.
 */
import { EMPTY_DRAFT, MIN_COMMENT, formProblem, reasonsFor, REASONS } from './dispute.ts'

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

function ok(value: boolean, name: string): void {
  eq(value, true, name)
}

/* --------------------------------------------------------- набор причин */

ok(reasonsFor('talk_reply').some((r) => r.code === 'off_context'),
   'у реплики разговора есть «ответил не на то»')
ok(!reasonsFor('talk_reply').some((r) => r.code === 'unfair'),
   'у реплики разговора нет причин про балл')
ok(reasonsFor('criterion').some((r) => r.code === 'unfair'),
   'у критерия ЕГЭ причина про балл есть')
ok(reasonsFor('app').length >= 2, 'у отзыва о приложении есть из чего выбрать')
ok(REASONS.every((r) => r.hint.length > 5), 'у каждой причины есть подсказка для поля')
eq(new Set(REASONS.map((r) => r.code)).size, REASONS.length, 'коды причин не повторяются')

/* ------------------------------------------------- что мешает отправить */

const long = 'Аспект второй я раскрыл словами про экономию времени'

eq(formProblem(EMPTY_DRAFT, false), 'Выбери, что не так', 'пустая форма: сначала причина')

eq(
  formProblem({ ...EMPTY_DRAFT, reason: 'unfair' }, true),
  'Отметь, каким должен быть балл',
  'там, где есть балл, его требуем',
)

eq(
  formProblem({ ...EMPTY_DRAFT, reason: 'unfair', claimScore: -1, comment: long }, true),
  null,
  '«дело не в балле» — это тоже ответ, он засчитывается',
)

eq(
  formProblem({ ...EMPTY_DRAFT, reason: 'misheard', claimScore: 3, comment: long }, true),
  'Напиши, что ты сказал на самом деле',
  'жалоба на распознавание без своей версии не уходит',
)

eq(
  formProblem(
    { reason: 'misheard', claimScore: 3, said: 'their', comment: long },
    true,
  ),
  null,
  'жалоба на распознавание со своей версией уходит',
)

eq(
  formProblem({ ...EMPTY_DRAFT, reason: 'other', comment: 'не так' }, false),
  `Опиши, что не так — ещё ${MIN_COMMENT - 'не так'.length} символов`,
  'короткое объяснение: говорим, сколько ещё нужно',
)

eq(
  formProblem({ ...EMPTY_DRAFT, reason: 'other', comment: '          ' }, false),
  `Опиши, что не так — ещё ${MIN_COMMENT} символов`,
  'пробелы за объяснение не считаются',
)

eq(formProblem({ ...EMPTY_DRAFT, reason: 'other', comment: long }, false), null,
   'заполненная форма отправляется')

console.log()
console.log(failed ? `ПРОВАЛОВ: ${failed}` : 'ВСЁ ЗЕЛЕНО')
if (failed) process.exit(1)
