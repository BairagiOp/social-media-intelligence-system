import { useCallback, useEffect, useRef, useState } from 'react'
import apiClient from '../services/api'

/**
 * Generic data-fetching hook with backend-error handling.
 * fn: async () => data ; deps: dependency list
 */
export function useAsync(fn, deps = [], { immediate = true } = {}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(immediate)
  const [error, setError] = useState(null)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const execute = useCallback(async (...args) => {
    setLoading(true)
    setError(null)
    try {
      const result = await fn(...args)
      if (mounted.current) setData(result)
      return result
    } catch (err) {
      if (mounted.current) setError(err)
      return null
    } finally {
      if (mounted.current) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    if (immediate) execute()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [execute, immediate])

  return { data, loading, error, execute, setData }
}

/** Polls /api/health; exposes backend reachability + bootstrap status. */
export function useHealth(pollMs = 15000) {
  const [health, setHealth] = useState(null)
  const [reachable, setReachable] = useState(true)

  useEffect(() => {
    let timer
    let alive = true
    const tick = async () => {
      try {
        const data = await apiClient.health()
        if (!alive) return
        setHealth(data)
        setReachable(true)
      } catch (err) {
        if (!alive) return
        if (err.code === 'backend_unavailable') setReachable(false)
      } finally {
        if (alive) timer = setTimeout(tick, pollMs)
      }
    }
    tick()
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [pollMs])

  return { health, reachable }
}

/** Tracks a training job until it completes or fails. */
export function useTrainingJob() {
  const [job, setJob] = useState(null)
  const timerRef = useRef(null)

  const stop = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = null
  }, [])

  const track = useCallback(
    async (jobId) => {
      stop()
      return new Promise((resolve) => {
        timerRef.current = setInterval(async () => {
          try {
            const state = await apiClient.job(jobId)
            setJob(state)
            if (state.status === 'COMPLETE' || state.status === 'FAILED') {
              stop()
              resolve(state)
            }
          } catch (err) {
            stop()
            setJob({ status: 'FAILED', error: err.detail, progress: 0 })
            resolve({ status: 'FAILED', error: err.detail })
          }
        }, 700)
      })
    },
    [stop]
  )

  useEffect(() => stop, [stop])

  return { job, track, setJob, stop }
}
