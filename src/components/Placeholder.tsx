export function Placeholder({ title, note }: { title: string; note?: string }) {
  return (
    <div className="placeholder">
      <h2 className="placeholder__title">{title}</h2>
      {note && <p className="placeholder__note">{note}</p>}
    </div>
  )
}
