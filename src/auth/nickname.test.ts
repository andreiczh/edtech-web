/**
 * Тесты генератора ников (16.09.2026).
 *
 * Запуск: npm run test. Ник стоит на главной под приветствием и обязан быть
 * длиннее любого из них — и по буквам, и по знакам с пробелом.
 */
import { GREETINGS } from '../account/greeting.ts'
import { NICK_MAX, NICK_MIN, randomNickname } from './nickname.ts'

let failed = 0

function ok(cond: boolean, name: string, detail = ''): void {
  if (cond) {
    console.log(`OK   ${name}`)
  } else {
    failed += 1
    console.log(`FAIL ${name}${detail ? `\n     ${detail}` : ''}`)
  }
}

const N = 3000
const seen = new Set<string>()
let bad = ''
for (let i = 0; i < N; i++) {
  const nick = randomNickname()
  seen.add(nick)
  if (!/^[A-Z][a-z]+[A-Z][a-z]+$/.test(nick) || nick.length < NICK_MIN || nick.length > NICK_MAX) {
    bad = nick
    break
  }
}
ok(!bad, `${N} ников: два слова с заглавной, только буквы, от ${NICK_MIN} до ${NICK_MAX}`, bad)

const longestChars = Math.max(...GREETINGS.map((g) => g.length))
const longestLetters = Math.max(...GREETINGS.map((g) => g.replace(/[^A-Za-z]/g, '').length))
ok(NICK_MIN > longestChars, `ник длиннее самого длинного приветствия со всеми пробелами (${longestChars} знаков)`)
ok(NICK_MIN > longestLetters, `и по буквам (${longestLetters})`)
ok(seen.size > N * 0.5, `ники не повторяются по кругу: ${seen.size} разных из ${N}`)

if (failed) throw new Error(`ПРОВАЛОВ: ${failed}`)
console.log('\nВСЁ ЗЕЛЁНОЕ')
