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
import { BottomBar } from '../design/ui'
import { useConversation, type ConversationState } from '../useConversation'

const CAPTIONS: Record<ConversationState, string> = {
  idle: 'Нажми на микрофон и говори',
  listening: 'Слушаю…',
  processing: 'Думаю…',
  speaking: 'Отвечаю…',
}

export function ConversationScreen({ onFeedback }: { onFeedback: () => void }) {
  const { state, toggle, transcript, reply, error, latency } = useConversation()

  /* Шапку с тумблером рисует App: она общая для верхних экранов и не
     пересоздаётся при переключении вкладок — в этом и есть «бесшовность». */
  return (
    <div className="screenbody">
      <div className="screen__body">
        <VoiceOrbs state={state} />

        {(reply || error) && (
          <div className="card2 answer scroll-soft" aria-live="polite">
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

      {/* QUIT здесь некуда: разговор — корневой экран, выходить из него не во
          что. Кнопки без смысла быть не должно. */}
      <BottomBar caption={CAPTIONS[state]} onFeedback={onFeedback} />
    </div>
  )
}
