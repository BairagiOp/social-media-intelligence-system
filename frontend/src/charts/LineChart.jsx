import { useEffect, useMemo, useRef, useState } from 'react'
import * as d3 from 'd3'

/**
 * Multi-series line chart built on D3 scales/path generators, rendered by React.
 * series: [{ name, color, points: [{ x: Date|number, y: number }] }]
 */
export default function LineChart({
  series,
  height = 220,
  yFormat = (v) => v,
  xIsDate = true,
  area = false,
  yLabel = '',
}) {
  const ref = useRef(null)
  const [tooltip, setTooltip] = useState(null)
  const [width, setWidth] = useState(560)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      setWidth(Math.max(220, entries[0].contentRect.width))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const margin = { top: 14, right: 16, bottom: 28, left: 46 }
  const iw = Math.max(50, width - margin.left - margin.right)
  const ih = Math.max(50, height - margin.top - margin.bottom)

  const active = useMemo(
    () => (series || []).filter((s) => s.points && s.points.length),
    [series]
  )

  const computed = useMemo(() => {
    if (!active.length) return null
    try {
      const xs = active.flatMap((s) => s.points.map((p) => p.x))
      const ys = active.flatMap((s) => s.points.map((p) => p.y))

      const x = xIsDate
        ? d3.scaleTime().domain(d3.extent(xs)).range([0, iw])
        : d3.scaleLinear()
            .domain(d3.extent(xs))
            .nice()
            .range([0, iw])
      const y = d3
        .scaleLinear()
        .domain([Math.min(0, d3.min(ys)), d3.max(ys) || 1])
        .nice()
        .range([ih, 0])

      const line = d3
        .line()
        .x((p) => x(p.x))
        .y((p) => y(p.y))
        .curve(d3.curveMonotoneX)
      const areaGen = d3
        .area()
        .x((p) => x(p.x))
        .y0(ih)
        .y1((p) => y(p.y))
        .curve(d3.curveMonotoneX)

      return {
        x,
        y,
        line,
        areaGen,
        xTicks: x.ticks(Math.min(7, Math.max(3, Math.floor(iw / 90)))),
        yTicks: y.ticks(5),
      }
    } catch {
      return null
    }
  }, [active, iw, ih, xIsDate])

  if (!active.length) return <div className="small faint">No data points</div>
  if (!computed) return <div className="small faint">Could not render chart</div>

  const { x, y, line, areaGen, xTicks, yTicks } = computed

  const handleMove = (evt) => {
    const svg = ref.current?.querySelector('svg')
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    const mx = evt.clientX - rect.left - margin.left
    try {
      const xVal = x.invert(mx)
      const first = active[0].points
      let nearest = first[0]
      let best = Infinity
      for (const p of first) {
        const dist = Math.abs(+p.x - +xVal)
        if (dist < best) {
          best = dist
          nearest = p
        }
      }
      const rows = active
        .map((s) => {
          const match = s.points.find((p) => +p.x === +nearest.x)
          return match ? { name: s.name, color: s.color, y: match.y } : null
        })
        .filter(Boolean)
      setTooltip({
        x: evt.clientX,
        y: evt.clientY,
        title: xIsDate
          ? new Date(nearest.x).toISOString().slice(0, 10)
          : String(nearest.x),
        rows,
      })
    } catch {
      /* ignore hover errors */
    }
  }

  return (
    <div className="chart-box" ref={ref}>
      <svg
        width={width}
        height={height}
        onMouseMove={handleMove}
        onMouseLeave={() => setTooltip(null)}
      >
        <g transform={`translate(${margin.left},${margin.top})`}>
          {yTicks.map((t) => (
            <g key={`y${t}`}>
              <line className="gridline" x1={0} x2={iw} y1={y(t)} y2={y(t)} />
              <text
                x={-8}
                y={y(t)}
                textAnchor="end"
                dominantBaseline="middle"
                fill="var(--ink-muted)"
                fontSize={10.5}
              >
                {yFormat(t)}
              </text>
            </g>
          ))}
          {xTicks.map((t) => (
            <text
              key={`x${+t}`}
              x={x(t)}
              y={ih + 18}
              textAnchor="middle"
              fill="var(--ink-muted)"
              fontSize={10}
            >
              {xIsDate ? d3.timeFormat('%b %d')(new Date(t)) : String(t).slice(0, 8)}
            </text>
          ))}
          {area &&
            active.map((s) => (
              <path key={`a${s.name}`} d={areaGen(s.points)} fill={s.color} opacity={0.1} />
            ))}
          {active.map((s) => (
            <path
              key={s.name}
              d={line(s.points)}
              fill="none"
              stroke={s.color}
              strokeWidth={1.8}
              strokeLinecap="round"
            />
          ))}
        </g>
        {yLabel && (
          <text x={4} y={10} fill="var(--ink-muted)" fontSize={10}>
            {yLabel}
          </text>
        )}
      </svg>

      {active.length > 1 && (
        <div className="legend">
          {active.map((s) => (
            <span key={s.name}>
              <span className="swatch" style={{ background: s.color }} />
              {s.name}
            </span>
          ))}
        </div>
      )}

      {tooltip && (
        <div
          className="chart-tooltip"
          style={{ left: tooltip.x + 14, top: tooltip.y - 10 }}
        >
          <div className="tt-title">{tooltip.title}</div>
          {tooltip.rows.map((r) => (
            <div key={r.name} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span
                className="swatch"
                style={{ background: r.color, width: 8, height: 8, borderRadius: 2 }}
              />
              {r.name}: <strong>{yFormat(r.y)}</strong>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
