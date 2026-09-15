/**
 * Избранные задания: звёздочка в правом верхнем углу задания — и в серии
 * тренажёра, и в демо-варианте — и «избранный вариант» из отмеченного.
 *
 * Источник правды — сервер (/me/favorites): избранное следует за аккаунтом
 * между устройствами, как прогресс и настройки. localStorage — кэш под
 * аккаунт, чтобы звёздочки рисовались сразу и без сети. Логика без
 * хранилища (дубли, порядок варианта) — в favoritesCore.ts, там её тест.
 */
import { useSyncExternalStore } from 'react'

import { currentUser, identityId } from '../auth/auth'
import { favoriteSession, withFavorite, type FavoriteItem } from './favoritesCore'
import { TASKS, variantById, type TaskId } from './tasks'

const BACKEND = (import.meta.env.VITE_BACKEND_URL ?? '').replace(/\/+$/, '')

/* Кэш — у каждого аккаунта свой: за общим компьютером следующий человек не
   должен увидеть чужие звёздочки даже до ответа сервера. */
const cacheKey = (owner: string) => `gospeak.favorites.v1:${owner}`

function isItem(x: unknown): x is FavoriteItem {
  if (!x || typeof x !== 'object') return false
  const f = x as Record<string, unknown>
  return typeof f.taskId === 'number' && typeof f.variantId === 'string' && typeof f.at === 'string'
}

function readCache(owner: string): FavoriteItem[] {
  try {
    const raw = localStorage.getItem(cacheKey(owner))
    const arr: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(arr) ? arr.filter(isItem) : []
  } catch {
    return []
  }
}

let owner = identityId()
let current: FavoriteItem[] = readCache(owner)
const listeners = new Set<() => void>()

function publish(list: FavoriteItem[]) {
  current = list
  try {
    localStorage.setItem(cacheKey(owner), JSON.stringify(list))
  } catch {
    /* приватный режим: избранное проживёт до перезагрузки */
  }
  listeners.forEach((cb) => cb())
}

/** Вошёл другой человек — переключаемся на его кэш. */
function followOwner() {
  const id = identityId()
  if (id === owner) return
  owner = id
  current = readCache(owner)
  listeners.forEach((cb) => cb())
}

export function useFavorites(): FavoriteItem[] {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    () => current,
  )
}

export function isFavorite(list: FavoriteItem[], variantId: string): boolean {
  return list.some((f) => f.variantId === variantId)
}

function fromServer(x: unknown): FavoriteItem | null {
  if (!x || typeof x !== 'object') return null
  const f = x as Record<string, unknown>
  const item = { taskId: Number(f.task_id), variantId: String(f.variant_id ?? ''), at: String(f.at ?? '') }
  return item.variantId && Number.isFinite(item.taskId) ? item : null
}

function listFrom(data: unknown): FavoriteItem[] | null {
  const items = (data as { items?: unknown } | null)?.items
  if (!Array.isArray(items)) return null
  return items.map(fromServer).filter((f): f is FavoriteItem => f !== null)
}

/** При старте и после входа: избранное аккаунта побеждает кэш. */
export async function syncFavorites(): Promise<void> {
  followOwner()
  if (!currentUser()) return
  try {
    const res = await fetch(`${BACKEND}/me/favorites`, { headers: { 'X-Device': identityId() } })
    if (!res.ok) return
    const list = listFrom(await res.json())
    if (list) publish(list)
  } catch {
    /* без сети остаётся кэш */
  }
}

/**
 * Звёздочка: на экране — сразу, потом на сервер. Сервер не принял — звёздочка
 * честно возвращается как была: избранное, которое молча не сохранилось,
 * хуже, чем кнопка, которая не сработала. true — сохранилось.
 */
export async function toggleFavorite(taskId: TaskId, variantId: string, on: boolean): Promise<boolean> {
  followOwner()
  const before = current
  publish(withFavorite(current, { taskId, variantId }, on))
  if (!currentUser()) return true
  try {
    const res = await fetch(`${BACKEND}/me/favorites`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Device': identityId() },
      body: JSON.stringify({ task_id: taskId, variant_id: variantId, on }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const list = listFrom(await res.json())
    if (list) publish(list)
    return true
  } catch {
    publish(before)
    return false
  }
}

/** Серия «Избранный вариант»: варианты, которых нет в банке или которые
    закрыты «скоро», в неё не попадают. */
export function favoriteSessionItems(): Array<{ taskId: TaskId; variantId: string }> {
  followOwner()
  return favoriteSession(current, (f) => {
    const task = TASKS[f.taskId as TaskId]
    return !!task && !task.comingSoon && !!variantById(f.taskId as TaskId, f.variantId)
  }) as Array<{ taskId: TaskId; variantId: string }>
}
