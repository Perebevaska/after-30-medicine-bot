import { useState, Fragment } from 'react'
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

function WishCard() {
  const [wish, setWish] = useState(randomWish)
  const [spinning, setSpinning] = useState(false)

  const next = () => {
    setSpinning(true)
    setWish((w) => randomWish(w))
    setTimeout(() => setSpinning(false), 400)
  }

  return (
    <div className="wish-card">
      <span className="wish-text">{wish}</span>
      <button
        className={`wish-refresh${spinning ? ' wish-refresh--spin' : ''}`}
        onClick={next}
        aria-label="Другое пожелание"
      >
        🔄
      </button>
    </div>
  )
}

function isDue(reminderTime: string): boolean {
  const now = new Date()
  const [h, m] = reminderTime.split(':').map(Number)
  return now.getHours() * 60 + now.getMinutes() >= h * 60 + m
}

function MedCard({ item }: { item: TodayItem }) {
  const { mutate, isPending } = useLogIntake()

  const log = (status: 'taken' | 'skipped' | 'pending') => {
    mutate({
      medication_id: item.medication_id,
      scheduled_time: item.reminder_time,
      status,
    })
  }

  const due = item.status === 'pending' && isDue(item.reminder_time)

  return (
    <div className={`mlist-card${item.status !== 'pending' ? ' mlist-card--paused' : ''}${due ? ' mlist-card--due' : ''}`}>
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

  const duePending = (data ?? []).filter(
    (i) => i.status === 'pending' && isDue(i.reminder_time)
  )

  const handleTakeAll = async () => {
    if (!duePending.length) return
    setTakingAll(true)
    // Оптимистично ставим всем статус taken
    qc.setQueryData<TodayItem[]>(['today'], (old) =>
      old?.map((item) =>
        item.status === 'pending' && isDue(item.reminder_time)
          ? { ...item, status: 'taken' as const }
          : item
      )
    )
    try {
      await Promise.all(
        duePending.map((item) =>
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

  // Найти индекс первого due-pending для вставки кнопки
  const firstDueIdx = (data ?? []).findIndex(
    (i) => i.status === 'pending' && isDue(i.reminder_time)
  )

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

      {data && data.length > 0 && (
        <div className="mlist-list">
          {data.map((item, i) => (
            <Fragment key={`${item.medication_id}-${item.reminder_time}`}>
              {i === firstDueIdx && duePending.length > 1 && (
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
              <MedCard item={item} />
            </Fragment>
          ))}
        </div>
      )}
    </div>
  )
}
