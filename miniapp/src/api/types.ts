export interface TodayItem {
  medication_id: number
  name: string
  dosage: string
  meal_relation: string
  reminder_time: string
  status: 'pending' | 'taken' | 'skipped'
  dependent_name: string | null
}

export interface IntakeIn {
  medication_id: number
  scheduled_time: string
  status: 'taken' | 'skipped'
}

export interface AdherenceMed {
  medication_id: number
  name: string
  dosage: string
  dependent_name: string | null
  due: number
  taken: number
  pct: number
}

export interface AdherenceResponse {
  medications: AdherenceMed[]
  total_pct: number | null
}

export interface StreakItem {
  dependent_id: number | null
  name: string | null
  streak: number
}
