/**
 * Shared status components: loading, error and empty states.
 *
 * Skeletons stand in for content that is genuinely in flight; there is no
 * artificial delay anywhere. The spinner remains available for short,
 * indeterminate waits such as a running training job.
 */

export function Spinner({ label = 'Loading', large = false }) {
  return (
    <div className="center" role="status" aria-live="polite">
      <div className={`spinner ${large ? 'spinner-lg' : ''}`} />
      <span className="small muted">{label}</span>
    </div>
  )
}

/** Text placeholder: a heading-width bar followed by paragraph lines. */
export function SkeletonText({ lines = 3, label = 'Loading content' }) {
  return (
    <div role="status" aria-busy="true" aria-label={label}>
      <div className="skeleton skeleton-line" style={{ width: '38%', height: '1rem' }} />
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="skeleton skeleton-line"
          style={{ width: i === lines - 1 ? '62%' : '100%' }}
        />
      ))}
    </div>
  )
}

/** Block placeholder sized like the chart or table it replaces. */
export function SkeletonBlock({ height = 180, label = 'Loading chart' }) {
  return (
    <div
      className="skeleton skeleton-block"
      style={{ height }}
      role="status"
      aria-busy="true"
      aria-label={label}
    />
  )
}

/** Table placeholder with the given number of rows. */
export function SkeletonTable({ rows = 6, columns = 5, label = 'Loading rows' }) {
  return (
    <div className="table-wrap" role="status" aria-busy="true" aria-label={label}>
      <table className="data">
        <tbody>
          {Array.from({ length: rows }).map((_, r) => (
            <tr key={r}>
              {Array.from({ length: columns }).map((_, c) => (
                <td key={c}>
                  <div
                    className="skeleton skeleton-line"
                    style={{ width: c === 0 ? '70%' : '45%', marginBottom: 0 }}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function ErrorNotice({ error, onRetry }) {
  if (!error) return null
  const detail = typeof error === 'string' ? error : error.detail || error.message
  const code = typeof error === 'object' ? error.code : null
  return (
    <div className="notice error mb-16" role="alert">
      <div style={{ flex: 1 }}>
        {code === 'model_not_trained' ? (
          <>
            <strong>Model not trained.</strong> {detail}
          </>
        ) : (
          <>{detail}</>
        )}
      </div>
      {onRetry && (
        <button className="btn btn-sm" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title, message, action }) {
  return (
    <div className="empty-state">
      <h3>{title}</h3>
      <p>{message}</p>
      {action && <div className="actions">{action}</div>}
    </div>
  )
}
