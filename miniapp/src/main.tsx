import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { init, isTMA } from '@telegram-apps/sdk-react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
})

export const inTelegram = isTMA()

if (inTelegram) {
  init()
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
