import { useState, useRef, useEffect, useMemo, forwardRef, useImperativeHandle } from 'react'
import { createPortal } from 'react-dom'
import { Check, X, Globe, Pill, Pause, ArrowRight, Heart, Send } from 'lucide-react'
import { postEvent } from '@telegram-apps/sdk-react'
import { useToday, useLogIntake, useHearts, useSettings, useMedications, useWishesStatus, useWishInbox, useSendWish, useReactWish } from '../api/hooks'
import { useQueryClient } from '@tanstack/react-query'
import { api, apiErrorMessage } from '../api/client'
import type { TodayItem } from '../api/types'
import { randomWish } from '../wishes'
import { MEAL_LABELS } from '../constants'
import DepSectionTitle from '../components/DepSectionTitle'

interface HeartParticle {
  id: number
  x: number
  y: number
  dx: number
  dy: number
  size: number
  dur: number
  emoji?: string
}

let _pid = 0

export type WishCardHandle = { celebrate: () => void; skipped: () => void }

const WishCard = forwardRef<WishCardHandle>(function WishCard(_, ref) {
  const [wish, setWish] = useState(randomWish)
  const [particles, setParticles] = useState<HeartParticle[]>([])
  const [shaking, setShaking] = useState(false)
  const heartRef = useRef<HTMLSpanElement>(null)
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([])

  useEffect(() => () => { timersRef.current.forEach(clearTimeout) }, [])

  const addTimer = (fn: () => void, ms: number) => {
    const id = setTimeout(fn, ms)
    timersRef.current.push(id)
    return id
  }
  // G1: счётчик сердечек рядом с ❤️
  const { data: heartsData } = useHearts()
  const hearts = heartsData?.hearts ?? 0

  const spawnHearts = () => {
    const rect = heartRef.current?.getBoundingClientRect()
    if (!rect) return
    const cx = rect.left + rect.width / 2
    const cy = rect.top + rect.height / 2
    const count = 13
    const batch: HeartParticle[] = Array.from({ length: count }, () => {
      const angle = Math.random() * Math.PI * 2
      const dist = 65 + Math.random() * 140
      return {
        id: ++_pid,
        x: cx,
        y: cy,
        dx: Math.cos(angle) * dist,
        dy: Math.sin(angle) * dist,
        size: 9 + Math.random() * 13,
        dur: 520 + Math.random() * 380,
      }
    })
    setParticles((p) => [...p, ...batch])
    const maxDur = Math.max(...batch.map((p) => p.dur)) + 60
    const ids = new Set(batch.map((p) => p.id))
    addTimer(() => setParticles((p) => p.filter((pt) => !ids.has(pt.id))), maxDur)
  }

  const celebrate = () => {
    setWish((w) => randomWish(w))
    spawnHearts()
  }

  const spawnBrokenHearts = () => {
    const rect = heartRef.current?.getBoundingClientRect()
    if (!rect) return
    const cx = rect.left + rect.width / 2
    const cy = rect.top + rect.height / 2
    const batch: HeartParticle[] = Array.from({ length: 3 }, () => ({
      id: ++_pid,
      x: cx,
      y: cy,
      dx: (Math.random() - 0.5) * 50,
      dy: 65 + Math.random() * 55,
      size: 14 + Math.random() * 6,
      dur: 480 + Math.random() * 180,
      emoji: '💔',
    }))
    setParticles((p) => [...p, ...batch])
    const maxDur = Math.max(...batch.map((p) => p.dur)) + 60
    const ids = new Set(batch.map((p) => p.id))
    addTimer(() => setParticles((p) => p.filter((pt) => !ids.has(pt.id))), maxDur)
  }

  const skipped = () => {
    setShaking(true)
    addTimer(() => setShaking(false), 580)
    spawnBrokenHearts()
  }

  useImperativeHandle(ref, () => ({ celebrate, skipped }))

  return (
    <>
      <div className="wish-card">
        <div className="wish-text-wrap">
          <span className="wish-text">{wish}</span>
        </div>
        <span className="wish-heart-wrap">
          <span ref={heartRef} className={`wish-heart${shaking ? ' wish-heart--shake' : ''}`} aria-hidden="true">❤️</span>
          <span className="wish-heart-count">{hearts}</span>
        </span>
      </div>
      {createPortal(
        <div className="hearts-overlay" aria-hidden="true">
          {particles.map((p) => (
            <span
              key={p.id}
              className="heart-particle"
              style={{
                left: p.x,
                top: p.y,
                fontSize: p.size,
                '--dx': `${p.dx}px`,
                '--dy': `${p.dy}px`,
                '--dur': `${p.dur}ms`,
              } as React.CSSProperties}
            >
              {p.emoji ?? '❤️'}
            </span>
          ))}
        </div>,
        document.body
      )}
    </>
  )
})

const itemKey = (i: TodayItem) => `${i.medication_id}-${i.reminder_time}`
// AX5: is_due приходит с сервера (TZ аккаунта), не считаем по времени браузера.
const isDuePending = (i: TodayItem) => i.status === 'pending' && i.is_due

// Вибрация в конце удержания: нативный Telegram haptic (impact heavy).
// Требует web_app_ready при старте (main.tsx), иначе Android-клиент игнорит событие.
function haptic(style: 'heavy' | 'light' = 'heavy') {
  try {
    postEvent('web_app_trigger_haptic_feedback', { type: 'impact', impact_style: style })
    return
  } catch { /* noop */ }
  // Веб-фоллбэк (вне Telegram)
  try { navigator.vibrate?.(style === 'light' ? 12 : 35) } catch { /* noop */ }
}

// Подсказка-инструкция показывается, пока юзер не отметит первый приём.
const SLIDE_LEARNED_KEY = 'slide_learned'
function slideLearned(): boolean {
  try { return localStorage.getItem(SLIDE_LEARNED_KEY) === '1' } catch { return false }
}
function markSlideLearned(): void {
  try { localStorage.setItem(SLIDE_LEARNED_KEY, '1') } catch { /* noop */ }
}

const KNOB = 42
const KNOB_MARGIN = 3 // .slide-knob margin в CSS — синхронизировать при изменении

// Слайдер «сдвинь, чтобы принять»: тянем бегунок вправо до конца → onConfirm.
// Осознанное действие — случайный тап не отмечает.
function SlideToConfirm({ onConfirm, disabled }: { onConfirm: () => void; disabled?: boolean }) {
  // Позиция кружка двигается напрямую через DOM (без React-state) — иначе ре-рендер
  // на каждый pointermove не успевает за пальцем в Telegram-webview.
  const trackRef = useRef<HTMLDivElement>(null)
  const knobRef = useRef<HTMLSpanElement>(null)
  const fillRef = useRef<HTMLSpanElement>(null)
  const labelRef = useRef<HTMLSpanElement>(null)
  const draggingRef = useRef(false)
  const offsetRef = useRef(0)
  const maxRef = useRef(0)
  const doneRef = useRef(false)

  const computeMax = () => Math.max(0, (trackRef.current?.clientWidth ?? 0) - KNOB - 2 * KNOB_MARGIN)

  // Стартовая позиция через DOM, НЕ через inline-style в JSX: иначе любой ре-рендер
  // родителя (фоновый refetch ['today'] после отметки) сбрасывал бы кружок на 0 во время тяги.
  useEffect(() => {
    if (knobRef.current) knobRef.current.style.transform = 'translateX(0px)'
    if (fillRef.current) fillRef.current.style.width = `${KNOB + 2 * KNOB_MARGIN}px`
  }, [])

  // Прямая отрисовка позиции x по DOM. withTr — плавный переход (только возврат/завершение).
  const render = (x: number, withTr: boolean) => {
    // ВАЖНО: для отключения перехода нужно валидное `none`, НЕ `transform none`
    // (последнее — невалидный CSS, игнорится → старый 0.2s залипает → лаг за пальцем).
    if (knobRef.current) {
      knobRef.current.style.transition = withTr ? 'transform 0.2s' : 'none'
      knobRef.current.style.transform = `translateX(${x}px)`
    }
    if (fillRef.current) {
      fillRef.current.style.transition = withTr ? 'width 0.2s' : 'none'
      fillRef.current.style.width = `${x + KNOB + 2 * KNOB_MARGIN}px`
    }
    if (labelRef.current) {
      const pct = maxRef.current ? x / maxRef.current : 0
      labelRef.current.style.opacity = `${Math.max(0, 1 - pct * 1.4)}`
    }
  }

  const down = (e: React.PointerEvent) => {
    if (disabled) return
    e.preventDefault()
    draggingRef.current = true
    doneRef.current = false
    maxRef.current = computeMax()
    // getComputedStyle до mount-effect может вернуть 'none' (нет transform в CSS) —
    // DOMMatrixReadOnly('none') кидает SyntaxError, поэтому гасим явно.
    const tr = knobRef.current ? getComputedStyle(knobRef.current).transform : 'none'
    const cur = tr && tr !== 'none' ? new DOMMatrixReadOnly(tr).m41 : 0
    offsetRef.current = e.clientX - cur
    e.currentTarget.setPointerCapture?.(e.pointerId)
  }
  const move = (e: React.PointerEvent) => {
    if (!draggingRef.current) return
    const nx = Math.min(maxRef.current, Math.max(0, e.clientX - offsetRef.current))
    render(nx, false)
    if (nx >= maxRef.current - 1 && !doneRef.current) {
      doneRef.current = true
      draggingRef.current = false
      haptic()
      render(maxRef.current, false) // полная зелёная заливка видна
      requestAnimationFrame(() => onConfirm()) // кадр на отрисовку заливки
    }
  }
  const up = () => {
    if (!draggingRef.current) return
    draggingRef.current = false
    if (!doneRef.current) render(0, true) // плавный возврат
  }

  return (
    <div className={`slide-confirm${disabled ? ' slide-confirm--disabled' : ''}`} ref={trackRef}>
      <span className="slide-fill" ref={fillRef} />
      <span className="slide-label" ref={labelRef}>Сдвинь, чтобы принять</span>
      <span
        className="slide-knob"
        ref={knobRef}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
      >
        <Check size={22} strokeWidth={2.75} />
      </span>
    </div>
  )
}

// Пропуск приёма — вторичное действие: тап → «Точно пропустить?» → тап подтверждает.
// Круглая кнопка «пропустить»: тап1 взводит (красная заливка + пульс + подпись),
// тап2 подтверждает. Авто-сброс через 3с. Случайный одиночный тап не пропустит.
function SkipButton({ onConfirm, disabled }: { onConfirm: () => void; disabled?: boolean }) {
  const [armed, setArmed] = useState(false) // взведено — ждём подтверждающий тап
  const tRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => { if (tRef.current) clearTimeout(tRef.current) }, [])

  const click = () => {
    if (disabled) return
    if (!armed) {
      setArmed(true)
      haptic('light')
      if (tRef.current) clearTimeout(tRef.current)
      tRef.current = setTimeout(() => setArmed(false), 3000)
      return
    }
    if (tRef.current) clearTimeout(tRef.current)
    haptic('light')
    onConfirm()
  }

  return (
    <div className="skip-wrap">
      {armed && <span className="skip-tip">Тап — пропустить</span>}
      <button
        type="button"
        className={`skip-circle${armed ? ' skip-circle--armed' : ''}`}
        disabled={disabled}
        aria-label={armed ? 'Подтвердить пропуск' : 'Пропустить приём'}
        onClick={click}
      >
        <X size={26} strokeWidth={2.75} />
      </button>
    </div>
  )
}

function MedCard({
  item,
  entering,
  onTaken,
  onSkipped,
}: {
  item: TodayItem
  entering?: boolean
  onTaken?: () => void
  onSkipped?: () => void
}) {
  const { mutate, isPending } = useLogIntake()

  // Undo убран намеренно: отмена приёма ломала «курс завершён» (COUNT taken).
  // Приём подтверждается слайдером (SlideToConfirm) — случайный тап не отметит.
  const log = (status: 'taken' | 'skipped') => {
    if (status === 'taken') onTaken?.()
    if (status === 'skipped') onSkipped?.()
    mutate({
      medication_id: item.medication_id,
      scheduled_time: item.reminder_time,
      status,
    })
  }

  const due = isDuePending(item)
  const extraClass = entering ? ' mlist-card--enter' : ''
  const statusClass = item.status === 'skipped'
    ? ' mlist-card--skipped'
    : item.status === 'taken'
    ? ' mlist-card--taken'
    : ''

  const pending = item.status === 'pending'
  return (
    <div
      className={`mlist-card${statusClass}${due ? ' mlist-card--due' : ''}${extraClass}${pending ? ' mlist-card--slide' : ''}`}
    >
      <div className="mlist-info">
        <div className="mlist-name mlist-name--withtime">
          <span className="mlist-nm">{item.name}</span>
          <span className="mlist-time">{item.reminder_time}</span>
        </div>
        <div className="mlist-meta">
          {item.dosage} · {MEAL_LABELS[item.meal_relation] ?? item.meal_relation}
        </div>
      </div>

      {pending ? (
        <div className="slide-row">
          <SlideToConfirm onConfirm={() => log('taken')} disabled={isPending} />
          <SkipButton onConfirm={() => log('skipped')} disabled={isPending} />
        </div>
      ) : (
        <div className="med-actions">
          <span className={`med-status med-status--${item.status}`} aria-hidden="true">
            {item.status === 'taken' ? <Check size={26} strokeWidth={2.75} /> : <X size={26} strokeWidth={2.75} />}
          </span>
        </div>
      )}
    </div>
  )
}

// Ф15: соцмеханика пожеланий (тестовый функционал). Самодостаточный блок —
// рендерится только если в настройках включён тогл «Слова поддержки».
function WishZone({ enabled }: { enabled: boolean }) {
  const { data: inbox } = useWishInbox(enabled)
  const { data: status } = useWishesStatus(enabled)
  const sendWish = useSendWish()
  const reactWish = useReactWish()
  const [open, setOpen] = useState(false)
  const [justSent, setJustSent] = useState(false)

  if (!enabled) return null

  const incoming = inbox?.[0]
  const canSend = !!status?.pool_ready && (status?.sent_today ?? 0) < (status?.daily_limit ?? 0)
  const ackHelped = status?.ack_helped ?? 0
  const ackSupported = status?.ack_supported ?? 0
  const ackTotal = ackHelped + ackSupported

  const onSend = async (code: string) => {
    try {
      await sendWish.mutateAsync(code)
      haptic('light')
      setOpen(false)
      setJustSent(true)
      setTimeout(() => setJustSent(false), 2500)
    } catch { /* ошибка — тихо, статус обновится */ }
  }

  const onReact = (id: number, reaction: 'helped' | 'supported') => {
    haptic('light')
    reactWish.mutate({ id, reaction })
  }

  return (
    <div className="wish-zone">
      {incoming && (
        <div className="wish-inbox">
          <div className="wish-inbox-head"><Heart size={15} strokeWidth={2} className="ic" /> Вам передали поддержку</div>
          <div className="wish-inbox-text">{incoming.text}</div>
          <div className="wish-inbox-actions">
            <button className="wish-react-btn" onClick={() => onReact(incoming.id, 'helped')}>👍 Помогло</button>
            <button className="wish-react-btn wish-react-btn--love" onClick={() => onReact(incoming.id, 'supported')}>❤️ Очень поддержало</button>
          </div>
        </div>
      )}

      {ackTotal > 0 && (
        <div className="wish-ack">
          <Heart size={15} strokeWidth={2} className="ic" />
          <span>Вашу поддержку оценили {ackTotal}&nbsp;раз{ackHelped ? ` · 👍 ${ackHelped}` : ''}{ackSupported ? ` · ❤️ ${ackSupported}` : ''}</span>
        </div>
      )}

      {justSent ? (
        <div className="wish-sent-toast"><Heart size={15} strokeWidth={2} className="ic" /> Поддержка отправлена</div>
      ) : canSend ? (
        <div className="wish-send">
          {!open ? (
            <button className="wish-send-btn" onClick={() => setOpen(true)}>
              <Send size={15} strokeWidth={2} className="ic" /> Передать поддержку незнакомцу
            </button>
          ) : (
            <div className="wish-send-presets">
              <div className="wish-send-head">Выберите пожелание — оно уйдёт случайному человеку:</div>
              {(status?.presets ?? []).map((p) => (
                <button
                  key={p.code}
                  className="wish-preset-chip"
                  disabled={sendWish.isPending}
                  onClick={() => onSend(p.code)}
                >
                  {p.text}
                </button>
              ))}
              <button className="wish-send-cancel" onClick={() => setOpen(false)}>Отмена</button>
            </div>
          )}
        </div>
      ) : status && !status.pool_ready ? (
        <div className="wish-pool-hint">Пока мало участников — поддержку можно будет передать позже</div>
      ) : null}
    </div>
  )
}

export default function Dashboard({ onNavigate }: { onNavigate?: (p: 'medications') => void }) {
  const { data, isLoading, error } = useToday()
  const { data: meds } = useMedications()
  const { data: settings } = useSettings()
  const qc = useQueryClient()
  const [takingAll, setTakingAll] = useState(false)
  const [takeAllArmed, setTakeAllArmed] = useState(false) // двойной тап: 1й взводит, 2й принимает
  const takeAllTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => { if (takeAllTimer.current) clearTimeout(takeAllTimer.current) }, [])
  const [tzBannerDismissed, setTzBannerDismissed] = useState(false)
  const [showHoldHint, setShowHoldHint] = useState(!slideLearned())
  const wishRef = useRef<WishCardHandle>(null)

  const learnHold = () => { markSlideLearned(); setShowHoldHint(false) }

  // Раскладка приёмов по секциям — пересчитывается только при смене данных ['today'].
  const {
    localDepGroups, linkedGroups, sharedDepGroups, dueItems, otherItems, linkedItems, sharedDepItems,
  } = useMemo(() => {
    const allItems = data ?? []
    // F7: separate own items from linked dependents' items
    const ownItems = allItems.filter((i) => !i.linked_user_id && !i.dep_share_id && !i.dependent_id)
    // Свои локальные близкие — отдельным блоком (как F7/F8)
    const localDepItems = allItems.filter((i) => !i.linked_user_id && !i.dep_share_id && !!i.dependent_id)
    const linkedItems = allItems.filter((i) => !!i.linked_user_id)
    const sharedDepItems = allItems.filter((i) => !!i.dep_share_id)

    // Группировка своих локальных близких по dependent_id
    const localDepGroups = localDepItems.reduce<Record<number, { name: string; items: TodayItem[] }>>((acc, item) => {
      const did = item.dependent_id!
      if (!acc[did]) acc[did] = { name: item.dependent_name ?? `№${did}`, items: [] }
      acc[did].items.push(item)
      return acc
    }, {})

    // Group linked items by linked_user_id
    const linkedGroups = linkedItems.reduce<Record<number, { name: string; items: TodayItem[] }>>((acc, item) => {
      const uid = item.linked_user_id!
      if (!acc[uid]) acc[uid] = { name: item.linked_user_name ?? `id${uid}`, items: [] }
      acc[uid].items.push(item)
      return acc
    }, {})

    // F8: group shared dep items by dep_share_id
    const sharedDepGroups = sharedDepItems.reduce<Record<number, { name: string; items: TodayItem[] }>>((acc, item) => {
      const did = item.dep_share_id!
      if (!acc[did]) acc[did] = { name: item.dep_share_name ?? `dep${did}`, items: [] }
      acc[did].items.push(item)
      return acc
    }, {})

    const dueItems = ownItems
      .filter(isDuePending)
      .sort((a, b) => b.reminder_time.localeCompare(a.reminder_time))
    const otherItems = ownItems.filter((i) => !isDuePending(i))
    return { localDepGroups, linkedGroups, sharedDepGroups, dueItems, otherItems, linkedItems, sharedDepItems }
  }, [data])

  const clickTakeAll = () => {
    if (takingAll || !dueItems.length) return
    if (!takeAllArmed) {
      setTakeAllArmed(true)
      haptic('light')
      if (takeAllTimer.current) clearTimeout(takeAllTimer.current)
      takeAllTimer.current = setTimeout(() => setTakeAllArmed(false), 3000)
      return
    }
    if (takeAllTimer.current) clearTimeout(takeAllTimer.current)
    setTakeAllArmed(false)
    handleTakeAll()
  }

  const handleTakeAll = async () => {
    if (!dueItems.length) return
    setTakingAll(true)
    learnHold()
    wishRef.current?.celebrate()
    // Метим только СВОИ due-приёмы (как dueItems) — кнопка «Принять всё»
    // постит лишь own. Иначе due локальных близких/shared мигали бы «принято».
    const dueKeys = new Set(dueItems.map(itemKey))
    const prev = qc.getQueryData<TodayItem[]>(['today'])
    qc.setQueryData<TodayItem[]>(['today'], (old) =>
      old?.map((item) =>
        dueKeys.has(itemKey(item)) ? { ...item, status: 'taken' as const } : item
      )
    )
    try {
      await Promise.all(
        dueItems.map((item) =>
          api.post('/today/intake', {
            medication_id: item.medication_id,
            scheduled_time: item.reminder_time,
            status: 'taken',
          })
        )
      )
    } catch {
      if (prev) qc.setQueryData(['today'], prev)
    } finally {
      await qc.invalidateQueries({ queryKey: ['today'] })
      await qc.invalidateQueries({ queryKey: ['hearts'] })
      qc.invalidateQueries({ queryKey: ['streak'], refetchType: 'none' })
      qc.invalidateQueries({ queryKey: ['adherence'], refetchType: 'none' })
      qc.invalidateQueries({ queryKey: ['stats-overview'], refetchType: 'none' })
      setTakingAll(false)
    }
  }

  const hasAny = dueItems.length > 0 || otherItems.length > 0
  const hasLinked = linkedItems.length > 0
  const hasSharedDeps = sharedDepItems.length > 0

  const showTzBanner = !tzBannerDismissed && settings?.timezone === 'UTC'

  return (
    <div className="page">
      {showTzBanner && (
        <div className="tz-banner">
          <span className="tz-banner-text">
            <Globe size={15} strokeWidth={2} className="ic" /> Похоже, часовой пояс не задан — напоминания могут приходить не вовремя.
            Зайди в <b>Настройки</b> и выбери свой город.
          </span>
          <button className="tz-banner-close" onClick={() => setTzBannerDismissed(true)} aria-label="Закрыть">
            <X size={16} strokeWidth={2.5} />
          </button>
        </div>
      )}
      <WishCard ref={wishRef} />

      {isLoading && <p className="hint">Загрузка…</p>}

      {error && <p className="hint error">{apiErrorMessage(error)}</p>}

      {data && data.length === 0 && (() => {
        const ownMeds = (meds ?? []).filter((m) => !m.linked_user_id && !m.dep_share_id)
        if (ownMeds.length === 0) {
          return (
            <div className="empty-state">
              <p className="empty-state-title"><Pill size={17} strokeWidth={2} className="ic" /> Пока нет препаратов</p>
              <p className="empty-state-text">Добавьте первый — и я напомню о приёмах вовремя.</p>
              <button type="button" className="empty-state-link" onClick={() => onNavigate?.('medications')}>
                В Аптечку <ArrowRight size={14} strokeWidth={2} className="ic" />
              </button>
            </div>
          )
        }
        if (ownMeds.every((m) => m.paused)) {
          return (
            <div className="empty-state">
              <p className="empty-state-title"><Pause size={17} strokeWidth={2} className="ic" /> Все препараты на паузе</p>
              <p className="empty-state-text">Напоминания не приходят. Снимите паузу, когда будете готовы.</p>
              <button type="button" className="empty-state-link" onClick={() => onNavigate?.('medications')}>
                В Аптечку <ArrowRight size={14} strokeWidth={2} className="ic" />
              </button>
            </div>
          )
        }
        return <p className="hint">На сегодня нет приёмов</p>
      })()}

      {data && hasAny && (
        <>
          {dueItems.length > 0 && (
            <>
              <h2 className="section-title">Сейчас</h2>
              {showHoldHint && (
                <p className="hold-caption">
                  Сдвиньте бегунок вправо, чтобы отметить приём
                </p>
              )}
              <div className="mlist-list">
                {dueItems.map((item) => (
                  <MedCard
                    key={itemKey(item)}
                    item={item}
                    onTaken={() => { wishRef.current?.celebrate(); learnHold() }}
                    onSkipped={() => { wishRef.current?.skipped(); learnHold() }}
                  />
                ))}
              </div>
            </>
          )}

          {dueItems.length >= 2 && (
            <div className="take-all-row">
              <button
                className={`btn-take-all${takeAllArmed ? ' btn-take-all--armed' : ''}`}
                onClick={clickTakeAll}
                disabled={takingAll}
              >
                {takeAllArmed ? 'Тап — принять всё' : 'Принять всё'}
              </button>
            </div>
          )}

          {otherItems.length > 0 && (
            <>
              <h2 className="section-title">Сегодня</h2>
              <div className="mlist-list">
                {otherItems.map((item) => (
                  <MedCard
                    key={itemKey(item)}
                    item={item}
                    entering
                    onTaken={() => wishRef.current?.celebrate()}
                    onSkipped={() => wishRef.current?.skipped()}
                  />
                ))}
              </div>
            </>
          )}
        </>
      )}

      {/* Свои локальные близкие — активные карточки (владелец отмечает приём) */}
      {Object.entries(localDepGroups).map(([did, group]) => (
        <div key={did}>
          <DepSectionTitle name={group.name} />
          <div className="mlist-list">
            {group.items.map((item) => (
              <MedCard
                key={itemKey(item)}
                item={item}
                onTaken={() => wishRef.current?.celebrate()}
                onSkipped={() => wishRef.current?.skipped()}
              />
            ))}
          </div>
        </div>
      ))}

      {/* F7: read-only sections for linked dependents */}
      {hasLinked && Object.entries(linkedGroups).map(([uid, group]) => (
        <div key={uid}>
          <DepSectionTitle name={group.name} account />
          <div className="mlist-list">
            {group.items.map((item) => (
              <div
                key={itemKey(item)}
                className={`mlist-card${item.status === 'skipped' ? ' mlist-card--skipped' : item.status === 'taken' ? ' mlist-card--taken' : ''}${item.is_due && item.status === 'pending' ? ' mlist-card--due' : ''}`}
              >
                <div className="mlist-info">
                  <div className="mlist-name mlist-name--withtime">
                    <span className="mlist-nm">{item.name}</span>
                    <span className="mlist-time">{item.reminder_time}</span>
                  </div>
                  <div className="mlist-meta">
                    {item.dosage}
                  </div>
                </div>
                <div className="med-actions">
                  {item.status === 'pending' ? (
                    <>
                      <button className="btn-take" disabled><Check size={18} strokeWidth={2.5} /></button>
                      <button className="btn-skip" disabled><X size={18} strokeWidth={2.5} /></button>
                    </>
                  ) : (
                    <button className="btn-undo" disabled>
                      {item.status === 'taken' ? <Check size={18} strokeWidth={2.5} /> : <X size={18} strokeWidth={2.5} />}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* F8: shared local dependents — помощник №2 отмечает приёмы (CRUD-доступ) */}
      {hasSharedDeps && Object.entries(sharedDepGroups).map(([did, group]) => (
        <div key={did}>
          <DepSectionTitle name={group.name} />
          <div className="mlist-list">
            {group.items.map((item) => (
              <MedCard
                key={itemKey(item)}
                item={item}
                onTaken={() => wishRef.current?.celebrate()}
                onSkipped={() => wishRef.current?.skipped()}
              />
            ))}
          </div>
        </div>
      ))}

      <WishZone enabled={!!settings?.wishes_enabled} />
    </div>
  )
}
