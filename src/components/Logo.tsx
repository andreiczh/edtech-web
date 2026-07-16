/** Логотип: четыре фирменные точки + «Копилот». */
export function Logo() {
  return (
    <div className="brand">
      <span className="brand__dots" aria-hidden="true">
        <i />
        <i />
        <i />
        <i />
      </span>
      <span className="brand__name">Копилот</span>
    </div>
  )
}
