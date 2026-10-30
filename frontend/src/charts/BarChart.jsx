import { useEffect, useMemo, useRef, useState } from 'react'
import * as d3 from 'd3'

/**
 * Horizontal bar chart. data: [{ label, value, color? }]
 */
export default function BarChart({ data, height, valueFormat = (v) => v, maxBars = 14 }) {
  const ref = useRef(null)
  const [width, setWidth] = useState(520)
  const [hover, setHover] = useState(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver((e) => setWidth(Math.max(200, e[0].contentRect.width)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const rows = useMemo(
    () => (data || []).filter((d) => d && d.value !== undefined && d.value !== null).slice(0, maxBars),
    [data, maxBars]
  )

  if (!rows.length) return <div className="small faint">No data</div>

  const labelW = Math.min(150, Math.max(70, d3.max(rows, (d) => d.label.length) * 6.6 + 12))
  const barH = 22
  const gap = 8
  const margin = { top: 4, right: 58, bottom: 4, left: labelW }
  const iw = Math.max(40, width - margin.left - margin.right)
  const heightTotal = margin.top + rows.length * (barH + gap) + margin.bottom

  const x = d3
    .scaleLinear()
    .domain([0, d3.max(rows, (d) => d.value) || 1])
    .range([0, iw])

  const fallbackColor = '#15535f'

  return (
    <div className="chart-box" ref={ref} style={height ? { height } : undefined}>
      <svg width={width} height={heightTotal}>
        <g transform={`translate(${margin.left},${margin.top})`}>
          {rows.map((d, i) => {
            const y = i * (barH + gap)
            const color = d.color || fallbackColor
            return (
              <g
                key={d.label}
                onMouseEnter={(e) => setHover({ d, x: e.clientX, y: e.clientY })}
                onMouseMove={(e) => setHover({ d, x: e.clientX, y: e.clientY })}
                onMouseLeave={() => setHover(null)}
              >
                <text
                  x={-10}
                  y={y + barH / 2}
                  textAnchor="end"
                  dominantBaseline="middle"
                  fill="var(--ink-soft)"
                  fontSize={11.5}
                >
                  {d.label.length > 24 ? `${d.label.slice(0, 23)}...` : d.label}
                </text>
                <rect
                  x={0}
                  y={y}
                  width={iw}
                  height={barH}
                  rx={5}
                  fill="rgba(122,162,247,0.05)"
                />
                <rect
                  x={0}
                  y={y}
                  width={Math.max(2, x(d.value))}
                  height={barH}
                  rx={5}
                  fill={color}
                  opacity={0.85}
                />
                <text
                  x={Math.max(2, x(d.value)) + 8}
                  y={y + barH / 2}
                  dominantBaseline="middle"
                  fill="var(--ink)"
                  fontSize={11}
                  fontFamily="var(--mono)"
                >
                  {valueFormat(d.value)}
                </text>
              </g>
            )
          })}
        </g>
      </svg>
      {hover && (
        <div className="chart-tooltip" style={{ left: hover.x + 12, top: hover.y - 8 }}>
          <div className="tt-title">{hover.d.label}</div>
          <div>{valueFormat(hover.d.value)}</div>
          {hover.d.detail && <div className="faint small">{hover.d.detail}</div>}
        </div>
      )}
    </div>
  )
}
