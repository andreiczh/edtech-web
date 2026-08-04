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
import { useMemo, useState } from 'react'

import { reportDispute, type Delivery, type TaskFeedback } from '../ege2/feedback'
import { TASKS, type TaskId } from '../ege2/tasks'
import { highlightPieces } from '../ege2/selection'

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

/**
 * «Как это прозвучало» — единственный блок на ИЗМЕРЕНИЯХ звука: темп и паузы
 * посчитаны по пословным таймкодам, а не выданы моделью. Первая попытка
 * (спросить модель) провалилась — она отвечала одинаково на любую запись,
 * см. DECISIONS §6.5. Оценки произношения тут нет и не будет: пословная
 * вероятность распознавания не фонетика, выдавать её за неё — тот же обман.
 * Блока нет — значит замер выключен или не удался; молчим, а не выдумываем.
 */
function DeliveryBlock({ d }: { d?: Delivery }) {
  if (!d) return null
  const PACE: Record<string, string> = { slow: 'медленно', ok: 'ровный', fast: 'быстро' }
  return (
    <div className="card2 resblock">
      <h3 className="resblock__title">КАК ЭТО ПРОЗВУЧАЛО</h3>
      <div className="pair">
        <div className="pair__side">
          <span className="pair__label">темп</span>
          <span className={d.pace === 'ok' ? 'pair__ok' : 'pair__wrong'}>
            {d.wpm} слов/мин · {PACE[d.pace] ?? d.pace}
          </span>
        </div>
        <div className="pair__side">
          <span className="pair__label">заминки</span>
          <span className={d.pause_count === 0 ? 'pair__ok' : 'pair__wrong'}>
            {d.pause_count === 0 ? 'нет' : d.pause_count}
          </span>
        </div>
        <div className="pair__side">
          <span className="pair__label">звучало</span>
          <span>{d.seconds} с</span>
        </div>
      </div>
      {d.pauses.length > 0 && (
        <p className="pair__why">
          Самые долгие:{' '}
          {d.pauses.map((p) => `${p.sec} с после «${p.after}»`).join(', ')}.
        </p>
      )}
      {d.comment && <p className="pair__why">{d.comment}</p>}
    </div>
  )
}

function ReadingResult({
  feedback,
  reference,
}: {
  feedback: TaskFeedback
  reference: string
}) {
  const pieces = useMemo(
    () => highlightPieces(reference, feedback.errors ?? []),
    [reference, feedback],
  )
  const errors = feedback.errors ?? []

  /* Подсвеченный кусок теперь можно нажать и увидеть, ЧТО с ним не так.
     Раньше подсветка была немой: цвет есть, объяснения нет — жалоба
     тестировщика 05.08.2026 («при нажатии на слово нет пояснения»).
     Ищем разбор по тому же фрагменту, которым кусок и был помечен. */
  const [openPiece, setOpenPiece] = useState<string | null>(null)
  const explainOf = (text: string) => {
    const key = text.trim().toLowerCase()
    const hit = errors.find((e) => (e.correction || '').trim().toLowerCase() === key)
    if (!hit) return null
    return hit.explanation
      ? hit.explanation
      : hit.cat === 'missing'
        ? 'этого куска в записи нет — он не прозвучал'
        : 'здесь прозвучало не то, что написано'
  }

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
          <span className="legend__item legend__hint">нажми на подсветку — покажу, что не так</span>
        </div>
        <p className="reftext">
          {pieces.map((p, i) =>
            p.mark ? (
              <mark
                key={i}
                className={`hl hl--${p.mark} hl--tappable`}
                role="button"
                tabIndex={0}
                onClick={() => setOpenPiece(openPiece === p.text ? null : p.text)}
                onKeyDown={(ev) => {
                  if (ev.key === 'Enter' || ev.key === ' ') {
                    ev.preventDefault()
                    setOpenPiece(openPiece === p.text ? null : p.text)
                  }
                }}
              >
                {p.text}
              </mark>
            ) : (
              <span key={i}>{p.text}</span>
            ),
          )}
        </p>
        {openPiece && (
          <p className="hlnote">
            <b>«{openPiece}»</b> — {explainOf(openPiece) ?? 'разбор не оставил пояснения к этому куску'}
          </p>
        )}
        <p className="resnote">
          Балл считается по сверке с текстом. Произношение и акцент не оцениваем —
          проверить это нечем, а выдуманная оценка хуже её отсутствия.
        </p>
      </div>

      <DeliveryBlock d={feedback.delivery} />

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

  return (
    <>
      {items.map((c, i) => {
        const failed = !c.score
        return (
          <section className="qsection" key={c.key || i}>
            <h3 className="qsection__title">
              {label} №{i + 1}
            </h3>
            {/* «Ваш ответ» — это ВСЕГДА то, что человек сказал, а не вердикт
                проверки. Раньше у зачтённого пункта здесь стоял комментарий
                модели («вопрос засчитан, грамматика верна»), и свой ответ
                перечитать было негде — жалоба тестировщика 05.08.2026. */}
            <div className={`card2 qcard${failed ? ' qcard--bad' : ''}`}>
              <div className="pair">
                <div className="pair__side">
                  <span className="pair__label">ваш ответ</span>
                  <span className={failed ? 'pair__wrong' : ''}>
                    {c.quote || (failed ? '— не прозвучал —' : '—')}
                  </span>
                </div>
                <div className="pair__side">
                  <span className="pair__label">{failed ? 'правильно' : 'итог'}</span>
                  {failed ? (
                    <span className="pair__right">{c.correction || 'не засчитан'}</span>
                  ) : (
                    <span className="pair__ok">Засчитан. Так держать!</span>
                  )}
                </div>
              </div>
              {c.comment && <p className="pair__why">{c.comment}</p>}
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

/** «Не согласен с оценкой» — одна тихая строка под разбором, не мешает
    чтению. Вместе с жалобой уходит расшифровка ответа (по явному нажатию —
    единственный случай, когда транскрипт сохраняется). */
function DisputeRow({
  taskId,
  feedback,
  transcript,
  variantId,
}: {
  taskId: TaskId
  feedback: TaskFeedback
  transcript?: string
  variantId?: string
}) {
  const [state, setState] = useState<'idle' | 'sending' | 'done' | 'fail'>('idle')
  if (!transcript) return null // без расшифровки жалоба бесполезна для разбора

  if (state === 'done')
    return <p className="dispute dispute--done">Отправлено — этот разбор пересмотрят.</p>

  return (
    <p className="dispute">
      {state === 'fail' && 'Не ушло — попробуй ещё раз. '}
      <button
        type="button"
        className="dispute__btn"
        disabled={state === 'sending'}
        onClick={() => {
          setState('sending')
          void reportDispute({
            kind: TASKS[taskId].kind,
            variant: variantId,
            score: feedback.score,
            max: feedback.max,
            transcript,
            feedback,
          }).then((ok) => setState(ok ? 'done' : 'fail'))
        }}
      >
        {state === 'sending' ? 'Отправляю…' : 'Не согласен с оценкой'}
      </button>
    </p>
  )
}

export function ResultView({
  taskId,
  feedback,
  transcript,
  reference,
  audioUrl,
  variantId,
}: {
  taskId: TaskId
  feedback: TaskFeedback
  transcript?: string
  reference?: string
  audioUrl?: string | null
  variantId?: string
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

      <DisputeRow
        taskId={taskId}
        feedback={feedback}
        transcript={transcript}
        variantId={variantId}
      />
    </div>
  )
}
