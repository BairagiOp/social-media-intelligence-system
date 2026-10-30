import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Bot, RefreshCw, ShieldQuestion } from '../components/icons'
import Panel from '../components/Panel'
import DatasetPicker from '../components/DatasetPicker'
import { EmptyState, ErrorNotice, Spinner } from '../components/Status'
import BarChart from '../charts/BarChart'
import { useAsync } from '../hooks/useApi'
import { useDatasets } from '../hooks/useDatasets'
import apiClient from '../services/api'
import { formatNumber, formatPercent, scoreColor } from '../utils/format'

export default function BotPage() {
  const { datasets, selectedId, setSelectedId, loading: dsLoading } = useDatasets()
  const [limit, setLimit] = useState(40)

  const { data, loading, error, execute } = useAsync(
    () => (selectedId ? apiClient.bot(selectedId) : Promise.resolve(null)),
    [selectedId],
    { immediate: !!selectedId }
  )

  const notTrained = error?.code === 'model_not_trained'

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Automated-Account Analysis</h1>
          <p className="page-subtitle">
            Transparent feature-based classification: account age, followers/following ratio,
            posting cadence, content duplication and engagement are scored by the active model
            with per-account explanations.
          </p>
        </div>
        <div className="page-actions">
          <DatasetPicker datasets={datasets} value={selectedId} onChange={setSelectedId} loading={dsLoading} />
          <button className="btn btn-ghost" onClick={execute} disabled={!selectedId}>
            <RefreshCw size={14} /> Re-run
          </button>
        </div>
      </div>

      {notTrained ? (
        <EmptyState
          title="Model not trained"
          message="No active automated-account model exists yet. Train one in the Training Center (task: Automated-Account Detection) and activate it,  this page never invents scores."
          action={<Link to="/training" className="btn btn-primary">Open Training Center</Link>}
        />
      ) : error ? (
        <ErrorNotice error={error} onRetry={execute} />
      ) : loading && !data ? (
        <Spinner label="Scoring accounts..." />
      ) : null}

      {data && (
        <>
          <div className="notice warn mb-16">
            <ShieldQuestion size={15} />
            <div>{data.disclaimer}</div>
          </div>

          <div className="grid grid-4">
            <Metric label="Accounts scored" value={formatNumber(data.accounts.length)} />
            <Metric
              label="Mean likelihood"
              value={formatPercent(
                data.accounts.reduce((s, a) => s + a.score, 0) / (data.accounts.length || 1), 1
              )}
            />
            <Metric
              label="Likely automated, score 0.5 and above"
              value={formatNumber(data.accounts.filter((a) => a.score >= 0.5).length)}
              tone="warn"
            />
            <Metric
              label="Very high, score 0.8 and above"
              value={formatNumber(data.accounts.filter((a) => a.score >= 0.8).length)}
              tone="bad"
            />
          </div>

          <div className="grid grid-2 mt-16">
            <Panel
              title="Likelihood distribution"
              hint={`model ${data.model.model_id}, ${data.model.model_type}`}
            >
              <BarChart
                data={(data.distribution.buckets || []).map((count, i) => ({
                  label: `${(i / 10).toFixed(1)} to ${((i + 1) / 10).toFixed(1)}`,
                  value: count,
                  color: i >= 6 ? '#933029' : i >= 4 ? '#8a5516' : '#2c6240',
                }))}
                valueFormat={(v) => v}
              />
              <div className="small faint mt-8">
                Accuracy {data.model.metrics?.accuracy != null
                  ? formatPercent(data.model.metrics.accuracy, 1)
                  : 'not reported'}
                , F1 {data.model.metrics?.f1 != null
                  ? formatPercent(data.model.metrics.f1, 1)
                  : 'not reported'}
                , ROC-AUC {data.model.metrics?.roc_auc != null
                  ? formatPercent(data.model.metrics.roc_auc, 1)
                  : 'not reported'}
              </div>
            </Panel>

            <Panel
              title="How the score is built"
              hint="model feature importances"
            >
              {data.model.metrics?.feature_importance ? (
                <BarChart
                  data={Object.entries(data.model.metrics.feature_importance)
                    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
                    .map(([label, value]) => ({ label, value: Math.abs(value), color: '#15535f' }))}
                  valueFormat={(v) => v.toFixed(4)}
                />
              ) : (
                <div className="small faint">Feature importances not recorded for this model.</div>
              )}
            </Panel>
          </div>

          <Panel
            title="Account scores"
            actions={
              <span className="flex">
                <input
                  className="input"
                  type="number"
                  min={5}
                  max={200}
                  aria-label="Number of accounts to score"
                  value={limit}
                  onChange={(e) => setLimit(Number(e.target.value))}
                  style={{ width: 80 }}
                />
                <span className="hint">rows shown</span>
              </span>
            }
          >
            <div className="table-wrap" style={{ maxHeight: '55vh' }}>
              <table className="data">
                <thead>
                  <tr>
                    <th>Account</th>
                    <th>Likelihood</th>
                    <th>Band</th>
                    <th>Classification</th>
                    <th>Top contributing features</th>
                  </tr>
                </thead>
                <tbody>
                  {data.accounts.slice(0, limit).map((a) => (
                    <tr key={a.username}>
                      <td className="cell-mono">{a.username}</td>
                      <td style={{ width: 170 }}>
                        <div className="flex" style={{ gap: 8 }}>
                          <div className="progress-track" style={{ flex: 1, height: 6 }}>
                            <div
                              className="progress-fill"
                              style={{
                                width: `${a.score * 100}%`,
                                background: scoreColor(a.score),
                              }}
                            />
                          </div>
                          <span className="mono small" style={{ color: scoreColor(a.score) }}>
                            {a.score.toFixed(3)}
                          </span>
                        </div>
                      </td>
                      <td>
                        <span
                          className={`badge ${
                            a.likelihood_band.includes('high') ? 'red'
                              : a.likelihood_band === 'medium' ? 'amber'
                              : 'green'
                          }`}
                        >
                          {a.likelihood_band.replace('_', ' ')}
                        </span>
                      </td>
                      <td>
                        <span className={`badge ${a.classification === 'LIKELY_AUTOMATED' ? 'red' : 'green'}`}>
                          {a.classification.replace('_', ' ').toLowerCase()}
                        </span>
                      </td>
                      <td>
                        <div className="contrib">
                          {a.feature_contributions.slice(0, 4).map((c) => (
                            <div className="contrib-row" key={c.feature}>
                              <span className="contrib-name">{c.feature}</span>
                              <div className="contrib-track">
                                <div
                                  className="contrib-bar"
                                  style={{
                                    width: `${Math.min(100, Math.abs(c.contribution) * 40)}%`,
                                    background: c.contribution >= 0 ? '#933029' : '#2c6240',
                                  }}
                                />
                              </div>
                              <span className="contrib-val">
                                {c.contribution >= 0 ? '+' : ''}{c.contribution.toFixed(2)}
                              </span>
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="small faint mt-16">
              <Bot size={12} /> Red bars push the score toward â€œlikely automatedâ€, green bars away
              from it. Model estimates only,  verify manually before drawing conclusions.
            </div>
          </Panel>
        </>
      )}
    </>
  )
}

function Metric({ label, value, tone }) {
  return (
    <div className="metric">
      <div className="m-label">{label}</div>
      <div className="m-value">{value}</div>
      {tone && <div className={`stat-sub ${tone}`} />}
    </div>
  )
}
