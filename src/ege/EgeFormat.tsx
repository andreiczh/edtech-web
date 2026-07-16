import { useState } from 'react'
import { VariantPicker } from './VariantPicker'
import { EgeTrainer } from './EgeTrainer'

/**
 * «Ответ в формате ЕГЭ»: выбор варианта → прохождение экзамена → результат.
 * Пройденные варианты запоминаются (в рамках сессии) и отмечаются в списке.
 */
export function EgeFormat() {
  const [variant, setVariant] = useState<number | null>(null)
  const [solved, setSolved] = useState<number[]>([])

  if (variant === null) {
    return <VariantPicker onStart={setVariant} solved={solved} />
  }

  return (
    <EgeTrainer
      variant={variant}
      onExit={() => setVariant(null)}
      onComplete={() => setSolved((s) => (s.includes(variant) ? s : [...s, variant]))}
    />
  )
}
