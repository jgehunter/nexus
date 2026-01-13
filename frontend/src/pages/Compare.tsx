/**
 * Compare page - multi-run comparison with efficient frontier visualization.
 */

import { useState, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from 'recharts'
import {
  getFrontier,
  getSweepDetail,
  type FrontierConfig,
  type FrontierTableResponse,
  type SweepDetailResponse,
} from '../api/sweeps'

// Color scale based on internalization ratio (green = high, red = low)
function getColor(internalization: number): string {
  const hue = internalization * 120 // 0 = red, 120 = green
  return `hsl(${hue}, 70%, 50%)`
}

// Format parameter value for display
function formatParamValue(value: unknown): string {
  if (typeof value === 'number') {
    if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`
    if (value >= 1000) return `${(value / 1000).toFixed(1)}K`
    return value.toFixed(2)
  }
  return String(value)
}

// Custom tooltip for scatter plot
function FrontierTooltip({ active, payload }: { active?: boolean; payload?: unknown[] }) {
  if (!active || !payload || payload.length === 0) return null

  const data = (payload[0] as { payload: FrontierConfig }).payload
  return (
    <div className="frontier-tooltip">
      <div className="tooltip-header">
        <strong>{data.config_hash}</strong>
        {data.is_pareto_optimal && <span className="pareto-badge">Pareto</span>}
      </div>
      <div className="tooltip-row">
        <span>PnL/Volume:</span>
        <span>{data.pnl_per_volume_bps.toFixed(2)} bps</span>
      </div>
      <div className="tooltip-row">
        <span>Risk Score:</span>
        <span>{data.inventory_risk_score.toFixed(4)}</span>
      </div>
      <div className="tooltip-row">
        <span>Internalization:</span>
        <span>{(data.internalization_ratio * 100).toFixed(1)}%</span>
      </div>
      <div className="tooltip-row">
        <span>Max Drawdown:</span>
        <span>{data.max_drawdown_pct.toFixed(2)}%</span>
      </div>
      {Object.keys(data.parameters).length > 0 && (
        <div className="tooltip-params">
          <strong>Parameters:</strong>
          {Object.entries(data.parameters).map(([k, v]) => (
            <div key={k} className="param-row">
              <span>{k}:</span>
              <span>{formatParamValue(v)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Sortable table component
function ConfigsTable({
  configs,
  sortKey,
  sortDirection,
  onSort,
}: {
  configs: FrontierConfig[]
  sortKey: string
  sortDirection: 'asc' | 'desc'
  onSort: (key: string) => void
}) {
  const getSortIndicator = (key: string) => {
    if (sortKey !== key) return ''
    return sortDirection === 'asc' ? ' ▲' : ' ▼'
  }

  return (
    <div className="configs-table-container">
      <table className="configs-table">
        <thead>
          <tr>
            <th onClick={() => onSort('config_hash')}>Config{getSortIndicator('config_hash')}</th>
            <th onClick={() => onSort('pnl_per_volume_bps')}>PnL/Vol (bps){getSortIndicator('pnl_per_volume_bps')}</th>
            <th onClick={() => onSort('inventory_risk_score')}>Risk Score{getSortIndicator('inventory_risk_score')}</th>
            <th onClick={() => onSort('max_drawdown_pct')}>Max DD %{getSortIndicator('max_drawdown_pct')}</th>
            <th onClick={() => onSort('internalization_ratio')}>Int. Ratio{getSortIndicator('internalization_ratio')}</th>
            <th onClick={() => onSort('risk_adjusted_return')}>Risk-Adj Ret{getSortIndicator('risk_adjusted_return')}</th>
            <th>Parameters</th>
            <th>Pareto</th>
          </tr>
        </thead>
        <tbody>
          {configs.map((config) => (
            <tr key={config.run_id} className={config.is_pareto_optimal ? 'pareto-row' : ''}>
              <td className="config-hash">{config.config_hash}</td>
              <td className={config.pnl_per_volume_bps >= 0 ? 'positive' : 'negative'}>
                {config.pnl_per_volume_bps.toFixed(2)}
              </td>
              <td>{config.inventory_risk_score.toFixed(4)}</td>
              <td>{config.max_drawdown_pct.toFixed(2)}</td>
              <td>{(config.internalization_ratio * 100).toFixed(1)}%</td>
              <td className={config.risk_adjusted_return >= 0 ? 'positive' : 'negative'}>
                {config.risk_adjusted_return.toFixed(2)}
              </td>
              <td className="params-cell">
                {Object.entries(config.parameters).map(([k, v]) => (
                  <span key={k} className="param-tag">
                    {k}={formatParamValue(v)}
                  </span>
                ))}
              </td>
              <td className="pareto-cell">{config.is_pareto_optimal ? '✓' : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// Main Compare page
export function Compare() {
  const [searchParams] = useSearchParams()
  const sweepId = searchParams.get('sweep')

  const [sweep, setSweep] = useState<SweepDetailResponse | null>(null)
  const [frontier, setFrontier] = useState<FrontierTableResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Constraint filters
  const [maxRisk, setMaxRisk] = useState<number | undefined>(undefined)
  const [minInternalization, setMinInternalization] = useState<number | undefined>(undefined)
  const [maxDrawdown, setMaxDrawdown] = useState<number | undefined>(undefined)

  // Table sorting
  const [sortKey, setSortKey] = useState('risk_adjusted_return')
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc')

  // Load sweep and frontier data
  useEffect(() => {
    if (!sweepId) {
      setError('No sweep ID provided. Go to Sweeps page to select a sweep.')
      setLoading(false)
      return
    }

    async function loadData() {
      setLoading(true)
      try {
        const [sweepData, frontierData] = await Promise.all([
          getSweepDetail(sweepId!),
          getFrontier(sweepId!, maxRisk, minInternalization, maxDrawdown),
        ])
        setSweep(sweepData)
        setFrontier(frontierData)
        setError(null)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load data')
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [sweepId, maxRisk, minInternalization, maxDrawdown])

  // Sort configs
  const sortedConfigs = useMemo(() => {
    if (!frontier) return []

    const sorted = [...frontier.configs].sort((a, b) => {
      const aVal = a[sortKey as keyof FrontierConfig]
      const bVal = b[sortKey as keyof FrontierConfig]

      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortDirection === 'asc' ? aVal - bVal : bVal - aVal
      }

      const aStr = String(aVal)
      const bStr = String(bVal)
      return sortDirection === 'asc'
        ? aStr.localeCompare(bStr)
        : bStr.localeCompare(aStr)
    })

    return sorted
  }, [frontier, sortKey, sortDirection])

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      // Default direction based on metric type
      const higherIsBetter = ['pnl_per_volume_bps', 'risk_adjusted_return', 'internalization_ratio']
      setSortDirection(higherIsBetter.includes(key) ? 'desc' : 'asc')
    }
  }

  const clearFilters = () => {
    setMaxRisk(undefined)
    setMinInternalization(undefined)
    setMaxDrawdown(undefined)
  }

  if (loading) {
    return (
      <div className="page compare-page">
        <div className="loading">Loading frontier data...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page compare-page">
        <div className="error-banner">{error}</div>
      </div>
    )
  }

  if (!sweep || !frontier) {
    return (
      <div className="page compare-page">
        <div className="empty-state">No data available</div>
      </div>
    )
  }

  return (
    <div className="page compare-page">
      <div className="page-header">
        <div className="page-header-main">
          <h1>Efficient Frontier</h1>
          <p className="page-description">
            {sweep.config.name || sweep.sweep_id} &mdash; {frontier.filtered_count} configs
            ({frontier.pareto_count} Pareto-optimal)
          </p>
        </div>
      </div>

      {/* Constraint Filters */}
      <div className="filter-panel">
        <h3>Constraints</h3>
        <div className="filter-row">
          <div className="filter-input">
            <label>Max Risk Score</label>
            <input
              type="number"
              step="0.01"
              placeholder="e.g., 0.5"
              value={maxRisk ?? ''}
              onChange={e => setMaxRisk(e.target.value ? Number(e.target.value) : undefined)}
            />
          </div>
          <div className="filter-input">
            <label>Min Internalization</label>
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              placeholder="e.g., 0.8"
              value={minInternalization ?? ''}
              onChange={e => setMinInternalization(e.target.value ? Number(e.target.value) : undefined)}
            />
          </div>
          <div className="filter-input">
            <label>Max Drawdown %</label>
            <input
              type="number"
              step="0.1"
              placeholder="e.g., 10"
              value={maxDrawdown ?? ''}
              onChange={e => setMaxDrawdown(e.target.value ? Number(e.target.value) : undefined)}
            />
          </div>
          <button className="btn btn-secondary btn-sm" onClick={clearFilters}>
            Clear
          </button>
        </div>
      </div>

      {/* Scatter Plot */}
      <div className="frontier-chart-section">
        <h3>Return vs Risk</h3>
        <div className="chart-container">
          <ResponsiveContainer width="100%" height={400}>
            <ScatterChart margin={{ top: 20, right: 30, bottom: 40, left: 60 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis
                type="number"
                dataKey="inventory_risk_score"
                name="Risk"
                stroke="var(--color-text-muted)"
                label={{
                  value: 'Inventory Risk Score (lower = better)',
                  position: 'bottom',
                  offset: 20,
                  fill: 'var(--color-text-muted)',
                }}
              />
              <YAxis
                type="number"
                dataKey="pnl_per_volume_bps"
                name="Return"
                stroke="var(--color-text-muted)"
                label={{
                  value: 'PnL/Volume (bps)',
                  angle: -90,
                  position: 'insideLeft',
                  offset: -40,
                  fill: 'var(--color-text-muted)',
                }}
              />
              <ReferenceLine y={0} stroke="var(--color-text-subtle)" strokeDasharray="3 3" />
              <Tooltip content={<FrontierTooltip />} />
              <Scatter data={sortedConfigs} name="Configurations">
                {sortedConfigs.map((config) => (
                  <Cell
                    key={config.run_id}
                    fill={getColor(config.internalization_ratio)}
                    stroke={config.is_pareto_optimal ? 'var(--color-text)' : 'none'}
                    strokeWidth={config.is_pareto_optimal ? 2 : 0}
                    r={config.is_pareto_optimal ? 8 : 6}
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>

        {/* Legend */}
        <div className="chart-legend">
          <div className="legend-item">
            <span
              className="legend-gradient"
              style={{
                background: 'linear-gradient(to right, hsl(0,70%,50%), hsl(60,70%,50%), hsl(120,70%,50%))',
              }}
            />
            <span>Internalization: Low → High</span>
          </div>
          <div className="legend-item">
            <span className="legend-dot pareto" />
            <span>Pareto Optimal (black border)</span>
          </div>
        </div>
      </div>

      {/* Configs Table */}
      <div className="table-section">
        <h3>All Configurations</h3>
        <ConfigsTable
          configs={sortedConfigs}
          sortKey={sortKey}
          sortDirection={sortDirection}
          onSort={handleSort}
        />
      </div>
    </div>
  )
}
