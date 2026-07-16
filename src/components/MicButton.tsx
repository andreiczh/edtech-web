import type { ConversationState } from '../useConversation'

const LABELS: Record<ConversationState, string> = {
  idle: 'Начать говорить',
  listening: 'Остановить запись',
  processing: 'ИИ думает',
  speaking: 'Перебить и ответить',
}

export function MicButton({
  state,
  onToggle,
}: {
  state: ConversationState
  onToggle: () => void
}) {
  const active = state === 'listening'

  return (
    <button
      type="button"
      className={`mic mic--${state}${active ? ' mic--active' : ''}`}
      onClick={onToggle}
      disabled={state === 'processing'}
      aria-label={LABELS[state]}
      aria-pressed={active}
    >
      {active && (
        <>
          <span className="mic__ring" />
          <span className="mic__ring mic__ring--delay" />
        </>
      )}
      <svg className="mic__icon" viewBox="0 0 42 42" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path
          fillRule="evenodd"
          clipRule="evenodd"
          d="M21 4c-1.6 0-3.1.6-4.2 1.8A6 6 0 0 0 15 10v7.5a6 6 0 0 0 12 0V10a6 6 0 0 0-1.8-4.2A6 6 0 0 0 21 4ZM10.5 16c.4 0 .8.2 1.1.4.3.3.4.7.4 1.1a9 9 0 0 0 18 0c0-.4.2-.8.4-1.1a1.5 1.5 0 0 1 2.6 1.1 12 12 0 0 1-10.5 11.9v3.6a1.5 1.5 0 0 1-3 0v-3.6A12 12 0 0 1 9 17.5c0-.4.2-.8.4-1.1.3-.2.7-.4 1.1-.4Z"
          fill="currentColor"
        />
      </svg>
    </button>
  )
}
