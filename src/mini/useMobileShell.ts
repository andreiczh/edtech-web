/**
 * Когда показывать мини-оболочку (макеты «iPhone 16 & 17 Pro») вместо
 * настольного каркаса с рейлом: всегда при запуске из MAX (там окно
 * телефонное и в настольном клиенте), в любом окне уже 820 px — настольная
 * главная ниже этого не читается (масштаб 0.23 на телефоне, §6.35) — и по
 * адресу с `?mini`: так телефонную версию смотрят с компьютера
 * (https://pingo-ai-dpd9.onrender.com/?mini), оболочка встаёт колонкой 430 px
 * посередине окна.
 */
import { useEffect, useState } from 'react'

import { isMaxLaunch } from '../max/bridge'

const QUERY = '(max-width: 820px), (max-width: 1024px) and (max-height: 500px)'

function forcedByUrl(): boolean {
  try {
    return new URLSearchParams(window.location.search).has('mini')
  } catch {
    return false
  }
}

export function useMobileShell(locked = false): boolean {
  const [narrow, setNarrow] = useState(() => window.matchMedia(QUERY).matches)
  useEffect(() => {
    if (locked) return // resizing/rotation must not unmount an active recording
    const mq = window.matchMedia(QUERY)
    setNarrow(mq.matches)
    const cb = (e: MediaQueryListEvent) => setNarrow(e.matches)
    mq.addEventListener('change', cb)
    return () => mq.removeEventListener('change', cb)
  }, [locked])
  return narrow || forcedByUrl() || isMaxLaunch()
}
