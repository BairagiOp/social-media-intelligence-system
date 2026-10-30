import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Globe, Link2, Rss, Search, Plus, X, ShieldCheck, Loader } from './icons'
import { ErrorNotice } from './Status'
import apiClient from '../services/api'

const TABS = [
  { id: 'fetch', label: 'Fetch a file', icon: Link2 },
  { id: 'collect', label: 'Platform source', icon: Rss },
  { id: 'crawl', label: 'Crawl a page', icon: Globe },
]

const EMPTY_FIELDS = [
  { name: 'headline', selector: 'h2' },
  { name: 'text', selector: 'p' },
]

/**
 * Web collection: fetch a public dataset file, pull from an official platform
 * API, or crawl a page with CSS selectors. Everything lands in the normal
 * immutable ingest, so it gets a SHA-256 hash and an EV- evidence id.
 */
export default function CollectPanel({ onCollected }) {
  const [policy, setPolicy] = useState(null)
  const [sources, setSources] = useState([])
  const [tab, setTab] = useState('fetch')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const [url, setUrl] = useState('')
  const [datasetName, setDatasetName] = useState('')
  const [license, setLicense] = useState('')

  const [sourceId, setSourceId] = useState('')
  const [params, setParams] = useState({})

  const [crawlUrl, setCrawlUrl] = useState('')
  const [fields, setFields] = useState(EMPTY_FIELDS)
  const [maxPages, setMaxPages] = useState(5)
  const [maxDepth, setMaxDepth] = useState(1)

  useEffect(() => {
    let alive = true
    apiClient
      .sources()
      .then((data) => {
        if (!alive) return
        setPolicy(data.policy || null)
        setSources(data.sources || [])
        if (data.sources?.length && !sourceId) setSourceId(data.sources[0].id)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const run = async (fn) => {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const data = await fn()
      setResult(data)
      onCollected?.(data)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  const submitFetch = () =>
    run(() =>
      apiClient.fetchDataset({
        url: url.trim(),
        name: datasetName.trim() || null,
        license: license.trim() || null,
      })
    )

  const activeSource = sources.find((s) => s.id === sourceId) || null

  const submitCollect = () =>
    run(() =>
      apiClient.collectFrom({
        source: sourceId,
        params,
        name: datasetName.trim() || null,
        license: license.trim() || null,
      })
    )

  const submitCrawl = () =>
    run(() =>
      apiClient.crawlSite({
        url: crawlUrl.trim(),
        name: datasetName.trim() || null,
        license: license.trim() || null,
        fields: fields
          .filter((f) => f.name.trim() && f.selector.trim())
          .map((f) => ({ name: f.name.trim(), selector: f.selector.trim() })),
        max_pages: Number(maxPages),
        max_depth: Number(maxDepth),
      })
    )

  const updateField = (index, key, value) =>
    setFields((rows) => rows.map((row, i) => (i === index ? { ...row, [key]: value } : row)))

  const nameField = (
    <label className="field">
      <span>Dataset name</span>
      <input
        className="input"
        type="text"
        placeholder="Optional"
        value={datasetName}
        onChange={(e) => setDatasetName(e.target.value)}
      />
    </label>
  )

  const licenseField = (
    <label className="field">
      <span>License / provenance note</span>
      <input
        className="input"
        type="text"
        placeholder="e.g. CC-BY-4.0"
        value={license}
        onChange={(e) => setLicense(e.target.value)}
      />
    </label>
  )

  return (
    <div className="panel mb-16">
      <div className="panel-title">
        <span>Collect from the web</span>
        <span className="hint">
          <ShieldCheck size={12} /> public sources only, robots.txt honoured
        </span>
      </div>

      <div className="flex mb-16" style={{ gap: 6, flexWrap: 'wrap' }}>
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`btn btn-sm ${tab === t.id ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => {
              setTab(t.id)
              setError(null)
            }}
            disabled={busy}
          >
            <t.icon size={13} /> {t.label}
          </button>
        ))}
      </div>

      {policy && (
        <div className="notice info mb-16">
          <ShieldCheck size={15} />
          <div className="small">
            <strong>{policy.statement}</strong>
            <div className="faint mt-8">
              {policy.schemes.join(' / ')} only, private &amp; loopback targets{' '}
              {policy.private_targets_blocked ? 'blocked' : 'allowed (unsafe)'},{' '}
              {policy.robots_obeyed ? 'robots.txt obeyed' : 'robots.txt ignored'},{' '}
              {policy.max_mb} MB cap, {policy.timeout_seconds}s timeout,{' '}
              {policy.max_redirects} redirects, {policy.min_interval_seconds}s between
              requests, crawl at most {policy.crawl_max_pages} pages, depth {policy.crawl_max_depth}
              {policy.host_allowlist?.length > 0 && (
                <>, allow-list: {policy.host_allowlist.join(', ')}</>
              )}
              {policy.blocked_domains?.length > 0 && (
                <>
                  {' '}, blanket-blocked (fast-fail):{' '}
                  {policy.blocked_domains.join(', ')}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {policy && policy.enabled === false && (
        <div className="notice warn mb-16">
          Web collection is disabled (<code className="mono">SMDPIS_FETCH_ENABLED=false</code>).
        </div>
      )}

      <ErrorNotice error={error} />

      {result && (
        <div className="notice ok mb-16">
          <Globe size={15} />
          <div style={{ flex: 1 }}>
            {result.message}
            <div className="faint small mt-8">
              {result.dataset?.records?.toLocaleString()} records,{' '}
              {result.dataset?.columns} columns, evidence{' '}
              <span className="mono">{result.dataset?.evidence_id}</span>
            </div>
          </div>
          <Link to="/datasets" className="btn btn-sm">
            Open Dataset Manager →
          </Link>
        </div>
      )}

      {tab === 'fetch' && (
        <div className="stack">
          <p className="small muted">
            Download a CSV, JSON, JSONL or Parquet file from a public URL, for example an
            open-data portal export. The bytes are stored immutably and hashed before parsing.
          </p>
          <label className="field">
            <span>File URL *</span>
            <input
              className="input"
              type="url"
              placeholder="https://example.org/data/posts.csv"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </label>
          <div className="grid grid-2">
            {nameField}
            {licenseField}
          </div>
          <div>
            <button
              className="btn btn-primary"
              onClick={submitFetch}
              disabled={busy || !url.trim()}
            >
              {busy ? <Loader size={14} className="spinner" /> : <Link2 size={14} />}
              {busy ? 'Fetching...' : 'Fetch dataset'}
            </button>
          </div>
        </div>
      )}

      {tab === 'collect' && (
        <div className="stack">
          <p className="small muted">
            Pull records from an official, unauthenticated public API. SMDPIS never logs in and
            never stores credentials.
          </p>
          <div className="grid grid-3">
            {sources.map((s) => (
              <button
                key={s.id}
                className={`btn ${sourceId === s.id ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setSourceId(s.id)}
                disabled={busy}
                style={{ textAlign: 'left' }}
              >
                <Rss size={13} /> {s.label}
              </button>
            ))}
          </div>

          {activeSource && (
            <>
              <p className="small muted">
                {activeSource.description}
                <br />
                <span className="faint mono">{activeSource.endpoint}</span>
              </p>
              <div className="grid grid-3">
                {activeSource.params.map((p) => (
                  <label className="field" key={p.name}>
                    <span>
                      {p.label}
                      {p.required ? ' *' : ''}
                    </span>
                    <input
                      className="input"
                      type={p.type === 'number' ? 'number' : 'text'}
                      placeholder={p.placeholder || ''}
                      value={params[p.name] ?? p.default ?? ''}
                      onChange={(e) =>
                        setParams((s) => ({
                          ...s,
                          [p.name]: p.type === 'number' ? Number(e.target.value) : e.target.value,
                        }))
                      }
                    />
                  </label>
                ))}
              </div>
              <div className="grid grid-2">
                {nameField}
                {licenseField}
              </div>
              <div className="flex" style={{ gap: 8 }}>
                <button
                  className="btn btn-primary"
                  onClick={submitCollect}
                  disabled={busy || !sourceId}
                >
                  {busy ? <Loader size={14} className="spinner" /> : <Search size={14} />}
                  {busy ? 'Collecting...' : 'Collect records'}
                </button>
              </div>
              <div className="small faint">{activeSource.license_note}</div>
            </>
          )}
        </div>
      )}

      {tab === 'crawl' && (
        <div className="stack">
          <p className="small muted">
            Breadth-first crawl that stays on the start page's domain, honours robots.txt and
            extracts only the fields you name. Selector syntax: <code className="mono">tag</code>,{' '}
            <code className="mono">.class</code>, <code className="mono">#id</code>,{' '}
            <code className="mono">[attr]</code>, <code className="mono">tag.class</code>,{' '}
            descendants and <code className="mono">&gt;</code>.
          </p>

          <label className="field">
            <span>Start URL *</span>
            <input
              className="input"
              type="url"
              placeholder="https://blog.example.org/"
              value={crawlUrl}
              onChange={(e) => setCrawlUrl(e.target.value)}
            />
          </label>

          <div>
            <div
              className="faint"
              style={{ fontSize: 10, letterSpacing: '.1em', textTransform: 'uppercase' }}
            >
              Fields to extract
            </div>
            {fields.map((row, i) => (
              <div className="flex mt-8" style={{ gap: 8 }} key={i}>
                <input
                  className="input"
                  placeholder="column name (e.g. headline)"
                  value={row.name}
                  onChange={(e) => updateField(i, 'name', e.target.value)}
                  style={{ maxWidth: 220 }}
                />
                <input
                  className="input"
                  placeholder="selector (e.g. article h2)"
                  value={row.selector}
                  onChange={(e) => updateField(i, 'selector', e.target.value)}
                />
                <button
                  className="btn btn-sm btn-ghost"
                  title="Remove field"
                  onClick={() => setFields((rows) => rows.filter((_, x) => x !== i))}
                  disabled={fields.length === 1}
                >
                  <X size={13} />
                </button>
              </div>
            ))}
            <button
              className="btn btn-sm btn-ghost mt-8"
              onClick={() => setFields((rows) => [...rows, { name: '', selector: '' }])}
              disabled={fields.length >= 20}
            >
              <Plus size={13} /> Add field
            </button>
            <div className="small faint mt-8">
              A <code className="mono">text</code> column is added automatically if none is
              defined, so sentiment and topic analysis work on the result.
            </div>
          </div>

          <div className="grid grid-3">
            <label className="field">
              <span>Max pages</span>
              <input
                className="input"
                type="number"
                min={1}
                max={200}
                value={maxPages}
                onChange={(e) => setMaxPages(e.target.value)}
              />
            </label>
            <label className="field">
              <span>Max depth</span>
              <input
                className="input"
                type="number"
                min={0}
                max={10}
                value={maxDepth}
                onChange={(e) => setMaxDepth(e.target.value)}
              />
            </label>
            <div />
          </div>

          <div className="grid grid-2">
            {nameField}
            {licenseField}
          </div>

          <div>
            <button
              className="btn btn-primary"
              onClick={submitCrawl}
              disabled={busy || !crawlUrl.trim()}
            >
              {busy ? <Loader size={14} className="spinner" /> : <Globe size={14} />}
              {busy ? 'Crawling...' : 'Start crawl'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
