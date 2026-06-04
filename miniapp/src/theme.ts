// Фаза 13: управление темой (auto/light/dark) поверх тёплой палитры «Коралл + крем».
// auto = тёплая палитра + light/dark по Telegram colorScheme (или системной теме вне Telegram).
export type ThemePref = 'auto' | 'light' | 'dark'

const STORAGE_KEY = 'theme_pref'

type TgWebApp = {
  colorScheme?: 'light' | 'dark'
  onEvent?: (event: string, cb: () => void) => void
}

function tg(): TgWebApp | undefined {
  return (window as unknown as { Telegram?: { WebApp?: TgWebApp } }).Telegram?.WebApp
}

export function getThemePref(): ThemePref {
  const v = localStorage.getItem(STORAGE_KEY)
  return v === 'light' || v === 'dark' ? v : 'auto'
}

function systemIsDark(): boolean {
  const scheme = tg()?.colorScheme
  if (scheme === 'dark') return true
  if (scheme === 'light') return false
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

export function resolveTheme(pref: ThemePref): 'light' | 'dark' {
  return pref === 'auto' ? (systemIsDark() ? 'dark' : 'light') : pref
}

export function applyTheme(pref: ThemePref): void {
  document.documentElement.setAttribute('data-theme', resolveTheme(pref))
}

export function setThemePref(pref: ThemePref): void {
  localStorage.setItem(STORAGE_KEY, pref)
  applyTheme(pref)
}

let bound = false
export function initTheme(): void {
  applyTheme(getThemePref())
  if (bound) return
  bound = true
  // В режиме auto переотрисовываемся при смене темы Telegram / системы.
  const onChange = () => { if (getThemePref() === 'auto') applyTheme('auto') }
  tg()?.onEvent?.('themeChanged', onChange)
  window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener?.('change', onChange)
}
