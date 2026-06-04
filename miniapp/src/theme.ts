// Фаза 13/18: тема = режим (auto/light/dark). Один фикс-акцент бренда.
//  - Режим диктует ФОН/ТЕКСТ: auto = цвета Telegram, light/dark = нейтральные.
//  - Акцент — единый бренд-цвет (sea-green: доверие/здоровье), не перекрашивается.
// Переменные инъектируются в <html> из JS (applyTheme).
export type ThemePref = 'auto' | 'light' | 'dark'
type Mode = 'light' | 'dark'

const KEY_MODE = 'theme_pref'

// Единый бренд-акцент. Свой оттенок для dark (светлее — контраст на тёмном фоне).
const ACCENT: Record<Mode, string> = { light: '#2b8a9e', dark: '#4fb3c7' }

// Стандартные нейтральные поверхности (когда режим задан явно light/dark).
const SURFACE: Record<Mode, { bg: string; card: string; secondary: string; text: string; hint: string; separator: string }> = {
  light: { bg: '#ffffff', card: '#ffffff', secondary: '#f1f3f5', text: '#000000', hint: '#8e8e93', separator: 'rgba(0,0,0,0.08)' },
  dark: { bg: '#17212b', card: '#1d2733', secondary: '#232e3c', text: '#ffffff', hint: '#8a9aa9', separator: 'rgba(255,255,255,0.08)' },
}

const DESTRUCTIVE: Record<Mode, string> = { light: '#d64c3c', dark: '#f0796a' }

type TgWebApp = { colorScheme?: 'light' | 'dark'; onEvent?: (e: string, cb: () => void) => void }
function tg(): TgWebApp | undefined {
  return (window as unknown as { Telegram?: { WebApp?: TgWebApp } }).Telegram?.WebApp
}

export function getThemePref(): ThemePref {
  const v = localStorage.getItem(KEY_MODE)
  return v === 'light' || v === 'dark' ? v : 'auto'
}

function systemIsDark(): boolean {
  const scheme = tg()?.colorScheme
  if (scheme === 'dark') return true
  if (scheme === 'light') return false
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}
function resolveMode(pref: ThemePref): Mode {
  return pref === 'auto' ? (systemIsDark() ? 'dark' : 'light') : pref
}

export function applyTheme(): void {
  const pref = getThemePref()
  const mode = resolveMode(pref)
  const root = document.documentElement
  root.setAttribute('data-theme', mode)
  const set = (k: string, v: string) => root.style.setProperty(k, v)

  if (pref === 'auto') {
    // Цвета Telegram (фоллбэк по resolved-режиму, если клиент не задал var).
    const f = SURFACE[mode]
    set('--bg', `var(--tg-theme-bg-color, ${f.bg})`)
    set('--card', `var(--tg-theme-bg-color, ${f.card})`)
    set('--secondary-bg', `var(--tg-theme-secondary-bg-color, ${f.secondary})`)
    set('--text', `var(--tg-theme-text-color, ${f.text})`)
    set('--hint', `var(--tg-theme-hint-color, ${f.hint})`)
    set('--separator', `var(--tg-theme-section-separator-color, ${f.separator})`)
  } else {
    const s = SURFACE[mode]
    set('--bg', s.bg)
    set('--card', s.card)
    set('--secondary-bg', s.secondary)
    set('--text', s.text)
    set('--hint', s.hint)
    set('--separator', s.separator)
  }

  const accent = ACCENT[mode]
  set('--destructive', DESTRUCTIVE[mode])
  set('--accent', accent)
  set('--button-bg', accent)
  set('--button-color', accent)
  set('--button-text', '#ffffff')
  set('--button-text-color', '#ffffff')
  set('--link', accent)
  set('--link-color', accent)
}

export function setThemePref(pref: ThemePref): void {
  localStorage.setItem(KEY_MODE, pref)
  applyTheme()
}

let bound = false
export function initTheme(): void {
  applyTheme()
  if (bound) return
  bound = true
  const onChange = () => { if (getThemePref() === 'auto') applyTheme() }
  tg()?.onEvent?.('themeChanged', onChange)
  window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener?.('change', onChange)
}
