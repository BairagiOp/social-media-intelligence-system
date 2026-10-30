import { useEffect, useMemo, useState } from 'react'
import { Search, Users, Share2, Crown, RefreshCw, ShieldCheck, Filter } from '../components/icons'
import Panel from '../components/Panel'
import DatasetPicker from '../components/DatasetPicker'
import { EmptyState, ErrorNotice, Spinner } from '../components/Status'
import ForceGraph from '../charts/ForceGraph'
import { useAsync } from '../hooks/useApi'
import { useDatasets } from '../hooks/useDatasets'
import apiClient from '../services/api'
import { formatNumber } from '../utils/format'
import { categoricalColor } from '../utils/datasets'

const EDGE_TYPES = ['mention', 'reply', 'share']

export default function NetworkPage() {
  const { datasets, selectedId, setSelectedId, loading: dsLoading } = useDatasets()

  const [edgeType, setEdgeType] = useState('all')
  const [minWeight, setMinWeight] = useState(1)
  const [maxNodes, setMaxNodes] = useState(250)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [sizeMode, setSizeMode] = useState('degree')
  const [colorMode, setColorMode] = useState('platform')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState(null)
  const [config, setConfig] = useState(null)

  const fetchGraph = async () => {
    const params = {
      dataset_id: selectedId,
      edge_types: edgeType === 'all' ? EDGE_TYPES.join(',') : edgeType,
      min_weight: minWeight,
      max_nodes: maxNodes,
    }
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo
    const res = await apiClient.graph(params)
    setConfig(res)
    return res
  }

  const { data, loading, error, execute } = useAsync(
    () => (selectedId ? fetchGraph() : Promise.resolve(null)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selectedId],
    { immediate: !!selectedId }
  )

  const graph = data || config

  const communities = useMemo(() => graph?.communities?.communities || [], [graph])
  const centrality = graph?.centrality || {}

  useEffect(() => setSelected(null), [data])

  if (!selectedId && !dsLoading) {
    return (
      <>
        <div className="page-head">
          <div>
            <h1 className="page-title">Social Network Analysis</h1>
            <p className="page-subtitle">
              Interaction graphs built from mentions, replies and shares in the loaded dataset.
            </p>
          </div>
        </div>
        <EmptyState
          title="Select a dataset"
          message="Load a dataset containing usernames and text with @mentions / replies / shares."
        />
      </>
    )
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Social Network Analysis</h1>
          <p className="page-subtitle">
            D3 force-directed graph with zoom, pan, search and selection. Communities via Louvain,
            centrality via degree / betweenness / PageRank, statistical relationships only, no
            claims about real-world coordination.
          </p>
        </div>
        <div className="page-actions">
          <DatasetPicker datasets={datasets} value={selectedId} onChange={setSelectedId} loading={dsLoading} />
        </div>
      </div>

      <div className="notice info mb-16">
        <ShieldCheck size={15} />
        <div>{graph?.disclaimer || 'Private IP addresses are hashed at ingestion and never shown.'}</div>
      </div>

      <Panel
        title="Graph controls"
        actions={
          <button className="btn btn-sm btn-primary" onClick={execute} disabled={!selectedId || loading}>
            <RefreshCw size={13} /> Rebuild
          </button>
        }
      >
        <div className="filters">
          <label className="field">
            <span><Filter size={11} /> Edge type</span>
            <select className="select" value={edgeType} onChange={(e) => setEdgeType(e.target.value)}>
              <option value="all">All interactions</option>
              {EDGE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Min edge weight</span>
            <input className="input" type="number" min={1} max={20} value={minWeight}
              onChange={(e) => setMinWeight(Number(e.target.value))} />
          </label>
          <label className="field">
            <span>Max nodes</span>
            <input className="input" type="number" min={20} max={1000} step={10} value={maxNodes}
              onChange={(e) => setMaxNodes(Number(e.target.value))} />
          </label>
          <label className="field">
            <span>From</span>
            <input className="input" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label className="field">
            <span>To</span>
            <input className="input" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
          <label className="field">
            <span>Node size</span>
            <select className="select" value={sizeMode} onChange={(e) => setSizeMode(e.target.value)}>
              <option value="degree">Degree</option>
              <option value="engagement">Engagement</option>
              <option value="activity">Activity volume</option>
            </select>
          </label>
          <label className="field">
            <span>Node color</span>
            <select className="select" value={colorMode} onChange={(e) => setColorMode(e.target.value)}>
              <option value="platform">Platform</option>
              <option value="cluster">Community</option>
              <option value="classification">Model classification</option>
            </select>
          </label>
          <label className="field" style={{ flex: 1, minWidth: 180 }}>
            <span><Search size={11} /> Search node</span>
            <input
              className="input"
              placeholder="highlight account..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
        </div>
      </Panel>

      {error && <ErrorNotice error={error} onRetry={execute} />}
      {loading && !graph && <Spinner label="Building graph..." />}

      {graph && (
        <>
          <div className="grid grid-4 mt-16">
            <Metric label="Nodes" value={formatNumber(graph.stats.nodes)} />
            <Metric label="Edges" value={formatNumber(graph.stats.edges)} />
            <Metric label="Communities" value={graph.communities.count} sub={graph.communities.method} />
            <Metric label="Interaction volume" value={formatNumber(graph.stats.total_interaction_volume)} />
          </div>

          <Panel
            title="Interaction graph"
            hint={`${graph.stats.components} components, density ${graph.stats.density}`}
            className="mt-16"
          >
            {!graph.nodes.length ? (
              <EmptyState
                title="No edges found"
                message="Try lowering the minimum edge weight or selecting all interaction types. The dataset needs @mentions, reply_to_username or shared_from_username columns to form edges."
              />
            ) : (
              <>
                <ForceGraph
                  nodes={graph.nodes}
                  edges={graph.edges}
                  sizeMode={sizeMode}
                  colorMode={colorMode}
                  search={search}
                  selectedId={selected?.id || null}
                  onSelect={setSelected}
                  height={560}
                />
                {selected && (
                  <div className="graph-info">
                    <div className="flex-between">
                      <strong style={{ color: 'var(--accent)' }}>{selected.label}</strong>
                      <button className="btn btn-sm" onClick={() => setSelected(null)}>×</button>
                    </div>
                    <div className="small muted mt-8">
                      platform: {selected.platform}, degree: {selected.degree}, community:{' '}
                      {selected.cluster ?? ', '}
                    </div>
                    <div className="small muted">
                      activity: {selected.activity}, engagement: {formatNumber(selected.engagement)},
                      pagerank: {selected.pagerank}
                    </div>
                    {selected.classification_score !== undefined && (
                      <div className="small mt-8" style={{ color: 'var(--warn)' }}>
                        Automated-account likelihood: {selected.classification_score}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </Panel>

          <div className="grid grid-2 mt-16">
            <Panel title="Communities" actions={<span className="hint">{graph.communities.method}</span>}>
              <div className="stack">
                {communities.slice(0, 10).map((c) => (
                  <div className="toplist-item" key={c.id}>
                    <div>
                      <span className="badge purple">community {c.id}</span>
                      <div className="small muted mt-8">
                        {c.members.slice(0, 6).join(', ')}
                        {c.members.length > 6 && ` +${c.members.length - 6} more`}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div className="mono small">{c.size} members</div>
                      <div className="faint small">{formatNumber(c.interaction_volume)} interactions</div>
                    </div>
                  </div>
                ))}
                {!communities.length && <div className="small faint">No communities detected.</div>}
              </div>
            </Panel>

            <div className="stack">
              <Panel title="Central accounts" actions={<Crown size={14} style={{ color: 'var(--warn)' }} />}>
                <div className="grid grid-3">
                  <CentralityList title="Degree" icon={<Share2 size={12} />} rows={centrality.degree} />
                  <CentralityList title="Betweenness" icon={<Filter size={12} />} rows={centrality.betweenness} />
                  <CentralityList title="PageRank" icon={<Crown size={12} />} rows={centrality.pagerank} />
                </div>
              </Panel>

              <Panel title="Graph statistics">
                <dl className="kv">
                  <dt>Nodes</dt><dd>{formatNumber(graph.stats.nodes)}</dd>
                  <dt>Edges</dt><dd>{formatNumber(graph.stats.edges)}</dd>
                  <dt>Density</dt><dd>{graph.stats.density}</dd>
                  <dt>Components</dt><dd>{graph.stats.components}</dd>
                  <dt>Avg degree</dt><dd>{graph.stats.avg_degree}</dd>
                  <dt>Communities</dt><dd>{graph.communities.count} ({graph.communities.method})</dd>
                </dl>
                <div className="small faint mt-16">
                  <Users size={12} /> Community structure reflects interaction patterns in this
                  dataset only, it is not evidence of coordination between real-world parties.
                </div>
              </Panel>
            </div>
          </div>
        </>
      )}
    </>
  )
}

function CentralityList({ title, icon, rows = [] }) {
  return (
    <div>
      <div className="small muted mb-8 flex" style={{ gap: 6 }}>{icon} {title}</div>
      <div className="stack" style={{ gap: 6 }}>
        {rows.slice(0, 8).map((r, i) => (
          <div key={r.id} className="small" style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
            <span className="mono" style={{ fontSize: 11.5 }}>
              {i + 1}. {r.id.length > 14 ? `${r.id.slice(0, 13)}...` : r.id}
            </span>
            <span className="faint mono" style={{ fontSize: 11 }}>
              {typeof r.value === 'number' ? r.value.toFixed?.(3) ?? r.value : r.value}
            </span>
          </div>
        ))}
        {!rows.length && <span className="small faint">, </span>}
      </div>
    </div>
  )
}

function Metric({ label, value, sub }) {
  return (
    <div className="metric">
      <div className="m-label">{label}</div>
      <div className="m-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  )
}
