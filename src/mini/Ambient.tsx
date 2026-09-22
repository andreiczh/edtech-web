/** Два размытых пятна фона из макетов 32–38: сверху справа сиреневое, снизу слева мятное. */
export function Ambient() {
  return (
    <>
      <div className="amb amb--top" aria-hidden="true" />
      <div className="amb amb--bottom" aria-hidden="true" />
    </>
  )
}

/** Иконка из макета: контур дословно, размер — из bbox в пунктах. */
export function Icon({
  icon,
  className,
  style,
}: {
  icon: { vb: string; svg: string; w: number; h: number }
  className?: string
  style?: React.CSSProperties
}) {
  return (
    <svg
      className={className}
      style={style}
      viewBox={icon.vb}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      focusable="false"
      dangerouslySetInnerHTML={{ __html: icon.svg }}
    />
  )
}
