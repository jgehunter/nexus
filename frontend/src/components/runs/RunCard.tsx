/**
 * RunCard component - displays a single run with status badge and actions.
 */

import type { RunListItem, RunStatus } from '../../api/runs'

interface RunCardProps {
  run: RunListItem
  onViewProgress: (runId: string) => void
  onViewResults: (runId: string) => void
  onCancel: (runId: string) => void
  onDelete: (runId: string) => void
}

function getStatusBadgeClass(status: RunStatus): string {
  switch (status) {
    case 'completed':
      return 'status-badge status-completed'
    case 'running':
      return 'status-badge status-running'
    case 'failed':
      return 'status-badge status-failed'
    case 'cancelled':
      return 'status-badge status-cancelled'
    case 'created':
    default:
      return 'status-badge status-created'
  }
}

function formatRelativeTime(ms: number): string {
  const now = Date.now()
  const diff = now - ms
  const seconds = Math.floor(diff / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)

  if (days > 0) return `${days}d ago`
  if (hours > 0) return `${hours}h ago`
  if (minutes > 0) return `${minutes}m ago`
  return 'just now'
}

export function RunCard({
  run,
  onViewProgress,
  onViewResults,
  onCancel,
  onDelete,
}: RunCardProps) {
  const displayName = run.config.name || `Run ${run.run_id.slice(0, 8)}...`
  const createdTime = formatRelativeTime(run.created_at_ms)

  return (
    <div className="run-card">
      <div className="run-card-header">
        <div className="run-card-title">
          <span className="run-name">{displayName}</span>
          <span className={getStatusBadgeClass(run.status)}>{run.status}</span>
        </div>
        <div className="run-card-meta">
          <span className="run-id">{run.run_id.slice(0, 8)}...</span>
          <span className="run-created">{createdTime}</span>
        </div>
      </div>

      <div className="run-card-details">
        <div className="run-detail">
          <span className="run-detail-label">Dataset:</span>
          <span className="run-detail-value">{run.config.dataset}</span>
        </div>
        {run.config.tradebook && (
          <div className="run-detail">
            <span className="run-detail-label">Tradebook:</span>
            <span className="run-detail-value">{run.config.tradebook}</span>
          </div>
        )}
        {run.status === 'running' && (
          <div className="run-progress-inline">
            <div className="run-progress-bar">
              <div
                className="run-progress-fill"
                style={{ width: `${run.progress_pct}%` }}
              />
            </div>
            <span className="run-progress-text">
              {run.completed_shards}/{run.total_shards} shards ({run.progress_pct.toFixed(0)}%)
            </span>
          </div>
        )}
        {run.status === 'failed' && run.error_message && (
          <div className="run-error">
            <span className="run-error-label">Error:</span>
            <span className="run-error-message">{run.error_message}</span>
          </div>
        )}
      </div>

      <div className="run-card-actions">
        {run.status === 'running' && (
          <>
            <button
              className="btn btn-secondary"
              onClick={() => onViewProgress(run.run_id)}
            >
              View Progress
            </button>
            <button
              className="btn btn-danger"
              onClick={() => onCancel(run.run_id)}
            >
              Cancel
            </button>
          </>
        )}
        {run.status === 'completed' && (
          <button
            className="btn btn-primary"
            onClick={() => onViewResults(run.run_id)}
          >
            View Results
          </button>
        )}
        {(run.status === 'completed' || run.status === 'failed' || run.status === 'cancelled') && (
          <button
            className="btn btn-ghost"
            onClick={() => onDelete(run.run_id)}
          >
            Delete
          </button>
        )}
        {run.status === 'created' && (
          <button
            className="btn btn-primary"
            onClick={() => onViewProgress(run.run_id)}
          >
            Start Run
          </button>
        )}
      </div>
    </div>
  )
}
