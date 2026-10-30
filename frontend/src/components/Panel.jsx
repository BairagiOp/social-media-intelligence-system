export default function Panel({ title, hint, actions, children, className = '' }) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <div className="panel-title">
          <span>{title}</span>
          <span className="hint">{actions || hint}</span>
        </div>
      )}
      {children}
    </section>
  )
}
