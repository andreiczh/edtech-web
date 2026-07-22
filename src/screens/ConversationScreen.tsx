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
 */
import { MicButton } from '../components/MicButton'
import { VoiceOrbs } from '../components/VoiceOrbs'
import { BottomBar, Pill, TopBar, type TopTab } from '../design/ui'
import { useConversation, type ConversationState } from '../useConversation'

const CAPTIONS: Record<ConversationState, string> = {
  idle: 'Нажми на микрофон и говори',
  listening: 'Слушаю…',
  processing: 'Думаю…',
  speaking: 'Отвечаю…',
}

export function ConversationScreen({
  tabs,
  activeTab,
  onTab,
  onProfile,
  onQuit,
  onFeedback,
}: {
  tabs: TopTab[]
  activeTab: string
  onTab: (id: string) => void
  onProfile: () => void
  onQuit: () => void
  onFeedback: () => void
}) {
  const { state, toggle, transcript, reply, error, latency } = useConversation()

  return (
    <div className="screen">
      <TopBar tabs={tabs} active={activeTab} onTab={onTab} onProfile={onProfile} />

      <div className="rowend" style={{ justifyContent: 'center' }}>
        <Pill title="Ограничить время разговора — появится позже">Таймер</Pill>
      </div>

      <div className="screen__body">
        <VoiceOrbs state={state} />

        {(reply || error) && (
          <div className="card2 answer glass" aria-live="polite">
            {error ? (
              <p className="dialog__err">{error}</p>
            ) : (
              <>
                <p>{reply}</p>

                {/* Слот под телеметрию: скорость сервера, стадии и расшифровка.
                    Пользователь просил оставить его видимым на время отладки. */}
                <div className="answer__meta">
                  {latency && (
                    <>
                      <span>
                        пауза до ответа{' '}
                        <b>{(latency.stt + latency.first_audio).toFixed(2)}s</b>
                      </span>
                      <span>распознавание {latency.stt}s</span>
                      <span>ответ и озвучка {latency.first_audio}s</span>
                      <span>сервер всего {latency.total}s</span>
                    </>
                  )}
                  {transcript && <span>распознано: «{transcript}»</span>}
                </div>
              </>
            )}
          </div>
        )}

        <MicButton state={state} onToggle={toggle} />
      </div>

      <BottomBar caption={CAPTIONS[state]} onQuit={onQuit} onFeedback={onFeedback} />
    </div>
  )
}
