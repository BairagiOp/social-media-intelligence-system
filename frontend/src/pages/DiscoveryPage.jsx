import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink, HardDriveDownload, Tags, Database } from '../components/icons'
import Panel from '../components/Panel'
import CollectPanel from '../components/CollectPanel'
import { ErrorNotice, Spinner } from '../components/Status'
import { useAsync } from '../hooks/useApi'
import apiClient from '../services/api'

const CATEGORY_COLORS = {
  sentiment: '#15535f',
  bot_detection: '#2b7183',
  misinformation: '#0e3d47',
  topic_model: '#4a93a4',
  social_network_analysis: '#74b2bf',
}

export default function DiscoveryPage() {
  const { data, loading, error, execute } = useAsync(() => apiClient.discovery(), [])
  const [activeCat, setActiveCat] = useState('all')
  const [sampleState, setSampleState] = useState({ loading: false, msg: null, error: null })

  const loadSample = async () => {
    setSampleState({ loading: true, msg: null, error: null })
    try {
      const res = await apiClient.loadSample()
      setSampleState({
        loading: false,
        msg: `Loaded ${res.dataset.name} (${res.dataset.records.toLocaleString()} records).`,
        error: null,
      })
    } catch (err) {
      setSampleState({ loading: false, msg: null, error: err })
    }
  }

  const categories = data?.categories || []
  const datasets = (data?.datasets || []).filter(
    (d) => activeCat === 'all' || d.category === activeCat || d.ml_task === activeCat
  )

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Dataset Discovery</h1>
          <p className="page-subtitle">
            What data each ML task needs, and where to legitimately obtain it. Collect directly
            from public sources below, or review the licenses, download manually and upload
            instead. SMDPIS never authenticates, never bypasses access controls and only
            contacts sources that permit automated reads.
          </p>
        </div>
        <div className="page-actions">
          <button className="btn btn-primary" onClick={loadSample} disabled={sampleState.loading}>
            <HardDriveDownload size={14} />
            {sampleState.loading ? 'Preparing...' : 'Load local sample dataset'}
          </button>
        </div>
      </div>

      {sampleState.msg && <div className="notice ok mb-16"><Database size={15} /> {sampleState.msg} <Link to="/datasets">Open Dataset Manager →</Link></div>}
      <ErrorNotice error={sampleState.error} />

      <CollectPanel />

      {loading && <Spinner label="Loading dataset catalog..." />}
      {error && <ErrorNotice error={error} onRetry={execute} />}

      {data && (
        <>
      <Panel title="Requirements by ML task">
        <div className="grid grid-3">
          {categories.map((c) => (
            <div className="topic-card" key={c.id}>
              <div className="flex-between">
                <strong style={{ color: CATEGORY_COLORS[c.id] || 'var(--ink)' }}>
                  {c.name}
                </strong>
                <span className="badge gray">{c.ml_task}</span>
              </div>
              <p className="small muted mt-8">{c.description}</p>
              <div className="small mt-8">
                <div className="faint" style={{ fontSize: 10, letterSpacing: '.1em', textTransform: 'uppercase' }}>
                  Required columns
                </div>
                <div className="topic-keywords">
                  {c.required_columns.map((r) => (
                    <span className="keyword" key={r}>{r}</span>
                  ))}
                </div>
                {c.optional_columns?.length > 0 && (
                  <div className="faint mt-8" style={{ fontSize: 10, letterSpacing: '.1em', textTransform: 'uppercase' }}>
                    Optional
                  </div>
                )}
                <div className="topic-keywords">
                  {(c.optional_columns || []).map((r) => (
                    <span className="keyword" key={r} style={{ opacity: 0.6 }}>{r}</span>
                  ))}
                </div>
                <div className="small faint mt-8">Minimum records: {c.min_records?.toLocaleString()}</div>
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel
        title="Recommended public datasets"
        actions={
          <span className="flex" style={{ gap: 6, flexWrap: 'wrap' }}>
            <button
              className={`btn btn-sm ${activeCat === 'all' ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => setActiveCat('all')}
            >
              All
            </button>
            {categories.map((c) => (
              <button
                key={c.id}
                className={`btn btn-sm ${activeCat === c.id ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setActiveCat(c.id)}
              >
                {c.name}
              </button>
            ))}
          </span>
        }
      >
        <div className="notice info mb-16">
          <Tags size={15} />
          <div>{data?.note}</div>
        </div>

        <div className="stack">
          {datasets.map((d) => (
            <div className="topic-card" key={d.name}>
              <div className="flex-between">
                <div>
                  <strong>{d.name}</strong>
                  <div className="small muted">
                    {d.source}, {d.dataset_type}, {d.records ? `${d.records} records` : 'size varies'}
                  </div>
                </div>
                <div className="flex" style={{ gap: 6, flexWrap: 'wrap' }}>
                  <span className="badge blue">{d.ml_task}</span>
                  <span className={`badge ${d.labels_available ? 'green' : 'gray'}`}>
                    {d.labels_available ? 'labels included' : 'no labels'}
                  </span>
                  <span className="badge purple">{d.license.slice(0, 34)}{d.license.length > 34 ? '...' : ''}</span>
                  {d.locally_available && <span className="badge cyan">local</span>}
                </div>
              </div>

              <div className="topic-keywords mt-8">
                {d.required_columns?.map((c) => (
                  <span className="keyword" key={c}>{c}</span>
                ))}
              </div>

              {d.notes && <p className="small muted mt-8">{d.notes}</p>}

              <div className="mt-8">
                {d.link.startsWith('local://') ? (
                  <Link to="/datasets" className="btn btn-sm">
                    <Database size={13} /> Open in Dataset Manager
                  </Link>
                ) : (
                  <a href={d.link} target="_blank" rel="noreferrer noopener" className="btn btn-sm">
                    <ExternalLink size={13} /> Source / download page
                  </a>
                )}
              </div>
            </div>
          ))}
          {!datasets.length && <div className="small faint">No datasets in this category.</div>}
        </div>
      </Panel>
        </>
      )}
    </>
  )
}
