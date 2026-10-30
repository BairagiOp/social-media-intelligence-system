import { ShieldCheck, Server, KeyRound, Database, ExternalLink } from '../components/icons'
import Panel from '../components/Panel'
import { ErrorNotice, Spinner } from '../components/Status'
import { useAsync, useHealth } from '../hooks/useApi'
import apiClient from '../services/api'

export default function SettingsPage() {
  const { data: meta, loading, error, execute } = useAsync(() => apiClient.meta(), [])
  const { health } = useHealth(20000)

  if (loading && !meta) return <Spinner label="Loading settings..." />
  if (error) return <ErrorNotice error={error} onRetry={execute} />

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Settings & System</h1>
          <p className="page-subtitle">
            Runtime configuration exposed by the backend, API reference, and security posture.
            All secrets come from environment variables, nothing is hard-coded.
          </p>
        </div>
        <div className="page-actions">
          <a className="btn" href="/api/docs" target="_blank" rel="noreferrer noopener">
            <ExternalLink size={14} /> OpenAPI docs
          </a>
        </div>
      </div>

      <div className="grid grid-2">
        <Panel title="Application" actions={<Server size={14} />}>
          <dl className="kv">
            <dt>Name</dt><dd>SMDPIS, Social Media Data Parser &amp; Intelligence System</dd>
            <dt>Version</dt><dd className="mono">{health?.version || ', '}</dd>
            <dt>Environment</dt><dd>{health?.environment || ', '}</dd>
            <dt>API status</dt>
            <dd>
              {health ? (
                <span className={`badge ${health.status === 'ok' ? 'green' : 'amber'}`}>
                  {health.status}
                </span>
              ) : ', '}
            </dd>
            <dt>Database</dt><dd className="mono small">{health?.database || ', '}</dd>
            <dt>Bootstrap</dt>
            <dd>
              <span className={`badge ${
                health?.bootstrap?.status === 'READY' ? 'green'
                  : health?.bootstrap?.status === 'DEGRADED' ? 'red' : 'blue'
              }`}>
                {health?.bootstrap?.status || ', '}
              </span>
            </dd>
          </dl>

          {(health?.bootstrap?.steps || []).length > 0 && (
            <>
              <div className="section-divider">Bootstrap steps</div>
              <div className="stack" style={{ gap: 6 }}>
                {health.bootstrap.steps.map((s, i) => (
                  <div key={i} className="flex-between small">
                    <span className="mono">{s.name}</span>
                    <span className={`badge ${s.status === 'DONE' ? 'green' : s.status === 'ERROR' ? 'red' : 'blue'}`}>
                      {s.status}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </Panel>

        <Panel title="Active models" actions={<ShieldCheck size={14} />}>
          <dl className="kv">
            {Object.entries(health?.models || {}).map(([task, modelId]) => (
              <div key={task} style={{ display: 'contents' }}>
                <dt style={{ textTransform: 'capitalize' }}>{task.replace('_', ' ')}</dt>
                <dd className="mono small">
                  {modelId || <span className="badge amber">Model not trained</span>}
                </dd>
              </div>
            ))}
          </dl>
        </Panel>
      </div>

      <div className="grid grid-2 mt-16">
        <Panel title="Upload & storage limits" actions={<Database size={14} />}>
          <dl className="kv">
            <dt>Max upload size</dt><dd>{meta?.max_upload_mb} MB</dd>
            <dt>Allowed types</dt>
            <dd className="flex" style={{ gap: 6, flexWrap: 'wrap' }}>
              {(meta?.allowed_extensions || []).map((e) => (
                <span className="badge gray" key={e}>{e}</span>
              ))}
            </dd>
            <dt>Sample data</dt><dd>10,000 synthetic records, 1,000 accounts</dd>
            <dt>IP handling</dt>
            <dd>
              <span className="badge cyan">auto-hashed at ingestion</span>{' '}
              <span className="small faint">never exposed in dashboards</span>
            </dd>
          </dl>
        </Panel>

        <Panel title="Security posture" actions={<KeyRound size={14} />}>
          <ul className="small muted" style={{ paddingLeft: 18, lineHeight: 1.9 }}>
            <li>Secrets via environment variables only (<code className="mono">SMDPIS_SECRET_KEY</code>)</li>
            <li>SHA-256 evidence hashing with immutable source files</li>
            <li>HMAC-SHA256 signatures on every audit event</li>
            <li>Extension + size validation on all uploads</li>
            <li>Parameterized SQL via SQLAlchemy ORM (no string-built queries)</li>
            <li>CORS restricted to configured origins</li>
            <li>Generic error messages, internals stay in server logs</li>
            <li>Public/authorized datasets only, no authenticated scraping</li>
          </ul>
        </Panel>
      </div>

      <Panel title="ML tasks exposed by this backend" className="mt-16">
        <div className="stack">
          {Object.entries(meta?.tasks || {}).map(([id, t]) => (
            <div className="toplist-item" key={id}>
              <div>
                <strong>{t.label}</strong>
                <div className="small faint">
                  targets: {(t.target_candidates || [', ']).join(', ')}
                  {t.feature_candidates && <>, {t.feature_candidates.length} feature candidates</>}
                </div>
              </div>
              <div className="flex" style={{ gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                {(t.models || []).map((m) => (
                  <span className="badge gray" key={m.id}>{m.id}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Panel>
    </>
  )
}
