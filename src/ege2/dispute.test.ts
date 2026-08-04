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
import { EMPTY_DRAFT, MIN_COMMENT, PLACES, formProblem, reasonsFor, REASONS } from './dispute.ts'

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
ok(reasonsFor('app').length >= 6, 'у отзыва о приложении есть из чего выбрать')
ok(reasonsFor('app').some((r) => r.code === 'mic'),
   'в отзыве можно пожаловаться на микрофон — это самая частая поломка')
ok(!reasonsFor('app').some((r) => r.code === 'misheard'),
   'причин про оценку в общем отзыве нет: оценивать там нечего')
ok(REASONS.every((r) => r.hint.length > 5), 'у каждой причины есть подсказка для поля')
eq(new Set(REASONS.map((r) => r.code)).size, REASONS.length, 'коды причин не повторяются')

/* ------------------------------------------------- что мешает отправить */

const long = 'Аспект второй я раскрыл словами про экономию времени'

eq(formProblem(EMPTY_DRAFT, {}), 'Выбери, что не так', 'пустая форма: сначала причина')

eq(
  formProblem({ ...EMPTY_DRAFT, reason: 'unfair' }, { score: true }),
  'Отметь, каким должен быть балл',
  'там, где есть балл, его требуем',
)

eq(
  formProblem({ ...EMPTY_DRAFT, reason: 'unfair', claimScore: -1, comment: long }, { score: true }),
  null,
  '«дело не в балле» — это тоже ответ, он засчитывается',
)

eq(
  formProblem({ ...EMPTY_DRAFT, reason: 'misheard', claimScore: 3, comment: long }, { score: true }),
  'Напиши, что ты сказал на самом деле',
  'жалоба на распознавание без своей версии не уходит',
)

eq(
  formProblem(
    { ...EMPTY_DRAFT, reason: 'misheard', claimScore: 3, said: 'their', comment: long },
    { score: true },
  ),
  null,
  'жалоба на распознавание со своей версией уходит',
)

eq(
  formProblem({ ...EMPTY_DRAFT, reason: 'other', comment: 'не так' }, {}),
  `Опиши, что не так — ещё ${MIN_COMMENT - 'не так'.length} символов`,
  'короткое объяснение: говорим, сколько ещё нужно',
)

eq(
  formProblem({ ...EMPTY_DRAFT, reason: 'other', comment: '          ' }, {}),
  `Опиши, что не так — ещё ${MIN_COMMENT} символов`,
  'пробелы за объяснение не считаются',
)

eq(formProblem({ ...EMPTY_DRAFT, reason: 'other', comment: long }, {}), null,
   'заполненная форма отправляется')

/* --------------------------------------------- общий отзыв: где случилось */

eq(
  formProblem({ ...EMPTY_DRAFT, reason: 'mic', comment: long }, { place: true }),
  'Отметь, где это случилось',
  'отзыв о приложении без экрана не уходит: воспроизвести его будет негде',
)

eq(
  formProblem({ ...EMPTY_DRAFT, reason: 'mic', place: 'task39', comment: long }, { place: true }),
  null,
  'с указанным экраном отзыв уходит',
)

ok(PLACES.length >= 6, 'экранов на выбор хватает на весь продукт')
eq(new Set(PLACES.map((p) => p.code)).size, PLACES.length, 'коды экранов не повторяются')

console.log()
console.log(failed ? `ПРОВАЛОВ: ${failed}` : 'ВСЁ ЗЕЛЕНО')
if (failed) process.exit(1)
