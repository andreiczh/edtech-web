/**
 * «Не согласен» — форма несогласия с ИИ. Одна на все экраны.
 *
 * Почему форма, а не кнопка. Кнопка «не согласен» сообщает один бит: где-то
 * не так. Чтобы что-то ПОЧИНИТЬ, нужны четыре вещи — с чем спорим, из-за чего,
 * каким должен быть балл и что человек имел в виду словами. Первое подставляет
 * экран (`ctx`), остальные спрашиваем, и без них форма не отправляется:
 * полупустая жалоба не суммируется с другими и не проверяется, то есть занимает
 * место в копилке, ничего в неё не добавляя.
 *
 * Три экранных правила, выстраданных на этом продукте:
 *  - причина выбирается ОДНИМ нажатием из готовых вариантов. Свободный текст
 *    как единственное поле люди пропускают, а из «всё плохо» вывод не сделать;
 *  - подсказка под кнопкой всегда говорит, чего не хватает, — кнопка не может
 *    быть просто серой и молчаливой;
 *  - что именно уедет вместе с жалобой, написано прямым текстом. Речь ученика
 *    сохраняется ТОЛЬКО здесь и только по этому нажатию — человек должен
 *    понимать, что он отдаёт.
 *
 * Модалка через createPortal в document.body: у панелей продукта backdrop-filter,
 * а он делает элемент контейнером для position: fixed — вложенная модалка
 * проваливается внутрь панели (эти грабли в проекте уже собирали, см. src/CLAUDE.md).
 */
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import {
  EMPTY_DRAFT,
  PLACES,
  formProblem,
  reasonsFor,
  type DisputeContext,
  type DisputeDraft,
} from '../ege2/dispute'
import { sendDispute } from '../ege2/feedback'
import { imageFromPaste, prepareShot, type Shot } from '../ege2/screenshot'

/** Что уедет на сервер — словами, по объекту спора. Врать тут нельзя. */
function whatGoes(ctx: DisputeContext): string {
  switch (ctx.target) {
    case 'talk_reply':
      return 'Вместе с жалобой уйдут последние реплики этого разговора — иначе разобраться в них нечем.'
    case 'talk_review':
      return 'Вместе с жалобой уйдут разговор и его разбор — иначе пересмотреть спор нечем.'
    case 'app':
      return 'К отзыву приложатся модель браузера и размер экрана — без них «не работает» невозможно повторить. Снимок экрана увидит только владелец.'
    default:
      return 'Вместе с жалобой уйдут расшифровка твоего ответа, текст задания и сам разбор — иначе пересмотреть оценку нечем.'
  }
}

export function DisagreeModal({
  ctx,
  onClose,
  onSent,
}: {
  ctx: DisputeContext
  onClose: () => void
  onSent: () => void
}) {
  const [draft, setDraft] = useState<DisputeDraft>(EMPTY_DRAFT)
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [shot, setShot] = useState<Shot | null>(null)
  const [shotBusy, setShotBusy] = useState(false)
  const firstRef = useRef<HTMLButtonElement | null>(null)
  const fileRef = useRef<HTMLInputElement | null>(null)

  /* Один путь для всех трёх способов приложить снимок: кнопка, перетаскивание
     и Ctrl+V. Сжатие живёт в screenshot.ts — форме о нём знать незачем. */
  const takeFile = (file: File | Blob | null | undefined) => {
    if (!file) return
    setShotBusy(true)
    setError(null)
    void prepareShot(file).then((res) => {
      setShotBusy(false)
      if (res.shot) setShot(res.shot)
      else if (res.error) setError(res.error)
    })
  }

  useEffect(() => {
    firstRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const reasons = reasonsFor(ctx.target)
  const max = ctx.max ?? 0
  const needScore = max > 0
  // Экран спрашиваем только в общем отзыве: у спора об оценке место известно
  // из контекста, а отзыв приходит «из ниоткуда».
  const needPlace = ctx.target === 'app'
  const problem = formProblem(draft, { score: needScore, place: needPlace })
  const hint = reasons.find((r) => r.code === draft.reason)?.hint ?? 'Что именно не так'
  const notice = whatGoes(ctx)

  const submit = () => {
    if (problem || sending) return
    setSending(true)
    setError(null)
    // Выбранный экран уезжает тем же полем, что и место спора у оценки: в
    // админке всё группируется одинаково, отдельной колонки не нужно.
    const place = PLACES.find((p) => p.code === draft.place)
    const full: DisputeContext = place
      ? { ...ctx, targetKey: place.code, targetLabel: `Отзыв · ${place.label}` }
      : ctx
    void sendDispute(full, draft, shot && { data: shot.data, mime: shot.mime }).then((res) => {
      setSending(false)
      if (res.ok) {
        setSent(true)
        onSent()
      } else setError(res.error ?? 'Не ушло — попробуй ещё раз.')
    })
  }

  /* Подтверждение — экраном, а не исчезновением модалки: человек только что
     потратил минуту на объяснение и должен видеть, что оно дошло, а не гадать. */
  if (sent)
    return createPortal(
      <div className="modal-backdrop" onClick={onClose}>
        <div className="modal dsg dsg--thanks" role="dialog" aria-modal="true">
          <p className="dsg__thanks">Спасибо. Разберём этот случай руками.</p>
          <p className="dsg__thankswhy">
            Такие жалобы — единственный способ научить проверку не ошибаться
            дважды в одном месте.
          </p>
          <button type="button" className="pill pressable" onClick={onClose}>
            Закрыть
          </button>
        </div>
      </div>,
      document.body,
    )

  return createPortal(
    <div
      className="modal-backdrop"
      onClick={() => {
        // Клик мимо закрывает только пустую форму: терять набранный текст
        // случайным промахом — верный способ больше жалоб не получать.
        if (!draft.comment.trim()) onClose()
      }}
    >
      <div
        className="modal dsg"
        role="dialog"
        aria-modal="true"
        aria-labelledby="dsg-title"
        onClick={(e) => e.stopPropagation()}
        /* Вставка и перетаскивание ловятся на ВСЕЙ модалке, а не на кнопке:
           человек со снимком в буфере жмёт Ctrl+V там, где стоит курсор, и
           попадать при этом в маленькую зону не обязан. */
        onPaste={(e) => {
          const file = imageFromPaste(e.nativeEvent)
          if (file) {
            e.preventDefault()
            takeFile(file)
          }
        }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          const file = e.dataTransfer?.files?.[0]
          if (file) {
            e.preventDefault()
            takeFile(file)
          }
        }}
      >
        <header className="dsg__head">
          <h2 className="dsg__title" id="dsg-title">
            Что не так?
          </h2>
          {ctx.targetLabel && <span className="dsg__where">{ctx.targetLabel}</span>}
        </header>

        <div className="dsg__scroll scroll-soft">
          <fieldset className="dsg__block">
            <legend className="dsg__legend">В чём дело</legend>
            <div className="dsg__chips">
              {reasons.map((r, i) => (
                <button
                  key={r.code}
                  ref={i === 0 ? firstRef : undefined}
                  type="button"
                  className={`dsg__chip${draft.reason === r.code ? ' dsg__chip--on' : ''}`}
                  aria-pressed={draft.reason === r.code}
                  onClick={() => setDraft({ ...draft, reason: r.code })}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </fieldset>

          {needPlace && (
            <fieldset className="dsg__block">
              <legend className="dsg__legend">Где это случилось</legend>
              <div className="dsg__chips">
                {PLACES.map((p) => (
                  <button
                    key={p.code}
                    type="button"
                    className={`dsg__chip${draft.place === p.code ? ' dsg__chip--on' : ''}`}
                    aria-pressed={draft.place === p.code}
                    onClick={() => setDraft({ ...draft, place: p.code })}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </fieldset>
          )}

          {needScore && (
            <fieldset className="dsg__block">
              <legend className="dsg__legend">
                Каким должен быть балл{' '}
                <span className="dsg__now">
                  сейчас {ctx.score ?? 0} из {max}
                </span>
              </legend>
              <div className="dsg__chips">
                {Array.from({ length: max + 1 }, (_, n) => (
                  <button
                    key={n}
                    type="button"
                    className={`dsg__score${draft.claimScore === n ? ' dsg__chip--on' : ''}`}
                    aria-pressed={draft.claimScore === n}
                    onClick={() => setDraft({ ...draft, claimScore: n })}
                  >
                    {n}
                  </button>
                ))}
                {/* Спорить можно и не о балле: объяснение бывает неверным при
                    верной цифре. Без этой кнопки человек ставил бы балл наугад,
                    и копилка наполнялась бы враньём. */}
                <button
                  type="button"
                  className={`dsg__chip${draft.claimScore === -1 ? ' dsg__chip--on' : ''}`}
                  aria-pressed={draft.claimScore === -1}
                  onClick={() => setDraft({ ...draft, claimScore: -1 })}
                >
                  дело не в балле
                </button>
              </div>
            </fieldset>
          )}

          {draft.reason === 'misheard' && (
            <fieldset className="dsg__block">
              <legend className="dsg__legend">Что ты сказал на самом деле</legend>
              {/* Единственное поле, ради которого стоит спрашивать вообще: пара
                  «что записали — что было сказано» это готовый замер ошибки
                  распознавания, а не мнение. */}
              <input
                className="auth-input dsg__input"
                value={draft.said}
                onChange={(e) => setDraft({ ...draft, said: e.target.value })}
                placeholder="твоими словами, по-английски"
              />
            </fieldset>
          )}

          <fieldset className="dsg__block">
            <legend className="dsg__legend">Расскажи подробнее</legend>
            <textarea
              className="auth-input dsg__area"
              value={draft.comment}
              onChange={(e) => setDraft({ ...draft, comment: e.target.value })}
              placeholder={hint}
              rows={3}
            />
          </fieldset>

          {/* Снимок экрана. Показать быстрее, чем описать: «кнопка не
              нажимается» и скриншот этой кнопки — две разные по полезности
              жалобы. Необязателен: требовать картинку значило бы отсекать всех,
              кто не умеет её делать. */}
          <fieldset className="dsg__block">
            <legend className="dsg__legend">
              Снимок экрана <span className="dsg__now">по желанию</span>
            </legend>
            {shot ? (
              <div className="dsg__shot">
                <img className="dsg__shotimg" src={shot.url} alt="Снимок экрана" />
                <div className="dsg__shotside">
                  <span className="dsg__now">{Math.round(shot.bytes / 1024)} КБ</span>
                  <button
                    type="button"
                    className="dsg__chip"
                    onClick={() => {
                      setShot(null)
                      if (fileRef.current) fileRef.current.value = ''
                    }}
                  >
                    Убрать
                  </button>
                </div>
              </div>
            ) : (
              <div className="dsg__chips">
                <button
                  type="button"
                  className="dsg__chip"
                  disabled={shotBusy}
                  onClick={() => fileRef.current?.click()}
                >
                  {shotBusy ? 'Готовлю…' : '📎 Выбрать картинку'}
                </button>
                <span className="dsg__now">или перетащи сюда, или вставь через Ctrl+V</span>
              </div>
            )}
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg"
              hidden
              onChange={(e) => takeFile(e.target.files?.[0])}
            />
          </fieldset>

          {notice && <p className="dsg__notice">{notice}</p>}
          {error && <p className="dsg__error">{error}</p>}
        </div>

        <footer className="dsg__foot">
          <span className="dsg__problem">{problem ?? 'Готово к отправке'}</span>
          <span className="dsg__buttons">
            <button type="button" className="pill pressable dsg__ghost" onClick={onClose}>
              Отмена
            </button>
            <button
              type="button"
              className="pill pressable"
              disabled={!!problem || sending}
              onClick={submit}
            >
              {sending ? 'Отправляю…' : 'Отправить'}
            </button>
          </span>
        </footer>
      </div>
    </div>,
    document.body,
  )
}

/**
 * Кнопка-ссылка рядом со спорным местом плюс сама форма.
 *
 * Нарочно тихая: жалоба не должна конкурировать с «Дальше» и «Ещё раз», но
 * обязана быть ровно там, где возникает несогласие. Одна общая кнопка внизу
 * экрана этого не даёт — по ней невозможно понять, о каком из пяти вопросов
 * речь, и именно эта привязка к месту делает копилку пригодной для калибровки.
 */
export function Disagree({
  ctx,
  label = 'не согласен',
  block = false,
}: {
  ctx: DisputeContext
  label?: string
  /** Отдельной строкой по центру (под разбором целиком), а не в углу блока. */
  block?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [sent, setSent] = useState(false)
  const sentOnce = useRef(false)

  if (sent)
    return (
      <p className={block ? 'dispute dispute--done' : 'dsg__link dsg__link--done'}>
        Спасибо — разберём.
      </p>
    )

  return (
    <>
      {block ? (
        <p className="dispute">
          <button type="button" className="dispute__btn" onClick={() => setOpen(true)}>
            {label}
          </button>
        </p>
      ) : (
        <button type="button" className="dsg__link" onClick={() => setOpen(true)}>
          ⚑ {label}
        </button>
      )}
      {open && (
        <DisagreeModal
          ctx={ctx}
          onClose={() => {
            setOpen(false)
            // Отправленную жалобу не предлагаем отправить второй раз: копилка
            // не должна наполняться дублями одного и того же спора.
            if (sentOnce.current) setSent(true)
          }}
          onSent={() => {
            sentOnce.current = true
          }}
        />
      )}
    </>
  )
}
