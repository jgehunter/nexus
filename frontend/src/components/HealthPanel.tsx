/**
 * Health status panel showing backend connection and system metrics.
 */

import type { ConnectionState } from '../api/health'

interface HealthPanelProps {
  state: ConnectionState
  onRetry: () => void
}

export function HealthPanel({ state, onRetry }: HealthPanelProps) {
  const { status, health, error, lastChecked } = state

  const formatTime = (ms: number) => {
    const date = new Date(ms)
    return date.toLocaleTimeString()
  }

  const formatBytes = (mb: number) => {
    if (mb >= 1024) {
      return `${(mb / 1024).toFixed(1)} GB`
    }
    return `${mb} MB`
  }

  return (
    <div className="health-panel">
      <div className="health-panel-header">
        <h3>System Status</h3>
        {lastChecked && (
          <span className="last-checked">
            Last checked: {formatTime(lastChecked)}
          </span>
        )}
      </div>

      <div className="health-panel-content">
        {/* Connection Status */}
        <div className={`connection-status connection-${status}`}>
          <div className="status-indicator" />
          <div className="status-details">
            <span className="status-label">
              {status === 'connected' && 'Connected'}
              {status === 'connecting' && 'Connecting...'}
              {status === 'disconnected' && 'Reconnecting...'}
              {status === 'error' && 'Connection Failed'}
            </span>
            {health && (
              <span className="version">v{health.version}</span>
            )}
          </div>
          {(status === 'error' || status === 'disconnected') && (
            <button className="retry-btn" onClick={onRetry}>
              Retry
            </button>
          )}
        </div>

        {/* Error Message */}
        {error && (
          <div className="health-error">
            <span className="error-icon">!</span>
            <span className="error-message">{error}</span>
          </div>
        )}

        {/* Health Checks */}
        {health && (
          <>
            <div className="health-section">
              <h4>Health Checks</h4>
              <div className="checks-grid">
                {Object.entries(health.checks).map(([name, passed]) => (
                  <div
                    key={name}
                    className={`check-item ${passed ? 'check-pass' : 'check-fail'}`}
                  >
                    <span className="check-icon">{passed ? '✓' : '✗'}</span>
                    <span className="check-name">{name}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* System Metrics */}
            <div className="health-section">
              <h4>System Metrics</h4>
              <div className="metrics-grid">
                <div className="metric-item">
                  <span className="metric-label">CPU</span>
                  <div className="metric-bar-container">
                    <div
                      className="metric-bar"
                      style={{ width: `${Math.min(health.system.cpu_percent, 100)}%` }}
                      data-level={health.system.cpu_percent > 80 ? 'high' : health.system.cpu_percent > 50 ? 'medium' : 'low'}
                    />
                  </div>
                  <span className="metric-value">{health.system.cpu_percent.toFixed(1)}%</span>
                </div>

                <div className="metric-item">
                  <span className="metric-label">Memory</span>
                  <div className="metric-bar-container">
                    <div
                      className="metric-bar"
                      style={{ width: `${health.system.memory_percent}%` }}
                      data-level={health.system.memory_percent > 80 ? 'high' : health.system.memory_percent > 50 ? 'medium' : 'low'}
                    />
                  </div>
                  <span className="metric-value">{health.system.memory_percent.toFixed(1)}%</span>
                </div>

                <div className="metric-item metric-text">
                  <span className="metric-label">Available</span>
                  <span className="metric-value">{formatBytes(health.system.memory_available_mb)}</span>
                </div>

                <div className="metric-item metric-text">
                  <span className="metric-label">DuckDB</span>
                  <span className="metric-value mono">{health.system.duckdb_version}</span>
                </div>
              </div>
            </div>
          </>
        )}

        {/* Disconnected State */}
        {!health && status !== 'error' && (
          <div className="health-loading">
            <div className="loading-spinner" />
            <span>Checking backend status...</span>
          </div>
        )}
      </div>
    </div>
  )
}
