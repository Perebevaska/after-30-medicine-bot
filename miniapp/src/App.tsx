import { themeParams, viewport } from '@telegram-apps/sdk-react'
import { useEffect, useState } from 'react'
import { inTelegram } from './main'
import Dashboard from './pages/Dashboard'
import MedicationList from './pages/MedicationList'
import MedicationForm from './pages/MedicationForm'
import './App.css'

type NavPage = 'dashboard' | 'medications'

function BottomNav({ active, onChange }: { active: NavPage; onChange: (p: NavPage) => void }) {
  return (
    <nav className="bottom-nav">
      <button
        type="button"
        className={`nav-item${active === 'dashboard' ? ' nav-item--active' : ''}`}
        onClick={() => onChange('dashboard')}
      >
        <span className="nav-icon">📅</span>
        <span className="nav-label">Сегодня</span>
      </button>
      <button
        type="button"
        className={`nav-item${active === 'medications' ? ' nav-item--active' : ''}`}
        onClick={() => onChange('medications')}
      >
        <span className="nav-icon">💊</span>
        <span className="nav-label">Лекарства</span>
      </button>
    </nav>
  )
}

export default function App() {
  const [navPage, setNavPage] = useState<NavPage>('dashboard')
  const [editMedId, setEditMedId] = useState<number | undefined>()
  const [showForm, setShowForm] = useState(false)

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

  const openForm = (editId?: number) => {
    setEditMedId(editId)
    setShowForm(true)
  }

  const closeForm = () => {
    setShowForm(false)
    setEditMedId(undefined)
  }

  if (showForm) {
    return <MedicationForm editId={editMedId} onBack={closeForm} />
  }

  return (
    <>
      {navPage === 'dashboard' && <Dashboard />}
      {navPage === 'medications' && (
        <MedicationList onAdd={() => openForm()} onEdit={(id) => openForm(id)} />
      )}
      <BottomNav active={navPage} onChange={setNavPage} />
    </>
  )
}
