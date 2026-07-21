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
  const { state, toggle, transcript, reply, error, latency } = useConversation()

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
            {latency && (
              // «Пауза» = stt + first_audio. Показывать один first_audio нельзя:
              // он считается ПОСЛЕ распознавания, то есть занижает реальное
              // ожидание студента примерно на 20-30%. total — не пауза вообще,
              // это когда сервер доделал ПОСЛЕДНЮЮ фразу, поэтому подписан честно.
              <p className="dialog__lat">
                пауза до ответа: {(latency.stt + latency.first_audio).toFixed(2)}s
                {' '}(stt {latency.stt}s + {latency.first_audio}s) · сервер отработал
                за {latency.total}s
              </p>
            )}
          </>
        )}
      </div>
    </div>
  )
}
