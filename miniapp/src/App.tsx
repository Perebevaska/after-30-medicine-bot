import {
  useSignal,
  initDataRaw,
  themeParams,
  viewport,
} from '@telegram-apps/sdk-react'
import { useEffect } from 'react'
import { setInitData } from './api/client'
import { inTelegram } from './main'
import Dashboard from './pages/Dashboard'
import './App.css'

export default function App() {
  const rawData = useSignal(initDataRaw)

  useEffect(() => {
    if (rawData) setInitData(rawData)
  }, [rawData])

  // В Telegram ждём initDataRaw перед запросами к API
  if (inTelegram && !rawData) {
    return <p className="hint">Загрузка…</p>
  }

  useEffect(() => {
    if (!inTelegram) return

    void themeParams.mount().then(() => themeParams.bindCssVars())
    void viewport.mount().then(() => {
      viewport.expand()
      viewport.bindCssVars()
    })

    return () => {
      themeParams.unmount()
      viewport.unmount()
    }
  }, [])

  return <Dashboard />
}
