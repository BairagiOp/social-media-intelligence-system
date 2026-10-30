import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft, Columns3, Play, ShieldCheck, CheckCircle2,
} from '../components/icons'
import Panel from '../components/Panel'
import { ErrorNotice, Spinner } from '../components/Status'
import DonutChart from '../charts/DonutChart'
import BarChart from '../charts/BarChart'
import apiClient from '../services/api'
import { formatNumber, formatPercent } from '../utils/format'
import { CANONICAL_LABELS, categoricalColor } from '../utils/datasets'

const OPTIONS = [
  ['deduplicate', 'Remove duplicate records'],
  ['drop_missing_text', 'Drop rows with missing text'],
  ['impute_numeric', 'Impute missing numeric values (median)'],
  ['lowercase', 'Lowercase text'],
  ['handle_emoji', 'Strip emoji'],
  ['remove_stopwords', 'Remove stopwords'],
  ['lemmatize', 'Lemmatize tokens'],
  ['feature_engineering', 'Engineer features (engagement, ratios, time parts)'],
]

const TEXT_OPTIONS = [
  ['handle_urls', 'URL handling', ['placeholder', 'strip', 'keep']],
  ['handle_mentions', 'Mention handling', ['strip', 'placeholder', 'keep']],
  ['handle_hashtags', 'Hashtag handling', ['unwrap', 'strip', 'keep']],
]

export default function DatasetProfilePage() {
  const { id } = useParams()
  const [dataset, setDataset] = useState(null)
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [mapping, setMapping] = useState({})
  const [mapSaving, setMapSaving] = useState(false)
  const [mapSaved, setMapSaved] = useState(false)

  const [options, setOptions] = useState({
    deduplicate: true,
    drop_missing_text: true,
    impute_numeric: true,
    lowercase: true,
    handle_emoji: true,
    remove_stopwords: false,
    lemmatize: false,
    feature_engineering: true,
    handle_urls: 'placeholder',
    handle_mentions: 'strip',
    handle_hashtags: 'unwrap',
  })
  const [prep, setPrep] = useState({ running: false, result: null, error: null })

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [ds, prof] = await Promise.all([
        apiClient.getDataset(id),
        apiClient.getProfile(id),
      ])
      setDataset(ds)
      setProfile(prof.profile)
      setMapping(ds.column_map || {})
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  const saveMapping = async () => {
    setMapSaving(true)
    setError(null)
    try {
      const ds = await apiClient.setColumnMap(id, mapping)
      setDataset(ds)
      setMapping(ds.column_map || {})
      const prof = await apiClient.getProfile(id, true)
      setProfile(prof.profile)
      setMapSaved(true)
      setTimeout(() => setMapSaved(false), 2500)
    } catch (err) {
      setError(err)
    } finally {
      setMapSaving(false)
    }
  }

  const runPreprocess = async () => {
    setPrep({ running: true, result: null, error: null })
    try {
      const res = await apiClient.preprocess(id, options)
      setPrep({ running: false, result: res, error: null })
    } catch (err) {
      setPrep({ running: false, result: null, error: err })
    }
  }

  if (loading) return <Spinner label="Loading dataset profile..." />
  if (error && !dataset) return <ErrorNotice error={error} onRetry={load} />
  if (!dataset) return null

  const p = profile || {}
  const classDists = p.class_distributions || {}
  const missingTop = Object.entries(p.missing_values || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12)
  const canonicalKeys = Object.keys(CANONICAL_LABELS)

  return (
    <>
      <div className="page-head">
        <div>
          <Link to="/datasets" className="small"><ArrowLeft size={13} /> Back to datasets</Link>
          <h1 className="page-title mt-8">{dataset.name}</h1>
          <p className="page-subtitle">
            <span className="badge cyan">{dataset.format}</span>{' '}
            <span className="badge blue">{dataset.status}</span>{' '}
            <span className="badge gray">v{dataset.version}</span>{' '}
            {formatNumber(dataset.records)} records, {dataset.column_names?.length || 0} columns
            {dataset.parent_id && <>, derived from <code className="mono">{dataset.parent_id}</code></>}
          </p>
        </div>
        <div className="page-actions">
          {dataset.evidence_id && (
            <Link to="/evidence" className="btn btn-ghost">
              <ShieldCheck size={14} /> Evidence {dataset.evidence_id}
            </Link>
          )}
          <Link to={`/explorer?dataset=${dataset.id}`} className="btn">Open in Explorer</Link>
        </div>
      </div>

      <ErrorNotice error={error} onRetry={() => setError(null)} />

      {/* ---- headline stats ---- */}
      <div className="grid grid-4">
        <Stat label="Records" value={formatNumber(p.records ?? dataset.records)} />
        <Stat label="Columns" value={p.columns_count ?? dataset.column_names?.length ?? ', '} />
        <Stat label="Duplicates" value={formatNumber(p.duplicate_records)} />
        <Stat label="Unique Users" value={formatNumber(p.unique_users)} />
        <Stat label="Avg Text Length" value={p.avg_text_length ? `${p.avg_text_length} chars` : ', '} />
        <Stat label="Median Text Length" value={p.median_text_length ? `${p.median_text_length} chars` : ', '} />
        <Stat
          label="Date Range"
          value={
            p.date_range
              ? `${p.date_range.min.slice(0, 10)} → ${p.date_range.max.slice(0, 10)}`
              : ', '
          }
        />
        <Stat
          label="Sentiment (mean)"
          value={
            p.sentiment_distribution?.mean_compound !== undefined
              ? p.sentiment_distribution.mean_compound.toFixed(3)
              : ', '
          }
        />
      </div>

      <div className="grid grid-2 mt-16">
        <Panel title="Platform distribution">
          {Object.keys(p.platform_distribution || {}).length ? (
            <DonutChart
              data={Object.entries(p.platform_distribution).map(([label, value], i) => ({
                label, value, color: categoricalColor(i, label),
              }))}
            />
          ) : (
            <div className="small faint">No platform column detected.</div>
          )}
        </Panel>

        <Panel title="Language distribution">
          {Object.keys(p.language_distribution || {}).length ? (
            <BarChart
              data={Object.entries(p.language_distribution).map(([label, value]) => ({
                label,
                value: Math.round(value * 1000) / 10,
                color: '#2b7183',
              }))}
              valueFormat={(v) => `${v}%`}
            />
          ) : (
            <div className="small faint">No language data.</div>
          )}
        </Panel>
      </div>

      <div className="grid grid-2 mt-16">
        <Panel title="Sentiment distribution" hint="VADER, tone only, not intent">
          {p.sentiment_distribution?.labels ? (
            <BarChart
              data={Object.entries(p.sentiment_distribution.labels).map(([label, value]) => ({
                label,
                value: Math.round(value * 1000) / 10,
                color:
                  label === 'positive' ? '#2c6240' : label === 'negative' ? '#933029' : '#9b958a',
              }))}
              valueFormat={(v) => `${v}%`}
            />
          ) : (
            <div className="small faint">No text column available.</div>
          )}
        </Panel>

        <Panel title="Class distributions" hint="label columns detected automatically">
          {Object.keys(classDists).length ? (
            <div className="stack">
              {Object.entries(classDists).map(([key, dist]) => (
                <div key={key}>
                  <div className="small muted mb-8">
                    <strong>{CANONICAL_LABELS[key] || key}</strong>{' '}
                    <span className="faint">({dist.column})</span>
                  </div>
                  <BarChart
                    data={Object.entries(dist.counts).map(([label, value]) => ({
                      label: String(label), value, color: '#15535f',
                    }))}
                    valueFormat={(v) => formatNumber(v)}
                  />
                </div>
              ))}
            </div>
          ) : (
            <div className="small faint">No label columns detected.</div>
          )}
        </Panel>
      </div>

      {/* ---- missing values ---- */}
      <Panel title="Missing values" hint={missingTop.length ? 'top 12 columns' : 'complete dataset'}>
        {missingTop.length && missingTop.some(([, v]) => v > 0) ? (
          <BarChart
            data={missingTop
              .filter(([, v]) => v > 0)
              .map(([label, value]) => ({ label, value, color: '#4a93a4' }))}
            valueFormat={(v) => formatNumber(v)}
          />
        ) : (
          <div className="notice ok"><CheckCircle2 size={15} /> No missing values detected.</div>
        )}
      </Panel>

      {/* ---- manual column mapping ---- */}
      <Panel
        title="Column mapping"
        actions={
          <span className="flex">
            {mapSaved && <span className="badge green">Saved</span>}
            <button className="btn btn-sm btn-primary" onClick={saveMapping} disabled={mapSaving}>
              <Columns3 size={13} /> {mapSaving ? 'Saving...' : 'Save mapping'}
            </button>
          </span>
        }
      >
        <p className="small muted mb-16">
          Columns were detected automatically. Override any mapping if detection failed, then save, 
          profiling and all analysis engines will use your mapping.
        </p>
        <div className="grid grid-3">
          {canonicalKeys.map((key) => (
            <label className="field" key={key}>
              <span>{CANONICAL_LABELS[key]}</span>
              <select
                className="select"
                value={mapping[key] || ''}
                onChange={(e) => setMapping({ ...mapping, [key]: e.target.value })}
              >
                <option value="">,  not mapped, </option>
                {(dataset.column_names || []).map((col) => (
                  <option key={col} value={col}>{col}</option>
                ))}
              </select>
            </label>
          ))}
        </div>
      </Panel>

      {/* ---- preprocessing ---- */}
      <Panel title="Preprocessing pipeline" actions={<span className="hint">creates a new dataset version</span>}>
        <div className="grid grid-2">
          <div className="stack">
            {OPTIONS.map(([key, label]) => (
              <label className="checkbox-row" key={key}>
                <input
                  type="checkbox"
                  checked={!!options[key]}
                  onChange={(e) => setOptions({ ...options, [key]: e.target.checked })}
                />
                {label}
              </label>
            ))}
          </div>
          <div className="stack">
            {TEXT_OPTIONS.map(([key, label, choices]) => (
              <label className="field" key={key}>
                <span>{label}</span>
                <select
                  className="select"
                  value={options[key]}
                  onChange={(e) => setOptions({ ...options, [key]: e.target.value })}
                >
                  {choices.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </label>
            ))}
            <button className="btn btn-primary" onClick={runPreprocess} disabled={prep.running}>
              <Play size={14} /> {prep.running ? 'Running pipeline...' : 'Run preprocessing'}
            </button>
          </div>
        </div>

        {prep.running && <div className="mt-16"><Spinner label="Preprocessing..." /></div>}
        {prep.error && <div className="mt-16"><ErrorNotice error={prep.error} /></div>}
        {prep.result && (
          <div className="notice ok mt-16">
            <CheckCircle2 size={15} />
            <div>
              <div>
                Created <strong>v{prep.result.report.version}</strong> dataset{' '}
                <Link to={`/datasets/${prep.result.dataset.id}`}>
                  <code className="mono">{prep.result.dataset.id}</code>
                </Link>{' '}
              , {formatNumber(prep.result.report.input_records)} →{' '}
                {formatNumber(prep.result.report.output_records)} records.
              </div>
              <div className="small mt-8">
                Steps: {prep.result.report.steps.map((s) => s.step).join(' → ')}
              </div>
            </div>
          </div>
        )}
      </Panel>
    </>
  )
}

function Stat({ label, value }) {
  return (
    <div className="metric">
      <div className="m-label">{label}</div>
      <div className="m-value">{value}</div>
    </div>
  )
}
