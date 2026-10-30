import { Link } from 'react-router-dom'
import { useEffect, useState } from 'react'
import {
  Database, Users, Bot, AlertTriangle, Tags, ShieldCheck,
  Target, ArrowUpRight, RefreshCw,
} from '../components/icons'
import apiClient from '../services/api'
import Panel from '../components/Panel'
import StatCard from '../components/StatCard'
import { ErrorNotice, SkeletonBlock } from '../components/Status'
import LineChart from '../charts/LineChart'
import BarChart from '../charts/BarChart'
import DonutChart from '../charts/DonutChart'
import { useAsync, useHealth } from '../hooks/useApi'
import { formatNumber, formatPercent } from '../utils/format'
import { categoricalColor } from '../utils/datasets'

/**
 * Placeholder shaped like the real dashboard: a figure strip followed by the
 * chart grid. Shown only while the first request is in flight.
 */
function DashboardSkeleton() {
  return (
    <>
      <header className="page-head">
        <div style={{ flex: 1 }}>
          <div className="skeleton skeleton-line" style={{ width: '18rem', height: '2rem' }} />
          <div className="skeleton skeleton-line mt-8" style={{ width: '70%' }} />
        </div>
      </header>
      <div className="grid grid-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div className="stat-card" key={i}>
            <div className="skeleton skeleton-line" style={{ width: '55%', height: '0.6rem' }} />
            <div className="skeleton skeleton-line" style={{ width: '45%', height: '1.6rem' }} />
            <div className="skeleton skeleton-line" style={{ width: '70%' }} />
          </div>
        ))}
      </div>
      <div className="grid grid-2 mt-16">
        {Array.from({ length: 4 }).map((_, i) => (
          <section className="panel" key={i}>
            <div className="panel-title">
              <div className="skeleton skeleton-line" style={{ width: '9rem', height: '1rem' }} />
            </div>
            <SkeletonBlock height={190} label="Loading chart" />
          </section>
        ))}
      </div>
    </>
  )
}


export default function DashboardPage() {
  const { data, loading, error, execute } = useAsync(() => apiClient.dashboard(), [])
  const { health } = useHealth(8000)
  const [tick, setTick] = useState(0)

  // refresh while bootstrap is still running
  const bootBusy =
    health?.bootstrap?.status === 'RUNNING' || health?.bootstrap?.status === 'PENDING'

  useEffect(() => {
    if (!bootBusy) return
    const t = setTimeout(() => {
      setTick((v) => v + 1)
      execute()
    }, 6000)
    return () => clearTimeout(t)
  }, [bootBusy, tick, execute])

  if (loading && !data) return <DashboardSkeleton />
  if (error) return <ErrorNotice error={error} onRetry={execute} />

  const d = data || {}
  const accuracyEntries = Object.entries(d.model_accuracy || {}).filter(([, v]) => v)

  const sentimentSeries = (d.sentiment_timeline || []).map((p) => ({
    x: new Date(p.date),
    y: p.mean_compound,
  }))
  const activitySeries = (d.activity_timeline || []).map((p) => ({
    x: new Date(p.date),
    y: p.count,
  }))
  const engagementSeries = (d.engagement_trend || []).map((p) => ({
    x: new Date(p.date),
    y: p.value,
  }))

  const topAccuracy = accuracyEntries
    .map(([, v]) => v.accuracy)
    .filter((v) => v !== null && v !== undefined)

  const botBuckets = d.bot_distribution?.buckets || null

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Intelligence Dashboard</h1>
          <p className="page-subtitle">
            Aggregated statistics computed live from loaded datasets, the evidence store and
            trained models. Model metrics come from real train/test evaluation.
          </p>
        </div>
        <div className="page-actions">
          <button className="btn btn-ghost" onClick={() => execute()}>
            <RefreshCw size={14} /> Refresh
          </button>
          <Link to="/training" className="btn btn-primary">
            <Target size={14} /> Training Center
          </Link>
        </div>
      </div>

      {(d.warnings || []).length > 0 && (
        <div className="notice warn mb-16">
          <AlertTriangle size={15} />
          <div>
            {d.warnings.map((w) => (
              <div key={w}>{w}</div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-4">
        <StatCard label="Total Records" value={formatNumber(d.total_records)} sub={`${d.active_datasets} active datasets`} icon={Database} />
        <StatCard label="Active Datasets" value={formatNumber(d.active_datasets)} sub="registered & queryable" icon={Database} />
        <StatCard label="Accounts Analyzed" value={formatNumber(d.accounts_analyzed)} sub="unique accounts in view" icon={Users} />
        <StatCard
          label="Automated-Account Likelihood"
          value={d.automated_likelihood ? formatPercent(d.automated_likelihood.mean, 1) : ', '}
          sub={d.automated_likelihood
            ? `${d.automated_likelihood.high_risk} accounts scored at or above 0.6, of ${d.automated_likelihood.total_accounts}`
            : 'Model not trained'}
          subTone={d.automated_likelihood ? 'warn' : ''}
          icon={Bot}
        />
        <StatCard
          label="Flagged Content"
          value={d.flagged_content ? formatNumber(d.flagged_content.model_flagged) : ', '}
          sub={d.flagged_content
            ? `model classification, ${d.flagged_content.evaluated} evaluated`
            : 'Model not trained'}
          subTone={d.flagged_content ? 'warn' : ''}
          icon={AlertTriangle}
        />
        <StatCard label="Topic Count" value={formatNumber(d.topic_count)} sub="NMF topics discovered" icon={Tags} />
        <StatCard label="Evidence Items" value={formatNumber(d.evidence_items)} sub="SHA-256 custody records" icon={ShieldCheck} />
        <StatCard
          label="Model Accuracy"
          value={topAccuracy.length ? formatPercent(Math.max(...topAccuracy), 1) : ', '}
          sub={topAccuracy.length
            ? `best of ${topAccuracy.length} active supervised models`
            : 'Model not trained'}
          subTone={topAccuracy.length ? 'good' : ''}
          icon={Target}
        />
      </div>

      <div className="grid grid-2 mt-16">
        <Panel title="Activity Timeline" hint="records per day">
          {activitySeries.length ? (
            <LineChart series={[{ name: 'Posts', color: '#2b7183', points: activitySeries }]} area yFormat={(v) => formatNumber(v)} />
          ) : (
            <div className="small faint">No timestamp data</div>
          )}
        </Panel>

        <Panel title="Sentiment Timeline" hint="mean VADER compound / day">
          {sentimentSeries.length ? (
            <LineChart
              series={[{ name: 'Mean compound', color: '#4a93a4', points: sentimentSeries }]}
              yFormat={(v) => Number(v).toFixed(2)}
            />
          ) : (
            <div className="small faint">No sentiment data</div>
          )}
        </Panel>
      </div>

      <div className="grid grid-2 mt-16">
        <Panel title="Platform Distribution">
          {Object.keys(d.platform_distribution || {}).length ? (
            <DonutChart
              data={Object.entries(d.platform_distribution).map(([label, value], i) => ({
                label,
                value,
                color: categoricalColor(i, label),
              }))}
            />
          ) : (
            <div className="small faint">No platform column detected</div>
          )}
        </Panel>

        <Panel title="Automated-Account Likelihood Distribution" hint="model output, 10 bins">
          {botBuckets ? (
            <BarChart
              data={botBuckets.map((count, i) => ({
                label: `${(i / 10).toFixed(1)} to ${((i + 1) / 10).toFixed(1)}`,
                value: count,
                color: i >= 6 ? '#0e3d47' : i >= 4 ? '#74b2bf' : '#4a93a4',
              }))}
              valueFormat={(v) => v}
            />
          ) : (
            <div className="small faint">Model not trained, train a bot-detection model to populate.</div>
          )}
        </Panel>
      </div>

      <div className="grid grid-2 mt-16">
        <Panel title="Topic Distribution" hint="documents per topic">
          {Object.keys(d.topic_distribution || {}).length ? (
            <BarChart
              data={Object.entries(d.topic_distribution).map(([label, value]) => ({
                label: `Topic ${label}`,
                value,
                color: '#2b7183',
              }))}
              valueFormat={(v) => formatNumber(v)}
            />
          ) : (
            <div className="small faint">No topics computed yet</div>
          )}
        </Panel>

        <Panel title="Engagement Trend" hint="mean engagement score / day">
          {engagementSeries.length ? (
            <LineChart
              series={[{ name: 'Engagement', color: '#74b2bf', points: engagementSeries }]}
              area
              yFormat={(v) => formatNumber(v)}
            />
          ) : (
            <div className="small faint">No engagement columns detected</div>
          )}
        </Panel>
      </div>

      <div className="grid grid-2 mt-16">
        <Panel title="Active Model Performance" hint="from model registry">
          {accuracyEntries.length ? (
            <div className="stack">
              {accuracyEntries.map(([task, m]) => (
                <div className="toplist-item" key={task}>
                  <span style={{ textTransform: 'capitalize' }}>{task.replace('_', ' ')}</span>
                  <span className="mono small">
                    {m.accuracy !== null && m.accuracy !== undefined
                      ? `acc ${formatPercent(m.accuracy, 1)}`
                      : m.f1 !== null && m.f1 !== undefined
                        ? `f1 ${formatPercent(m.f1, 1)}`
                        : 'unsupervised'}
                    <span className="faint">, {m.model_id}</span>
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="small faint">No active models. Visit the Training Center.</div>
          )}
        </Panel>

        <Panel title="Quick Navigation">
          <div className="stack">
            <Link className="toplist-item" to="/datasets">
              <span>Datasets: upload, profile, preprocess</span> <ArrowUpRight size={14} />
            </Link>
            <Link className="toplist-item" to="/explorer">
              <span>Data explorer: search, filter, inspect rows</span> <ArrowUpRight size={14} />
            </Link>
            <Link className="toplist-item" to="/network">
              <span>Network graph: communities and centrality</span> <ArrowUpRight size={14} />
            </Link>
            <Link className="toplist-item" to="/evidence">
              <span>Evidence: SHA-256 chain of custody</span> <ArrowUpRight size={14} />
            </Link>
            <Link className="toplist-item" to="/reports">
              <span>Reports: generated intelligence summaries</span> <ArrowUpRight size={14} />
            </Link>
          </div>
        </Panel>
      </div>
    </>
  )
}
