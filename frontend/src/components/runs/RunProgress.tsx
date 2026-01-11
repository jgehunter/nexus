/**
 * RunProgress component - real-time progress view for running runs.
 */

import { useState, useEffect, useRef } from 'react'
import {
  getRunStatus,
  startRun,
  cancelRun,
  type RunStatusResponse,
} from '../../api/runs'

interface RunProgressProps {
  runId: string
  autoStart?: boolean
  onBack: () => void
  onComplete: (runId: string) => void
}

export function RunProgress({ runId, autoStart = false, onBack, onComplete }: RunProgressProps) {
  const [status, setStatus] = useState<RunStatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [elapsedMs, setElapsedMs] = useState(0)
  const startedRef = useRef(false)
  const startTimeRef = useRef<number | null>(null)

  // Start run if autoStart is true
  useEffect(() => {
    if (!autoStart || startedRef.current) return
    startedRef.current = true

    async function start() {
      try {
        const response = await startRun(runId)
        setStatus(response)
        startTimeRef.current = Date.now()
        setLoading(false)
      } catch (err) {
        console.error('Failed to start run:', err)
        setError('Failed to start run')
        setLoading(false)
      }
    }

    start()
  }, [runId, autoStart])

  // Poll for status updates
  useEffect(() => {
    if (loading) return
    if (
      status?.status === 'completed' ||
      status?.status === 'failed' ||
      status?.status === 'cancelled'
    ) {
      return
    }

    const poll = async () => {
      try {
        const response = await getRunStatus(runId)
        setStatus(response)

        if (response.started_at_ms && !startTimeRef.current) {
          startTimeRef.current = response.started_at_ms
        }
      } catch (err) {
        console.error('Failed to get run status:', err)
      }
    }

    const interval = setInterval(poll, 2000)
    return () => clearInterval(interval)
  }, [runId, loading, status?.status])

  // Update elapsed time
  useEffect(() => {
    if (!startTimeRef.current) return
    if (
      status?.status === 'completed' ||
      status?.status === 'failed' ||
      status?.status === 'cancelled'
    ) {
      return
    }

    const interval = setInterval(() => {
      setElapsedMs(Date.now() - (startTimeRef.current || Date.now()))
    }, 1000)

    return () => clearInterval(interval)
  }, [status?.status])

  const handleCancel = async () => {
    if (!confirm('Are you sure you want to cancel this run?')) return
    try {
      await cancelRun(runId)
      const response = await getRunStatus(runId)
      setStatus(response)
    } catch (err) {
      console.error('Failed to cancel run:', err)
      setError('Failed to cancel run')
    }
  }

  const formatElapsed = (ms: number): string => {
    const seconds = Math.floor(ms / 1000)
    const minutes = Math.floor(seconds / 60)
    const hours = Math.floor(minutes / 60)

    if (hours > 0) {
      return `${hours}h ${minutes % 60}m ${seconds % 60}s`
    }
    if (minutes > 0) {
      return `${minutes}m ${seconds % 60}s`
    }
    return `${seconds}s`
  }

  if (loading) {
    return (
      <div className="run-progress-view">
        <div className="loading-state">
          <div className="spinner" />
          <p>Starting run...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="run-progress-view">
        <div className="error-state">
          <p>{error}</p>
          <button className="btn btn-secondary" onClick={onBack}>
            Back to List
          </button>
        </div>
      </div>
    )
  }

  if (!status) {
    return (
      <div className="run-progress-view">
        <div className="error-state">
          <p>Failed to load run status</p>
          <button className="btn btn-secondary" onClick={onBack}>
            Back to List
          </button>
        </div>
      </div>
    )
  }

  const isComplete =
    status.status === 'completed' ||
    status.status === 'failed' ||
    status.status === 'cancelled'

  return (
    <div className="run-progress-view">
      <div className="progress-header">
        <button className="btn btn-ghost back-btn" onClick={onBack}>
          &larr; Back
        </button>
        <h2>Run {runId.slice(0, 8)}...</h2>
      </div>

      <div className="progress-content">
        <div className="progress-status">
          <span className={`status-badge status-${status.status}`}>
            {status.status}
          </span>
          {!isComplete && (
            <span className="elapsed-time">Elapsed: {formatElapsed(elapsedMs)}</span>
          )}
        </div>

        {status.status === 'running' && (
          <div className="progress-bar-container">
            <div className="progress-bar-large">
              <div
                className="progress-fill"
                style={{ width: `${status.progress_pct}%` }}
              />
            </div>
            <div className="progress-stats">
              <span className="progress-pct">{status.progress_pct.toFixed(1)}%</span>
              <span className="progress-shards">
                {status.completed_shards} / {status.total_shards} shards
              </span>
              {status.failed_shards > 0 && (
                <span className="progress-failed">
                  ({status.failed_shards} failed)
                </span>
              )}
            </div>
          </div>
        )}

        {status.status === 'completed' && (
          <div className="completion-message success">
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <polyline points="20 6 9 17 4 12" />
            </svg>
            <p>Run completed successfully!</p>
          </div>
        )}

        {status.status === 'failed' && (
          <div className="completion-message error">
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
            <p>Run failed: {status.error_message || 'Unknown error'}</p>
          </div>
        )}

        {status.status === 'cancelled' && (
          <div className="completion-message warning">
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="8" y1="12" x2="16" y2="12" />
            </svg>
            <p>Run was cancelled</p>
          </div>
        )}
      </div>

      <div className="progress-actions">
        {status.status === 'running' && (
          <button className="btn btn-danger" onClick={handleCancel}>
            Cancel Run
          </button>
        )}
        {status.status === 'completed' && (
          <button className="btn btn-primary" onClick={() => onComplete(runId)}>
            View Results
          </button>
        )}
        {(status.status === 'failed' || status.status === 'cancelled') && (
          <button className="btn btn-secondary" onClick={onBack}>
            Back to List
          </button>
        )}
      </div>
    </div>
  )
}
