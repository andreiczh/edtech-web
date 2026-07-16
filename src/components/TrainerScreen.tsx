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
  const { state, toggle } = useConversation()

  return (
    <div className="stage">
      <VoiceOrbs state={state} />

      <div className="controls">
        <p className={`caption caption--${state}`}>{CAPTIONS[state]}</p>
        <MicButton state={state} onToggle={toggle} />
      </div>
    </div>
  )
}
