/**
 * Results page - manager-grade reporting with KPIs, charts, and metrics.
 */

import { useState, useEffect } from 'react'
import {
  getRunSummary,
  getTimeseries,
  getPnLBreakdown,
  getKPIDefinitions,
  type RunSummary,
  type TimeseriesPoint,
  type PnLBreakdownEntry,
  type KPIDefinition,
} from '../api/results'
import {
  listRuns,
  type RunListItem,
} from '../api/runs'
import {
  ScoreCard,
  PnLChart,
  PnLBreakdownChart,
  RiskPanel,
  InternalizationPanel,
  OpsPanel,
} from '../components/results'

type TabId = 'overview' | 'risk' | 'internalization' | 'operations'

export function Results() {
  // State
  const [runs, setRuns] = useState<RunListItem[]>([])
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabId>('overview')

  // Data
  const [summary, setSummary] = useState<RunSummary | null>(null)
  const [timeseries, setTimeseries] = useState<TimeseriesPoint[]>([])
  const [pnlBreakdown, setPnlBreakdown] = useState<PnLBreakdownEntry[]>([])
  const [kpiDefinitions, setKpiDefinitions] = useState<Record<string, KPIDefinition>>({})

  // Loading states
  const [loadingRuns, setLoadingRuns] = useState(true)
  const [loadingData, setLoadingData] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Load completed runs and KPI definitions on mount
  useEffect(() => {
    async function loadInitialData() {
      try {
        const [runsResponse, kpiResponse] = await Promise.all([
          listRuns('completed'),
          getKPIDefinitions(),
        ])

        // Filter to completed runs only
        const completedRuns = runsResponse.runs.filter(
          (r) => r.status === 'completed'
        )
        setRuns(completedRuns)

        // Convert KPI definitions to lookup map
        const defsMap: Record<string, KPIDefinition> = {}
        kpiResponse.definitions.forEach((d) => {
          defsMap[d.id] = d
        })
        setKpiDefinitions(defsMap)

        // Auto-select first run if available
        if (completedRuns.length > 0) {
          setSelectedRunId(completedRuns[0].run_id)
        }
      } catch (err) {
        console.error('Failed to load initial data:', err)
        setError('Failed to load runs')
      } finally {
        setLoadingRuns(false)
      }
    }

    loadInitialData()
  }, [])

  // Load run data when selection changes
  useEffect(() => {
    if (!selectedRunId) {
      setSummary(null)
      setTimeseries([])
      setPnlBreakdown([])
      return
    }

    async function loadRunData() {
      setLoadingData(true)
      setError(null)

      try {
        const [summaryData, timeseriesData, breakdownData] = await Promise.all([
          getRunSummary(selectedRunId!),
          getTimeseries(selectedRunId!, 500),
          getPnLBreakdown(selectedRunId!, 'pair'),
        ])

        setSummary(summaryData)
        setTimeseries(timeseriesData.points)
        setPnlBreakdown(breakdownData.breakdown)
      } catch (err) {
        console.error('Failed to load run data:', err)
        setError('Failed to load run data')
      } finally {
        setLoadingData(false)
      }
    }

    loadRunData()
  }, [selectedRunId])

  // Render helpers
  const tabs: { id: TabId; label: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'risk', label: 'Risk' },
    { id: 'internalization', label: 'Internalization' },
    { id: 'operations', label: 'Operations' },
  ]

  // Loading state
  if (loadingRuns) {
    return (
      <div className="page">
        <div className="page-header">
          <h1>Results</h1>
          <p className="page-description">
            Analyze PnL, risk metrics, and internalization from completed runs
          </p>
        </div>
        <div className="loading-state">
          <div className="spinner" />
          <p>Loading runs...</p>
        </div>
      </div>
    )
  }

  // No completed runs
  if (runs.length === 0) {
    return (
      <div className="page">
        <div className="page-header">
          <h1>Results</h1>
          <p className="page-description">
            Analyze PnL, risk metrics, and internalization from completed runs
          </p>
        </div>
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
              <path d="M3 3v18h18" />
              <path d="M18 9l-5 5-4-4-3 3" />
            </svg>
          </div>
          <h3>No results yet</h3>
          <p>Complete a backtest run to view detailed results and analytics</p>
        </div>
      </div>
    )
  }

  return (
    <div className="page results-page">
      <div className="page-header">
        <div className="page-header-main">
          <h1>Results</h1>
          <p className="page-description">
            Analyze PnL, risk metrics, and internalization from completed runs
          </p>
        </div>

        {/* Run Selector */}
        <div className="run-selector">
          <label htmlFor="run-select">Select Run:</label>
          <select
            id="run-select"
            value={selectedRunId || ''}
            onChange={(e) => setSelectedRunId(e.target.value)}
          >
            {runs.map((run) => (
              <option key={run.run_id} value={run.run_id}>
                {run.config?.name || run.run_id.slice(0, 8)} ({new Date(run.created_at_ms).toLocaleDateString()})
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {loadingData ? (
        <div className="loading-state">
          <div className="spinner" />
          <p>Loading run data...</p>
        </div>
      ) : summary ? (
        <>
          {/* Scorecard */}
          <ScoreCard summary={summary} definitions={kpiDefinitions} />

          {/* Tabs */}
          <div className="tabs">
            <div className="tab-list">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
                  onClick={() => setActiveTab(tab.id)}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="tab-content">
              {activeTab === 'overview' && (
                <div className="overview-tab">
                  <div className="charts-row">
                    <PnLChart data={timeseries} height={300} />
                  </div>
                  <div className="charts-row">
                    <PnLBreakdownChart data={pnlBreakdown} groupBy="pair" height={250} />
                  </div>

                  {/* Summary Stats */}
                  <div className="summary-stats">
                    <div className="stat-item">
                      <span className="stat-label">Pairs Traded</span>
                      <span className="stat-value">{summary.pairs.join(', ') || 'None'}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">Date Range</span>
                      <span className="stat-value">
                        {summary.date_range
                          ? `${summary.date_range[0]} to ${summary.date_range[1]}`
                          : 'N/A'}
                      </span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">Total Shards</span>
                      <span className="stat-value">{summary.total_shards}</span>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'risk' && (
                <RiskPanel metrics={summary.risk_metrics} definitions={kpiDefinitions} />
              )}

              {activeTab === 'internalization' && (
                <InternalizationPanel
                  metrics={summary.internalization_metrics}
                  definitions={kpiDefinitions}
                />
              )}

              {activeTab === 'operations' && (
                <OpsPanel metrics={summary.ops_metrics} definitions={kpiDefinitions} />
              )}
            </div>
          </div>
        </>
      ) : null}
    </div>
  )
}
