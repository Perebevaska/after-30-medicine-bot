import { useSyncExternalStore } from 'react'

// Бейдж «новых ачивок» на вкладке «Прогресс»: храним коды уже увиденных ачивок
// в localStorage. Новые = unlocked − seen. Помечаем увиденными при открытии
// вкладки. useSyncExternalStore отдаёт стабильный снапшот (cache) — без петель.
const KEY = 'seen_achievements'
const listeners = new Set<() => void>()

function load(): string[] {
  try { return JSON.parse(localStorage.getItem(KEY) || '[]') } catch { return [] }
}

let cache: string[] = load()

export function markAchievementsSeen(codes: string[]) {
  const next = new Set(cache)
  let changed = false
  for (const c of codes) if (!next.has(c)) { next.add(c); changed = true }
  if (!changed) return
  cache = [...next]
  localStorage.setItem(KEY, JSON.stringify(cache))
  listeners.forEach((l) => l())
}

export function useSeenAchievements(): string[] {
  return useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => { listeners.delete(cb) } },
    () => cache,
  )
}
