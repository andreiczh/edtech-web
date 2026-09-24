/**
 * Разговор с собеседником — макет «66 · Redesign 39» (24.09.2026): аватар,
 * четыре круга, карточка с текстом, круглая кнопка микрофона; во вкладках
 * на этом экране — микрофон. Логика та же, что на настольной
 * (`useConversation`): круги живут состоянием разговора (слушаю / думаю /
 * отвечаю — те же ключевые кадры, что в index.css), карточка показывает
 * ответ собеседника (если в настройках включён текст), а разбор беседы
 * появляется с третьей реплики — как и на настольной, раньше разбирать нечего.
 */
import { useCallback, useState, type CSSProperties } from 'react'

import { useSettings } from '../account/me'
import { ReviewCard } from '../talk/ReviewCard'
import { requestTalkReview, type TalkReview } from '../talk/review'
import { useConversation, type ConversationState } from '../useConversation'
import { Ambient, Icon } from './Ambient'
import { ICONS } from './icons'

const LABELS: Record<ConversationState, string> = {
  idle: 'Начать говорить',
  listening: 'Остановить запись',
  processing: 'ИИ думает',
  speaking: 'Перебить и ответить',
}

/** Что стоит в карточке, пока ответа нет: в покое — подпись из макета. */
const CAPTIONS: Record<ConversationState, string> = {
  idle: 'Начните говорить...',
  listening: 'Слушаю…',
  processing: 'Думаю…',
  speaking: 'Отвечаю…',
}

/** Столько реплик нужно, чтобы разбор имел смысл (то же число на сервере). */
const MIN_TURNS_FOR_REVIEW = 3

export function MiniTalk() {
  const { state, toggle, transcript, reply, error, turns, endSession, getHistory } = useConversation()
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
  const shownReply = showText && reply && (state === 'speaking' || state === 'idle') ? reply : ''
  const text = error ?? reviewError ?? shownReply ?? ''
  const body = text || CAPTIONS[state]
  const isCaption = !text

  return (
    <>
      <Ambient />
      <div className="t-ava" role="img" aria-label="Аватар" />

      <div className={`t-orbs t-orbs--${state}`} aria-hidden="true">
        {[0, 1, 2, 3].map((i) => (
          <span key={i} className={`t-orb t-orb--${i + 1}`} style={{ '--i': i } as CSSProperties} />
        ))}
      </div>

      <div className={`t-card${isCaption ? ' t-card--caption' : ''}${error || reviewError ? ' t-card--error' : ''}`} role="status" aria-live="polite">
        <p className="t-text">{body}</p>
        {shownReply && transcript && !error && <p className="t-heard">распознано: «{transcript}»</p>}
        {canReview && !review && (
          <button type="button" className="m-btn t-review" onClick={() => void runReview()} disabled={reviewing}>
            {reviewing ? 'Разбираю…' : 'Разбор беседы'}
          </button>
        )}
      </div>

      <button
        type="button"
        className={`m-btn t-mic t-mic--${state}`}
        onClick={toggle}
        disabled={state === 'processing'}
        aria-label={LABELS[state]}
        aria-pressed={state === 'listening'}
      >
        <Icon icon={ICONS.micBig} />
      </button>

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
    </>
  )
}
