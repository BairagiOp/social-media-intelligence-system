import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, RefreshCw, FileWarning } from '../components/icons'
import Panel from '../components/Panel'
import DatasetPicker from '../components/DatasetPicker'
import { EmptyState, ErrorNotice, Spinner } from '../components/Status'
import BarChart from '../charts/BarChart'
import { useAsync } from '../hooks/useApi'
import { useDatasets } from '../hooks/useDatasets'
import apiClient from '../services/api'
import { formatNumber, formatPercent, truncate } from '../utils/format'

export default function MisinformationPage() {
  const { datasets, selectedId, setSelectedId, loading: dsLoading } = useDatasets()
  const [limit, setLimit] = useState(300)
  const [onlyFlagged, setOnlyFlagged] = useState(true)

  const { data, loading, error, execute } = useAsync(
    () => (selectedId ? apiClient.misinformation(selectedId, limit) : Promise.resolve(null)),
    [selectedId, limit],
    { immediate: !!selectedId }
  )

  const notTrained = error?.code === 'model_not_trained'

  const items = (data?.items || []).filter(
    (i) => !onlyFlagged || i.classification === 'MODEL_FLAGGED'
  )

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Misinformation Classification</h1>
          <p className="page-subtitle">
            Baseline TF-IDF + Logistic Regression model producing classifications with confidence
            estimates and per-post feature explanations.
          </p>
        </div>
        <div className="page-actions">
          <DatasetPicker datasets={datasets} value={selectedId} onChange={setSelectedId} loading={dsLoading} />
          <button className="btn btn-ghost" onClick={execute} disabled={!selectedId}>
            <RefreshCw size={14} /> Re-run
          </button>
        </div>
      </div>

      <div className="notice warn mb-16">
        <AlertTriangle size={15} />
        <div>
          <strong>Human verification required.</strong> Model classifications and confidence
          estimates are statistical patterns in text, not factual determinations that content is
          misinformation. Verify claims against reliable sources before drawing any conclusion,
          and never treat output as a label for a real person or organization.
        </div>
      </div>

      {notTrained ? (
        <EmptyState
          title="Model not trained"
          message="No active misinformation model exists. Train the baseline in the Training Center (task: Misinformation Classification) and activate it."
          action={<Link to="/training" className="btn btn-primary">Open Training Center</Link>}
        />
      ) : error ? (
        <ErrorNotice error={error} onRetry={execute} />
      ) : loading && !data ? (
        <Spinner label="Classifying content..." />
      ) : null}

      {data && (
        <>
          <div className="grid grid-4">
            <Metric label="Evaluated" value={formatNumber(data.summary.evaluated)} />
            <Metric label="Model-flagged" value={formatNumber(data.summary.model_flagged)} tone="warn" />
            <Metric label="Flagged ratio" value={formatPercent(data.summary.flagged_ratio)} />
            <Metric label="Mean confidence" value={formatPercent(data.summary.mean_confidence)} />
          </div>

          <Panel
            title="Model & evaluation"
            hint={`${data.model.model_id}, ${data.model.model_type}, v${data.model.version}`}
            className="mt-16"
          >
            <div className="metric-row">
              <Metric label="Accuracy" value={data.model.metrics?.accuracy != null ? formatPercent(data.model.metrics.accuracy, 1) : ', '} />
              <Metric label="Precision" value={data.model.metrics?.precision != null ? formatPercent(data.model.metrics.precision, 1) : ', '} />
              <Metric label="Recall" value={data.model.metrics?.recall != null ? formatPercent(data.model.metrics.recall, 1) : ', '} />
              <Metric label="F1" value={data.model.metrics?.f1 != null ? formatPercent(data.model.metrics.f1, 1) : ', '} />
              <Metric label="ROC-AUC" value={data.model.metrics?.roc_auc != null ? formatPercent(data.model.metrics.roc_auc, 1) : ', '} />
              <Metric label="Train / test" value={`${formatNumber(data.model.metrics?.train_size || 0)} / ${formatNumber(data.model.metrics?.test_size || 0)}`} />
            </div>
            <div className="small faint mt-16">
              Held-out metrics from training, shown exactly as recorded in the model registry.
            </div>
          </Panel>

          <Panel
            title={`Classifications (${items.length})`}
            actions={
              <label className="checkbox-row" style={{ fontSize: 12 }}>
                <input type="checkbox" checked={onlyFlagged} onChange={(e) => setOnlyFlagged(e.target.checked)} />
                flagged only
              </label>
            }
          >
            {!items.length ? (
              <div className="small faint">No items match the current filter.</div>
            ) : (
              <div className="stack">
                {items.slice(0, 60).map((item, i) => (
                  <div className="topic-card" key={i}>
                    <div className="flex-between">
                      <span className={`badge ${item.classification === 'MODEL_FLAGGED' ? 'red' : 'green'}`}>
                        {item.classification.replace('_', ' ').toLowerCase()}
                      </span>
                      <span className="mono small">
                        confidence {formatPercent(item.confidence)}, p={item.flag_probability.toFixed(3)}
                      </span>
                    </div>
                    <p className="mt-8" style={{ fontSize: 13 }}>{truncate(item.text, 260)}</p>
                    <div className="small faint mt-8">
                      {item.username && <>{item.username}, </>}
                      {item.platform} {item.domain && <>, {item.domain}</>}
                    </div>
                    {item.top_features?.length > 0 && (
                      <div className="topic-keywords mt-8">
                        {item.top_features.map((f) => (
                          <span
                            className="keyword"
                            key={f.term}
                            title={`tfidf ${f.tfidf}, contribution ${f.weight}`}
                            style={{
                              color: f.weight >= 0 ? 'var(--bad)' : 'var(--ok)',
                            }}
                          >
                            {f.term} {f.weight >= 0 ? '▲' : '▼'}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            <div className="small faint mt-16">
              <FileWarning size={12} /> Terms shown are the model's highest-weighted features for
              each post, an explanation of model behavior, not evidence about the content.
            </div>
          </Panel>

          <Panel title="Flag rate overview" className="mt-16">
            <BarChart
              data={[
                { label: 'Model flagged', value: data.summary.model_flagged, color: '#933029' },
                { label: 'Not flagged', value: data.summary.evaluated - data.summary.model_flagged, color: '#2c6240' },
              ]}
              valueFormat={(v) => formatNumber(v)}
            />
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
