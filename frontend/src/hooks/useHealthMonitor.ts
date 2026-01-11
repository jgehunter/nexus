/**
 * Health monitoring hook with automatic retry and polling.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getDetailedHealth,
  type ConnectionState,
  type ConnectionStatus,
} from '../api/health'

const POLL_INTERVAL = 30000 // 30 seconds when connected
const RETRY_INTERVAL = 5000 // 5 seconds when disconnected
const MAX_RETRIES = 3

export function useHealthMonitor() {
  const [state, setState] = useState<ConnectionState>({
    status: 'connecting',
    health: null,
    error: null,
    lastChecked: null,
    retryCount: 0,
  })

  const timerRef = useRef<number | null>(null)
  const mountedRef = useRef(true)

  const checkHealth = useCallback(async () => {
    if (!mountedRef.current) return

    try {
      const health = await getDetailedHealth()

      if (!mountedRef.current) return

      setState({
        status: 'connected',
        health,
        error: null,
        lastChecked: Date.now(),
        retryCount: 0,
      })
    } catch (err) {
      if (!mountedRef.current) return

      const error = err instanceof Error ? err.message : 'Connection failed'
      const isNetworkError = error.includes('fetch') || error.includes('network') || error.includes('Failed')

      setState((prev) => {
        const newRetryCount = prev.retryCount + 1
        const status: ConnectionStatus =
          newRetryCount >= MAX_RETRIES ? 'error' : 'disconnected'

        return {
          status,
          health: null,
          error: isNetworkError
            ? 'Cannot connect to backend. Make sure the server is running on port 8000.'
            : error,
          lastChecked: Date.now(),
          retryCount: newRetryCount,
        }
      })
    }
  }, [])

  const retry = useCallback(() => {
    setState((prev) => ({
      ...prev,
      status: 'connecting',
      retryCount: 0,
    }))
    checkHealth()
  }, [checkHealth])

  useEffect(() => {
    mountedRef.current = true
    checkHealth()

    return () => {
      mountedRef.current = false
      if (timerRef.current) {
        clearTimeout(timerRef.current)
      }
    }
  }, [checkHealth])

  useEffect(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
    }

    const interval =
      state.status === 'connected'
        ? POLL_INTERVAL
        : state.status === 'disconnected'
          ? RETRY_INTERVAL
          : null

    if (interval && mountedRef.current) {
      timerRef.current = window.setTimeout(checkHealth, interval)
    }

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
      }
    }
  }, [state.status, state.lastChecked, checkHealth])

  return { ...state, retry }
}
