import { useState } from 'react'
import { useAdherence, useStreak, useSendExport, useWeekStats, useMedications, useSettings } from '../api/hooks'
import type { AdherenceMed, WeekStatRow, Medication } from '../api/types'

function pctColor(pct: number): string {
  if (pct >= 80) return '#4caf50'
  if (pct >= 50) return '#ff9800'
  return '#f44336'
}

// ─── Previews ─────────────────────────────────────────────────────────────

function PlanPreview({ meds }: { meds: Medication[] }) {
  const active = meds.filter((m) => m.active && !m.paused)
  if (!active.length) return <p className="preview-empty">Нет активных лекарств</p>
  return (
    <div className="preview-list">
      {active.map((m) => (
        <div key={m.id} className="preview-row">
          <span className="preview-name">
            {m.name}
            {m.dependent_name && <span className="preview-dep"> · {m.dependent_name}</span>}
          </span>
          <span className="preview-meta">
            {m.rules.map((r) => r.reminder_time).join(', ')} · {m.dosage}
          </span>
        </div>
      ))}
    </div>
  )
}

function WeekPreview({ rows }: { rows: WeekStatRow[] }) {
  if (!rows.length) return <p className="preview-empty">Нет данных за 7 дней</p>
  // группируем по дню
  const byDay: Record<string, { taken: number; total: number }> = {}
  for (const r of rows) {
    if (!byDay[r.day]) byDay[r.day] = { taken: 0, total: 0 }
    byDay[r.day].taken += r.taken
    byDay[r.day].total += r.total
  }
  const days = Object.entries(byDay).sort(([a], [b]) => b.localeCompare(a)).slice(0, 7)
  return (
    <div className="preview-list">
      {days.map(([day, { taken, total }]) => {
        const pct = total ? Math.round(taken / total * 100) : 0
        const d = new Date(day)
        const label = d.toLocaleDateString('ru', { day: 'numeric', month: 'short', weekday: 'short' })
        return (
          <div key={day} className="preview-row preview-row--week">
            <span className="preview-name">{label}</span>
            <div className="preview-week-bar">
              <div className="adh-bar-bg" style={{ width: 80, display: 'inline-block' }}>
                <div className="adh-bar-fill" style={{ width: `${pct}%`, background: pctColor(pct) }} />
              </div>
              <span className="preview-meta" style={{ color: pctColor(pct) }}>{pct}%</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function AdhPreview({ meds, totalPct }: { meds: AdherenceMed[]; totalPct: number | null | undefined }) {
  if (!meds.length) return <p className="preview-empty">Нет данных за 30 дней</p>
  return (
    <div className="preview-list">
      {totalPct !== null && totalPct !== undefined && (
        <div className="preview-row preview-row--total">
          <span className="preview-name" style={{ fontWeight: 700 }}>Итого</span>
          <span style={{ fontWeight: 700, color: pctColor(totalPct) }}>{totalPct}%</span>
        </div>
      )}
      {meds.map((m) => (
        <div key={m.medication_id} className="preview-row">
          <span className="preview-name">
            {m.name}
            {m.dependent_name && <span className="preview-dep"> · {m.dependent_name}</span>}
          </span>
          <span style={{ color: pctColor(m.pct), fontWeight: 600, fontSize: 13 }}>{m.pct}%</span>
        </div>
      ))}
    </div>
  )
}

function DoctorPreview({ meds }: { meds: Medication[] }) {
  const active = meds.filter((m) => m.active && !m.paused)
  if (!active.length) return <p className="preview-empty">Нет активных лекарств</p>
  return (
    <div className="preview-list">
      {active.map((m) => (
        <div key={m.id} className="preview-row">
          <span className="preview-name">
            {m.name}
            {m.dependent_name && <span className="preview-dep"> · {m.dependent_name}</span>}
          </span>
          <span className="preview-meta">{m.dosage} · {m.rules.length} приёмов/день</span>
        </div>
      ))}
    </div>
  )
}

// ─── Report card ──────────────────────────────────────────────────────────

type ReportDef = {
  slot: string
  icon: string
  title: string
  desc: string
}

const REPORTS: ReportDef[] = [
  {
    slot: 'plan',
    icon: '📋',
    title: 'Расписание на неделю',
    desc: 'Все лекарства с временем приёма и указанием относительно еды.',
  },
  {
    slot: 'week',
    icon: '📅',
    title: 'История за 7 дней',
    desc: 'Что и когда принято или пропущено за последние 7 дней.',
  },
  {
    slot: 'adherence',
    icon: '📊',
    title: 'Соблюдение режима',
    desc: 'Процент выполнения по каждому лекарству за 30 дней.',
  },
  {
    slot: 'doctor',
    icon: '🩺',
    title: 'Отчёт для врача',
    desc: 'Сводка лекарств и расписания в формате для врача или стационара.',
  },
]

function ReportCard({
  slot, icon, title, desc,
  weekRows, adherenceMeds, adherenceTotalPct, medications,
}: ReportDef & {
  weekRows: WeekStatRow[]
  adherenceMeds: AdherenceMed[]
  adherenceTotalPct: number | null | undefined
  medications: Medication[]
}) {
  const { mutate, isPending, isError, reset } = useSendExport()
  const [sent, setSent] = useState(false)
  const [expanded, setExpanded] = useState(false)

  const handleSend = () => {
    mutate(slot, {
      onSuccess: () => {
        setSent(true)
        setTimeout(() => { setSent(false); reset() }, 3000)
      },
    })
  }

  return (
    <div className="report-card">
      <div className="report-header">
        <span className="report-icon">{icon}</span>
        <div className="report-titles">
          <span className="report-title">{title}</span>
          <span className="report-desc">{desc}</span>
        </div>
      </div>

      <div className="report-actions">
        <button
          className="report-preview-btn"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? 'Скрыть ▲' : 'Просмотр ▼'}
        </button>
        <button
          className={`report-send-btn${sent ? ' report-send-btn--sent' : ''}${isError ? ' report-send-btn--err' : ''}`}
          onClick={handleSend}
          disabled={isPending}
        >
          {isPending ? '⏳' : sent ? '✅ Отправлено' : isError ? '⚠️ Ошибка' : '📨 В Telegram'}
        </button>
      </div>

      {expanded && (
        <div className="report-preview">
          {slot === 'plan'      && <PlanPreview meds={medications} />}
          {slot === 'week'      && <WeekPreview rows={weekRows} />}
          {slot === 'adherence' && <AdhPreview meds={adherenceMeds} totalPct={adherenceTotalPct} />}
          {slot === 'doctor'    && <DoctorPreview meds={medications} />}
        </div>
      )}
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────

export default function StatsPage() {
  const { data: streakData, isLoading: streakLoading } = useStreak()
  const { data: adherence, isLoading: adherenceLoading } = useAdherence()
  const { data: weekRows = [] } = useWeekStats()
  const { data: medications = [] } = useMedications()
  const { data: settings } = useSettings()

  const caregiverEnabled = !!settings?.caregiver_enabled
  const ownerStreak = streakData?.find((s) => s.dependent_id === null)?.streak ?? 0
  const depStreaks = caregiverEnabled
    ? (streakData?.filter((s) => s.dependent_id !== null) ?? [])
    : []
  const totalPct = adherence?.total_pct
  const allMeds = adherence?.medications ?? []
  const meds = caregiverEnabled ? allMeds : allMeds.filter((m) => !m.dependent_name)

  return (
    <div className="page">
      <div className="page-header">
        <span className="page-header-title">Прогресс</span>
      </div>
      <h2 className="section-title">Серия</h2>
      {streakLoading && <p className="hint">Загрузка…</p>}
      {!streakLoading && (
        <div className="stats-streak-block">
          <div className="streak-row">
            <span className="streak-fire">🔥</span>
            <span className="streak-count">{ownerStreak}</span>
            <span className="streak-label">дней подряд</span>
          </div>
          {depStreaks.map((s) => (
            <div key={s.dependent_id} className="streak-row streak-row--dep">
              <span className="streak-fire">🔥</span>
              <span className="streak-count">{s.streak}</span>
              <span className="streak-label">{s.name}</span>
            </div>
          ))}
        </div>
      )}

      <h2 className="section-title">Соблюдение (30 дней)</h2>
      {adherenceLoading && <p className="hint">Загрузка…</p>}
      {!adherenceLoading && meds.length === 0 && (
        <p className="hint">Нет данных — начните отмечать приёмы</p>
      )}
      {!adherenceLoading && meds.length > 0 && (
        <div className="stats-adh-block">
          {totalPct !== null && totalPct !== undefined && (
            <div className="adh-total">
              <span className="adh-total-label">Всего</span>
              <span className="adh-total-pct" style={{ color: pctColor(totalPct) }}>{totalPct}%</span>
            </div>
          )}
          {meds.map((m) => (
            <div key={m.medication_id} className="adh-row">
              <div className="adh-row-header">
                <span className="adh-name">
                  {m.name}
                  {m.dependent_name && <span className="adh-dep"> · {m.dependent_name}</span>}
                </span>
                <span className="adh-pct" style={{ color: pctColor(m.pct) }}>{m.pct}%</span>
              </div>
              <div className="adh-bar-bg">
                <div className="adh-bar-fill" style={{ width: `${m.pct}%`, background: pctColor(m.pct) }} />
              </div>
              <span className="adh-counts">{m.taken} из {m.due}</span>
            </div>
          ))}
        </div>
      )}

      <h2 className="section-title">Отчёты</h2>
      <p className="section-hint">Файл придёт прямо в чат с ботом</p>
      <div className="reports-list">
        {REPORTS.map((r) => (
          <ReportCard
            key={r.slot}
            {...r}
            weekRows={weekRows}
            adherenceMeds={meds}
            adherenceTotalPct={totalPct}
            medications={medications}
          />
        ))}
      </div>
    </div>
  )
}
