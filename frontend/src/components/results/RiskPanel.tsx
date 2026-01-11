/**
 * RiskPanel component - displays risk metrics in a panel layout.
 */

import type { RiskMetrics, KPIDefinition } from '../../api/results'
import { KPICard } from './KPICard'

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

function formatNumber(value: number): string {
  if (value >= 1000000) {
    return `${(value / 1000000).toFixed(2)}M`
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}K`
  }
  return value.toFixed(0)
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
          Measures of position size and exposure throughout the simulation.
        </p>
        <div className="panel-metrics">
          <KPICard
            label="Peak Position"
            value={formatNumber(metrics.max_abs_inventory)}
            subtitle="Maximum absolute inventory"
            trend={metrics.max_abs_inventory > 5000 ? 'warning' : 'neutral'}
            definition={definitions['max_abs_inventory']}
          />
          <KPICard
            label="Position P95"
            value={formatNumber(metrics.inventory_p95)}
            subtitle="95th percentile"
            trend="neutral"
            definition={definitions['inventory_p95']}
          />
          <KPICard
            label="Position P99"
            value={formatNumber(metrics.inventory_p99)}
            subtitle="99th percentile (tail risk)"
            trend={metrics.inventory_p99 > metrics.inventory_p95 * 1.5 ? 'warning' : 'neutral'}
            definition={definitions['inventory_p99']}
          />
          <KPICard
            label="Time Above Band"
            value={formatPercent(metrics.time_above_risk_band_pct)}
            subtitle="% time exceeding threshold"
            trend={metrics.time_above_risk_band_pct > 20 ? 'warning' : 'positive'}
            definition={definitions['time_above_risk_band_pct']}
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
    </div>
  )
}
