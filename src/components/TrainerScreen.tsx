import { VoiceOrbs } from './VoiceOrbs'
import { MicButton } from './MicButton'
import { useConversation, type ConversationState } from '../useConversation'

const CAPTIONS: Record<ConversationState, string> = {
  idle: 'Нажми на микрофон и говори',
  listening: 'Слушаю…',
  processing: 'Думаю…',
  speaking: 'Отвечаю…',
}

export function TrainerScreen() {
  const { state, toggle, transcript, reply, error } = useConversation()

  return (
    <div className="stage">
      <VoiceOrbs state={state} />

      <div className="controls">
        <p className={`caption caption--${state}`}>{CAPTIONS[state]}</p>
        <MicButton state={state} onToggle={toggle} />
      </div>

      {/* Расшифровка/ответ/ошибка — плавающий блок снизу, не сдвигает композицию. */}
      <div className="dialog" aria-live="polite">
        {error ? (
          <p className="dialog__err">{error}</p>
        ) : (
          <>
            {transcript && <p className="dialog__you">Ты: {transcript}</p>}
            {reply && <p className="dialog__ai">ИИ: {reply}</p>}
          </>
        )}
      </div>
    </div>
  )
}
