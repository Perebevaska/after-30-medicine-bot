import { useState, useEffect, useMemo } from 'react'
import {
  useSettings, useSetReminderMode, useSetDailyPlan, useSetCaregiver,
  useDependents, useCreateDependent, useDeleteDependent,
  useSetTimezone, useSetTimezoneByLocation,
} from '../api/hooks'

const TIMEZONES: { value: string; label: string }[] = [
  { value: 'Europe/Kaliningrad', label: 'Калининград UTC+2' },
  { value: 'Europe/Moscow', label: 'Москва, Петербург UTC+3' },
  { value: 'Europe/Samara', label: 'Самара, Ижевск UTC+4' },
  { value: 'Asia/Yekaterinburg', label: 'Екатеринбург UTC+5' },
  { value: 'Asia/Omsk', label: 'Омск UTC+6' },
  { value: 'Asia/Krasnoyarsk', label: 'Красноярск UTC+7' },
  { value: 'Asia/Irkutsk', label: 'Иркутск UTC+8' },
  { value: 'Asia/Yakutsk', label: 'Якутск UTC+9' },
  { value: 'Asia/Vladivostok', label: 'Владивосток UTC+10' },
  { value: 'Asia/Magadan', label: 'Магадан UTC+11' },
  { value: 'Asia/Kamchatka', label: 'Камчатка UTC+12' },
  { value: 'Europe/Minsk', label: 'Минск UTC+3' },
  { value: 'Europe/Kyiv', label: 'Киев UTC+2/3' },
  { value: 'Asia/Almaty', label: 'Алматы UTC+5' },
  { value: 'Asia/Tashkent', label: 'Ташкент UTC+5' },
  { value: 'Asia/Bishkek', label: 'Бишкек UTC+6' },
  { value: 'Asia/Tbilisi', label: 'Тбилиси UTC+4' },
  { value: 'Asia/Yerevan', label: 'Ереван UTC+4' },
  { value: 'Asia/Baku', label: 'Баку UTC+4' },
  { value: 'Europe/London', label: 'Лондон UTC+0/1' },
  { value: 'Europe/Paris', label: 'Париж, Берлин UTC+1/2' },
  { value: 'Europe/Helsinki', label: 'Хельсинки UTC+2/3' },
  { value: 'Europe/Istanbul', label: 'Стамбул UTC+3' },
  { value: 'Asia/Dubai', label: 'Дубай UTC+4' },
  { value: 'Asia/Karachi', label: 'Пакистан UTC+5' },
  { value: 'Asia/Kolkata', label: 'Индия UTC+5:30' },
  { value: 'Asia/Bangkok', label: 'Бангкок UTC+7' },
  { value: 'Asia/Singapore', label: 'Сингапур UTC+8' },
  { value: 'Asia/Shanghai', label: 'Китай UTC+8' },
  { value: 'Asia/Tokyo', label: 'Токио UTC+9' },
  { value: 'America/New_York', label: 'Нью-Йорк UTC-5/-4' },
  { value: 'America/Chicago', label: 'Чикаго UTC-6/-5' },
  { value: 'America/Los_Angeles', label: 'Лос-Анджелес UTC-8/-7' },
  { value: 'America/Sao_Paulo', label: 'Сан-Паулу UTC-3' },
  { value: 'Australia/Sydney', label: 'Сидней UTC+10/11' },
]

export default function SettingsPage() {
  const { data, isLoading } = useSettings()
  const setMode = useSetReminderMode()
  const setDailyPlan = useSetDailyPlan()
  const setCaregiver = useSetCaregiver()

  const { data: deps } = useDependents()
  const createDep = useCreateDependent()
  const deleteDep = useDeleteDependent()

  const setTz = useSetTimezone()
  const setTzByLocation = useSetTimezoneByLocation()

  const [dailyPlanTime, setDailyPlanTime] = useState('08:00')
  const [newDepName, setNewDepName] = useState('')
  const [tzEditing, setTzEditing] = useState(false)
  const [tzSearch, setTzSearch] = useState('')
  const [geoError, setGeoError] = useState('')

  const filteredZones = useMemo(() => {
    const q = tzSearch.toLowerCase()
    if (!q) return TIMEZONES
    return TIMEZONES.filter(
      (z) => z.label.toLowerCase().includes(q) || z.value.toLowerCase().includes(q)
    )
  }, [tzSearch])

  const handleSelectTz = (tz: string) => {
    setTz.mutate(tz, { onSuccess: () => { setTzEditing(false); setTzSearch('') } })
  }

  const handleGeolocate = () => {
    setGeoError('')
    if (!navigator.geolocation) {
      setGeoError('Геолокация не поддерживается браузером')
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setTzByLocation.mutate(
          { lat: pos.coords.latitude, lng: pos.coords.longitude },
          {
            onSuccess: () => { setTzEditing(false); setTzSearch('') },
            onError: () => setGeoError('Не удалось определить часовой пояс'),
          }
        )
      },
      () => setGeoError('Нет доступа к геолокации')
    )
  }

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
        Если включён повтор — бот будет напоминать каждые 5 минут до 2 часов, пока не отметишь приём.
      </p>
      <div className="settings-block">
        <div className="settings-row">
          <span className="settings-label">Повтор напоминаний</span>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={data.reminder_mode === 'repeat'}
              onChange={(e) => setMode.mutate(e.target.checked ? 'repeat' : 'once')}
            />
            <span className="toggle-track" />
          </label>
        </div>
      </div>

      <h2 className="section-title">Ежедневный план</h2>
      <p className="section-hint">
        Каждое утро бот пришлёт список всех запланированных на день приёмов.
        Удобно, чтобы сразу увидеть лекарства на весь день.
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

      <h2 className="section-title">Часовой пояс</h2>
      <p className="section-hint">
        Используется для точного расчёта времени напоминаний о приёме лекарств.
        Укажи свой город или выбери по геолокации.
      </p>
      <div className="settings-block">
        <div className="settings-row">
          <span className="settings-label">Текущий</span>
          <span className="tz-current">{data.timezone}</span>
          {!tzEditing && (
            <button className="tz-change-btn" onClick={() => setTzEditing(true)}>
              Изменить
            </button>
          )}
        </div>
        {tzEditing && (
          <div className="tz-picker">
            <button
              className="tz-geo-btn"
              onClick={handleGeolocate}
              disabled={setTzByLocation.isPending}
            >
              {setTzByLocation.isPending ? 'Определяю…' : '📍 По геолокации'}
            </button>
            {geoError && <p className="tz-error">{geoError}</p>}
            <input
              className="tz-search-input"
              placeholder="Москва, Moscow, UTC+3…"
              value={tzSearch}
              onChange={(e) => setTzSearch(e.target.value)}
              autoFocus
            />
            <div className="tz-list">
              {filteredZones.map((z) => (
                <div
                  key={z.value}
                  className={`tz-list-item${z.value === data.timezone ? ' tz-list-item--active' : ''}`}
                  onClick={() => handleSelectTz(z.value)}
                >
                  <span className="tz-item-label">{z.label}</span>
                  <span className="tz-item-value">{z.value}</span>
                </div>
              ))}
              {filteredZones.length === 0 && (
                <p className="tz-empty">Ничего не найдено</p>
              )}
            </div>
            <button className="tz-cancel-btn" onClick={() => { setTzEditing(false); setTzSearch(''); setGeoError('') }}>
              Отмена
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
