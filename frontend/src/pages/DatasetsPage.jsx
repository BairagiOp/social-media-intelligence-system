import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Upload, FlaskConical, Trash2, ChevronRight, Radar, FileSpreadsheet,
} from '../components/icons'
import Panel from '../components/Panel'
import { ErrorNotice, EmptyState, Spinner } from '../components/Status'
import { useDatasets } from '../hooks/useDatasets'
import apiClient from '../services/api'
import { formatDate, formatNumber } from '../utils/format'

const STATUS_BADGE = {
  UPLOADED: 'blue',
  VALIDATED: 'cyan',
  PREPROCESSED: 'green',
  DELETED: 'red',
  ERROR: 'red',
}

export default function DatasetsPage() {
  const { datasets, loading, error, reload } = useDatasets()
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState(null)
  const [uploadError, setUploadError] = useState(null)
  const [drag, setDrag] = useState(false)
  const fileRef = useRef(null)

  const doUpload = async (file) => {
    if (!file) return
    setUploading(true)
    setUploadError(null)
    setUploadMsg(null)
    try {
      const ds = await apiClient.uploadDataset(file, file.name.replace(/\.[^.]+$/, ''))
      setUploadMsg(`Uploaded ${ds.name}, ${formatNumber(ds.records)} records profiled.`)
      await reload()
    } catch (err) {
      setUploadError(err)
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const loadSample = async () => {
    setUploading(true)
    setUploadError(null)
    try {
      const res = await apiClient.loadSample()
      setUploadMsg(`Sample dataset ready: ${res.dataset.name} (${formatNumber(res.dataset.records)} records).`)
      await reload()
    } catch (err) {
      setUploadError(err)
    } finally {
      setUploading(false)
    }
  }

  const remove = async (id) => {
    if (!window.confirm('Mark this dataset as deleted? Evidence and audit history are preserved.')) return
    try {
      await apiClient.deleteDataset(id)
      await reload()
    } catch (err) {
      setUploadError(err)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Dataset Manager</h1>
          <p className="page-subtitle">
            Upload CSV / JSON / JSONL / Parquet files or load the bundled synthetic sample.
            Every upload is hashed (SHA-256), validated and auto-profiled.
          </p>
        </div>
        <div className="page-actions">
          <Link to="/datasets/discovery" className="btn btn-ghost">
            <Radar size={14} /> Find public datasets
          </Link>
        </div>
      </div>

      <ErrorNotice error={uploadError} onRetry={() => setUploadError(null)} />
      {uploadMsg && <div className="notice ok mb-16"><FileSpreadsheet size={15} /> {uploadMsg}</div>}

      <Panel title="Add data">
        <div
          className={`dropzone ${drag ? 'drag' : ''}`}
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDrag(false)
            doUpload(e.dataTransfer.files?.[0])
          }}
        >
          <Upload size={22} style={{ marginBottom: 8 }} />
          <div style={{ fontWeight: 600 }}>Drop a dataset here or click to browse</div>
          <div className="small faint mt-8">CSV, JSON, JSONL, Parquet, max 50 MB</div>
          {uploading && <div className="mt-8"><Spinner label="Uploading & profiling..." /></div>}
        </div>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,.json,.jsonl,.parquet"
          aria-label="Choose a dataset file to upload"
          style={{ display: 'none' }}
          onChange={(e) => doUpload(e.target.files?.[0])}
        />
        <div className="flex mt-16">
          <button className="btn" onClick={loadSample} disabled={uploading}>
            <FlaskConical size={14} /> Load included sample dataset
          </button>
          <span className="small faint">10,000 synthetic records, 1,000 accounts, ML labels</span>
        </div>
      </Panel>

      <Panel
        title={`Registered datasets (${datasets.length})`}
        hint="click a row to open its profile"
      >
        {loading ? (
          <Spinner label="Loading datasets..." />
        ) : error ? (
          <ErrorNotice error={error} onRetry={reload} />
        ) : !datasets.length ? (
          <EmptyState
            title="No datasets yet"
            message="Upload your own file or load the synthetic sample to explore the full pipeline."
            action={<button className="btn btn-primary" onClick={loadSample}>Load sample dataset</button>}
          />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Format</th>
                  <th>Records</th>
                  <th>Columns</th>
                  <th>Version</th>
                  <th>Status</th>
                  <th>Evidence</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {datasets.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <Link to={`/datasets/${d.id}`} style={{ fontWeight: 600 }}>
                        {d.name}
                      </Link>
                      <div className="small faint mono">{d.id}</div>
                    </td>
                    <td><span className="badge gray">{d.format}</span></td>
                    <td className="cell-mono">{formatNumber(d.records)}</td>
                    <td className="cell-mono">{d.columns}</td>
                    <td className="cell-mono">v{d.version}</td>
                    <td>
                      <span className={`badge ${STATUS_BADGE[d.status] || 'gray'}`}>
                        {d.status}
                      </span>
                    </td>
                    <td className="cell-mono small">{d.evidence_id || ', '}</td>
                    <td className="cell-dim small">{formatDate(d.created_at)}</td>
                    <td>
                      <div className="flex" style={{ gap: 6, justifyContent: 'flex-end' }}>
                        <Link className="btn btn-sm" to={`/datasets/${d.id}`}>
                          Profile <ChevronRight size={13} />
                        </Link>
                        <button
                          className="btn btn-sm btn-danger"
                          onClick={() => remove(d.id)}
                          title="Soft delete (evidence preserved)"
                        >
                          <Trash2 size={13} />
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
    </>
  )
}
