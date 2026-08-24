/**
 * Тесты допуска к озвучке слова (№39).
 *
 * Главное, что здесь проверяется, — СОВПАДЕНИЕ С СЕРВЕРОМ. Правила живут в
 * двух местах (`backend/speak_check.py` и `speakable.ts`), и разъехаться им
 * нельзя: кнопка либо появится там, где сервер откажет, либо пропадёт там,
 * где всё бы работало. Набор случаев ниже — тот же, что в
 * `backend/test_speak_check.py`.
 *
 * Запуск: npm run test
 */
import { MAX_CHARS, MAX_TOKENS, speakable, wordsOf } from './speakable.ts'

let failed = 0

function ok(cond: boolean, name: string): void {
  if (cond) {
    console.log(`OK   ${name}`)
  } else {
    failed += 1
    console.log(`FAIL ${name}`)
  }
}

/* --- что озвучиваем ---------------------------------------------------- */
for (const good of ['observed', 'lifespan', 'medium-sized', "can't", 'they can not',
                    '  Parrots  ', 'have been observed']) {
  ok(speakable(good), `слово проходит: ${JSON.stringify(good.trim())}`)
}

/* --- что не озвучиваем ------------------------------------------------- */
for (const [bad, why] of [
  ['', 'пусто'],
  ['   ', 'одни пробелы'],
  ['Привет, как дела', 'кириллица'],
  ['one two three four', 'четыре слова'],
  ['Buy cheap pills now!', 'знаки препинания'],
  ['12345', 'цифры'],
  ['a.b', 'точка внутри'],
  ['antidisestablishmentarianism antidisestablishmentarianism', 'длиннее потолка'],
] as Array<[string, string]>) {
  ok(!speakable(bad), `отклоняется (${why})`)
}

/* --- разбор на слова: ровно как на сервере ------------------------------ */
// Апостроф НЕ разделяет слово, дефис — разделяет. Разъедется — «can't»
// станет двумя словами, а «medium-sized» одним, и потолок в три слова
// начнёт срабатывать не там.
ok(JSON.stringify(wordsOf("can't")) === JSON.stringify(["can't"]),
   "апостроф не разбивает слово: can't — одно слово")
ok(JSON.stringify(wordsOf('medium-sized')) === JSON.stringify(['medium', 'sized']),
   'дефис разбивает слово: medium-sized — два слова')
ok(JSON.stringify(wordsOf('“observed”')) === JSON.stringify(['observed']),
   'кавычки отбрасываются')
ok(JSON.stringify(wordsOf("’tis")) === JSON.stringify(['tis']),
   'апостроф по краю срезается')

/* --- потолки заявлены теми же числами, что на сервере ------------------- */
ok(MAX_CHARS === 48, 'потолок знаков совпадает с серверным (48)')
ok(MAX_TOKENS === 3, 'потолок слов совпадает с серверным (3)')
// «can't be» — два слова по счёту сервера, и оно обязано проходить.
ok(speakable("can't be bought"), 'три слова с апострофом проходят')

console.log('')
if (failed > 0) {
  console.log(`ПРОВАЛЕНО: ${failed}`)
  process.exit(1)
}
console.log('Всё сошлось: правила озвучки те же, что на сервере.')
