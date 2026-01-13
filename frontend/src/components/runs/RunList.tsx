/**
 * RunList component - displays list of runs with filtering.
 */

import { useState, useEffect, useCallback } from 'react'
import { listRuns, cancelRun, deleteRun, type RunListItem, type RunStatus } from '../../api/runs'
import { RunCard } from './RunCard'

type FilterTab = 'all' | 'running' | 'completed' | 'failed'

interface RunListProps {
  onViewProgress: (runId: string) => void
  onViewResults: (runId: string) => void
  onStartRun: (runId: string) => void
}

export function RunList({ onViewProgress, onViewResults, onStartRun }: RunListProps) {
  const [runs, setRuns] = useState<RunListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeFilter, setActiveFilter] = useState<FilterTab>('all')

  const fetchRuns = useCallback(async () => {
    try {
      const statusFilter: RunStatus | undefined =
        activeFilter === 'all' ? undefined : activeFilter
      const response = await listRuns(statusFilter)
      setRuns(response.runs)
      setError(null)
    } catch (err) {
      console.error('Failed to fetch runs:', err)
      setError('Failed to load runs')
    } finally {
      setLoading(false)
    }
  }, [activeFilter])

  useEffect(() => {
    fetchRuns()
  }, [fetchRuns])

  // Auto-refresh when there are running runs
  useEffect(() => {
    const hasRunningRuns = runs.some((r) => r.status === 'running')
    if (!hasRunningRuns) return

    const interval = setInterval(fetchRuns, 5000)
    return () => clearInterval(interval)
  }, [runs, fetchRuns])

  const handleCancel = async (runId: string) => {
    if (!confirm('Are you sure you want to cancel this run?')) return
    try {
      await cancelRun(runId)
      await fetchRuns()
    } catch (err) {
      console.error('Failed to cancel run:', err)
      setError('Failed to cancel run')
    }
  }

  const handleDelete = async (runId: string) => {
    if (!confirm('Are you sure you want to delete this run?')) return
    try {
      await deleteRun(runId)
      await fetchRuns()
    } catch (err) {
      console.error('Failed to delete run:', err)
      setError('Failed to delete run')
    }
  }

  const handleViewProgress = (runId: string) => {
    const run = runs.find((r) => r.run_id === runId)
    if (run?.status === 'created') {
      onStartRun(runId)
    } else {
      onViewProgress(runId)
    }
  }

  const filterTabs: { id: FilterTab; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: 'running', label: 'Running' },
    { id: 'completed', label: 'Completed' },
    { id: 'failed', label: 'Failed' },
  ]

  if (loading) {
    return (
      <div className="loading-state">
        <div className="spinner" />
        <p>Loading runs...</p>
      </div>
    )
  }

  return (
    <div className="run-list">
      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      <div className="run-list-filters">
        {filterTabs.map((tab) => (
          <button
            key={tab.id}
            className={`filter-tab ${activeFilter === tab.id ? 'active' : ''}`}
            onClick={() => setActiveFilter(tab.id)}
          >
            {tab.label}
          </button>
        ))}
        <button className="btn btn-ghost refresh-btn" onClick={fetchRuns}>
          Refresh
        </button>
      </div>

      {runs.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <svg
              width="48"
              height="48"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
            >
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
          </div>
          <h3>No runs found</h3>
          <p>
            {activeFilter === 'all'
              ? 'Create a new run to get started'
              : `No ${activeFilter} runs`}
          </p>
        </div>
      ) : (
        <div className="run-list-items">
          {runs.map((run) => (
            <RunCard
              key={run.run_id}
              run={run}
              onViewProgress={handleViewProgress}
              onViewResults={onViewResults}
              onCancel={handleCancel}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  )
}
