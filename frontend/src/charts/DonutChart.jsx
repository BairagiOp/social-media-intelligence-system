import { useMemo, useState } from 'react'
import * as d3 from 'd3'

/**
 * Donut chart. data: [{ label, value, color? }]
 */
export default function DonutChart({ data, size = 190, thickness = 26 }) {
  const [hover, setHover] = useState(null)

  const rows = useMemo(
    () => (data || []).filter((d) => d && d.value > 0),
    [data]
  )

  if (!rows.length) return <div className="small faint">No data</div>

  const total = rows.reduce((s, d) => s + d.value, 0)
  const radius = size / 2
  const inner = radius - thickness

  const pie = d3.pie().value((d) => d.value).sort(null)
  const arcGen = d3.arc().innerRadius(inner).outerRadius(radius).cornerRadius(3).padAngle(0.02)

  const fallback = ['#15535f', '#4a93a4', '#74b2bf', '#0e3d47', '#2b7183', '#2b7183', '#a3ccd4', '#c6dde2']
  const arcs = pie(rows)

  return (
    <div style={{ display: 'flex', gap: 18, alignItems: 'center', flexWrap: 'wrap' }}>
      <svg width={size} height={size} style={{ flexShrink: 0 }}>
        <g transform={`translate(${radius},${radius})`}>
          {arcs.map((a, i) => (
            <path
              key={rows[i].label}
              d={arcGen(a)}
              fill={rows[i].color || fallback[i % fallback.length]}
              opacity={hover === i ? 1 : 0.85}
              stroke={hover === i ? 'var(--ink)' : 'none'}
              strokeWidth={1}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              style={{ transition: 'opacity .15s' }}
            />
          ))}
          <text
            textAnchor="middle"
            y={-4}
            fill="var(--ink)"
            fontSize={19}
            fontWeight={700}
            fontFamily="var(--mono)"
          >
            {total.toLocaleString()}
          </text>
          <text textAnchor="middle" y={14} fill="var(--ink-muted)" fontSize={9.5}
            letterSpacing="1.5">
            RECORDS
          </text>
        </g>
      </svg>
      <div className="legend" style={{ flexDirection: 'column', gap: 7, margin: 0 }}>
        {rows.map((d, i) => (
          <span
            key={d.label}
            style={{
              opacity: hover === null || hover === i ? 1 : 0.45,
              display: 'flex',
              alignItems: 'center',
              gap: 7,
            }}
          >
            <span
              className="swatch"
              style={{ background: d.color || fallback[i % fallback.length] }}
            />
            <span style={{ textTransform: 'capitalize' }}>{d.label}</span>
            <span className="faint mono" style={{ fontSize: 11 }}>
              {d.value.toLocaleString()} ({((d.value / total) * 100).toFixed(1)}%)
            </span>
          </span>
        ))}
      </div>
    </div>
  )
}
