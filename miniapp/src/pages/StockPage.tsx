import { useRef, useState, useEffect } from 'react'
import {
  useMedications,
  useStock,
  useSetStock,
  useAddStock,
  useSetStockUnits,
  useSetStockThreshold,
  useDisableStock,
} from '../api/hooks'
import type { Medication } from '../api/types'

function daysClass(daysLeft: number, threshold: number): string {
  if (daysLeft <= Math.max(1, Math.floor(threshold / 2))) return 'stock-status--critical'
  if (daysLeft <= threshold) return 'stock-status--low'
  return 'stock-status--ok'
}

function daysLabel(n: number): string {
  if (n === 1) return '1 день'
  if (n >= 2 && n <= 4) return `${n} дня`
  return `${n} дней`
}

function StockExpanded({ med }: { med: Medication }) {
  const { data, isLoading } = useStock(med.id)
  const mutSet = useSetStock()
  const mutAdd = useAddStock()
  const mutUnits = useSetStockUnits()
  const mutThreshold = useSetStockThreshold()
  const mutDisable = useDisableStock()

  const [addAmt, setAddAmt] = useState('')
  const [newQty, setNewQty] = useState('')
  const [unitsVal, setUnitsVal] = useState('')
  const [threshVal, setThreshVal] = useState('')
  const initialized = useRef(false)

  useEffect(() => {
    if (!data || initialized.current) return
    initialized.current = true
    if (data.stock_qty !== null && data.stock_qty !== undefined) {
      setNewQty(String(data.stock_qty))
    }
    setUnitsVal(String(data.units_per_dose ?? 1))
    setThreshVal(String(data.low_stock_days ?? 7))
  }, [data])

  if (isLoading) return <p className="stock-loading">Загрузка…</p>

  const hasStock = data?.stock_qty !== null && data?.stock_qty !== undefined
  const daysLeft = data?.days_left
  const threshold = data?.low_stock_days ?? 7

  return (
    <div className="stock-expanded">
      {hasStock && daysLeft !== null && daysLeft !== undefined && (
        <div className={`stock-days-badge ${daysClass(daysLeft, threshold)}`}>
          ~{daysLabel(daysLeft)} осталось
        </div>
      )}

      <div className="stock-row">
        <span className="stock-row-label">Установить запас</span>
        <input
          className="field-input field-input--short"
          type="number"
          inputMode="decimal"
          min="0"
          value={newQty}
          onChange={(e) => setNewQty(e.target.value)}
          placeholder="0"
        />
        <button
          className="stock-btn"
          disabled={mutSet.isPending || newQty === ''}
          onClick={() => {
            const qty = parseFloat(newQty)
            if (!isNaN(qty) && qty >= 0) mutSet.mutate({ medId: med.id, qty })
          }}
        >
          ✓
        </button>
      </div>

      {hasStock && (
        <div className="stock-row">
          <span className="stock-row-label">Пополнить</span>
          <input
            className="field-input field-input--short"
            type="number"
            inputMode="decimal"
            min="0"
            value={addAmt}
            onChange={(e) => setAddAmt(e.target.value)}
            placeholder="0"
          />
          <button
            className="stock-btn"
            disabled={mutAdd.isPending || addAmt === ''}
            onClick={() => {
              const amount = parseFloat(addAmt)
              if (!isNaN(amount) && amount > 0) {
                mutAdd.mutate({ medId: med.id, amount }, { onSuccess: () => setAddAmt('') })
              }
            }}
          >
            +
          </button>
        </div>
      )}

      <div className="stock-settings">
        <div className="stock-row">
          <span className="stock-row-label">Ед. за приём</span>
          <input
            className="field-input field-input--short"
            type="number"
            inputMode="decimal"
            min="0.1"
            step="0.5"
            value={unitsVal}
            onChange={(e) => setUnitsVal(e.target.value)}
          />
        </div>
        <div className="stock-row">
          <span className="stock-row-label">Порог (дней)</span>
          <input
            className="field-input field-input--short"
            type="number"
            inputMode="numeric"
            min="1"
            value={threshVal}
            onChange={(e) => setThreshVal(e.target.value)}
          />
        </div>
        <button
          className="btn-primary"
          disabled={mutUnits.isPending || mutThreshold.isPending}
          onClick={() => {
            const u = parseFloat(unitsVal)
            const t = parseInt(threshVal, 10)
            if (!isNaN(u) && u > 0) mutUnits.mutate({ medId: med.id, units: u })
            if (!isNaN(t) && t > 0) mutThreshold.mutate({ medId: med.id, days: t })
          }}
        >
          Сохранить настройки
        </button>
      </div>

      {hasStock && (
        <button
          className="stock-disable-btn"
          disabled={mutDisable.isPending}
          onClick={() => mutDisable.mutate(med.id)}
        >
          Отключить отслеживание
        </button>
      )}
    </div>
  )
}

function StockCard({ med }: { med: Medication }) {
  const [open, setOpen] = useState(false)
  const hasStock = med.stock_qty !== null && med.stock_qty !== undefined

  return (
    <div className="stock-card">
      <button className="stock-card-header" onClick={() => setOpen((v) => !v)}>
        <div className="stock-card-info">
          <span className="stock-card-name">{med.name}</span>
          <span className={`stock-card-qty${hasStock ? '' : ' stock-card-qty--none'}`}>
            {hasStock ? `${med.stock_qty} ед.` : 'не отслеживается'}
          </span>
        </div>
        <span className="stock-chevron">{open ? '▲' : '▼'}</span>
      </button>
      {open && <StockExpanded med={med} />}
    </div>
  )
}

export default function StockPage() {
  const { data, isLoading, error } = useMedications()

  return (
    <div className="page">
      <div className="mlist-header">
        <h2 className="mlist-title">Запас</h2>
      </div>

      {isLoading && <p className="hint">Загрузка…</p>}
      {error && <p className="hint error">{error.message}</p>}

      {data && data.length === 0 && <p className="hint">Нет лекарств</p>}

      {data && data.length > 0 && (
        <div className="stock-list">
          {data.map((med) => (
            <StockCard key={med.id} med={med} />
          ))}
        </div>
      )}
    </div>
  )
}
