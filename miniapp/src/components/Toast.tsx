import { useEffect, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'

// WP6: единый плавающий тост (fixed, над нав-баром). Тайминги — токены --dur/--ease.
// Авто-скрытие опционально (duration > 0); закрытие крестиком — при closable.
// Контекстные подтверждения (рядом с кнопкой) сюда НЕ сводим — они остаются inline.
export function Toast({
  children,
  onClose,
  duration,
  tone = 'accent',
  closable = false,
}: {
  children: ReactNode
  onClose?: () => void
  duration?: number
  tone?: 'accent' | 'success'
  closable?: boolean
}) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (!onClose || !duration || duration <= 0) return
    timerRef.current = setTimeout(onClose, duration)
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [onClose, duration])

  return (
    <div className={`toast toast--${tone}`} role="status">
      {children}
      {closable && onClose && (
        <button type="button" className="toast-close" aria-label="Закрыть" onClick={onClose}>
          <X size={16} strokeWidth={2.5} />
        </button>
      )}
    </div>
  )
}
