import { postEvent } from '@telegram-apps/sdk-react'

// Нативный Telegram haptic (impact). Требует web_app_ready при старте
// (main.tsx), иначе Android-клиент игнорит событие. Веб-фоллбэк через
// navigator.vibrate (вне Telegram).
export function haptic(style: 'heavy' | 'light' = 'heavy') {
  try {
    postEvent('web_app_trigger_haptic_feedback', { type: 'impact', impact_style: style })
    return
  } catch { /* noop */ }
  try { navigator.vibrate?.(style === 'light' ? 12 : 35) } catch { /* noop */ }
}
