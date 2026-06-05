import { Flame, Lock, Pill, Target, Handshake, type LucideIcon } from 'lucide-react'

// Ф18: медальон вместо эмодзи. code → {глиф группы, уровень-градиент}.
// Уровни по сложности: bronze→silver→gold→diamond; забота — бренд-бирюза.
const ACH_VISUAL: Record<string, { tier: string; Icon: LucideIcon }> = {
  intake_10:  { tier: 'bronze',  Icon: Pill },
  intake_100: { tier: 'silver',  Icon: Pill },
  intake_500: { tier: 'gold',    Icon: Pill },
  streak_7:   { tier: 'bronze',  Icon: Flame },
  streak_30:  { tier: 'silver',  Icon: Flame },
  streak_100: { tier: 'diamond', Icon: Flame },
  adh_30:     { tier: 'silver',  Icon: Target },
  adh_90:     { tier: 'gold',    Icon: Target },
  care_first: { tier: 'care',    Icon: Handshake },
}

export function AchMedal({ code, locked, large }: { code: string; locked: boolean; large?: boolean }) {
  const v = ACH_VISUAL[code]
  const cls = `ach-medal${large ? ' ach-medal--lg' : ''}`
  const sz = large ? 26 : 22
  if (locked || !v) {
    return <span className={`${cls} ach-medal--locked`}><Lock size={sz} strokeWidth={2} /></span>
  }
  const { tier, Icon } = v
  return <span className={`${cls} ach-medal--${tier}`}><Icon size={sz} strokeWidth={2} /></span>
}
