import { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { useToday, useLogIntake } from '../api/hooks'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { TodayItem } from '../api/types'
import { randomWish } from '../wishes'

const MEAL: Record<string, string> = {
  before: 'До еды',
  after: 'После еды',
  with: 'Во время еды',
  any: 'Не важно',
  no_meal: 'Не зависит',
}

interface HeartParticle {
  id: number
  x: number
  y: number
  dx: number
  dy: number
  size: number
  dur: number
}

// ── Health bar persistence ─────────────────────────────────────────────────
const HP_KEY = 'wish_hp'
const HP_TS_KEY = 'wish_hp_ts'
const DEPLETE_PER_MS = 100 / (8 * 3600 * 1000) // 100% за 8 часов

function loadHp(): number {
  try {
    const h = parseFloat(localStorage.getItem(HP_KEY) ?? '0')
    const ts = parseInt(localStorage.getItem(HP_TS_KEY) ?? '0', 10)
    if (!ts) return Math.max(0, h)
    return Math.max(0, h - (Date.now() - ts) * DEPLETE_PER_MS)
  } catch {
    return 0
  }
}

function saveHp(h: number): void {
  localStorage.setItem(HP_KEY, String(h))
  localStorage.setItem(HP_TS_KEY, String(Date.now()))
}
// ──────────────────────────────────────────────────────────────────────────

let _pid = 0

function WishCard() {
  const [wish, setWish] = useState(randomWish)
  const [hp, setHp] = useState(loadHp)
  const [particles, setParticles] = useState<HeartParticle[]>([])
  const btnRef = useRef<HTMLButtonElement>(null)

  // Обновляем hp раз в минуту (плавный drain)
  useEffect(() => {
    const id = setInterval(() => setHp(loadHp), 60_000)
    return () => clearInterval(id)
  }, [])

  const spawnHearts = () => {
    const rect = btnRef.current?.getBoundingClientRect()
    if (!rect) return
    const cx = rect.left + rect.width / 2
    const cy = rect.top + rect.height / 2
    const count = 13
    const batch: HeartParticle[] = Array.from({ length: count }, () => {
      const angle = Math.random() * Math.PI * 2
      const dist = 65 + Math.random() * 140
      return {
        id: ++_pid,
        x: cx,
        y: cy,
        dx: Math.cos(angle) * dist,
        dy: Math.sin(angle) * dist,
        size: 9 + Math.random() * 13,
        dur: 520 + Math.random() * 380,
      }
    })
    setParticles((p) => [...p, ...batch])
    const maxDur = Math.max(...batch.map((p) => p.dur)) + 60
    const ids = new Set(batch.map((p) => p.id))
    setTimeout(() => setParticles((p) => p.filter((pt) => !ids.has(pt.id))), maxDur)
  }

  const next = () => {
    setWish((w) => randomWish(w))
    spawnHearts()
    setHp(() => {
      const current = loadHp()
      const bonus = 10 + Math.random() * 15 // 10–25%
      const next = Math.min(100, current + bonus)
      saveHp(next)
      return next
    })
  }

  const clipRight = (100 - hp).toFixed(2)

  return (
    <>
      <div className="wish-card">
        <div className="wish-text-wrap">
          <span className="wish-text">{wish}</span>
          <span
            className="wish-text wish-text-hp"
            aria-hidden="true"
            style={{ clipPath: `inset(0 ${clipRight}% 0 0)` }}
          >
            {wish}
          </span>
        </div>
        <button
          ref={btnRef}
          className="wish-refresh"
          onClick={next}
          aria-label="Другое пожелание"
        >
          ❤️
        </button>
      </div>
      {createPortal(
        <div className="hearts-overlay" aria-hidden="true">
          {particles.map((p) => (
            <span
              key={p.id}
              className="heart-particle"
              style={{
                left: p.x,
                top: p.y,
                fontSize: p.size,
                '--dx': `${p.dx}px`,
                '--dy': `${p.dy}px`,
                '--dur': `${p.dur}ms`,
              } as React.CSSProperties}
            >
              ❤️
            </span>
          ))}
        </div>,
        document.body
      )}
    </>
  )
}

function isDue(reminderTime: string): boolean {
  const now = new Date()
  const [h, m] = reminderTime.split(':').map(Number)
  return now.getHours() * 60 + now.getMinutes() >= h * 60 + m
}

const itemKey = (i: TodayItem) => `${i.medication_id}-${i.reminder_time}`
const isDuePending = (i: TodayItem) => i.status === 'pending' && isDue(i.reminder_time)

function MedCard({
  item,
  exiting,
  entering,
}: {
  item: TodayItem
  exiting?: boolean
  entering?: boolean
}) {
  const { mutate, isPending } = useLogIntake()

  const log = (status: 'taken' | 'skipped' | 'pending') => {
    mutate({
      medication_id: item.medication_id,
      scheduled_time: item.reminder_time,
      status,
    })
  }

  const due = isDuePending(item)
  const extraClass = exiting ? ' mlist-card--exit' : entering ? ' mlist-card--enter' : ''

  return (
    <div
      className={`mlist-card${item.status !== 'pending' ? ' mlist-card--paused' : ''}${due ? ' mlist-card--due' : ''}${extraClass}`}
    >
      <div className="mlist-info">
        <div className="mlist-name">
          {item.name}
          {item.dependent_name && (
            <span className="mlist-dep"> · {item.dependent_name}</span>
          )}
        </div>
        <div className="mlist-meta">
          {item.dosage} · {MEAL[item.meal_relation] ?? item.meal_relation}
        </div>
        <div className="mlist-schedule">{item.reminder_time}</div>
      </div>

      {item.status === 'pending' ? (
        <div className="med-actions">
          <button className="btn-take" onClick={() => log('taken')} disabled={isPending}>✅</button>
          <button className="btn-skip" onClick={() => log('skipped')} disabled={isPending}>❌</button>
        </div>
      ) : (
        <div className="med-actions">
          <button
            className="btn-undo"
            onClick={() => log('pending')}
            disabled={isPending}
            title="Отменить отметку"
          >
            {item.status === 'taken' ? '✅' : '❌'}
          </button>
        </div>
      )}
    </div>
  )
}

export default function Dashboard() {
  const { data, isLoading, error } = useToday()
  const qc = useQueryClient()
  const [takingAll, setTakingAll] = useState(false)

  // exitingMap: снапшоты due-pending элементов, пока играет exit-анимация
  const [exitingMap, setExitingMap] = useState<Map<string, TodayItem>>(new Map())
  // enteringIds: ключи элементов, только что появившихся в секции others
  const [enteringIds, setEnteringIds] = useState<Set<string>>(new Set())
  const prevDataRef = useRef<TodayItem[]>([])

  useEffect(() => {
    if (!data) return
    const prevData = prevDataRef.current
    const prevDueKeys = new Set(prevData.filter(isDuePending).map(itemKey))
    const currentDueKeys = new Set(data.filter(isDuePending).map(itemKey))

    // Элементы, которые только что покинули due-pending группу
    const justLeft = prevData.filter(
      (i) => prevDueKeys.has(itemKey(i)) && !currentDueKeys.has(itemKey(i))
    )

    if (justLeft.length > 0) {
      // Кладём снапшоты (со статусом pending и green-подсветкой)
      setExitingMap((prev) => {
        const next = new Map(prev)
        justLeft.forEach((i) => next.set(itemKey(i), i))
        return next
      })
      const leftKeys = justLeft.map(itemKey)
      // После exit-анимации (250ms) убираем из due-секции и добавляем enter в others
      setTimeout(() => {
        setExitingMap((prev) => {
          const next = new Map(prev)
          leftKeys.forEach((k) => next.delete(k))
          return next
        })
        setEnteringIds((prev) => new Set([...prev, ...leftKeys]))
        setTimeout(() => {
          setEnteringIds((prev) => {
            const next = new Set(prev)
            leftKeys.forEach((k) => next.delete(k))
            return next
          })
        }, 320)
      }, 260)
    }

    prevDataRef.current = data
  }, [data])

  const allItems = data ?? []

  // Due-секция: реально due-pending + снапшоты exiting, сортировка по времени desc
  const dueItems = [
    ...allItems.filter(isDuePending),
    ...[...exitingMap.values()],
  ].sort((a, b) => b.reminder_time.localeCompare(a.reminder_time))

  // Others-секция: не-due + не-exiting
  const otherItems = allItems.filter(
    (i) => !isDuePending(i) && !exitingMap.has(itemKey(i))
  )

  // Реальные due-pending (без снапшотов) — для кнопки и handleTakeAll
  const trueDuePending = allItems.filter(isDuePending)

  const handleTakeAll = async () => {
    if (!trueDuePending.length) return
    setTakingAll(true)
    qc.setQueryData<TodayItem[]>(['today'], (old) =>
      old?.map((item) =>
        isDuePending(item) ? { ...item, status: 'taken' as const } : item
      )
    )
    try {
      await Promise.all(
        trueDuePending.map((item) =>
          api.post('/today/intake', {
            medication_id: item.medication_id,
            scheduled_time: item.reminder_time,
            status: 'taken',
          })
        )
      )
    } finally {
      await qc.invalidateQueries({ queryKey: ['today'] })
      await qc.invalidateQueries({ queryKey: ['streak'] })
      await qc.invalidateQueries({ queryKey: ['adherence'] })
      setTakingAll(false)
    }
  }

  const hasAny = dueItems.length > 0 || otherItems.length > 0

  return (
    <div className="page">
      <WishCard />

      <h2 className="section-title">Сегодня</h2>

      {isLoading && <p className="hint">Загрузка…</p>}

      {error && (
        <p className="hint error">
          {error.message.includes('401')
            ? 'Откройте приложение через Telegram'
            : error.message}
        </p>
      )}

      {data && data.length === 0 && (
        <p className="hint">На сегодня нет приёмов</p>
      )}

      {data && hasAny && (
        <div className="mlist-list">
          {dueItems.map((item) => (
            <MedCard
              key={itemKey(item)}
              item={item}
              exiting={exitingMap.has(itemKey(item))}
            />
          ))}

          {trueDuePending.length >= 2 && (
            <div className="take-all-row">
              <button
                className="btn-take-all"
                onClick={handleTakeAll}
                disabled={takingAll}
              >
                💊 Выпил всё
              </button>
            </div>
          )}

          {otherItems.map((item) => (
            <MedCard
              key={itemKey(item)}
              item={item}
              entering={enteringIds.has(itemKey(item))}
            />
          ))}
        </div>
      )}
    </div>
  )
}
