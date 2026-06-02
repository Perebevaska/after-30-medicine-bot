import { useToday, useAdherence, useStreak, useLogIntake } from '../api/hooks'
import type { TodayItem } from '../api/types'

const MEAL: Record<string, string> = {
  before: 'До еды',
  after: 'После еды',
  with: 'Во время еды',
  any: 'Не важно',
  no_meal: 'Не зависит',
}

function StatsBar() {
  const { data: streakData } = useStreak()
  const { data: adherence } = useAdherence()

  const ownerStreak = streakData?.find((s) => s.dependent_id === null)?.streak ?? 0
  const pct = adherence?.total_pct

  return (
    <div className="stats-bar">
      <span className="stat">
        <span className="stat-icon">🔥</span>
        <span className="stat-value">{ownerStreak}</span>
        <span className="stat-label">дней серия</span>
      </span>
      {pct !== null && pct !== undefined && (
        <span className="stat">
          <span className="stat-icon">📊</span>
          <span className="stat-value">{pct}%</span>
          <span className="stat-label">соблюдение</span>
        </span>
      )}
    </div>
  )
}

function MedCard({ item }: { item: TodayItem }) {
  const { mutate, isPending } = useLogIntake()

  const log = (status: 'taken' | 'skipped') => {
    mutate({
      medication_id: item.medication_id,
      scheduled_time: item.reminder_time,
      status,
    })
  }

  return (
    <div className={`med-card status-${item.status}`}>
      <div className="med-info">
        <div className="med-time">{item.reminder_time}</div>
        <div className="med-name">
          {item.name}
          {item.dependent_name && (
            <span className="med-dep"> (для {item.dependent_name})</span>
          )}
        </div>
        <div className="med-meta">
          {item.dosage} · {MEAL[item.meal_relation] ?? item.meal_relation}
        </div>
      </div>

      {item.status === 'pending' ? (
        <div className="med-actions">
          <button
            className="btn-take"
            onClick={() => log('taken')}
            disabled={isPending}
          >
            ✅
          </button>
          <button
            className="btn-skip"
            onClick={() => log('skipped')}
            disabled={isPending}
          >
            ❌
          </button>
        </div>
      ) : (
        <div className="med-status-badge">
          {item.status === 'taken' ? '✅' : '❌'}
        </div>
      )}
    </div>
  )
}

export default function Dashboard() {
  const { data, isLoading, error } = useToday()

  return (
    <div className="page">
      <StatsBar />

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
        <div className="med-list">
          {data.map((item) => (
            <MedCard
              key={`${item.medication_id}-${item.reminder_time}`}
              item={item}
            />
          ))}
        </div>
      )}
    </div>
  )
}
