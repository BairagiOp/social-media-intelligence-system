import { useState } from 'react'
import { Tags, RefreshCw, Link2 } from '../components/icons'
import Panel from '../components/Panel'
import DatasetPicker from '../components/DatasetPicker'
import { EmptyState, ErrorNotice, Spinner } from '../components/Status'
import LineChart from '../charts/LineChart'
import BarChart from '../charts/BarChart'
import ForceGraph from '../charts/ForceGraph'
import { useAsync } from '../hooks/useApi'
import { useDatasets } from '../hooks/useDatasets'
import apiClient from '../services/api'
import { formatNumber, truncate } from '../utils/format'
import { categoricalColor } from '../utils/datasets'

const PALETTE = ['#0e3d47', '#15535f', '#2b7183', '#4a93a4', '#74b2bf', '#a3ccd4', '#c6dde2', '#e2ecee']

export default function TopicsPage() {
  const { datasets, selectedId, setSelectedId, loading: dsLoading } = useDatasets()
  const [nTopics, setNTopics] = useState(6)
  const [topTerms, setTopTerms] = useState(8)
  const [ranConfig, setRanConfig] = useState(null)

  const { data, loading, error, execute } = useAsync(
    async () => {
      if (!selectedId) return null
      const res = await apiClient.topics(selectedId, nTopics, topTerms)
      setRanConfig({ selectedId, nTopics })
      return res
    },
    [selectedId],
    { immediate: !!selectedId }
  )

  if (!selectedId && !dsLoading) {
    return (
      <>
        <Head {...{ datasets, selectedId, setSelectedId, dsLoading }} controls={null} />
        <EmptyState title="Select a dataset" message="Choose a dataset to fit TF-IDF + NMF topics." />
      </>
    )
  }

  const relationNodes = (data?.topics || []).map((t) => ({
    id: String(t.id),
    label: `Topic ${t.id}`,
    platform: 'cluster',
    degree: Math.max(1, Math.round(t.share * 100)),
    weighted_degree: t.frequency,
    activity: t.frequency,
    engagement: t.frequency,
    cluster: t.id,
    pagerank: t.share,
  }))
  const relationEdges = (data?.relations || []).map((r) => ({
    source: String(r.source),
    target: String(r.target),
    weight: r.weight,
    edge_type: 'mention',
  }))

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Topic Modeling</h1>
          <p className="page-subtitle">
            TF-IDF vectorization + NMF factorization. Configurable topic count with top keywords,
            representative posts, frequency and per-topic trends over time.
          </p>
        </div>
        <div className="page-actions">
          <DatasetPicker datasets={datasets} value={selectedId} onChange={setSelectedId} loading={dsLoading} />
          <label className="field" style={{ width: 96 }}>
            <span>Topics</span>
            <input className="input" type="number" min={2} max={20} value={nTopics}
              onChange={(e) => setNTopics(Number(e.target.value))} />
          </label>
          <label className="field" style={{ width: 96 }}>
            <span>Keywords</span>
            <input className="input" type="number" min={3} max={20} value={topTerms}
              onChange={(e) => setTopTerms(Number(e.target.value))} />
          </label>
          <button className="btn btn-primary" onClick={execute} disabled={loading}>
            <RefreshCw size={14} /> {loading ? 'Fitting...' : 'Fit topics'}
          </button>
        </div>
      </div>

      {error && <ErrorNotice error={error} onRetry={execute} />}
      {loading && !data && <Spinner label="Fitting NMF model..." />}

      {data && (
        <>
          <div className="grid grid-4">
            <Metric label="Topics fitted" value={data.n_topics} />
            <Metric label="Documents" value={formatNumber(data.quality.documents)} />
            <Metric label="Mean doc-topic strength" value={data.quality.mean_document_topic_strength} />
            <Metric label="Reconstruction error" value={data.quality.reconstruction_error} />
          </div>

          <Panel title="Topic distribution" className="mt-16">
            <BarChart
              data={data.topics.map((t) => ({
                label: `Topic ${t.id}`,
                value: t.frequency,
                color: categoricalColor(t.id),
              }))}
              valueFormat={(v) => formatNumber(v)}
            />
          </Panel>

          <Panel title="Topic trends over time" hint="documents per day per topic">
            <LineChart
              series={data.topics.map((t) => ({
                name: `Topic ${t.id}`,
                color: categoricalColor(t.id),
                points: t.trend.map((p) => ({ x: new Date(p.date), y: p.count })),
              }))}
              yFormat={(v) => String(v)}
            />
          </Panel>

          <div className="grid grid-2 mt-16">
            {data.topics.map((t) => (
              <div className="topic-card" key={t.id}>
                <div className="flex-between">
                  <strong style={{ color: categoricalColor(t.id) }}>
                    <Tags size={14} style={{ verticalAlign: -2 }} /> Topic {t.id}
                  </strong>
                  <span className="badge blue">{t.frequency} docs, {(t.share * 100).toFixed(1)}%</span>
                </div>
                <div className="topic-keywords">
                  {t.keywords.map((k) => (
                    <span className="keyword" key={k.term} title={`weight ${k.weight}`}>
                      {k.term}
                    </span>
                  ))}
                </div>
                <div className="small muted mt-8">
                  {t.representative.length ? (
                    <>
                      <div className="faint" style={{ fontSize: 10, letterSpacing: '.1em', textTransform: 'uppercase' }}>
                        Representative posts
                      </div>
                      {t.representative.slice(0, 3).map((r, i) => (
                        <div key={i} className="mt-8" style={{ fontSize: 12.2 }}>
                          “{truncate(r.text, 170)}”
                          <span className="faint mono"> ({r.strength})</span>
                        </div>
                      ))}
                    </>
                  ) : (
                    <span className="faint">No members,  increase similarity or reduce topic count.</span>
                  )}
                </div>
              </div>
            ))}
          </div>

          {relationEdges.length > 0 && (
            <Panel
              title="Topic relationships"
              actions={
                <span className="hint">
                  <Link2 size={12} /> edge = authors posting in both topics (statistical co-occurrence)
                </span>
              }
              className="mt-16"
            >
              <ForceGraph
                nodes={relationNodes}
                edges={relationEdges}
                sizeMode="degree"
                colorMode="cluster"
                height={340}
              />
            </Panel>
          )}
        </>
      )}
    </>
  )
}

function Head(props) {
  return null // head rendered inline in this page
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <div className="m-label">{label}</div>
      <div className="m-value">{value}</div>
    </div>
  )
}
