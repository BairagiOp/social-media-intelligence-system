import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Search, ChevronLeft, ChevronRight, ShieldCheck, Activity } from '../components/icons'
import Panel from '../components/Panel'
import DetailDrawer from '../components/DetailDrawer'
import DatasetPicker from '../components/DatasetPicker'
import { EmptyState, ErrorNotice, SkeletonTable } from '../components/Status'
import { useDatasets } from '../hooks/useDatasets'
import apiClient from '../services/api'
import { formatDate, formatDateTime, formatNumber } from '../utils/format'

const PAGE_SIZE = 50

export default function ExplorerPage() {
  const { datasets, selectedId, setSelectedId, loading: dsLoading } = useDatasets()
  const [params, setParams] = useSearchParams()

  const [rows, setRows] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)
  const [rowSentiment, setRowSentiment] = useState(null)

  const [query, setQuery] = useState({
    search: '',
    platform: '',
    username: '',
    sentiment: '',
    classification: '',
    date_from: '',
    date_to: '',
    sort_by: '',
    sort_order: 'asc',
    page: 1,
    page_size: PAGE_SIZE,
  })

  useEffect(() => {
    const ds = params.get('dataset')
    if (ds && ds !== selectedId) setSelectedId(ds)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params])

  useEffect(() => {
    if (selectedId) setParams({ dataset: selectedId }, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId])

  const fetchRows = useCallback(async () => {
    if (!selectedId) return
    setLoading(true)
    setError(null)
    try {
      const clean = Object.fromEntries(
        Object.entries(query).filter(([, v]) => v !== '' && v !== null)
      )
      const data = await apiClient.queryRows(selectedId, clean)
      setRows(data)
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [selectedId, query])

  useEffect(() => {
    fetchRows()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, query])

  const update = (patch) => setQuery((q) => ({ ...q, ...patch, page: patch.page ?? 1 }))

  const toggleSort = (col) => {
    setQuery((q) => ({
      ...q,
      sort_by: col,
      sort_order: q.sort_by === col && q.sort_order === 'asc' ? 'desc' : 'asc',
      page: 1,
    }))
  }

  const selectedDataset = useMemo(
    () => datasets.find((d) => d.id === selectedId),
    [datasets, selectedId]
  )

  // live sentiment for the open drawer row (computed by the backend)
  useEffect(() => {
    if (!selected?.text) {
      setRowSentiment(null)
      return
    }
    let alive = true
    apiClient
      .inference({ task: 'sentiment', texts: [selected.text] })
      .then((res) => {
        if (alive) setRowSentiment(res.items?.[0] || null)
      })
      .catch(() => alive && setRowSentiment(null))
    return () => { alive = false }
  }, [selected])

  const platforms = selectedDataset?.profile?.platform_distribution
    ? Object.keys(selectedDataset.profile.platform_distribution)
    : []

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Data Explorer</h1>
          <p className="page-subtitle">
            Search, filter, sort and inspect individual records. Click any row to open its
            analysis drawer.
          </p>
        </div>
        <div className="page-actions">
          <DatasetPicker
            datasets={datasets}
            value={selectedId}
            onChange={setSelectedId}
            loading={dsLoading}
          />
        </div>
      </div>

      {!selectedId ? (
        <EmptyState
          title="Select a dataset"
          message="Upload or load a dataset first to explore its records."
        />
      ) : (
        <Panel title="Filters">
          <div className="filters">
            <label className="field" style={{ flex: 2, minWidth: 220 }}>
              <span>Search text</span>
              <div className="flex">
                <Search size={14} className="faint" />
                <input
                  className="input"
                  style={{ width: '100%' }}
                  placeholder="keyword, @handle, url..."
                  value={query.search}
                  onChange={(e) => update({ search: e.target.value })}
                />
              </div>
            </label>

            <label className="field">
              <span>Platform</span>
              <select className="select" value={query.platform} onChange={(e) => update({ platform: e.target.value })}>
                <option value="">All</option>
                {platforms.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>

            <label className="field">
              <span>User</span>
              <input
                className="input"
                placeholder="username"
                value={query.username}
                onChange={(e) => update({ username: e.target.value })}
              />
            </label>

            <label className="field">
              <span>Sentiment</span>
              <select className="select" value={query.sentiment} onChange={(e) => update({ sentiment: e.target.value })}>
                <option value="">All</option>
                <option value="positive">Positive</option>
                <option value="neutral">Neutral</option>
                <option value="negative">Negative</option>
              </select>
            </label>

            <label className="field">
              <span>Classification</span>
              <select className="select" value={query.classification} onChange={(e) => update({ classification: e.target.value })}>
                <option value="">All</option>
                <option value="MODEL_FLAGGED">Model flagged</option>
                <option value="NOT_FLAGGED">Not flagged</option>
              </select>
            </label>

            <label className="field">
              <span>From</span>
              <input className="input" type="date" value={query.date_from}
                onChange={(e) => update({ date_from: e.target.value })} />
            </label>
            <label className="field">
              <span>To</span>
              <input className="input" type="date" value={query.date_to}
                onChange={(e) => update({ date_to: e.target.value })} />
            </label>

            <button
              className="btn btn-ghost"
              onClick={() =>
                setQuery({
                  search: '', platform: '', username: '', sentiment: '',
                  classification: '', date_from: '', date_to: '',
                  sort_by: '', sort_order: 'asc', page: 1, page_size: PAGE_SIZE,
                })
              }
            >
              Reset
            </button>
          </div>
        </Panel>
      )}

      {selectedId && (
        <Panel
          title={`Records${rows ? `, ${formatNumber(rows.total_filtered)} of ${formatNumber(rows.total)}` : ''}`}
          actions={loading ? <span className="hint">Loading...</span> : <span className="hint">click a row for details</span>}
        >
          {error ? (
            <ErrorNotice error={error} onRetry={fetchRows} />
          ) : !rows ? (
            <SkeletonTable rows={8} columns={6} label="Loading records" />
          ) : !rows.items.length ? (
            <EmptyState title="No matching records" message="Adjust your filters or search terms." />
          ) : (
            <>
              <div className="table-wrap" style={{ maxHeight: '58vh' }}>
                <table className="data">
                  <thead>
                    <tr>
                      {['timestamp', 'username', 'platform', 'text', 'label', 'likes', 'comments', 'shares'].map((col) => (
                        <th key={col} onClick={() => toggleSort(col)}>
                          {col.replace('_', ' ')}
                          {query.sort_by === col && (
                            <span style={{ color: 'var(--accent)' }}> {query.sort_order === 'asc' ? 'â†‘' : 'â†“'}</span>
                          )}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.items.map((row, i) => (
                      <tr key={row.post_id || i} onClick={() => setSelected(row)}>
                        <td className="cell-mono cell-dim">{formatDateTime(row.timestamp) || ', '}</td>
                        <td>{row.username || row.user_id || ', '}</td>
                        <td><span className="badge gray">{row.platform || ', '}</span></td>
                        <td className="cell-wrap">{row.text || row.text_clean || ', '}</td>
                        <td>
                          {row.label ? (
                            <span
                              className={`badge ${
                                row.label === 'positive' ? 'green' : row.label === 'negative' ? 'red' : 'gray'
                              }`}
                            >
                              {row.label}
                            </span>
                          ) : ', '}
                        </td>
                        <td className="cell-mono">{formatNumber(row.likes)}</td>
                        <td className="cell-mono">{formatNumber(row.comments)}</td>
                        <td className="cell-mono">{formatNumber(row.shares)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="table-footer">
                <span className="pager-info">
                  Page {rows.page} of {rows.pages}, {formatNumber(rows.total)} total records
                </span>
                <div className="pager">
                  <button
                    className="btn btn-sm"
                    disabled={rows.page <= 1}
                    onClick={() => update({ page: rows.page - 1 })}
                  >
                    <ChevronLeft size={13} /> Prev
                  </button>
                  <span className="pager-info">{rows.page}</span>
                  <button
                    className="btn btn-sm"
                    disabled={rows.page >= rows.pages}
                    onClick={() => update({ page: rows.page + 1 })}
                  >
                    Next <ChevronRight size={13} />
                  </button>
                </div>
              </div>
            </>
          )}
        </Panel>
      )}

      <DetailDrawer
        open={!!selected}
        title="Record detail"
        subtitle={selected?.post_id || ''}
        onClose={() => { setSelected(null); setRowSentiment(null) }}
      >
        {selected && (
          <>
            <div className="section-divider" style={{ marginTop: 6 }}>Post</div>
            <p style={{ fontSize: 13.5, whiteSpace: 'pre-wrap' }}>{selected.text || selected.text_clean}</p>
            {selected.text_clean && selected.text_clean !== selected.text && (
              <>
                <div className="section-divider">Cleaned text</div>
                <p className="small muted" style={{ whiteSpace: 'pre-wrap' }}>{selected.text_clean}</p>
              </>
            )}

            <div className="section-divider">Context</div>
            <dl className="kv">
              <dt>User</dt><dd>{selected.username || selected.user_id || ', '}</dd>
              <dt>Platform</dt><dd>{selected.platform || ', '}</dd>
              <dt>Timestamp</dt><dd>{formatDateTime(selected.timestamp) || ', '}</dd>
              <dt>Headline</dt><dd>{selected.headline || ', '}</dd>
              <dt>Domain</dt><dd>{selected.domain || ', '}</dd>
              <dt>URL</dt><dd>{selected.url ? <a href={selected.url} target="_blank" rel="noreferrer noopener">{selected.url}</a> : ', '}</dd>
              <dt>Language</dt><dd>{selected.language || ', '}</dd>
            </dl>

            <div className="section-divider">Sentiment</div>
            {rowSentiment ? (
              <div className="metric-row">
                <div className="metric">
                  <div className="m-label">Classification</div>
                  <div className="m-value" style={{ fontSize: 15 }}>{rowSentiment.model_classification}</div>
                </div>
                <div className="metric">
                  <div className="m-label">Compound</div>
                  <div className="m-value" style={{ fontSize: 15 }}>{rowSentiment.scores.compound.toFixed(3)}</div>
                </div>
                <div className="metric">
                  <div className="m-label">Pos / Neu / Neg</div>
                  <div className="m-value" style={{ fontSize: 13 }}>
                    {rowSentiment.scores.pos.toFixed(2)} / {rowSentiment.scores.neu.toFixed(2)} / {rowSentiment.scores.neg.toFixed(2)}
                  </div>
                </div>
              </div>
            ) : (
              <div className="small faint"><Activity size={12} /> Computing...</div>
            )}
            <p className="small faint mt-8">Tone of text only, not evidence of intent.</p>

            <div className="section-divider">Model classifications</div>
            <dl className="kv">
              <dt>Dataset label</dt><dd>{selected.label || ', '}</dd>
              <dt>Misinfo label</dt><dd>{selected.misinfo_label ?? ', '}</dd>
              <dt>Automation label</dt><dd>{selected.is_automated ?? ', '}</dd>
              {selected.model_classification && (
                <>
                  <dt>Model output</dt><dd>{selected.model_classification}</dd>
                </>
              )}
            </dl>

            <div className="section-divider">Engagement</div>
            <dl className="kv">
              <dt>Likes</dt><dd>{formatNumber(selected.likes)}</dd>
              <dt>Comments</dt><dd>{formatNumber(selected.comments)}</dd>
              <dt>Shares</dt><dd>{formatNumber(selected.shares)}</dd>
              <dt>Engagement score</dt><dd>{formatNumber(selected.engagement_score)}</dd>
              <dt>Followers</dt><dd>{formatNumber(selected.followers)}</dd>
              <dt>Following</dt><dd>{formatNumber(selected.following)}</dd>
              <dt>Account age</dt><dd>{selected.account_age ?? ', '} days</dd>
            </dl>

            <div className="section-divider">Evidence reference</div>
            <div className="notice info">
              <ShieldCheck size={15} />
              <div>
                <div>Evidence: <span className="mono">{selectedDataset?.evidence_id || ', '}</span></div>
                <div className="small faint mt-8">
                  Source file stored read-only with SHA-256 verification.
                </div>
              </div>
            </div>

            <div className="section-divider">Audit</div>
            <div className="small faint">
              Created {formatDate(selectedDataset?.created_at)}, dataset v{selectedDataset?.version},{' '}
              {selectedDataset?.status}
            </div>
          </>
        )}
      </DetailDrawer>
    </>
  )
}
