import { useState } from 'react'
import { FileText, FilePlus2, Download, Eye } from '../components/icons'
import Panel from '../components/Panel'
import DatasetPicker from '../components/DatasetPicker'
import DetailDrawer from '../components/DetailDrawer'
import { EmptyState, ErrorNotice, Spinner } from '../components/Status'
import { useAsync } from '../hooks/useApi'
import { useDatasets } from '../hooks/useDatasets'
import apiClient from '../services/api'
import { formatDateTime } from '../utils/format'

const CLASS_META = {
  OBSERVED: { cls: 'observed', label: 'Observed data' },
  'MODEL OUTPUT': { cls: 'model', label: 'Model output' },
  INFERENCE: { cls: 'inference', label: 'Statistical inference' },
  HUMAN: { cls: 'human', label: 'Human interpretation required' },
}

export default function ReportsPage() {
  const { datasets, selectedId, setSelectedId, loading: dsLoading } = useDatasets()
  const [title, setTitle] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState(null)
  const [viewing, setViewing] = useState(null)
  const [viewLoading, setViewLoading] = useState(false)

  const { data, loading, error, execute } = useAsync(() => apiClient.reports(), [])

  const create = async () => {
    setCreating(true)
    setCreateError(null)
    try {
      const report = await apiClient.createReport({
        dataset_id: selectedId || null,
        title: title || null,
      })
      setTitle('')
      setViewing(report)
      execute()
    } catch (err) {
      setCreateError(err)
    } finally {
      setCreating(false)
    }
  }

  const openReport = async (summary) => {
    setViewLoading(true)
    try {
      const full = await apiClient.getReport(summary.id)
      setViewing(full)
    } catch (err) {
      setCreateError(err)
    } finally {
      setViewLoading(false)
    }
  }

  const download = (report) => {
    const blob = new Blob([report.markdown || ''], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${(report.title || 'report').replace(/[^\w\- ]+/g, '_')}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Intelligence Reports</h1>
          <p className="page-subtitle">
            Automated reports that separate <strong>observed data</strong>,{' '}
            <strong>model output</strong>, <strong>statistical inference</strong> and{' '}
            <strong>human interpretation</strong>. No unsupported accusations are generated.
          </p>
        </div>
      </div>

      <Panel title="Generate report">
        <div className="filters">
          <label className="field" style={{ flex: 1, minWidth: 240 }}>
            <span>Title (optional)</span>
            <input
              className="input"
              placeholder="e.g. Weekly platform audit"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <DatasetPicker datasets={datasets} value={selectedId} onChange={setSelectedId} loading={dsLoading} />
          <button className="btn btn-primary" onClick={create} disabled={creating}>
            <FilePlus2 size={14} /> {creating ? 'Generating...' : 'Generate'}
          </button>
        </div>
        <div className="small faint mt-16">
          Sections include executive summary, dataset info, evidence integrity, statistics,
          sentiment, topics, automated-account analysis, misinformation model results, network
          analysis, patterns, model performance, limitations and the full audit trail.
        </div>
        {createError && <div className="mt-16"><ErrorNotice error={createError} /></div>}
      </Panel>

      <Panel title={`Reports (${data?.total ?? 0})`}>
        {loading ? (
          <Spinner label="Loading reports..." />
        ) : error ? (
          <ErrorNotice error={error} onRetry={execute} />
        ) : !data?.items?.length ? (
          <EmptyState
            title="No reports yet"
            message="Generate your first report above, it will be stored with its full section structure and markdown export."
          />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Dataset</th>
                  <th>Sections</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => (
                  <tr key={r.id} onClick={() => openReport(r)}>
                    <td><FileText size={13} style={{ verticalAlign: -2, marginRight: 7, color: 'var(--accent)' }} />{r.title}</td>
                    <td className="cell-mono small">{r.dataset_id || ', '}</td>
                    <td className="cell-dim small">{r.sections?.length || 0} sections</td>
                    <td className="cell-dim small">{formatDateTime(r.created_at)}</td>
                    <td>
                      <div className="flex" style={{ gap: 6, justifyContent: 'flex-end' }}>
                        <button className="btn btn-sm" onClick={(e) => { e.stopPropagation(); openReport(r) }}>
                          <Eye size={13} /> View
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <DetailDrawer
        open={!!viewing}
        title={viewing?.title || ''}
        subtitle={viewing ? `Generated ${formatDateTime(viewing.created_at)}` : ''}
        onClose={() => setViewing(null)}
      >
        {viewLoading && <Spinner label="Loading report..." />}
        {viewing?.content && (
          <>
            <button
              className="btn btn-sm mb-16"
              onClick={() => download(viewing)}
              disabled={!viewing.markdown}
            >
              <Download size={13} /> Download Markdown
            </button>

            {Object.entries(viewing.content).map(([key, section]) => {
              const meta = CLASS_META[section.evidence_class] || { cls: 'observed', label: section.evidence_class }
              return (
                <div className="report-section" key={key}>
                  <div className="flex-between">
                    <h4>{section.title}</h4>
                    <span className={`evidence-class ${meta.cls}`}>{meta.label}</span>
                  </div>
                  <ReportBody body={section.body} />
                </div>
              )
            })}
          </>
        )}
      </DetailDrawer>
    </>
  )
}

function ReportBody({ body }) {
  if (typeof body === 'string') return <p className="small muted mt-8">{body}</p>
  if (Array.isArray(body)) {
    if (typeof body[0] === 'object' && body[0] !== null) {
      return (
        <div className="stack small muted mt-8" style={{ gap: 6 }}>
          {body.slice(0, 12).map((item, i) => (
            <div key={i} className="mono" style={{ fontSize: 11.5 }}>
              {JSON.stringify(item).slice(0, 220)}
            </div>
          ))}
        </div>
      )
    }
    return (
      <ul className="small muted mt-8" style={{ paddingLeft: 18 }}>
        {body.map((item, i) => <li key={i} style={{ marginBottom: 4 }}>{String(item)}</li>)}
      </ul>
    )
  }
  if (body && typeof body === 'object') {
    if (body.error) return <p className="small mt-8" style={{ color: 'var(--bad)' }}>{body.error}</p>
    if (body.status) return <p className="small muted mt-8">{body.status}</p>
    return (
      <dl className="kv mt-8" style={{ gridTemplateColumns: '130px 1fr' }}>
        {Object.entries(body).slice(0, 16).map(([k, v]) => (
          <div key={k} style={{ display: 'contents' }}>
            <dt>{String(k).replace(/_/g, ' ')}</dt>
            <dd className="small">
              {typeof v === 'object'
                ? JSON.stringify(v).slice(0, 300)
                : String(v)}
            </dd>
          </div>
        ))}
      </dl>
    )
  }
  return null
}
