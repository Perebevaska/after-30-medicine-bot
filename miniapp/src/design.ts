// Фаза 18: «новый вид» (design-v2) — теперь единственный стиль приложения.
//  - Класс `design-v2` всегда на <body>; вся v2-CSS в App.css под этим скоупом.
//  - Тоггл «классический» убран (классика больше не поддерживается).
export function applyDesign(): void {
  document.body.classList.add('design-v2')
}
