/**
 * Разбор задания №39 — макет «66 · Redesign 36» один в один.
 *
 * Что показываем честно, из того, что система реально меряет:
 *  - балл по шкале (кольцо: мятное — балл есть, коралловое — ноль) и текст
 *    разбора с сервера; строка «N ошибок из 2, искажающих смысл» — по счёту
 *    грубых ошибок сервера (misread_words);
 *  - запись ученика: плеер с волной, посчитанной из самого файла;
 *  - текст задания с подсветкой найденного: коралловая — прочитано другое
 *    слово (искажает смысл), персиковая — неверная форма слова (ближе к
 *    фонетике), контур — пропущенный кусок; нажатие на подсветку открывает
 *    карточку слова снизу: что услышано и как правильно, кнопка озвучки;
 *  - абзацы: текущий — крупно, остальные — серым; текущий следует за
 *    воспроизведением или нажатием.
 * Транскрипций IPA в системе нет — в карточке слова стоят сами слова.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import { isFavorite, toggleFavorite, useFavorites } from '../ege2/favorites'
import type { FeedbackError, TaskFeedback } from '../ege2/feedback'
import { sayWord, speakable } from '../ege2/sayWord'
import type { TaskId, TaskVariant } from '../ege2/tasks'
import { audioPeaks, type Peaks } from './audioPeaks'
import { Ambient, Icon } from './Ambient'
import { BackButton, MiniDisagree } from './ResultBits'
import { DeliveryCard, SummaryCard, disputeBase, WeakWordsCard } from './ResultExtras'
import { ICONS } from './icons'

const BARS = 58
const u = (v: number) => `calc(${v} * var(--u))`
const fmt2 = (s: number) => {
  const v = Math.max(0, Math.floor(Number.isFinite(s) ? s : 0))
  return `${String(Math.floor(v / 60)).padStart(2, '0')}:${String(v % 60).padStart(2, '0')}`
}

type Kind = 'sense' | 'phon' | 'skip'
interface Mark {
  from: number
  to: number
  kind: Kind
  err: FeedbackError
}

function markKind(e: FeedbackError): Kind {
  // Пропуск: сервер помечает cat=missing, а модель иногда пишет «пропущено»
  // в поле услышанного — это тот же пропуск, а не «прочитано другое слово».
  if (e.cat === 'missing' || /^пропущен/i.test(e.quote || '')) return 'skip'
  if (/форм[аы] слова|окончани/i.test(e.explanation)) return 'phon'
  return 'sense'
}

/** Позиции ошибок в эталоне — по слову из эталона (correction), как в ResultView. */
/** Текст без регистра и знаков препинания + карта «нормализованный индекс →
    исходный»: сервер цитирует пропущенный кусок без запятых, а в эталоне
    они есть, и по буквам это один и тот же фрагмент. */
function normalized(s: string): { text: string; map: number[] } {
  let text = ''
  const map: number[] = []
  for (let i = 0; i < s.length; i++) {
    const ch = s[i].toLowerCase()
    if (/[\p{L}\p{N}']/u.test(ch)) {
      text += ch
      map.push(i)
    } else if (/\s/.test(ch) && text.length && text[text.length - 1] !== ' ') {
      text += ' '
      map.push(i)
    }
  }
  return { text, map }
}

function findMarks(reference: string, errors: FeedbackError[]): Mark[] {
  const ref = normalized(reference)
  const marks: Mark[] = []
  for (const e of errors) {
    const needle = normalized(e.correction || '').text.trim()
    if (needle.length < 2) continue
    const at = ref.text.indexOf(needle)
    if (at < 0) continue
    const from = ref.map[at]
    const to = ref.map[at + needle.length - 1] + 1
    if (marks.some((m) => from < m.to && to > m.from)) continue
    marks.push({ from, to, kind: markKind(e), err: e })
  }
  return marks.sort((a, b) => a.from - b.from)
}

/** Текст на три части по предложениям (макет: два серых абзаца и текущий). */
function paragraphs(text: string): Array<{ from: number; to: number }> {
  const sentences: Array<{ from: number; to: number }> = []
  const re = /[^.!?]+[.!?]+["»']?\s*|[^.!?]+$/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    if (m[0].trim()) sentences.push({ from: m.index, to: m.index + m[0].length })
    if (!m[0].length) re.lastIndex++
  }
  if (sentences.length <= 2) return [{ from: 0, to: text.length }]
  const parts = Math.min(3, sentences.length)
  const target = text.length / parts
  const out: Array<{ from: number; to: number }> = []
  let start = 0
  let acc = 0
  for (let i = 0; i < sentences.length; i++) {
    acc += sentences[i].to - sentences[i].from
    const last = i === sentences.length - 1
    if ((acc >= target && out.length < parts - 1) || last) {
      out.push({ from: start, to: last ? text.length : sentences[i].to })
      start = sentences[i].to
      acc = 0
    }
  }
  return out
}

export function Player({
  blob,
  seconds,
  onProgress,
}: {
  blob: Blob
  seconds: number
  onProgress: (f: number) => void
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [url] = useState(() => URL.createObjectURL(blob))
  const [peaks, setPeaks] = useState<Peaks | null>(null)
  const [playing, setPlaying] = useState(false)
  const [pos, setPos] = useState(0)
  useEffect(() => () => URL.revokeObjectURL(url), [url])
  useEffect(() => {
    let alive = true
    void audioPeaks(blob, BARS).then((p) => alive && setPeaks(p))
    return () => {
      alive = false
    }
  }, [blob])
  const total = peaks?.seconds && Number.isFinite(peaks.seconds) ? peaks.seconds : seconds
  const bars = peaks?.bars ?? Array.from({ length: BARS }, () => 0.3)

  const toggle = () => {
    const a = audioRef.current
    if (!a) return
    if (a.paused) void a.play().catch(() => setPlaying(false))
    else a.pause()
  }
  return (
    <div className="r-player">
      <audio
        ref={audioRef}
        src={url}
        preload="auto"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => {
          setPlaying(false)
          setPos(0)
          onProgress(0)
        }}
        onTimeUpdate={(e) => {
          const t = e.currentTarget.currentTime
          setPos(t)
          if (total > 0) onProgress(Math.min(1, t / total))
        }}
      />
      <button
        type="button"
        className="m-btn r-play"
        onClick={toggle}
        aria-label={playing ? 'Пауза' : 'Слушать запись'}
      >
        {playing ? (
          <span className="r-play__pause" aria-hidden="true">
            <i />
            <i />
          </span>
        ) : (
          <Icon icon={ICONS.play} />
        )}
      </button>
      <svg className="r-wave" viewBox="0 0 64 17.7" aria-hidden="true">
        {bars.map((v, i) => {
          const h = 4.6 + (17.6 - 4.6) * v
          const x = 0.3 + i * 1.113
          return <line key={i} x1={x} x2={x} y1={8.85 - h / 2} y2={8.85 + h / 2} />
        })}
      </svg>
      <span className="r-time">
        {fmt2(pos)} / {fmt2(total)}
      </span>
    </div>
  )
}

function plural(n: number): string {
  const d = n % 10
  const dd = n % 100
  if (d === 1 && dd !== 11) return 'ошибка'
  if (d >= 2 && d <= 4 && (dd < 12 || dd > 14)) return 'ошибки'
  return 'ошибок'
}

export function ResultScreen({
  no,
  taskId,
  variant,
  feedback,
  transcript,
  failure,
  blob,
  seconds,
  onQuit,
  onNext,
  onBack,
}: {
  no: number
  taskId: TaskId
  variant: TaskVariant
  feedback: TaskFeedback | null
  transcript?: string
  failure: string | null
  blob: Blob | null
  seconds: number
  onQuit: () => void
  onNext: () => void
  onBack?: () => void
}) {
  const reference = variant.readText ?? transcript ?? ''
  const dispute = feedback ? disputeBase(taskId, variant, feedback, transcript) : null
  const errors = useMemo(() => feedback?.errors ?? [], [feedback])
  const marks = useMemo(() => findMarks(reference, errors), [reference, errors])
  const paras = useMemo(() => paragraphs(reference), [reference])
  const paraOf = useCallback(
    (pos: number) => Math.max(0, paras.findIndex((p) => pos >= p.from && pos < p.to)),
    [paras],
  )
  const [sel, setSel] = useState<Mark | null>(marks[0] ?? null)
  const [cur, setCur] = useState(() => (marks[0] ? paraOf(marks[0].from) : 0))
  const [saying, setSaying] = useState(false)
  const favs = useFavorites()
  const fav = isFavorite(favs, variant.id)
  const trRef = useRef<HTMLDivElement | null>(null)
  const [bar, setBar] = useState<{ top: number; height: number }>({ top: 0, height: 0 })

  // Серая полоса слева: где сейчас текущий абзац внутри всего текста.
  useEffect(() => {
    const box = trRef.current
    if (!box) return
    const p = box.querySelectorAll<HTMLElement>('.r-p')[cur]
    const total = box.offsetHeight
    if (!p || !total) return
    setBar({ top: (p.offsetTop / total) * 100, height: (p.offsetHeight / total) * 100 })
  }, [cur, reference])

  const onProgress = useCallback(
    (f: number) => {
      if (f <= 0) return
      setCur(paraOf(Math.floor(f * reference.length)))
    },
    [paraOf, reference.length],
  )

  const say = () => {
    if (!sel || saying) return
    setSaying(true)
    void sayWord(sel.err.correction, variant.id).finally(() => setSaying(false))
  }

  const score = feedback?.score ?? null
  const max = feedback?.max ?? 1
  const misread = feedback?.misread_words ?? errors.length
  const ringClass =
    feedback === null ? 'r-ring--none' : score !== null && score >= max ? '' : 'r-ring--zero'

  const renderPara = (p: { from: number; to: number }, i: number) => {
    const inside = marks.filter((m) => m.from < p.to && m.to > p.from)
    const nodes: ReactNode[] = []
    let cursor = p.from
    for (const m of inside) {
      const from = Math.max(m.from, p.from)
      const to = Math.min(m.to, p.to)
      if (from > cursor) nodes.push(reference.slice(cursor, from))
      const pick = (e: React.SyntheticEvent) => {
        e.stopPropagation()
        setSel(m)
        setCur(i)
      }
      nodes.push(
        <span
          key={`${m.from}-${m.kind}`}
          className={`r-mark r-mark--${m.kind}`}
          role="button"
          tabIndex={0}
          title={m.kind === 'skip' ? 'Пропущено при чтении' : m.err.explanation}
          onClick={pick}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              pick(e)
            }
          }}
        >
          {reference.slice(from, to)}
        </span>,
      )
      cursor = to
    }
    if (cursor < p.to) nodes.push(reference.slice(cursor, p.to))
    return (
      <button
        key={i}
        type="button"
        className={`m-btn r-p${i === cur ? ' r-p--cur' : ''}`}
        onClick={() => setCur(i)}
        aria-current={i === cur ? 'true' : undefined}
      >
        {nodes}
      </button>
    )
  }

  return (
    <div className="mini__frame">
      <Ambient />
      {onBack && <BackButton onBack={onBack} />}
      <button
        type="button"
        className={`m-btn r-star${fav ? ' r-star--on' : ''}`}
        aria-pressed={fav}
        aria-label={fav ? 'Убрать задание из избранного' : 'Добавить задание в избранное'}
        onClick={() => void toggleFavorite(taskId, variant.id, !fav)}
      >
        <Icon icon={ICONS.star} />
      </button>
      <div className="mini__scroll">
        <span className="m-label">ЗАДАНИЕ {no}</span>

        <div className="r-summary">
          <div className={`r-ring ${ringClass}`} aria-hidden="true" />
          <div className="r-score" aria-hidden="true">
            {score ?? '—'}
          </div>
          <div className="r-of" aria-hidden="true">
            из {max} {max === 1 ? 'балла' : 'баллов'}
          </div>
          <span className="m-sr">
            Балл: {score ?? 'нет'} из {max}.
          </span>
          {feedback ? (
            <>
              {feedback.summary}{' '}
              <b>
                {misread} {plural(misread)}
              </b>{' '}
              из 2, искажающих смысл
            </>
          ) : (
            (failure ?? 'Разбор не выполнен.')
          )}
          {blob && <Player blob={blob} seconds={seconds} onProgress={onProgress} />}
        </div>

        {feedback && reference && (
          <>
            <div className="r-legend" aria-hidden="true">
              <span className="r-legend__item">
                <i className="r-chip r-chip--sense" />— ошибки, искажающие смысл
              </span>
              <span className="r-legend__item">
                <i className="r-chip r-chip--phon" />— фонетические ошибки
              </span>
            </div>

            <div className="r-tr" ref={trRef}>
              <div className="r-bar" aria-hidden="true">
                <i style={{ top: `${bar.top}%`, height: `${bar.height}%` }} />
              </div>
              {paras.map(renderPara)}
            </div>
          </>
        )}

        {sel && (
          <div className="r-word">
            <div className="r-word__w">{sel.err.correction}</div>
            <button
              type="button"
              className="m-btn r-say"
              onClick={say}
              disabled={saying || !speakable(sel.err.correction)}
              aria-label="Послушать, как читается слово"
            >
              <Icon icon={ICONS.speaker} />
            </button>
            <div className="r-box r-box--l">
              <span className="r-box__k">вы произнесли</span>
              <span className="r-box__v r-box__v--heard">
                {sel.kind === 'skip' ? '—' : sel.err.quote}
              </span>
            </div>
            <div className="r-box r-box--r">
              <span className="r-box__k">правильно</span>
              <span className="r-box__v r-box__v--right">{sel.err.correction}</span>
            </div>
          </div>
        )}
        {sel && dispute && (
          <MiniDisagree
            center
            label="это не ошибка"
            ctx={{
              ...dispute,
              target: 'error',
              targetKey: (sel.err.quote || sel.err.correction).slice(0, 40),
              targetLabel: `«${sel.kind === 'skip' ? 'пропущено' : sel.err.quote}» → «${sel.err.correction}»`,
            }}
          />
        )}
        {feedback && <DeliveryCard d={feedback.delivery} />}
        {feedback && <WeakWordsCard variantId={variant.id} />}
        {feedback && <SummaryCard feedback={{ ...feedback, summary: '' }} />}
        {dispute && <MiniDisagree center label="не согласен с баллом" ctx={dispute} />}
        <div className="m-pad" />
      </div>

      <div className="m-bar">
        <button type="button" className="m-btn m-round" style={{ left: u(19.7) }} onClick={onQuit}>
          QUIT
        </button>
        <button type="button" className="m-btn r-next-hit" onClick={onNext} aria-label="К следующему заданию">
          <span className="r-next" aria-hidden="true">
            К СЛЕДУЮЩЕМУ ЗАДАНИЮ
          </span>
          <Icon icon={ICONS.arrowNext} className="r-next-arrow" />
        </button>
      </div>
    </div>
  )
}
