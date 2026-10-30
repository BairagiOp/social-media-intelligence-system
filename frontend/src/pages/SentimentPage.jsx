import { useState } from 'react'
import { Activity, SmilePlus, Frown, RefreshCw } from '../components/icons'
import Panel from '../components/Panel'
import DatasetPicker from '../components/DatasetPicker'
import { EmptyState, ErrorNotice, SkeletonBlock } from '../components/Status'
import LineChart from '../charts/LineChart'
import BarChart from '../charts/BarChart'
import { useAsync } from '../hooks/useApi'
import { useDatasets } from '../hooks/useDatasets'
import apiClient from '../services/api'
import { formatNumber, formatPercent, truncate } from '../utils/format'
import { categoricalColor } from '../utils/datasets'

export default function SentimentPage() {
  const { datasets, selectedId, setSelectedId, loading: dsLoading } = useDatasets()
  const [ran, setRan] = useState(null)

  const { data, loading, error, execute } = useAsync(
    async () => {
      if (!selectedId) return null
      const res = await apiClient.sentiment(selectedId)
      setRan(selectedId)
      return res
    },
    [selectedId],
    { immediate: !!selectedId }
  )

  if (!selectedId && !dsLoading) {
    return (
      <>
        <PageHead datasets={datasets} selectedId={selectedId} setSelectedId={setSelectedId} dsLoading={dsLoading} />
        <EmptyState title="Select a dataset" message="Choose a dataset to run VADER sentiment analysis." />
      </>
    )
  }

  const d = data

  return (
    <>
      <PageHead datasets={datasets} selectedId={selectedId} setSelectedId={setSelectedId} dsLoading={dsLoading} onRefresh={execute} />

      {error && <ErrorNotice error={error} onRetry={execute} />}
      {loading && !d && <SkeletonBlock height={220} label="Scoring sentiment" />}

      {d && (
        <>
          <div className="notice info mb-16">
            <Activity size={15} />
            <div>{d.disclaimer}</div>
          </div>

          <div className="grid grid-4">
            <Metric label="Posts scored" value={formatNumber(d.total)} />
            <Metric label="Positive" value={formatPercent(d.overall.ratios.positive)} tone="good" />
            <Metric label="Neutral" value={formatPercent(d.overall.ratios.neutral)} />
            <Metric label="Negative" value={formatPercent(d.overall.ratios.negative)} tone="bad" />
          </div>

          <Panel title="Sentiment over time" hint="mean VADER compound per day" className="mt-16">
            <LineChart
              series={[{ name: 'Mean compound', color: '#2b7183', points: d.timeline.map((p) => ({ x: new Date(p.date), y: p.mean_compound })) }]}
              yFormat={(v) => Number(v).toFixed(2)}
            />
          </Panel>

          <div className="grid grid-2 mt-16">
            <Panel title="Sentiment by platform" hint="mean compound">
              {Object.keys(d.by_platform || {}).length ? (
                <BarChart
                  data={Object.entries(d.by_platform).map(([label, v], i) => ({
                    label,
                    value: v.mean_compound,
                    color: categoricalColor(i, label),
                    detail: `${v.count} posts`,
                  }))}
                  valueFormat={(v) => v.toFixed(3)}
                />
              ) : (
                <div className="small faint">No platform column.</div>
              )}
            </Panel>

            <Panel title="Sentiment by user" hint="top 20 by volume, mean compound">
              {Object.keys(d.by_user || {}).length ? (
                <BarChart
                  data={Object.entries(d.by_user).map(([label, v]) => ({
                    label,
                    value: v.mean_compound,
                    color: v.mean_compound >= 0.05 ? '#2c6240' : v.mean_compound <= -0.05 ? '#933029' : '#9b958a',
                    detail: `${v.count} posts`,
                  }))}
                  maxBars={20}
                  valueFormat={(v) => v.toFixed(3)}
                />
              ) : (
                <div className="small faint">No user column.</div>
              )}
            </Panel>
          </div>

          <div className="grid grid-2 mt-16">
            <Panel title="Most positive posts" actions={<SmilePlus size={14} style={{ color: 'var(--ok)' }} />}>
              <div className="toplist">
                {d.most_positive.map((p, i) => (
                  <div className="toplist-item" key={i}>
                    <div>
                      <div>{truncate(p.text, 150)}</div>
                      <div className="small faint mt-8">
                        {p.username}, {p.platform}, {p.timestamp?.slice(0, 10)}
                      </div>
                    </div>
                    <span className="badge green mono">+{p.compound.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </Panel>

            <Panel title="Most negative posts" actions={<Frown size={14} style={{ color: 'var(--bad)' }} />}>
              <div className="toplist">
                {d.most_negative.map((p, i) => (
                  <div className="toplist-item" key={i}>
                    <div>
                      <div>{truncate(p.text, 150)}</div>
                      <div className="small faint mt-8">
                        {p.username}, {p.platform}, {p.timestamp?.slice(0, 10)}
                      </div>
                    </div>
                    <span className="badge red mono">{p.compound.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        </>
      )}
    </>
  )
}

function PageHead({ datasets, selectedId, setSelectedId, dsLoading, onRefresh }) {
  return (
    <div className="page-head">
      <div>
        <h1 className="page-title">Sentiment Analysis</h1>
        <p className="page-subtitle">
          VADER lexicon scoring (positive / negative / neutral / compound) across the dataset, 
          over time, platforms and users. Tone of text only; not intent.
        </p>
      </div>
      <div className="page-actions">
        <DatasetPicker datasets={datasets} value={selectedId} onChange={setSelectedId} loading={dsLoading} />
        {onRefresh && (
          <button className="btn btn-ghost" onClick={onRefresh}><RefreshCw size={14} /> Re-run</button>
        )}
      </div>
    </div>
  )
}

function Metric({ label, value, tone }) {
  return (
    <div className="metric">
      <div className="m-label">{label}</div>
      <div className="m-value">{value}</div>
    </div>
  )
}
