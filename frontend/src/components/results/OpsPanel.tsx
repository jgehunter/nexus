/**
 * OpsPanel component - displays operational metrics.
 */

import type { OpsMetrics, KPIDefinition } from '../../api/results'
import { KPICard } from './KPICard'

interface OpsPanelProps {
  metrics: OpsMetrics | null
  definitions: Record<string, KPIDefinition>
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

export function OpsPanel({ metrics, definitions }: OpsPanelProps) {
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
            value={formatVolume(metrics.total_hedge_volume)}
            subtitle="Total hedged amount"
            trend="neutral"
            definition={definitions['total_hedge_volume']}
          />
          <KPICard
            label="Avg Hedge Size"
            value={formatVolume(metrics.avg_hedge_size)}
            subtitle="Per-trade average"
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

      {/* Visual indicator */}
      <div className="panel-section">
        <h3 className="panel-section-title">Hedge Efficiency</h3>
        <div className="ops-stats">
          <div className="ops-stat">
            <div className="ops-stat-label">Hedges per 1000 units client flow</div>
            <div className="ops-stat-value">
              {metrics.hedge_count > 0 && metrics.total_hedge_volume > 0
                ? ((metrics.hedge_count / metrics.total_hedge_volume) * 1000).toFixed(1)
                : 'N/A'}
            </div>
          </div>
          <div className="ops-stat">
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
    </div>
  )
}
