/** Confusion matrix rendered from real evaluation output (backend metrics). */
export default function ConfusionMatrix({ matrix, classes }) {
  if (!matrix || !matrix.length) return <div className="small faint">No confusion matrix</div>
  const labels = classes && classes.length === matrix.length
    ? classes
    : matrix.map((_, i) => `C${i}`)

  const max = Math.max(...matrix.flat())
  const cellColor = (v) => {
    if (!max) return 'rgba(122,162,247,0.06)'
    const intensity = v / max
    if (intensity === 0) return 'rgba(122,162,247,0.05)'
    return `rgba(125, 207, 255, ${0.1 + intensity * 0.5})`
  }

  return (
    <table className="cmatrix">
      <thead>
        <tr>
          <th style={{ textAlign: 'right', paddingRight: 8 }}>pred ↓ / true →</th>
          {labels.map((c) => (
            <th key={c}>{String(c).slice(0, 12)}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {matrix.map((row, i) => (
          <tr key={i}>
            <td className="labelcell" style={{ textAlign: 'right', paddingRight: 8 }}>
              {String(labels[i]).slice(0, 12)}
            </td>
            {row.map((v, j) => (
              <td
                key={j}
                style={{
                  background: cellColor(v),
                  color: i === j ? 'var(--accent)' : 'var(--ink)',
                  fontWeight: i === j ? 700 : 400,
                }}
              >
                {v}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
