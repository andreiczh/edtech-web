/**
 * Экран «Разговор с носителем» по новому макету (фото 1 и 2).
 *
 * Фото 1 — покой: круги, микрофон, подпись «Нажми на микрофон и говори».
 * Фото 2 — после ответа: между кругами и микрофоном появляется карточка с ответом.
 *
 * Что просил пользователь и почему сделано именно так:
 *  - реплику ученика НЕ дублируем на экране: он только что её произнёс, а место
 *    на мобильном дорогое. Расшифровка нужна для отладки, поэтому она ушла в
 *    служебную строку под ответом вместе с таймингами;
 *  - префикса «Ответ от ИИ» нет — в карточке сразу текст;
 *  - если ответ длинный, прокручивается САМА карточка (max-height + overflow),
 *    иначе кнопка микрофона уезжала бы за нижнюю панель.
 *
 * Темы разговора на экране НЕТ и не должно быть (решение владельца,
 * 04.08.2026): человек говорит о чём хочет, а подстраивается система. Полоса с
 * названием темы стояла здесь один день — она задавала рамку там, где рамка не
 * нужна. Как система держит глубину разговора без темы — backend/dialogue.py.
 */
import { useCallback, useState } from 'react'

import { useSettings } from '../account/me'
import { Disagree } from '../components/Disagree'
import { MicButton } from '../components/MicButton'
import { BottomBar } from '../design/ui'
import { ReviewCard } from '../talk/ReviewCard'
import { requestTalkReview, type TalkReview } from '../talk/review'
import { useConversation, type ConversationState } from '../useConversation'

const CAPTIONS: Record<ConversationState, string> = {
  idle: 'Нажми на микрофон и говори',
  listening: 'Слушаю…',
  processing: 'Думаю…',
  speaking: 'Отвечаю…',
}

/** Столько реплик нужно, чтобы разбор имел смысл (то же число на сервере).
    Меньше — и разбирать нечего, а запрос к модели стоит столько же. */
const MIN_TURNS_FOR_REVIEW = 3

export function ConversationScreen({ onFeedback }: { onFeedback: () => void }) {
  const { state, toggle, transcript, reply, error, latency, turns, endSession, getHistory } =
    useConversation()
  /* Режим «чисто аудио» (настройка кабинета): карточка с текстом ответа не
     рисуется вовсе — только круги и голос, как в живом разговоре. Ошибки
     показываются ВСЕГДА: молчание вместо объяснения — худший из отказов. */
  const { showText } = useSettings()

  const [review, setReview] = useState<TalkReview | null>(null)
  const [reviewing, setReviewing] = useState(false)
  const [reviewError, setReviewError] = useState<string | null>(null)

  const runReview = useCallback(async () => {
    if (reviewing) return
    setReviewing(true)
    setReviewError(null)
    try {
      setReview(await requestTalkReview(getHistory()))
    } catch (e) {
      setReviewError(e instanceof Error ? e.message : String(e))
    } finally {
      setReviewing(false)
    }
  }, [getHistory, reviewing])

  const canReview = turns >= MIN_TURNS_FOR_REVIEW

  /* Шапку с тумблером рисует App: она общая для верхних экранов и не
     пересоздаётся при переключении вкладок — в этом и есть «бесшовность». */
  return (
    <div className="screenbody">
      <div className="screen__body">
        {((showText && reply) || error || reviewError) && (
          <div className="card2 answer scroll-soft" aria-live="polite">
            {error || reviewError ? (
              <p className="dialog__err">{error ?? reviewError}</p>
            ) : (
              <>
                <p>{reply}</p>

                {/* Слот под телеметрию: скорость сервера, стадии и расшифровка.
                    Пользователь просил оставить его видимым на время отладки. */}
                <div className="answer__meta">
                  {latency && (
                    <>
                      {/* first_audio теперь считается сервером ОТ ПРИХОДА
                          запроса (03.08.2026) — это и есть пауза, складывать
                          со stt больше нельзя: задвоило бы распознавание. */}
                      <span>
                        пауза до ответа <b>{latency.first_audio.toFixed(2)}s</b>
                      </span>
                      <span>распознавание {latency.stt}s</span>
                      <span>
                        ответ и озвучка{' '}
                        {Math.max(0, latency.first_audio - latency.stt).toFixed(2)}s
                      </span>
                      <span>сервер всего {latency.total}s</span>
                    </>
                  )}
                  {transcript && <span>распознано: «{transcript}»</span>}
                </div>

                {/* Жалоба на КОНКРЕТНУЮ реплику — прямо под ней и прямо сейчас.
                    До разбора в конце беседы человек это забудет, а «ответил не
                    на то» без самой пары реплик починить невозможно. Разговор
                    на сервере не хранится: сюда его хвост попадает только по
                    этому нажатию, о чём форма предупреждает. */}
                <Disagree
                  label="ответ невпопад?"
                  ctx={{
                    kind: 'talk',
                    target: 'talk_reply',
                    targetLabel: 'Реплика собеседника',
                    transcript: `Ученик: ${transcript || '—'}\nСобеседник: ${reply}`,
                    context: { turns: getHistory().slice(-6) },
                  }}
                />
              </>
            )}
          </div>
        )}

        {/* Сцена кружков: в покое и при ответе — ряд над микрофоном, во время
            записи — орбита вокруг него (см. .orbstage в ui.css). Сцена — обычный
            блок фиксированных пропорций, кружки за неё не вылезают и соседние
            блоки не перекрывают. */}
        <div className={`orbstage orbstage--${state}`} aria-hidden="false">
          <div className="orbstage__ring" aria-hidden="true">
            {[1, 2, 3, 4].map((i) => (
              <span key={i} className={`orbstage__orb orbstage__orb--${i}`} />
            ))}
          </div>
          <div className="orbstage__mic">
            <MicButton state={state} onToggle={toggle} />
          </div>
        </div>
      </div>

      {/* QUIT здесь некуда: разговор — корневой экран, выходить из него не во
          что. Левый слот отдан разбору — он появляется, только когда набралось
          что разбирать, чтобы кнопка никогда не жгла запрос впустую. */}
      <BottomBar
        caption={CAPTIONS[state]}
        onFeedback={onFeedback}
        onQuit={canReview ? runReview : undefined}
        quitLabel={reviewing ? 'Разбираю…' : 'Разбор'}
        quitIcon={null}
      />

      {review && (
        <ReviewCard
          review={review}
          history={getHistory()}
          onClose={() => setReview(null)}
          onNewTopic={() => {
            setReview(null)
            endSession()
          }}
        />
      )}
    </div>
  )
}
