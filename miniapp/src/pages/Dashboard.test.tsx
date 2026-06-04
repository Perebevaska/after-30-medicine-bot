import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import type { TodayItem, Medication } from '../api/types'

// --- мокаемое состояние хуков (управляем из тестов) ---
const state = vi.hoisted(() => ({
  today: undefined as TodayItem[] | undefined,
  meds: undefined as Medication[] | undefined,
  settings: { timezone: 'Europe/Moscow' } as { timezone: string } | undefined,
}))

vi.mock('../api/hooks', () => ({
  useToday: () => ({ data: state.today, isLoading: false, error: null }),
  useMedications: () => ({ data: state.meds }),
  useSettings: () => ({ data: state.settings }),
  useHearts: () => ({ data: { hearts: 0 } }),
  useLogIntake: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('../api/client', () => ({
  api: { post: vi.fn().mockResolvedValue({}) },
  apiErrorMessage: (e: unknown) => String(e),
}))

vi.mock('@telegram-apps/sdk-react', () => ({ postEvent: vi.fn() }))

vi.mock('../wishes', () => ({ randomWish: () => 'Держись 💪' }))

import Dashboard from './Dashboard'

// фабрики фикстур
function todayItem(over: Partial<TodayItem>): TodayItem {
  return {
    medication_id: 1,
    name: 'Аспирин',
    dosage: '1 таб',
    meal_relation: 'any',
    reminder_time: '09:00',
    status: 'pending',
    is_due: false,
    dependent_id: null,
    dependent_name: null,
    ...over,
  }
}

function med(over: Partial<Medication>): Medication {
  return {
    id: 1,
    name: 'Аспирин',
    dosage: '1 таб',
    meal_relation: 'any',
    times_per_day: 1,
    active: 1,
    paused: 0,
    dependent_id: null,
    dependent_name: null,
    stock_qty: null,
    units_per_dose: 1,
    low_stock_days: 3,
    unit_dose_value: null,
    unit_dose_label: 'мг',
    dose_per_intake: null,
    pack_size: null,
    course_total: null,
    rules: [],
    ...over,
  }
}

function renderDash() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  return render(<Dashboard />, { wrapper })
}

describe('Dashboard empty-state (Фаза 14)', () => {
  beforeEach(() => {
    localStorage.clear()
    state.today = undefined
    state.meds = undefined
    state.settings = { timezone: 'Europe/Moscow' }
  })

  it('нет своих препаратов → экран «Пока нет препаратов»', () => {
    state.today = []
    state.meds = []
    renderDash()
    expect(screen.getByText('Пока нет препаратов')).toBeInTheDocument()
  })

  it('все препараты на паузе → экран «Все препараты на паузе»', () => {
    state.today = []
    state.meds = [med({ paused: 1 })]
    renderDash()
    expect(screen.getByText('Все препараты на паузе')).toBeInTheDocument()
  })

  it('есть активные препараты, но приёмов нет → «На сегодня нет приёмов»', () => {
    state.today = []
    state.meds = [med({ paused: 0 })]
    renderDash()
    expect(screen.getByText('На сегодня нет приёмов')).toBeInTheDocument()
  })
})

describe('Dashboard секции «Сейчас»/«Сегодня»', () => {
  beforeEach(() => {
    localStorage.clear()
    state.meds = [med({})]
    state.settings = { timezone: 'Europe/Moscow' }
  })

  it('due-pending → «Сейчас»; остальные → «Сегодня»', () => {
    state.today = [
      todayItem({ medication_id: 1, name: 'Утренний', reminder_time: '09:00', status: 'pending', is_due: true }),
      todayItem({ medication_id: 2, name: 'Вечерний', reminder_time: '21:00', status: 'pending', is_due: false }),
    ]
    renderDash()
    expect(screen.getByText('Сейчас')).toBeInTheDocument()
    expect(screen.getByText('Сегодня')).toBeInTheDocument()
    expect(screen.getByText('Утренний')).toBeInTheDocument()
    expect(screen.getByText('Вечерний')).toBeInTheDocument()
  })

  it('«Принять всё» появляется при ≥2 due-pending', () => {
    state.today = [
      todayItem({ medication_id: 1, name: 'A', reminder_time: '09:00', status: 'pending', is_due: true }),
      todayItem({ medication_id: 2, name: 'B', reminder_time: '10:00', status: 'pending', is_due: true }),
    ]
    renderDash()
    expect(screen.getByText('Принять всё')).toBeInTheDocument()
  })

  it('«Принять всё» скрыт при единственном due-pending', () => {
    state.today = [
      todayItem({ medication_id: 1, name: 'A', reminder_time: '09:00', status: 'pending', is_due: true }),
    ]
    renderDash()
    expect(screen.queryByText('Принять всё')).not.toBeInTheDocument()
  })

  it('TZ-баннер при timezone=UTC', () => {
    state.settings = { timezone: 'UTC' }
    state.today = []
    state.meds = [med({ paused: 0 })]
    renderDash()
    expect(screen.getByText(/часовой пояс не задан/)).toBeInTheDocument()
  })
})
