import { useState } from 'react'
import { useMedications, useDeleteMedication, usePauseMedication } from '../api/hooks'
import type { Medication } from '../api/types'

const MEAL: Record<string, string> = {
  before: 'До еды',
  after: 'После еды',
  with: 'Во время еды',
  any: 'Не важно',
}

const FREQ: Record<string, string> = {
  daily: 'ежедневно',
  interval: 'раз в N дней',
  weekdays: 'по дням нед.',
  monthly: 'раз в месяц',
}

function scheduleLabel(med: Medication): string {
  if (!med.rules.length) return ''
  const times = med.rules
    .map((r) => (r.dosage ? `${r.reminder_time} (${r.dosage})` : r.reminder_time))
    .join(' · ')
  const freqs = [...new Set(med.rules.map((r) => FREQ[r.frequency] ?? r.frequency))]
  return `${times} (${freqs.join(', ')})`
}

interface CardProps {
  med: Medication
  onEdit: (id: number) => void
}

function MedCard({ med, onEdit }: CardProps) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const { mutate: del, isPending: delPending } = useDeleteMedication()
  const { mutate: pause, isPending: pausePending } = usePauseMedication()

  const handleDelete = () => {
    if (!confirmDelete) { setConfirmDelete(true); return }
    del(med.id, { onSuccess: () => setConfirmDelete(false) })
  }

  return (
    <div className={`mlist-card${med.paused ? ' mlist-card--paused' : ''}`}>
      <div className="mlist-info">
        <div className="mlist-name">
          {med.name}
          {!!med.paused && <span className="mlist-badge-paused">пауза</span>}
          {med.dependent_name && (
            <span className="mlist-dep"> · {med.dependent_name}</span>
          )}
        </div>
        <div className="mlist-meta">
          {med.rules.some((r) => r.dosage)
            ? <span className="mlist-custom-dosage">своя дозировка</span>
            : med.dosage
          } · {MEAL[med.meal_relation] ?? med.meal_relation}
        </div>
        {med.rules.length > 0 && (
          <div className="mlist-schedule">{scheduleLabel(med)}</div>
        )}
      </div>

      <div className="mlist-actions">
        <button
          className="mlist-btn mlist-btn--edit"
          onClick={() => onEdit(med.id)}
          title="Редактировать"
        >
          ✏️
        </button>
        <button
          className="mlist-btn mlist-btn--pause"
          onClick={() => pause({ id: med.id, paused: !med.paused })}
          disabled={pausePending}
          title={med.paused ? 'Возобновить' : 'Пауза'}
        >
          {med.paused ? '▶️' : '⏸️'}
        </button>
        <button
          className={`mlist-btn mlist-btn--del${confirmDelete ? ' mlist-btn--confirm' : ''}`}
          onClick={handleDelete}
          disabled={delPending}
          title="Удалить"
          onBlur={() => setConfirmDelete(false)}
        >
          {confirmDelete ? '✓?' : '🗑️'}
        </button>
      </div>
    </div>
  )
}

interface Props {
  onAdd: () => void
  onEdit: (id: number) => void
}

export default function MedicationList({ onAdd, onEdit }: Props) {
  const { data, isLoading, error } = useMedications()

  return (
    <div className="page">
      <div className="mlist-header">
        <h2 className="mlist-title">Мои лекарства</h2>
        <button className="mlist-add-btn" onClick={onAdd}>
          + Добавить
        </button>
      </div>

      {isLoading && <p className="hint">Загрузка…</p>}

      {error && <p className="hint error">{error.message}</p>}

      {data && data.length === 0 && (
        <div className="mlist-empty">
          <p className="mlist-empty-text">Лекарств пока нет</p>
          <button className="btn-primary" onClick={onAdd}>
            Добавить первое лекарство
          </button>
        </div>
      )}

      {data && data.length > 0 && (
        <div className="mlist-list">
          {data.map((med) => (
            <MedCard key={med.id} med={med} onEdit={onEdit} />
          ))}
        </div>
      )}
    </div>
  )
}
