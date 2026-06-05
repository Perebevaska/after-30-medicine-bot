import type { MealRelation } from './api/types'

// Лейблы отношения к еде — единый источник для всех страниц.
export const MEAL_LABELS: Record<string, string> = {
  before: 'До еды',
  after: 'После еды',
  with: 'Во время еды',
  any: 'Не зависит от еды',
}

// Опции для сегмент-контрола в форме (порядок + короткие подписи).
export const MEAL_OPTIONS: { value: MealRelation; label: string }[] = [
  { value: 'before', label: 'До еды' },
  { value: 'after', label: 'После еды' },
  { value: 'with', label: 'С едой' },
  { value: 'any', label: 'Не зависит от еды' },
]
