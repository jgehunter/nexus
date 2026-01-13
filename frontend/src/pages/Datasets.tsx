import { useEffect, useState } from 'react'
import { listDatasets, DatasetSummary } from '../api/datasets'
import { getDatasetHealth, DataHealthReport } from '../api/dataHealth'

// Dataset management page with health metrics
export function Datasets() {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([])
  const [healthReports, setHealthReports] = useState<Map<string, DataHealthReport>>(new Map())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [healthLoading, setHealthLoading] = useState(false)

  useEffect(() => {
    let mounted = true

    async function fetchDatasets() {
      try {
        setLoading(true)
        setError(null)
        const data = await listDatasets()
        if (mounted) {
          setDatasets(data)
          // Fetch health for each dataset
          fetchHealth(data)
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : 'Failed to load datasets')
        }
      } finally {
        if (mounted) {
          setLoading(false)
        }
      }
    }

    async function fetchHealth(datasets: DatasetSummary[]) {
      if (datasets.length === 0) return

      setHealthLoading(true)

      // Fetch health reports in parallel instead of sequentially
      const healthPromises = datasets.map(async (dataset) => {
        try {
          const health = await getDatasetHealth(dataset.name, false)
          return { name: dataset.name, health, error: null }
        } catch (err) {
          console.error(`Failed to load health for ${dataset.name}:`, err)
          return { name: dataset.name, health: null, error: err }
        }
      })

      const results = await Promise.all(healthPromises)

      if (mounted) {
        const reports = new Map<string, DataHealthReport>()
        for (const result of results) {
          if (result.health) {
            reports.set(result.name, result.health)
          }
        }
        setHealthReports(reports)
        setHealthLoading(false)
      }
    }

    fetchDatasets()

    return () => {
      mounted = false
    }
  }, [])

  return (
    <div className="page">
      <div className="page-header">
        <h1>Market Datasets</h1>
        <p className="page-description">
          Manage market data for backtesting (shared observable universe)
        </p>
      </div>

      {loading && (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading datasets...</p>
        </div>
      )}

      {error && (
        <div className="error-state">
          <div className="error-icon">⚠️</div>
          <h3>Failed to load datasets</h3>
          <p>{error}</p>
          <button onClick={() => window.location.reload()}>Retry</button>
        </div>
      )}

      {!loading && !error && datasets.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
          </div>
          <h3>No datasets yet</h3>
          <p>Upload your first dataset to get started with backtesting</p>
        </div>
      )}

      {!loading && !error && datasets.length > 0 && (
        <div className="datasets-grid">
          {datasets.map((dataset) => {
            const health = healthReports.get(dataset.name)
            return (
              <div key={dataset.name} className="dataset-card">
                <div className="dataset-header">
                  <h3>{dataset.name}</h3>
                  <span className="version-badge">{dataset.version_id}</span>
                </div>

                <div className="dataset-stats">
                  <div className="stat">
                    <span className="stat-label">Pairs</span>
                    <span className="stat-value">{dataset.pairs.length}</span>
                  </div>
                  <div className="stat">
                    <span className="stat-label">Dates</span>
                    <span className="stat-value">{dataset.dates.length}</span>
                  </div>
                  <div className="stat">
                    <span className="stat-label">Market Files</span>
                    <span className="stat-value">{dataset.total_market_files}</span>
                  </div>
                </div>

                {health && (
                  <div className="health-section">
                    <div className="health-header">
                      <h4>Data Quality</h4>
                      {(health.summary.gaps_over_5min ?? 0) > 0 ? (
                        <span className="health-badge health-warning">Gaps Detected</span>
                      ) : (
                        <span className="health-badge health-good">Ready</span>
                      )}
                    </div>

                    <div className="health-stats">
                      <div className="health-stat">
                        <span className="health-label">Market Files</span>
                        <span className="health-value">
                          {health.summary.total_tick_files || 0}
                        </span>
                      </div>
                      <div className="health-stat">
                        <span className="health-label">Total Ticks</span>
                        <span className="health-value">
                          {health.summary.total_ticks?.toLocaleString() || '0'}
                        </span>
                      </div>
                      <div className="health-stat">
                        <span className="health-label">Large Gaps</span>
                        <span className={`health-value ${(health.summary.gaps_over_5min ?? 0) > 0 ? 'health-value-warning' : ''}`}>
                          {health.summary.gaps_over_5min ?? 0}
                        </span>
                      </div>
                    </div>

                    {(health.summary.gaps_over_1min ?? 0) > 0 && (
                      <div className="health-warnings">
                        <div className="health-warning-item">
                          <span className="warning-icon">⚠️</span>
                          <div className="warning-text">
                            <strong>{health.summary.gaps_over_1min} gaps &gt;1min detected</strong>
                            {(health.summary.gaps_over_5min ?? 0) > 0 && (
                              <span className="warning-detail">
                                ({health.summary.gaps_over_5min} over 5min, {health.summary.gaps_over_15min} over 15min)
                              </span>
                            )}
                            <span className="warning-detail">
                              May affect pricing accuracy during gap periods
                            </span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {!health && healthLoading && (
                  <div className="health-section">
                    <div className="health-loading">
                      <div className="spinner-small"></div>
                      <span>Loading health data...</span>
                    </div>
                  </div>
                )}

                <div className="dataset-details">
                  <div className="detail-row">
                    <span className="detail-label">Pairs Covered:</span>
                    <span className="detail-value">{dataset.pairs.join(', ') || 'None'}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-label">Date Range:</span>
                    <span className="detail-value">
                      {dataset.dates.length > 0
                        ? `${dataset.dates[0]} - ${dataset.dates[dataset.dates.length - 1]}`
                        : 'No dates'}
                    </span>
                  </div>
                </div>

                <div className="dataset-actions">
                  <button className="btn-secondary">View Details</button>
                  <button className="btn-primary">Use Dataset</button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
