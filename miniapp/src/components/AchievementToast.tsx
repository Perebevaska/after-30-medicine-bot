import { useEffect, useState } from 'react'
import { useStatsOverview } from '../api/hooks'
import { Toast } from './Toast'
import { AchMedal } from './AchMedal'

// Коды, по которым тост уже поставлен в очередь в этой сессии — защита от повтора
// при рефетче overview (newly остаётся в кэше React Query).
const _toasted = new Set<string>()

// Глобальный тост достижения: рендерится на уровне App → виден на любой вкладке.
// Сам тянет /stats/overview (общий кэш с StatsPage). Несколько новых ачивок —
// очередь: показываем по одной, закрытие крестиком открывает следующую.
// Постоянный (без авто-скрытия).
export function AchievementToast() {
  const { data: overview } = useStatsOverview()
  const block = overview?.achievements
  const [queue, setQueue] = useState<{ code: string; title: string }[]>([])

  useEffect(() => {
    if (!block) return
    const fresh = block.newly.filter((c) => !_toasted.has(c))
    if (fresh.length === 0) return
    fresh.forEach((c) => _toasted.add(c))
    const items = fresh
      .map((c) => block.catalog.find((a) => a.code === c))
      .filter((a): a is NonNullable<typeof a> => !!a)
      .map((a) => ({ code: a.code, title: a.title }))
    if (items.length === 0) return
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setQueue((q) => [...q, ...items])
  }, [block])

  const current = queue[0]
  if (!current) return null
  const remaining = queue.length - 1
  return (
    <Toast tone="accent" closable onClose={() => setQueue((q) => q.slice(1))}>
      <span className="ach-toast-icon"><AchMedal code={current.code} locked={false} /></span>
      <div className="ach-toast-body">
        <span className="ach-toast-head">
          Новое достижение!{remaining > 0 && ` (ещё ${remaining})`}
        </span>
        <span className="ach-toast-title">{current.title}</span>
      </div>
    </Toast>
  )
}
