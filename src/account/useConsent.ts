import { useState } from 'react'
import { setCorpusConsent, useSettings } from './me'

/** Shared by desktop and MAX/mobile. A failed save leaves the real value visible. */
export function useConsent() {
  const { corpusConsent } = useSettings()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const toggle = async () => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await setCorpusConsent(!corpusConsent)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить согласие.')
    } finally {
      setBusy(false)
    }
  }
  return { busy, error, toggle }
}
