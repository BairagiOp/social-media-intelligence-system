import { useId, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Plus } from './icons'

/** Shared dataset selector used by the analysis pages. */
export default function DatasetPicker({ datasets, value, onChange, loading }) {
  const selectId = useId()
  const options = useMemo(
    () => (datasets || []).filter((d) => d.status !== 'DELETED'),
    [datasets]
  )

  if (loading) return <span className="small faint">Loading datasets...</span>

  if (!options.length) {
    return (
      <div className="flex small">
        <span className="muted">No dataset loaded.</span>
        <Link to="/datasets" className="btn btn-sm">
          <Plus size={13} /> Load a dataset
        </Link>
      </div>
    )
  }

  return (
    <label className="field dataset-picker" htmlFor={selectId}>
      <span>Dataset</span>
      <select
        id={selectId}
        className="select"
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
      >
        {!value && <option value="">Select a dataset</option>}
        {options.map((d) => (
          <option key={d.id} value={d.id}>
            {d.name}, {d.records.toLocaleString()} records, v{d.version}, {d.status}
          </option>
        ))}
      </select>
    </label>
  )
}
