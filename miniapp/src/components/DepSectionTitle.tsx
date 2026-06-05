import { User, Users } from 'lucide-react'

// Единый заголовок блока близкого (Приёмы + Аптечка).
// account=false → локальный профиль (свой / расшаренный): 👤 Имя
// account=true  → linked-аккаунт (F7): 👥 @username
// Счётчик «сколько принять» рендерит MedSection в шапке секции (Приёмы).
export default function DepSectionTitle({ name, account }: { name: string; account?: boolean }) {
  return (
    <h2 className="section-title section-title--dep">
      {account ? <Users size={15} strokeWidth={2} /> : <User size={15} strokeWidth={2} />}
      <span>{account ? `@${name}` : name}</span>
    </h2>
  )
}
