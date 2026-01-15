/**
 * OpsPanel component - displays operational metrics and trades table.
 */

import type { OpsMetrics, KPIDefinition } from '../../api/results'
import { KPICard } from './KPICard'
import { TradesTable } from './TradesTable'

interface OpsPanelProps {
  metrics: OpsMetrics | null
  definitions: Record<string, KPIDefinition>
  runId: string
  pairs: string[]
}

function formatVolume(value: number): string {
  if (value >= 1000000) {
    return `${(value / 1000000).toFixed(2)}M`
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}K`
  }
  return value.toFixed(0)
}

function formatNumber(value: number): string {
  return value.toLocaleString()
}

export function OpsPanel({ metrics, definitions, runId, pairs }: OpsPanelProps) {
  if (!metrics) {
    return (
      <div className="panel-empty">
        <p>Operations metrics not available for this run</p>
      </div>
    )
  }

  return (
    <div className="ops-panel">
      <div className="panel-section">
        <h3 className="panel-section-title">Hedge Activity</h3>
        <p className="panel-section-description">
          Statistics on hedge trade execution throughout the simulation.
        </p>
        <div className="panel-metrics">
          <KPICard
            label="Hedge Count"
            value={formatNumber(metrics.hedge_count)}
            subtitle="Total hedge trades"
            trend="neutral"
            definition={definitions['hedge_count']}
          />
          <KPICard
            label="Hedge Volume"
            value={`$${formatVolume(metrics.total_hedge_volume)}`}
            subtitle="Total hedged (USD)"
            trend="neutral"
            definition={definitions['total_hedge_volume']}
          />
          <KPICard
            label="Avg Hedge Size"
            value={`$${formatVolume(metrics.avg_hedge_size)}`}
            subtitle="Per-trade avg (USD)"
            trend="neutral"
            definition={definitions['avg_hedge_size']}
          />
          <KPICard
            label="Hedge Ratio"
            value={metrics.hedge_volume_ratio.toFixed(2)}
            subtitle="Hedge vol / client vol"
            trend={metrics.hedge_volume_ratio < 0.5 ? 'positive' : 'neutral'}
            definition={definitions['hedge_volume_ratio']}
          />
        </div>
      </div>

      {/* Hedge Efficiency metrics */}
      <div className="panel-section">
        <h3 className="panel-section-title">Hedge Efficiency</h3>
        <p className="panel-section-description">
          Operational efficiency metrics for hedging activity.
        </p>
        <div className="ops-stats">
          <div className="ops-stat" title="Number of hedge trades executed per $1 million of client flow. Lower values indicate more efficient batch hedging.">
            <div className="ops-stat-label">Hedges per $1M client flow</div>
            <div className="ops-stat-value">
              {metrics.total_client_volume > 0
                ? ((metrics.hedge_count / metrics.total_client_volume) * 1000000).toFixed(2)
                : 'N/A'}
            </div>
            <div className="ops-stat-description">
              {metrics.hedge_count === 0
                ? 'No hedges executed - full internalization'
                : metrics.total_client_volume > 0 && (metrics.hedge_count / metrics.total_client_volume) * 1000000 < 1
                ? 'Efficient batched hedging'
                : 'Frequent hedging activity'}
            </div>
          </div>
          <div className="ops-stat" title="Percentage of client flow that was hedged externally. Lower values indicate higher internalization.">
            <div className="ops-stat-label">Volume Coverage Ratio</div>
            <div className="ops-stat-value">
              {(metrics.hedge_volume_ratio * 100).toFixed(1)}%
            </div>
            <div className="ops-stat-description">
              {metrics.hedge_volume_ratio < 0.3
                ? 'High internalization - minimal external hedging'
                : metrics.hedge_volume_ratio < 0.7
                ? 'Moderate hedging activity'
                : 'Heavy external hedging - low internalization'}
            </div>
          </div>
        </div>
      </div>

      {/* Trades Table */}
      <div className="panel-section">
        <h3 className="panel-section-title">Trade History</h3>
        <p className="panel-section-description">
          Individual client fills and hedge trades with PnL attribution.
        </p>
        <TradesTable runId={runId} pairs={pairs} />
      </div>
    </div>
  )
}
