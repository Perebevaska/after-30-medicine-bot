import { useSignal, initDataRaw, themeParams, viewport } from '@telegram-apps/sdk-react'
import { useEffect } from 'react'
import { setInitData } from './api/client'
import './App.css'

function Dashboard() {
  return (
    <div className="page">
      <h1>Лекарства на сегодня</h1>
      <p className="hint">M2 — дашборд в разработке</p>
    </div>
  )
}

export default function App() {
  const rawData = useSignal(initDataRaw)

  useEffect(() => {
    if (rawData) setInitData(rawData)
  }, [rawData])

  useEffect(() => {
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
