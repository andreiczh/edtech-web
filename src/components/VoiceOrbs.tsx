import type { ConversationState } from '../useConversation'

/**
 * Четыре круга-индикатора. Анимация зависит от состояния:
 *  - listening → «эквалайзер»: круги дёргано растягиваются по вертикали (говорит юзер)
 *  - speaking  → «волна»: плавно пульсируют со сдвигом по фазе (отвечает ИИ)
 *  - processing→ синхронный быстрый пульс («думает»)
 *  - idle      → почти неподвижны, лёгкое дыхание
 */
export function VoiceOrbs({ state }: { state: ConversationState }) {
  return (
    <div className={`orbs orbs--${state}`} aria-hidden="true">
      {[0, 1, 2, 3].map((i) => (
        <span key={i} className={`orb orb--${i + 1}`} style={{ '--i': i } as React.CSSProperties} />
      ))}
    </div>
  )
}
