import { useEffect, useRef, useState } from 'react'
import * as d3 from 'd3'

/**
 * Interactive force-directed network graph (D3 v7).
 *
 * Props:
 *  nodes: [{ id, label, platform, degree, engagement, activity, cluster, classification_score?, pagerank?, betweenness? }]
 *  edges: [{ source, target, weight, edge_type }]
 *  sizeMode: 'degree' | 'engagement' | 'activity'
 *  colorMode: 'platform' | 'cluster' | 'classification'
 *  search: string, highlights matching nodes
 *  selectedId: string|null, emphasized node
 *  onSelect(node|null), onHover(node|null)
 */
export default function ForceGraph({
  nodes = [],
  edges = [],
  sizeMode = 'degree',
  colorMode = 'platform',
  search = '',
  selectedId = null,
  onSelect,
  onHover,
  height = 620,
}) {
  const containerRef = useRef(null)
  const svgRef = useRef(null)
  const zoomRef = useRef(null)
  const selectionRef = useRef(null)
  const simRef = useRef(null)
  const [tooltip, setTooltip] = useState(null)
  const [dims, setDims] = useState({ w: 900, h: height })

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      const w = Math.max(360, entries[0].contentRect.width)
      setDims({ w, h: height })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [height])

  useEffect(() => {
    const svgEl = svgRef.current
    if (!svgEl || !nodes.length) return

    const width = dims.w
    const heightPx = dims.h
    const svg = d3.select(svgEl)
    svg.selectAll('*').remove()
    svg.attr('width', width).attr('height', heightPx)

    const g = svg.append('g')

    // ---- scales -------------------------------------------------------
    const valueOf = (d) => Math.max(1, Number(d[sizeMode] ?? d.degree ?? 1))
    const maxVal = d3.max(nodes, valueOf) || 1
    const rScale = d3.scaleSqrt().domain([1, maxVal]).range([5, 30])

    const platformPalette = {
      x: '#15535f', reddit: '#15535f', mastodon: '#2b7183',
      threads: '#74b2bf', youtube: '#0e3d47', unknown: '#9b958a',
    }
    const clusterScale = d3.scaleOrdinal(d3.schemeTableau10)
    const colorOf = (d) => {
      if (colorMode === 'platform') return platformPalette[d.platform] || '#9b958a'
      if (colorMode === 'cluster')
        return d.cluster === null || d.cluster === undefined
          ? '#9b958a'
          : clusterScale(d.cluster)
      if (colorMode === 'classification') {
        const s = d.classification_score
        if (s === undefined || s === null) return '#9b958a'
        return d3.interpolateRdYlGn(1 - s) // high score → red
      }
      return '#15535f'
    }

    // ---- zoom & pan ---------------------------------------------------
    const zoomBehavior = d3
      .zoom()
      .scaleExtent([0.15, 6])
      .on('zoom', (event) => g.attr('transform', event.transform))
    svg.call(zoomBehavior)
    zoomRef.current = zoomBehavior

    // ---- edges --------------------------------------------------------
    const linkSel = g
      .append('g')
      .selectAll('line')
      .data(edges)
      .join('line')
      .attr('stroke', 'rgba(122,162,247,0.28)')
      .attr('stroke-width', (d) => Math.min(4, 0.6 + (d.weight || 1) * 0.35))
      .attr('stroke-opacity', 0.55)

    // ---- nodes --------------------------------------------------------
    const nodeSel = g
      .append('g')
      .selectAll('circle')
      .data(nodes, (d) => d.id)
      .join('circle')
      .attr('r', (d) => rScale(valueOf(d)))
      .attr('fill', colorOf)
      .attr('stroke', '#fcfbf8')
      .attr('stroke-width', 1.4)
      .style('cursor', 'pointer')

    // labels for the most connected nodes only (keeps large graphs readable)
    const labelNodes = nodes
      .slice()
      .sort((a, b) => (b.degree || 0) - (a.degree || 0))
      .slice(0, 18)
      .map((d) => d.id)
    const labelSel = g
      .append('g')
      .selectAll('text')
      .data(labelNodes)
      .join('text')
      .attr('class', 'node-label')
      .attr('text-anchor', 'middle')
      .text((id) => id)

    // ---- interactions -------------------------------------------------
    const tooltipHtml = (d) => {
      const rows = [
        ['Platform', d.platform],
        ['Degree', d.degree],
        ['Weighted degree', d.weighted_degree],
        ['Activity', d.activity],
        ['Engagement', d.engagement],
        ['Community', d.cluster ?? ', '],
        ['PageRank', d.pagerank ?? ', '],
      ]
      if (d.classification_score !== undefined && d.classification_score !== null) {
        rows.push(['Automated-account likelihood', d.classification_score])
      }
      return { title: d.label, rows }
    }

    nodeSel
      .on('mouseover', (event, d) => {
        setTooltip({ ...tooltipHtml(d), x: event.clientX, y: event.clientY })
        onHover?.(d)
        d3.select(event.currentTarget).attr('stroke', '#2b7183').attr('stroke-width', 2.4)
      })
      .on('mousemove', (event, d) =>
        setTooltip((t) => (t ? { ...t, x: event.clientX, y: event.clientY } : t))
      )
      .on('mouseout', (event) => {
        setTooltip(null)
        onHover?.(null)
        d3.select(event.currentTarget)
          .attr('stroke', '#fcfbf8')
          .attr('stroke-width', 1.4)
      })
      .on('click', (event, d) => {
        event.stopPropagation()
        onSelect?.(d)
      })

    svg.on('click', () => onSelect?.(null))

    const dragBehavior = d3
      .drag()
      .on('start', (event, d) => {
        if (!event.active) sim.alphaTarget(0.25).restart()
        d.fx = d.x
        d.fy = d.y
      })
      .on('drag', (event, d) => {
        d.fx = event.x
        d.fy = event.y
      })
      .on('end', (event, d) => {
        if (!event.active) sim.alphaTarget(0)
        d.fx = null
        d.fy = null
      })
    nodeSel.call(dragBehavior)

    // ---- simulation ---------------------------------------------------
    const nodeById = new Map(nodes.map((n) => [n.id, n]))
    const sim = d3
      .forceSimulation(nodes)
      .force(
        'link',
        d3
          .forceLink(edges)
          .id((d) => d.id)
          .distance((d) => 70 - Math.min(30, (d.weight || 1) * 4))
      )
      .force('charge', d3.forceManyBody().strength(-190))
      .force('center', d3.forceCenter(width / 2, heightPx / 2))
      .force('collide', d3.forceCollide((d) => rScale(valueOf(d)) + 4).iterations(2))
      .force('x', d3.forceX(width / 2).strength(0.04))
      .force('y', d3.forceY(heightPx / 2).strength(0.06))
      .on('tick', () => {
        linkSel
          .attr('x1', (d) => d.source.x)
          .attr('y1', (d) => d.source.y)
          .attr('x2', (d) => d.target.x)
          .attr('y2', (d) => d.target.y)
        nodeSel.attr('cx', (d) => d.x).attr('cy', (d) => d.y)
        labelSel
          .attr('x', (d) => nodeById.get(d)?.x ?? -999)
          .attr('y', (d) => (nodeById.get(d)?.y ?? -999) - 12)
      })

    simRef.current = sim
    selectionRef.current = { nodeSel, linkSel, svg, g }

    return () => {
      sim.stop()
      simRef.current = null
      selectionRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, sizeMode, colorMode, dims.w, dims.h])

  // ---- search highlight & selection emphasis (attribute updates only) ----
  useEffect(() => {
    const sel = selectionRef.current
    if (!sel) return
    const needle = (search || '').trim().toLowerCase()
    sel.nodeSel
      .attr('opacity', (d) =>
        needle && !String(d.id).toLowerCase().includes(needle) ? 0.15 : 1
      )
      .attr('stroke', (d) =>
        selectedId && d.id === selectedId ? '#2b7183' : '#fcfbf8'
      )
      .attr('stroke-width', (d) => (selectedId && d.id === selectedId ? 3 : 1.4))
    sel.linkSel.attr('stroke-opacity', (d) => {
      if (selectedId) {
        const ids = [d.source.id ?? d.source, d.target.id ?? d.target]
        return ids.includes(selectedId) ? 0.95 : 0.08
      }
      if (needle) {
        const ids = [d.source.id ?? d.source, d.target.id ?? d.target]
        return ids.some((i) => String(i).toLowerCase().includes(needle)) ? 0.8 : 0.06
      }
      return 0.55
    })
  }, [search, selectedId])

  const zoomBy = (factor) => {
    const svg = d3.select(svgRef.current)
    if (zoomRef.current) svg.transition().duration(220).call(zoomRef.current.scaleBy, factor)
  }
  const resetZoom = () => {
    const svg = d3.select(svgRef.current)
    if (zoomRef.current)
      svg.transition().duration(300).call(zoomRef.current.transform, d3.zoomIdentity)
  }

  return (
    <div className="graph-shell" ref={containerRef} style={{ height: dims.h }}>
      <svg ref={svgRef} role="img" aria-label="Network graph" />
      <div className="graph-zoom-controls">
        <button className="btn btn-sm" onClick={() => zoomBy(1.4)} title="Zoom in">+</button>
        <button className="btn btn-sm" onClick={() => zoomBy(0.7)} title="Zoom out">−</button>
        <button className="btn btn-sm" onClick={resetZoom} title="Reset view">Reset</button>
      </div>
      {tooltip && (
        <div className="chart-tooltip" style={{ left: tooltip.x + 14, top: tooltip.y - 10 }}>
          <div className="tt-title">{tooltip.title}</div>
          {tooltip.rows
            .filter(([, v]) => v !== undefined && v !== null && v !== '')
            .map(([k, v]) => (
              <div key={k} style={{ display: 'flex', gap: 8, justifyContent: 'space-between' }}>
                <span className="faint">{k}</span>
                <span>{v}</span>
              </div>
            ))}
        </div>
      )}
    </div>
  )
}
