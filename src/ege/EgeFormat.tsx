import { useState } from 'react'
import { VariantPicker } from './VariantPicker'
import { EgeTrainer } from './EgeTrainer'

/**
 * «Ответ в формате ЕГЭ»: сначала экран выбора варианта, затем — прохождение
 * экзамена по уже прописанной логике. Выход возвращает к выбору варианта.
 */
export function EgeFormat() {
  const [variant, setVariant] = useState<string | null>(null)

  if (variant === null) {
    return <VariantPicker onStart={setVariant} />
  }
  return <EgeTrainer variant={variant} onExit={() => setVariant(null)} />
}
