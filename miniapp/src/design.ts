// Фаза 18: тоггл «новый вид» (design-v2) для теста перед прод.
//  - Чисто визуал: ставит класс `design-v2` на <body>; все v2-стили в App.css под этим скоупом.
//  - Флаг в localStorage (per-устройство). Сервер не задействован (это не данные).
export type DesignPref = 'v1' | 'v2'

const KEY = 'design_pref'

export function getDesignPref(): DesignPref {
  return localStorage.getItem(KEY) === 'v2' ? 'v2' : 'v1'
}

export function applyDesign(): void {
  document.body.classList.toggle('design-v2', getDesignPref() === 'v2')
}

export function setDesignPref(pref: DesignPref): void {
  localStorage.setItem(KEY, pref)
  applyDesign()
}
