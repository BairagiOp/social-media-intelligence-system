import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ShieldCheck, FileDown, History, CheckCircle2, XCircle } from '../components/icons'
import Panel from '../components/Panel'
import DetailDrawer from '../components/DetailDrawer'
import { EmptyState, ErrorNotice, Spinner } from '../components/Status'
import { useAsync } from '../hooks/useApi'
import apiClient from '../services/api'
import { formatBytes, formatDateTime, shortHash } from '../utils/format'

export default function EvidencePage() {
  const { data, loading, error, execute } = useAsync(() => apiClient.listEvidence(), [])
  const [drawer, setDrawer] = useState(null) // { evidence, audit }
  const [auditLoading, setAuditLoading] = useState(false)
  const [auditError, setAuditError] = useState(null)

  const openEvidence = async (ev) => {
    setDrawer({ evidence: ev, audit: null })
    setAuditLoading(true)
    setAuditError(null)
    try {
      const audit = await apiClient.auditLog(ev.evidence_id)
      setDrawer({ evidence: ev, audit })
    } catch (err) {
      setAuditError(err)
    } finally {
      setAuditLoading(false)
    }
  }

  const exportReport = async (ev) => {
    try {
      const report = await apiClient.exportEvidence(ev.evidence_id)
      const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${ev.evidence_id}_report.json`
      a.click()
      URL.revokeObjectURL(url)
      execute()
    } catch (err) {
      setAuditError(err)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Evidence Management</h1>
          <p className="page-subtitle">
            Chain of custody for every ingested file: SHA-256 hash at intake, append-only
            HMAC-signed audit trail, integrity re-verification on demand. Original files are
            never modified.
          </p>
        </div>
      </div>

      <Panel title={`Evidence items (${data?.total ?? 0})`}>
        {loading ? (
          <Spinner label="Loading evidence..." />
        ) : error ? (
          <ErrorNotice error={error} onRetry={execute} />
        ) : !data?.items?.length ? (
          <EmptyState
            title="No evidence recorded"
            message="Upload a dataset to create the first SHA-256 custody record."
            action={<Link to="/datasets" className="btn btn-primary">Go to Datasets</Link>}
          />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Evidence ID</th>
                  <th>Filename</th>
                  <th>SHA-256</th>
                  <th>Size</th>
                  <th>Status</th>
                  <th>Dataset</th>
                  <th>Uploaded</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((ev) => (
                  <tr key={ev.id} onClick={() => openEvidence(ev)}>
                    <td className="cell-mono" style={{ color: 'var(--accent)' }}>{ev.evidence_id}</td>
                    <td>{ev.filename}</td>
                    <td className="cell-mono small">{shortHash(ev.sha256)}</td>
                    <td className="cell-mono">{formatBytes(ev.size_bytes)}</td>
                    <td>
                      <span className={`badge ${ev.status === 'REJECTED' ? 'red' : 'green'}`}>
                        {ev.status}
                      </span>
                    </td>
                    <td className="cell-mono small">{ev.dataset_id || ', '}</td>
                    <td className="cell-dim small">{formatDateTime(ev.uploaded_at)}</td>
                    <td>
                      <button
                        className="btn btn-sm"
                        onClick={(e) => { e.stopPropagation(); exportReport(ev) }}
                      >
                        <FileDown size={13} /> Export
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <DetailDrawer
        open={!!drawer}
        title={drawer?.evidence?.evidence_id || ''}
        subtitle={drawer?.evidence?.filename}
        onClose={() => setDrawer(null)}
      >
        {drawer && (
          <>
            <div className="section-divider" style={{ marginTop: 6 }}>Custody record</div>
            <dl className="kv">
              <dt>Evidence ID</dt><dd className="mono">{drawer.evidence.evidence_id}</dd>
              <dt>Filename</dt><dd>{drawer.evidence.filename}</dd>
              <dt>Size</dt><dd>{formatBytes(drawer.evidence.size_bytes)}</dd>
              <dt>Status</dt><dd>{drawer.evidence.status}</dd>
              <dt>Dataset</dt>
              <dd>
                {drawer.evidence.dataset_id ? (
                  <Link to={`/datasets/${drawer.evidence.dataset_id}`} className="mono">
                    {drawer.evidence.dataset_id}
                  </Link>
                ) : ', '}
              </dd>
              <dt>Uploaded</dt><dd>{formatDateTime(drawer.evidence.uploaded_at)}</dd>
            </dl>

            <div className="section-divider">SHA-256</div>
            <div className="hash-text">{drawer.evidence.sha256}</div>

            <div className="section-divider">Integrity check</div>
            {auditLoading && <Spinner label="Verifying & loading audit trail..." />}
            {auditError && <ErrorNotice error={auditError} />}
            {drawer.audit && (
              <>
                <div className={`notice ${drawer.audit.integrity.verified ? 'ok' : 'error'}`}>
                  {drawer.audit.integrity.verified ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
                  <div>
                    {drawer.audit.integrity.verified
                      ? 'Hash match, evidence unchanged since intake.'
                      : drawer.audit.integrity.reason || 'Hash mismatch, investigate immediately.'}
                  </div>
                </div>

                <div className="section-divider">
                  <span className="flex"><History size={13} /> Audit trail ({drawer.audit.total})</span>
                </div>
                <div className="stack">
                  {drawer.audit.items.map((e) => (
                    <div className="toplist-item" key={e.id}>
                      <div>
                        <span className={`badge ${
                          e.event === 'HASH' || e.event === 'VALIDATE' ? 'cyan'
                            : e.event === 'MODEL' || e.event === 'ANALYZE' ? 'purple'
                            : e.event === 'DELETE' ? 'red' : 'blue'
                        }`}>
                          {e.event}
                        </span>
                        <div className="small faint mt-8">{formatDateTime(e.created_at)}</div>
                      </div>
                      <div className="small muted" style={{ textAlign: 'right', maxWidth: 240 }}>
                        {Object.entries(e.details || {}).slice(0, 4).map(([k, v]) => (
                          <div key={k}>
                            {k}: <span className="mono">{String(v).slice(0, 60)}</span>
                          </div>
                        ))}
                        <div className="faint mono" style={{ fontSize: 10, marginTop: 4 }}>
                          sig {String(e.signature).slice(0, 18)}...
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="notice info mt-16">
                  <ShieldCheck size={15} />
                  <div className="small">
                    Each audit entry is signed with HMAC-SHA256 using the server secret, so the
                    trail cannot be silently altered.
                  </div>
                </div>
              </>
            )}
          </>
        )}
      </DetailDrawer>
    </>
  )
}
