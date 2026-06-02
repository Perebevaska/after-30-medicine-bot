import { useState, useEffect } from 'react'
import {
  useSettings, useSetReminderMode, useSetDailyPlan, useSetCaregiver,
  useDependents, useCreateDependent, useDeleteDependent,
} from '../api/hooks'

export default function SettingsPage() {
  const { data, isLoading } = useSettings()
  const setMode = useSetReminderMode()
  const setDailyPlan = useSetDailyPlan()
  const setCaregiver = useSetCaregiver()

  const { data: deps } = useDependents()
  const createDep = useCreateDependent()
  const deleteDep = useDeleteDependent()

  const [dailyPlanTime, setDailyPlanTime] = useState('08:00')
  const [newDepName, setNewDepName] = useState('')

  useEffect(() => {
    if (!data) return
    setDailyPlanTime(data.daily_plan_time ?? '08:00')
  }, [data])

  if (isLoading) return <div className="page"><p className="hint">Загрузка…</p></div>
  if (!data) return <div className="page"><p className="hint">Нет данных</p></div>

  const handleDailyPlanTimeBlur = () => {
    setDailyPlan.mutate({ enabled: !!data.daily_plan_enabled, time: dailyPlanTime })
  }

  const handleAddDep = () => {
    const name = newDepName.trim()
    if (!name) return
    createDep.mutate(name, { onSuccess: () => setNewDepName('') })
  }

  return (
    <div className="page">

      <h2 className="section-title">Напоминания</h2>
      <p className="section-hint">
        <b>Однократно</b> — бот отправит уведомление один раз в назначенное время.<br />
        <b>Повтор</b> — если не отметить приём, бот будет напоминать каждые 5 минут до 2 часов.
      </p>
      <div className="settings-block">
        <div className="settings-row">
          <span className="settings-label">Режим</span>
          <div className="toggle-group">
            <button
              className={`toggle-btn${data.reminder_mode === 'once' ? ' toggle-btn--active' : ''}`}
              onClick={() => setMode.mutate('once')}
            >
              Однократно
            </button>
            <button
              className={`toggle-btn${data.reminder_mode === 'repeat' ? ' toggle-btn--active' : ''}`}
              onClick={() => setMode.mutate('repeat')}
            >
              Повтор
            </button>
          </div>
        </div>
      </div>

      <h2 className="section-title">Ежедневный план</h2>
      <p className="section-hint">
        Каждое утро бот пришлёт список всех запланированных на день приёмов.
        Удобно, чтобы сразу видеть весь день.
      </p>
      <div className="settings-block">
        <div className="settings-row">
          <span className="settings-label">Включён</span>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={!!data.daily_plan_enabled}
              onChange={(e) => setDailyPlan.mutate({ enabled: e.target.checked, time: dailyPlanTime })}
            />
            <span className="toggle-track" />
          </label>
        </div>
        {!!data.daily_plan_enabled && (
          <div className="settings-row">
            <span className="settings-label">Время отправки</span>
            <input
              type="time"
              className="settings-time-input"
              value={dailyPlanTime}
              onChange={(e) => setDailyPlanTime(e.target.value)}
              onBlur={handleDailyPlanTimeBlur}
            />
          </div>
        )}
      </div>

      <h2 className="section-title">Режим опекуна</h2>
      <p className="section-hint">
        Позволяет добавлять лекарства для членов семьи или подопечных и отслеживать
        их приёмы отдельно — всё в одном приложении.
      </p>
      <div className="settings-block">
        <div className="settings-row">
          <span className="settings-label">Включён</span>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={!!data.caregiver_enabled}
              onChange={(e) => setCaregiver.mutate(e.target.checked)}
            />
            <span className="toggle-track" />
          </label>
        </div>
      </div>

      {!!data.caregiver_enabled && (
        <>
          <h2 className="section-title">Подопечные</h2>
          <div className="settings-block">
            {(!deps || deps.length === 0) && (
              <div className="settings-row">
                <span className="settings-label" style={{ color: 'var(--hint)' }}>
                  Пока нет подопечных
                </span>
              </div>
            )}
            {deps?.map((d) => (
              <div key={d.id} className="settings-row">
                <span className="settings-label">{d.name}</span>
                <button
                  className="dep-delete-btn"
                  onClick={() => deleteDep.mutate(d.id)}
                  disabled={deleteDep.isPending}
                >
                  Удалить
                </button>
              </div>
            ))}
            <div className="settings-row settings-row--add">
              <input
                className="dep-name-input"
                placeholder="Имя подопечного"
                value={newDepName}
                onChange={(e) => setNewDepName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAddDep()}
                maxLength={40}
              />
              <button
                className="dep-add-btn"
                onClick={handleAddDep}
                disabled={!newDepName.trim() || createDep.isPending}
              >
                Добавить
              </button>
            </div>
          </div>
        </>
      )}

      <div className="settings-footer">
        <span className="hint">Часовой пояс: {data.timezone}</span>
      </div>
    </div>
  )
}
