import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Play, Save, Layers, CheckCircle2, Activity, Archive, Star, RotateCw,
} from '../components/icons'
import Panel from '../components/Panel'
import DatasetPicker from '../components/DatasetPicker'
import { ErrorNotice, Spinner } from '../components/Status'
import ConfusionMatrix from '../charts/ConfusionMatrix'
import BarChart from '../charts/BarChart'
import { useAsync, useTrainingJob } from '../hooks/useApi'
import { useDatasets } from '../hooks/useDatasets'
import apiClient from '../services/api'
import { formatDate, formatNumber, formatPercent } from '../utils/format'

const STEPS = [
  'Dataset', 'Task', 'Target', 'Features', 'Split', 'Model', 'Train', 'Evaluate', 'Save',
]

export default function TrainingPage() {
  const { datasets, selectedId, setSelectedId, loading: dsLoading } = useDatasets()
  const { data: catalog, loading: catLoading } = useAsync(() => apiClient.mlTasks(), [])
  const { data: registryData, loading: regLoading, execute: reloadRegistry } =
    useAsync(() => apiClient.models(), [])
  const { job, track } = useTrainingJob()

  const [taskId, setTaskId] = useState('sentiment')
  const [target, setTarget] = useState('')
  const [features, setFeatures] = useState(null) // null = backend default
  const [modelType, setModelType] = useState('')
  const [testSize, setTestSize] = useState(0.2)
  const [nTopics, setNTopics] = useState(6)
  const [maxFeatures, setMaxFeatures] = useState(5000)
  const [startError, setStartError] = useState(null)
  const [lastResult, setLastResult] = useState(null)

  const dataset = useMemo(
    () => datasets.find((d) => d.id === selectedId) || null,
    [datasets, selectedId]
  )
  const task = catalog?.tasks?.[taskId] || null

  const columns = dataset?.column_names || []
  const targetOptions = useMemo(() => {
    if (!task) return columns
    const candidates = task.target_candidates || []
    const suggested = columns.filter((c) => candidates.includes(c))
    const rest = columns.filter((c) => !candidates.includes(c))
    return [...suggested, ...rest]
  }, [columns, task])

  const featureCandidates = task?.feature_candidates || []

  const activeStep = !selectedId ? 0
    : !taskId ? 1
    : task?.requires_target && !target ? 2
    : taskId === 'bot_detection' && Array.isArray(features) && features.length === 0 ? 3
    : lastResult ? 8
    : job ? 6
    : 5

  const stepState = (i) => {
    if (i < activeStep) return 'done'
    if (i === activeStep) return 'active'
    return ''
  }

  const startTraining = async () => {
    setStartError(null)
    setLastResult(null)
    const payload = {
      dataset_id: selectedId,
      task: taskId,
      test_size: Number(testSize),
      n_topics: Number(nTopics),
      max_features: Number(maxFeatures),
    }
    if (target) payload.target = target
    if (modelType) payload.model_type = modelType
    if (taskId === 'bot_detection' && features?.length) payload.features = features

    try {
      const started = await apiClient.train(payload)
      const final = await track(started.job_id)
      if (final.status === 'COMPLETE') {
        setLastResult(final.result?.model || null)
        reloadRegistry()
      } else {
        setStartError({ detail: final.error || 'Training failed.', code: 'training_failed' })
      }
    } catch (err) {
      setStartError(err)
    }
  }

  const activate = async (ref) => {
    try {
      await apiClient.activateModel(ref)
      reloadRegistry()
    } catch (err) {
      setStartError(err)
    }
  }

  const archive = async (ref) => {
    try {
      await apiClient.archiveModel(ref)
      reloadRegistry()
    } catch (err) {
      setStartError(err)
    }
  }

  const metrics = lastResult?.metrics || null

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">ML Training Center</h1>
          <p className="page-subtitle">
            Train models on your datasets with real train/test evaluation. Every metric below is
            computed by the backend from held-out data,  nothing is hard-coded. If a model has
            never been trained, the UI shows “Model not trained.”
          </p>
        </div>
      </div>

      <div className="steps">
        {STEPS.map((s, i) => (
          <span key={s} className={`step-chip ${stepState(i)}`}>
            <span className="step-num">{i + 1}</span> {s}
            {i < activeStep && <CheckCircle2 size={12} />}
          </span>
        ))}
      </div>

      <ErrorNotice error={startError} onRetry={() => setStartError(null)} />

      <div className="grid grid-2">
        {/* ---------------- configuration ---------------- */}
        <Panel title="Steps 1 to 6: configuration">
          <div className="stack">
            <label className="field">
              <span>Step 1: dataset</span>
              <DatasetPicker
                datasets={datasets}
                value={selectedId}
                onChange={(id) => { setSelectedId(id); setTarget(''); setLastResult(null) }}
                loading={dsLoading}
              />
            </label>

            <label className="field">
              <span>Step 2: machine learning task</span>
              <select
                className="select"
                value={taskId}
                onChange={(e) => {
                  setTaskId(e.target.value)
                  setTarget('')
                  setModelType('')
                  setFeatures(null)
                  setLastResult(null)
                }}
              >
                {catLoading && <option>Loading...</option>}
                {catalog &&
                  Object.entries(catalog.tasks).map(([id, t]) => (
                    <option key={id} value={id}>{t.label}</option>
                  ))}
              </select>
            </label>

            {task?.requires_target && (
              <label className="field">
                <span>
                  Step 3: target column
                  {task.target_candidates?.length > 0 && (
                    <em className="faint" style={{ textTransform: 'none', fontStyle: 'normal' }}>
                      {' '}suggested: {task.target_candidates.join(', ')}
                    </em>
                  )}
                </span>
                <select className="select" value={target} onChange={(e) => setTarget(e.target.value)}>
                  <option value="">Select target...</option>
                  {targetOptions.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </label>
            )}

            {taskId === 'bot_detection' && featureCandidates.length > 0 && (
              <div className="field">
                <span>Step 4: features (uncheck to exclude)</span>
                <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                  {featureCandidates.map((f) => {
                    const checked = features ? features.includes(f) : true
                    return (
                      <label className="checkbox-row" key={f}>
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => {
                            const current = features || [...featureCandidates]
                            const next = e.target.checked
                              ? [...new Set([...current, f])]
                              : current.filter((x) => x !== f)
                            setFeatures(next)
                          }}
                        />
                        <span className="mono" style={{ fontSize: 11.5 }}>{f}</span>
                      </label>
                    )
                  })}
                </div>
              </div>
            )}

            <div className="grid grid-2">
              <label className="field">
                <span>Step 5: test split</span>
                <select className="select" value={testSize} onChange={(e) => setTestSize(Number(e.target.value))}>
                  <option value={0.1}>90 / 10</option>
                  <option value={0.15}>85 / 15</option>
                  <option value={0.2}>80 / 20</option>
                  <option value={0.25}>75 / 25</option>
                  <option value={0.3}>70 / 30</option>
                </select>
              </label>

              <label className="field">
                <span>Step 6: model</span>
                <select className="select" value={modelType} onChange={(e) => setModelType(e.target.value)}>
                  <option value="">Backend default</option>
                  {(task?.models || []).map((m) => (
                    <option key={m.id} value={m.id}>{m.label}</option>
                  ))}
                </select>
              </label>
            </div>

            {taskId === 'topic_model' && (
              <div className="grid grid-2">
                <label className="field">
                  <span>Number of topics</span>
                  <input
                    className="input"
                    type="number"
                    min={2}
                    max={20}
                    value={nTopics}
                    onChange={(e) => setNTopics(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Max TF-IDF features</span>
                  <input
                    className="input"
                    type="number"
                    min={500}
                    max={50000}
                    step={500}
                    value={maxFeatures}
                    onChange={(e) => setMaxFeatures(e.target.value)}
                  />
                </label>
              </div>
            )}

            <button
              className="btn btn-primary"
              onClick={startTraining}
              disabled={!selectedId || !taskId || (task?.requires_target && !target) || (job && job.status !== 'COMPLETE' && job.status !== 'FAILED')}
            >
              <Play size={14} /> Start training
            </button>
          </div>
        </Panel>

        {/* ---------------- progress & results ---------------- */}
        <div className="stack">
          <Panel title="Step 7: training progress">
            {!job ? (
              <div className="small faint">
                No training run yet. Configure the steps on the left and press Start training.
              </div>
            ) : (
              <div className="stack">
                <div className="flex-between">
                  <span className="badge blue">{job.status}</span>
                  <span className="mono small">{job.progress}%</span>
                </div>
                <div className="progress-track">
                  <div className="progress-fill" style={{ width: `${job.progress}%` }} />
                </div>
                <div className="small muted">
                  Step: <strong>{job.step}</strong>
                  {job.detail && <>,  {job.detail}</>}
                </div>
                {job.status === 'RUNNING' && <Spinner label="Training in progress..." />}
                {job.status === 'FAILED' && (
                  <div className="notice error">Training failed: {job.error}</div>
                )}
              </div>
            )}
          </Panel>

          <Panel
            title="Step 8: evaluation"
            actions={lastResult ? <span className="hint">{lastResult.model_id}</span> : null}
          >
            {!lastResult ? (
              <div className="small faint">
                Model not trained in this session,  results will appear here after a run.
              </div>
            ) : (
              <div className="stack">
                <div className="flex-between">
                  <strong>{lastResult.name}</strong>
                  <span className="badge purple">{lastResult.task}</span>
                </div>

                {metrics && (
                  <>
                    <div className="metric-row">
                      {metrics.accuracy !== undefined && metrics.accuracy !== null && (
                        <Metric label="Accuracy" value={formatPercent(metrics.accuracy, 1)} />
                      )}
                      <Metric label="Precision" value={metrics.precision !== undefined && metrics.precision !== null ? formatPercent(metrics.precision, 1) : ', '} />
                      <Metric label="Recall" value={metrics.recall !== undefined && metrics.recall !== null ? formatPercent(metrics.recall, 1) : ', '} />
                      <Metric label="F1" value={metrics.f1 !== undefined && metrics.f1 !== null ? formatPercent(metrics.f1, 1) : ', '} />
                      <Metric label="ROC-AUC" value={metrics.roc_auc ? formatPercent(metrics.roc_auc, 1) : ', '} />
                      <Metric label="Train size" value={formatNumber(metrics.train_size ?? metrics.documents ?? metrics.accounts ?? 0)} />
                      <Metric label="Test size" value={metrics.test_size !== undefined ? formatNumber(metrics.test_size) : ', '} />
                      <Metric label="Model" value={metrics.model_type || lastResult.model_id} small />
                    </div>

                    {metrics.confusion_matrix && (
                      <div>
                        <div className="section-divider" style={{ marginTop: 8 }}>Confusion matrix (test set)</div>
                        <ConfusionMatrix matrix={metrics.confusion_matrix} classes={metrics.classes} />
                      </div>
                    )}

                    {metrics.feature_importance && (
                      <div>
                        <div className="section-divider">Feature importance</div>
                        <BarChart
                          data={Object.entries(metrics.feature_importance)
                            .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
                            .map(([label, value]) => ({ label, value: Math.abs(value), color: '#2b7183' }))}
                          valueFormat={(v) => v.toFixed(4)}
                        />
                      </div>
                    )}

                    {metrics.top_keywords && (
                      <div>
                        <div className="section-divider">Top keywords per topic</div>
                        <div className="stack small">
                          {Object.entries(metrics.top_keywords).map(([tid, words]) => (
                            <div key={tid}>
                              <span className="badge purple">topic {tid}</span>{' '}
                              <span className="mono muted">{words.join(', ')}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="notice info">
                      <Save size={15} />
                      <div className="small">
                        Saved to <span className="mono">{lastResult.artifact_path}</span> (joblib),
                        version v{lastResult.version}, {formatDate(lastResult.created_at)}
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}
          </Panel>
        </div>
      </div>

      {/* ---------------- registry ---------------- */}
      <Panel
        title={`Step 9: model registry (${registryData?.total ?? 0})`}
        actions={<span className="hint">activate one model per task for inference</span>}
      >
        {regLoading ? (
          <Spinner label="Loading registry..." />
        ) : !registryData?.items?.length ? (
          <div className="small faint">
            Registry empty,  train a model above, or run{' '}
            <code className="mono">python ml/training/train_sentiment.py</code>.
          </div>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Model ID</th>
                  <th>Name</th>
                  <th>Task</th>
                  <th>Version</th>
                  <th>Metrics</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {registryData.items.map((m) => (
                  <tr key={m.id}>
                    <td className="cell-mono" style={{ color: 'var(--accent)' }}>{m.model_id}</td>
                    <td>{m.name}</td>
                    <td><span className="badge gray">{m.task}</span></td>
                    <td className="cell-mono">v{m.version}</td>
                    <td className="cell-mono small">
                      {m.metrics.accuracy !== undefined && m.metrics.accuracy !== null
                        ? `acc ${formatPercent(m.metrics.accuracy, 1)}, f1 ${formatPercent(m.metrics.f1, 1)}`
                        : m.metrics.reconstruction_error !== undefined
                          ? `recon ${m.metrics.reconstruction_error}`
                          : ', '}
                    </td>
                    <td>
                      <span className={`badge ${m.status === 'ACTIVE' ? 'green' : m.status === 'ARCHIVED' ? 'gray' : 'blue'}`}>
                        {m.status}
                      </span>
                    </td>
                    <td className="cell-dim small">{formatDate(m.created_at)}</td>
                    <td>
                      <div className="flex" style={{ gap: 6, justifyContent: 'flex-end' }}>
                        {m.status !== 'ACTIVE' && (
                          <button className="btn btn-sm" onClick={() => activate(m.model_id)}>
                            <Star size={13} /> Activate
                          </button>
                        )}
                        {m.status === 'ACTIVE' && (
                          <button className="btn btn-sm" onClick={() => archive(m.model_id)}>
                            <Archive size={13} /> Archive
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="small faint mt-16">
          <Activity size={12} /> Inference lives on the analysis pages, {' '}
          <Link to="/bot-detection">Bot Detection</Link>, <Link to="/misinformation">Misinformation</Link>,{' '}
          <Link to="/sentiment">Sentiment</Link>. Registry metrics refresh after each run.{' '}
          <RotateCw size={11} />
        </div>
      </Panel>
    </>
  )
}

function Metric({ label, value, small }) {
  return (
    <div className="metric">
      <div className="m-label">{label}</div>
      <div className="m-value" style={{ fontSize: small ? 13 : 19 }}>{value}</div>
    </div>
  )
}
