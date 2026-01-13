/**
 * RiskPanel component - displays risk metrics in a panel layout.
 */

import type { RiskMetrics, KPIDefinition } from '../../api/results'
import { KPICard } from './KPICard'
import { CombinedPositionChart } from './CombinedPositionChart'
import { AggregatePositionChart } from './AggregatePositionChart'

interface RiskPanelProps {
  metrics: RiskMetrics | null
  definitions: Record<string, KPIDefinition>
}

function formatCurrency(value: number): string {
  const absValue = Math.abs(value)
  if (absValue >= 1000000) {
    return `${value >= 0 ? '' : '-'}$${(absValue / 1000000).toFixed(2)}M`
  }
  if (absValue >= 1000) {
    return `${value >= 0 ? '' : '-'}$${(absValue / 1000).toFixed(1)}K`
  }
  return `${value >= 0 ? '' : '-'}$${absValue.toFixed(2)}`
}

function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`
}

function formatTimestamp(ms: number): string {
  if (ms === 0) return 'N/A'
  const date = new Date(ms)
  return date.toLocaleString()
}

export function RiskPanel({ metrics, definitions }: RiskPanelProps) {
  if (!metrics) {
    return (
      <div className="panel-empty">
        <p>Risk metrics not available for this run</p>
      </div>
    )
  }

  return (
    <div className="risk-panel">
      <div className="panel-section">
        <h3 className="panel-section-title">Inventory Risk</h3>
        <p className="panel-section-description">
          Aggregate USD exposure across all direct currency pairs.
        </p>
        <div className="panel-metrics">
          <KPICard
            label="Peak Position"
            value={formatCurrency(metrics.max_abs_inventory)}
            subtitle="Maximum aggregate USD exposure"
            trend={metrics.max_abs_inventory > 50000 ? 'warning' : 'neutral'}
            definition={definitions['max_abs_inventory']}
          />
          <KPICard
            label="Position P95"
            value={formatCurrency(metrics.inventory_p95)}
            subtitle="95th percentile (USD)"
            trend="neutral"
            definition={definitions['inventory_p95']}
          />
          <KPICard
            label="Position P99"
            value={formatCurrency(metrics.inventory_p99)}
            subtitle="99th percentile (tail risk)"
            trend={metrics.inventory_p99 > metrics.inventory_p95 * 1.5 ? 'warning' : 'neutral'}
            definition={definitions['inventory_p99']}
          />
        </div>
      </div>

      <div className="panel-section">
        <h3 className="panel-section-title">Drawdown Analysis</h3>
        <p className="panel-section-description">
          Peak-to-trough analysis of cumulative PnL decline.
        </p>
        <div className="panel-metrics">
          <KPICard
            label="Max Drawdown"
            value={formatCurrency(metrics.max_drawdown)}
            subtitle="Largest absolute decline"
            trend={metrics.max_drawdown > 1000 ? 'negative' : 'neutral'}
            definition={definitions['max_drawdown']}
          />
          <KPICard
            label="Max Drawdown %"
            value={formatPercent(metrics.max_drawdown_pct)}
            subtitle="% of peak PnL"
            trend={metrics.max_drawdown_pct > 20 ? 'negative' : metrics.max_drawdown_pct > 10 ? 'warning' : 'positive'}
            definition={definitions['max_drawdown_pct']}
          />
        </div>
      </div>

      <div className="panel-section">
        <h3 className="panel-section-title">Interval Risk</h3>
        <p className="panel-section-description">
          Short-term risk measures based on 5-minute intervals.
        </p>
        <div className="panel-metrics">
          <KPICard
            label="Worst 5-Min"
            value={formatCurrency(metrics.worst_interval_pnl)}
            subtitle={`at ${formatTimestamp(metrics.worst_interval_start_ms)}`}
            trend={metrics.worst_interval_pnl < -500 ? 'negative' : 'neutral'}
            definition={definitions['worst_interval_pnl']}
          />
          <KPICard
            label="CVaR 95%"
            value={formatCurrency(metrics.cvar_95)}
            subtitle="Avg of worst 5% intervals"
            trend={metrics.cvar_95 < -200 ? 'warning' : 'neutral'}
            definition={definitions['cvar_95']}
          />
        </div>
      </div>

      {/* Aggregate Position Timeseries */}
      {metrics.aggregate_position_timeseries && metrics.aggregate_position_timeseries.points.length > 0 && (
        <div className="panel-section">
          <h3 className="panel-section-title">Total USD Exposure Over Time</h3>
          <p className="panel-section-description">
            Sum of absolute USD positions across all direct pairs at each point in time.
          </p>
          <AggregatePositionChart data={metrics.aggregate_position_timeseries} height={250} />
        </div>
      )}

      {/* Combined Position Timeseries Chart */}
      {metrics.position_timeseries && metrics.position_timeseries.length > 0 && (
        <div className="panel-section">
          <h3 className="panel-section-title">Net Position by Currency Pair</h3>
          <p className="panel-section-description">
            Net position over time for each direct currency pair. Toggle pairs on/off to compare.
          </p>
          <CombinedPositionChart positionTimeseries={metrics.position_timeseries} height={400} />
        </div>
      )}
    </div>
  )
}
