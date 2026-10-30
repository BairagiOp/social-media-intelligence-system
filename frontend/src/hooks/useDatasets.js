import { useEffect, useMemo, useRef, useState } from 'react'
import apiClient from '../services/api'
import { pickPrimaryDataset } from '../utils/datasets'

/**
 * Shared dataset loader: fetches the dataset list once per mount and keeps
 * a stable "primary" dataset selected unless overridden.
 */
export function useDatasets() {
  const [datasets, setDatasets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)

  const reload = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiClient.listDatasets()
      setDatasets(data.items)
      setSelectedId((current) => {
        if (current && data.items.some((d) => d.id === current)) return current
        return pickPrimaryDataset(data.items)?.id || null
      })
      return data.items
    } catch (err) {
      setError(err)
      return []
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const selected = useMemo(
    () => datasets.find((d) => d.id === selectedId) || null,
    [datasets, selectedId]
  )

  return { datasets, selected, selectedId, setSelectedId, loading, error, reload }
}
