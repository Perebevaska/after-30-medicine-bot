import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { init, isTMA, postEvent, restoreInitData, retrieveRawInitData } from '@telegram-apps/sdk-react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ErrorBoundary } from './components/ErrorBoundary'
import { setInitData } from './api/client'
import { initTheme } from './theme'
import './index.css'
import App from './App.tsx'

initTheme()

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
})

export const inTelegram = isTMA()

if (inTelegram) {
  init()
  restoreInitData()
  const raw = retrieveRawInitData()
  if (raw) setInitData(raw)
  // Без web_app_ready Telegram Android может игнорировать UI-события (в т.ч. haptic).
  try { postEvent('web_app_ready') } catch { /* noop */ }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
)
