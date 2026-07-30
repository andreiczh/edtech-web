/**
 * Экран результата задания — по макету владельца от 30.07.2026.
 *
 * У четырёх заданий устной части ответы устроены по-разному, поэтому и разбор
 * показывается по-разному:
 *   №39 — эталонный текст с подсветкой того, что ученик не прочитал или переврал;
 *   №40 и №41 — построчно по каждому вопросу: засчитан или нет и почему;
 *   №42 — три критерия ФИПИ, расшифровка ответа и комментарий по каждому критерию.
 *
 * ВСЁ, ЧТО ЗДЕСЬ ПОКАЗАНО, ПРИХОДИТ С СЕРВЕРА. Экран ничего не досочиняет: если
 * данных нет, блок не рисуется. Это важнее красоты — ученик принимает решения по
 * этим цифрам.
 *
 * Чего на экране НЕТ и почему (на макете это было, но данных не существует):
 *   - транскрипции произношения вида [trʌŋk] и пометок об интонации. Разбор
 *     работает с текстовой расшифровкой речи, звука он не слышит, и выдумывать
 *     фонетические ошибки промпты прямо запрещают;
 *   - «мини тренировки» — такой фичи в продукте пока нет.
 */
import { useMemo } from 'react'

import type { TaskFeedback } from '../ege2/feedback'
import type { TaskId } from '../ege2/tasks'

/* Кольцо с баллом. Заполняется долей набранного — это первое, что ищет глаз. */
function ScoreRing({ score, max }: { score: number; max: number }) {
  const share = max > 0 ? Math.max(0, Math.min(1, score / max)) : 0
  const R = 52
  const len = 2 * Math.PI * R
  return (
    <div className="ring">
      <svg viewBox="0 0 120 120" className="ring__svg" aria-hidden="true">
        <circle className="ring__track" cx="60" cy="60" r={R} />
        <circle
          className="ring__fill"
          cx="60"
          cy="60"
          r={R}
          style={{ strokeDasharray: len, strokeDashoffset: len * (1 - share) }}
        />
      </svg>
      <div className="ring__inner">
        <div className="ring__score">{score}</div>
        <div className="ring__max">из {max} {max === 1 ? 'балла' : 'баллов'}</div>
      </div>
    </div>
  )
}

/** Проигрыватель своей записи. Файл живёт только во вкладке: на сервере записи
    речи не хранятся — ученики несовершеннолетние, отдельного согласия нет. */
function OwnRecording({ url }: { url: string | null }) {
  if (!url) return null
  return <audio className="player" src={url} controls preload="metadata" />
}

/* --------------------------------------------------- №39: чтение вслух */

interface Piece {
  text: string
  mark?: 'missing' | 'misread'
}

/** Режет эталонный текст на куски и помечает те, что ученик пропустил или
    прочитал иначе. Ищем по фрагменту из разбора (correction) — это ровно тот
    кусок эталона, к которому у проверяющего возникли вопросы. */
function highlight(reference: string, feedback: TaskFeedback): Piece[] {
  const marks: Array<{ from: number; to: number; mark: 'missing' | 'misread' }> = []
  for (const e of feedback.errors ?? []) {
    const needle = (e.correction || '').trim()
    if (needle.length < 2) continue
    const at = reference.toLowerCase().indexOf(needle.toLowerCase())
    if (at < 0) continue
    const mark = e.cat === 'missing' ? 'missing' : 'misread'
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

function ReadingResult({
  feedback,
  reference,
}: {
  feedback: TaskFeedback
  reference: string
}) {
  const pieces = useMemo(() => highlight(reference, feedback), [reference, feedback])
  const errors = feedback.errors ?? []

  return (
    <>
      <div className="card2 resblock">
        <div className="legend">
          <span className="legend__item">
            <i className="legend__chip legend__chip--missing" /> пропущено
          </span>
          <span className="legend__item">
            <i className="legend__chip legend__chip--misread" /> прочитано иначе
          </span>
        </div>
        <p className="reftext">
          {pieces.map((p, i) =>
            p.mark ? (
              <mark key={i} className={`hl hl--${p.mark}`}>
                {p.text}
              </mark>
            ) : (
              <span key={i}>{p.text}</span>
            ),
          )}
        </p>
        <p className="resnote">
          Произношение и интонацию разбор не слышит — он сверяет расшифровку с эталоном.
        </p>
      </div>

      {errors.length > 0 && (
        <div className="card2 resblock">
          {errors.map((e, i) => (
            <div className="pair" key={i}>
              <div className="pair__side">
                <span className="pair__label">вы прочитали</span>
                <span className="pair__wrong">{e.quote || '— пропущено —'}</span>
              </div>
              <div className="pair__side">
                <span className="pair__label">в тексте</span>
                <span className="pair__right">{e.correction}</span>
              </div>
              {e.explanation && <p className="pair__why">{e.explanation}</p>}
            </div>
          ))}
        </div>
      )}
    </>
  )
}

/* ------------------------------------------ №40 и №41: по одному вопросу */

function ItemsResult({
  feedback,
  label,
}: {
  feedback: TaskFeedback
  label: 'ВОПРОС' | 'ОТВЕТ'
}) {
  const items = feedback.criteria ?? []
  const errors = feedback.errors ?? []

  return (
    <>
      {items.map((c, i) => {
        // Ошибку к вопросу подбираем по порядку: сервер кладёт их в том же
        // порядке, в каком не зачёл вопросы.
        const err = errors.filter((e) => e.quote)[
          items.slice(0, i).filter((x) => !x.score).length
        ]
        const failed = !c.score
        return (
          <section className="qsection" key={c.key || i}>
            <h3 className="qsection__title">
              {label} №{i + 1}
            </h3>
            <div className={`card2 qcard${failed ? ' qcard--bad' : ''}`}>
              <div className="pair">
                <div className="pair__side">
                  <span className="pair__label">ваш ответ</span>
                  <span className={failed ? 'pair__wrong' : ''}>
                    {failed && err?.quote ? err.quote : c.comment || '—'}
                  </span>
                </div>
                <div className="pair__side">
                  <span className="pair__label">{failed ? 'правильно' : 'итог'}</span>
                  {failed ? (
                    <span className="pair__right">{err?.correction || 'не засчитан'}</span>
                  ) : (
                    <span className="pair__ok">Засчитан. Так держать!</span>
                  )}
                </div>
              </div>
              {failed && c.comment && <p className="pair__why">{c.comment}</p>}
            </div>
          </section>
        )
      })}
    </>
  )
}

/* ------------------------------------------------------- №42: монолог */

function MonologueResult({
  feedback,
  transcript,
}: {
  feedback: TaskFeedback
  transcript?: string
}) {
  const criteria = feedback.criteria ?? []
  return (
    <>
      {transcript && (
        <div className="card2 resblock">
          <h3 className="resblock__title">РАСШИФРОВКА</h3>
          <p className="reftext">{transcript}</p>
        </div>
      )}
      {criteria.length > 0 && (
        <div className="card2 resblock">
          <h3 className="resblock__title">КОММЕНТАРИЙ</h3>
          {criteria.map((c, i) => (
            <div className="crit" key={c.key || i}>
              <div className="crit__head">
                <span className="crit__no">{i + 1}</span>
                <span className="crit__name">{c.name}</span>
                <span className="crit__score">
                  {c.score} из {c.max}
                </span>
              </div>
              {c.comment && <p className="crit__text">{c.comment}</p>}
            </div>
          ))}
        </div>
      )}
      {(feedback.errors?.length ?? 0) > 0 && (
        <div className="card2 resblock">
          {feedback.errors.map((e, i) => (
            <div className="pair" key={i}>
              <div className="pair__side">
                <span className="pair__label">вы сказали</span>
                <span className="pair__wrong">{e.quote}</span>
              </div>
              <div className="pair__side">
                <span className="pair__label">лучше</span>
                <span className="pair__right">{e.correction || '—'}</span>
              </div>
              {e.explanation && <p className="pair__why">{e.explanation}</p>}
            </div>
          ))}
        </div>
      )}
    </>
  )
}

/* ------------------------------------------------------------- сборка */

export function ResultView({
  taskId,
  feedback,
  transcript,
  reference,
  audioUrl,
}: {
  taskId: TaskId
  feedback: TaskFeedback
  transcript?: string
  reference?: string
  audioUrl?: string | null
}) {
  const criteria = feedback.criteria ?? []
  // У №40 и №41 критерии — это сами вопросы, их место в шапке, а не в кольце.
  const perItem = taskId === 40 || taskId === 41

  return (
    <div className="result">
      <div className="card2 resthead">
        <ScoreRing score={feedback.score} max={feedback.max} />
        <div className="resthead__mid">
          {perItem &&
            criteria.map((c, i) => (
              <div className="verdict" key={c.key || i}>
                <span className="verdict__name">
                  {taskId === 40 ? 'ВОПРОС' : 'ОТВЕТ'} №{i + 1}
                </span>
                <span className={c.score ? 'verdict__ok' : 'verdict__bad'}>
                  {c.score ? 'засчитан' : 'не засчитан'}
                </span>
              </div>
            ))}
          {taskId === 42 &&
            criteria.map((c, i) => (
              <div className="verdict" key={c.key || i}>
                <span className="verdict__name">{c.name}</span>
                <span className="verdict__ok">
                  {c.score} из {c.max}
                </span>
              </div>
            ))}
        </div>
        <OwnRecording url={audioUrl ?? null} />
      </div>

      {feedback.summary && (
        <div className="card2 resblock">
          <p style={{ margin: 0 }}>{feedback.summary}</p>
        </div>
      )}

      {taskId === 39 && reference && (
        <ReadingResult feedback={feedback} reference={reference} />
      )}
      {taskId === 40 && <ItemsResult feedback={feedback} label="ВОПРОС" />}
      {taskId === 41 && <ItemsResult feedback={feedback} label="ОТВЕТ" />}
      {taskId === 42 && <MonologueResult feedback={feedback} transcript={transcript} />}
    </div>
  )
}
