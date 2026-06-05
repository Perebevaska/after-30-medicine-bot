import { useEffect, useState } from 'react'

// Онбординг-тур первого запуска. Переключает активную вкладку под каждый шаг,
// подсвечивает пункт нав-бара ИЛИ элемент(ы) внутри страницы (по селектору,
// скоуп — активная .tab-panel). Несколько селекторов → подсветка их объединения.
// Флаг прохождения — localStorage 'onboarding_done'. Без внешних библиотек.

const KEY = 'onboarding_done'
const NAV_ORDER = ['dashboard', 'medications', 'stats', 'settings'] as const
type NavPage = typeof NAV_ORDER[number]

interface Step {
  tab: NavPage
  // 'nav' → иконка пункта нав-бара этой вкладки; строка/массив строк → CSS-селектор(ы)
  // элемента(ов) внутри активной панели (скроллим к центру, подсвечиваем объединение).
  target: 'nav' | string | string[]
  title: string
  text: string
  card?: 'top' | 'bottom' // принудительное положение карточки (иначе авто)
}

const STEPS: Step[] = [
  { tab: 'medications', target: ['.mlist-add-btn', '.mlist-card'], card: 'bottom', title: 'Аптечка',
    text: 'Здесь все препараты. Добавляйте новые кнопкой «+» сверху. Для примера мы уже добавили демо-препарат «Счастьепин».' },
  { tab: 'dashboard', target: '.mlist-card', card: 'bottom', title: 'Приёмы',
    text: 'Экран дня. Отмечайте принятые приёмы — сдвиньте зелёный бегунок вправо. Попробуйте на «Счастьепине».' },
  { tab: 'stats', target: '.streak-card', card: 'bottom', title: 'Прогресс',
    text: 'Серия без пропусков — сколько дней подряд вы принимаете препараты вовремя.' },
  { tab: 'stats', target: '#tour-reports', title: 'Отчёты',
    text: 'Выгрузка PDF: расписание на неделю, история приёмов, отчёт для врача — файл придёт прямо в чат с ботом.' },
  { tab: 'settings', target: 'nav', title: 'Настройки',
    text: 'Напоминания, тема оформления, часовой пояс и забота о близких.' },
  { tab: 'settings', target: '#tour-care', card: 'top', title: 'Забота',
    text: 'Режим «Забота»: следите за приёмами близких и управляйте их аптечкой — или дайте код помощнику, чтобы он помогал вам.' },
]

// eslint-disable-next-line react-refresh/only-export-components
export function shouldShowOnboarding(): boolean {
  return !localStorage.getItem(KEY)
}

// Сброс флага — обучение покажется снова (напр. после удаления всех данных).
// eslint-disable-next-line react-refresh/only-export-components
export function resetOnboarding(): void {
  localStorage.removeItem(KEY)
}

interface Rect { left: number; top: number; width: number; height: number }

export default function OnboardingTour({
  onClose,
  onNavigate,
}: {
  onClose: () => void
  onNavigate: (p: NavPage) => void
}) {
  const [step, setStep] = useState(0)
  const [rect, setRect] = useState<Rect | null>(null)
  const cur = STEPS[step]
  const isNav = cur.target === 'nav'

  // Принудительный сброс положения окон (скролл всех панелей) при старте тура —
  // иначе элемент шага может оказаться за пределами видимой области и не подсветиться.
  useEffect(() => {
    document.querySelectorAll('.tab-panel').forEach((p) => { (p as HTMLElement).scrollTop = 0 })
  }, [])

  useEffect(() => {
    onNavigate(cur.tab)
    let cancelled = false
    let raf = 0
    const panelIdx = NAV_ORDER.indexOf(cur.tab)

    const getEls = (): HTMLElement[] => {
      if (cur.target === 'nav') {
        const items = document.querySelectorAll('.bottom-nav .nav-item')
        const navEl = items[panelIdx] as HTMLElement | undefined
        const icon = navEl?.querySelector('svg') as unknown as HTMLElement | null
        return icon ? [icon] : navEl ? [navEl] : []
      }
      const panel = document.querySelectorAll('.tab-panel')[panelIdx] as HTMLElement | undefined
      const root: ParentNode = panel ?? document
      const sels = Array.isArray(cur.target) ? cur.target : [cur.target]
      return sels
        .map((s) => root.querySelector(s) as HTMLElement | null)
        .filter((e): e is HTMLElement => !!e)
    }

    const commit = (els: HTMLElement[]) => {
      if (cancelled) return
      if (!els.length) { setRect(null); return }
      let l = Infinity, t = Infinity, r = -Infinity, b = -Infinity
      els.forEach((e) => {
        const x = e.getBoundingClientRect()
        l = Math.min(l, x.left); t = Math.min(t, x.top)
        r = Math.max(r, x.right); b = Math.max(b, x.bottom)
      })
      setRect({ left: l, top: t, width: r - l, height: b - t })
    }

    let scrolled = false
    const tryMeasure = (deadline: number) => {
      if (cancelled) return
      const els = getEls()
      if (els.length) {
        if (isNav) { commit(els); return }
        if (!scrolled) {
          scrolled = true
          els[0].scrollIntoView({ block: 'center', behavior: 'smooth' })
          // домеряем после settle скролла (smooth ~ до ~500мс)
          window.setTimeout(() => commit(getEls()), 420)
          window.setTimeout(() => commit(getEls()), 760)
        }
        commit(els)
        return
      }
      // элемент ещё не отрисован (смена вкладки / дозагрузка демо-мед) — поллим
      if (Date.now() < deadline) raf = requestAnimationFrame(() => tryMeasure(deadline))
      else setRect(null)
    }

    const start = window.setTimeout(() => tryMeasure(Date.now() + 1800), isNav ? 60 : 100)
    const onResize = () => commit(getEls())
    window.addEventListener('resize', onResize)
    return () => {
      cancelled = true
      clearTimeout(start)
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
    }
  }, [step, cur.tab, cur.target, isNav, onNavigate])

  const finish = () => {
    localStorage.setItem(KEY, '1')
    onNavigate('dashboard')
    onClose()
  }
  const next = () => (step < STEPS.length - 1 ? setStep((s) => s + 1) : finish())
  const back = () => setStep((s) => Math.max(0, s - 1))

  const pad = isNav ? 13 : 8
  const cardPlace = cur.card ?? (rect && rect.top + rect.height / 2 > window.innerHeight * 0.55 ? 'top' : 'bottom')

  return (
    <div className="tour-overlay" onClick={next}>
      {rect && (
        <div
          className="tour-spot"
          style={{
            left: rect.left - pad,
            top: rect.top - pad,
            width: rect.width + pad * 2,
            height: rect.height + pad * 2,
          }}
        />
      )}
      <div className={`tour-card${cardPlace === 'top' ? ' tour-card--top' : ''}`} onClick={(e) => e.stopPropagation()}>
        <div className="tour-step-count">{step + 1} / {STEPS.length}</div>
        <h3 className="tour-title">{cur.title}</h3>
        <p className="tour-text">{cur.text}</p>
        <div className="tour-actions">
          <button type="button" className="tour-skip" onClick={finish}>Пропустить</button>
          <div className="tour-nav-btns">
            {step > 0 && (
              <button type="button" className="tour-back" onClick={back}>Назад</button>
            )}
            <button type="button" className="tour-next" onClick={next}>
              {step < STEPS.length - 1 ? 'Далее' : 'Понятно'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
