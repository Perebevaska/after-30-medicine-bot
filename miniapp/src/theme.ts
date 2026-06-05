// Тема = режим (auto/light/dark). Переменные инъектируются в <html> из JS (applyTheme).
//  - auto  = ПОЛНОСТЬЮ цвета Telegram (поверхности + accent/link), live через var(--tg-theme-*).
//  - light = фикс нейтральная светлая + бренд-акцент (sea-green).
//  - dark  = фикс Telegram classic dark (синяя палитра), НЕ зависит от настроек ТГ.
export type ThemePref = 'auto' | 'light' | 'dark'
type Mode = 'light' | 'dark'

const KEY_MODE = 'theme_pref'

type Palette = {
  bg: string; secondary: string; text: string; hint: string; separator: string
  accent: string; link: string; destructive: string
}

// Telegram classic dark — официальные themeParams. Фикс «тёмной» темы.
const DARK: Palette = {
  bg: '#17212b', secondary: '#232e3c', text: '#ffffff', hint: '#708499',
  separator: 'rgba(255,255,255,0.08)', accent: '#5288c1', link: '#6ab7ff', destructive: '#ec3942',
}
// Нейтральная светлая + бренд-акцент.
const LIGHT: Palette = {
  bg: '#ffffff', secondary: '#f1f3f5', text: '#000000', hint: '#8e8e93',
  separator: 'rgba(0,0,0,0.08)', accent: '#2b8a9e', link: '#2b8a9e', destructive: '#d64c3c',
}

function readVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

export function getThemePref(): ThemePref {
  const v = localStorage.getItem(KEY_MODE)
  return v === 'light' || v === 'dark' ? v : 'auto'
}

// Тёмный ли hex-цвет (по относительной яркости). Telegram отдаёт #rrggbb.
function isDarkColor(hex: string): boolean {
  const m = hex.replace('#', '')
  const v = m.length === 3 ? m.split('').map((c) => c + c).join('') : m
  if (v.length < 6) return false
  const r = parseInt(v.slice(0, 2), 16), g = parseInt(v.slice(2, 4), 16), b = parseInt(v.slice(4, 6), 16)
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) < 128
}

// Режим для auto: по реальному фону Telegram (после bindCssVars), иначе prefers-color-scheme.
function autoMode(): Mode {
  const bg = readVar('--tg-theme-bg-color')
  if (bg) return isDarkColor(bg) ? 'dark' : 'light'
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function resolveMode(pref: ThemePref): Mode {
  return pref === 'auto' ? autoMode() : pref
}

export function applyTheme(): void {
  const pref = getThemePref()
  const mode = resolveMode(pref)
  const root = document.documentElement
  root.setAttribute('data-theme', mode)
  const set = (k: string, v: string) => root.style.setProperty(k, v)

  const f = mode === 'dark' ? DARK : LIGHT

  if (pref === 'auto') {
    // Всё из Telegram (live), фоллбэк — палитра по resolved-режиму.
    set('--bg', `var(--tg-theme-bg-color, ${f.bg})`)
    set('--card', `var(--tg-theme-bg-color, ${f.bg})`)
    set('--secondary-bg', `var(--tg-theme-secondary-bg-color, ${f.secondary})`)
    set('--text', `var(--tg-theme-text-color, ${f.text})`)
    set('--hint', `var(--tg-theme-hint-color, ${f.hint})`)
    set('--separator', `var(--tg-theme-section-separator-color, ${f.separator})`)
    const acc = `var(--tg-theme-button-color, ${f.accent})`
    const link = `var(--tg-theme-link-color, ${f.link})`
    set('--accent', acc)
    set('--button-bg', acc)
    set('--button-color', acc)
    set('--link', link)
    set('--link-color', link)
    set('--destructive', `var(--tg-theme-destructive-text-color, ${f.destructive})`)
  } else {
    // Фикс-палитра (light/dark) — не зависит от Telegram.
    set('--bg', f.bg)
    set('--card', f.bg)
    set('--secondary-bg', f.secondary)
    set('--text', f.text)
    set('--hint', f.hint)
    set('--separator', f.separator)
    set('--accent', f.accent)
    set('--button-bg', f.accent)
    set('--button-color', f.accent)
    set('--link', f.link)
    set('--link-color', f.link)
    set('--destructive', f.destructive)
  }

  set('--button-text', '#ffffff')
  set('--button-text-color', '#ffffff')
}

export function setThemePref(pref: ThemePref): void {
  localStorage.setItem(KEY_MODE, pref)
  applyTheme()
}

// Перерисовать (после bindCssVars / на themeChanged) — auto перечитает реальные ТГ-цвета.
export function refreshTheme(): void {
  applyTheme()
}

let bound = false
export function initTheme(): void {
  applyTheme()
  if (bound) return
  bound = true
  window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener?.('change', () => refreshTheme())
}
