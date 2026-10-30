import { X } from './icons'

export default function DetailDrawer({ open, title, subtitle, onClose, children }) {
  if (!open) return null
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true">
        <button className="drawer-close" onClick={onClose} aria-label="Close">
          <X size={18} />
        </button>
        <h3>{title}</h3>
        {subtitle && <div className="small muted mb-8">{subtitle}</div>}
        {children}
      </aside>
    </>
  )
}
