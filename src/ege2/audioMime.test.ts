/**
 * Тесты подписи записи с микрофона (15.09.2026).
 *
 * Запуск: npm run test. Имя файла подсказывает серверу, чем открыть запись,
 * а iPhone пишет mp4 — до этой правки любая запись уходила как .webm.
 */
import { audioFileName, pickRecorderMime } from './audioMime.ts'

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

const CASES: [string, string][] = [
  ['audio/webm;codecs=opus', 'speech.webm'],
  ['audio/webm', 'speech.webm'],
  ['audio/mp4', 'speech.m4a'],
  ['audio/mp4;codecs=mp4a.40.2', 'speech.m4a'],
  ['audio/aac', 'speech.aac'],
  ['audio/ogg;codecs=opus', 'speech.ogg'],
  ['audio/wav', 'speech.wav'],
  ['audio/mpeg', 'speech.mp3'],
  ['', 'speech.webm'],
]

for (const [type, want] of CASES) {
  eq(audioFileName('speech', new Blob([], { type })), want, `тип «${type || 'пусто'}» -> ${want}`)
}

eq(pickRecorderMime(), undefined, 'без MediaRecorder (node) формат не выбирается')

if (failed) throw new Error(`ПРОВАЛОВ: ${failed}`)
console.log('\nВСЁ ЗЕЛЁНОЕ')
