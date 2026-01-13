/**
 * InternalizationPanel component - displays internalization metrics.
 */

import type { InternalizationMetrics, KPIDefinition } from '../../api/results'
import { KPICard } from './KPICard'

interface InternalizationPanelProps {
  metrics: InternalizationMetrics | null
  definitions: Record<string, KPIDefinition>
}

function formatCurrency(value: number): string {
  const absValue = Math.abs(value)
  if (absValue >= 1000000) {
    return `$${(absValue / 1000000).toFixed(2)}M`
  }
  if (absValue >= 1000) {
    return `$${(absValue / 1000).toFixed(1)}K`
  }
  return `$${absValue.toFixed(0)}`
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

export function InternalizationPanel({ metrics, definitions }: InternalizationPanelProps) {
  if (!metrics) {
    return (
      <div className="panel-empty">
        <p>Internalization metrics not available for this run</p>
      </div>
    )
  }

  return (
    <div className="internalization-panel">
      <div className="panel-section">
        <h3 className="panel-section-title">Volume Summary (USD)</h3>
        <p className="panel-section-description">
          Breakdown of how client flow was handled - internalized vs externally hedged.
          All volumes normalized to reporting currency (USD).
        </p>
        <div className="panel-metrics">
          <KPICard
            label="Client Volume"
            value={formatCurrency(metrics.total_client_volume_usd || metrics.total_client_volume)}
            subtitle="Total traded (USD)"
            trend="neutral"
            definition={definitions['total_client_volume']}
          />
          <KPICard
            label="Internalized"
            value={formatCurrency(metrics.total_internalized_volume_usd || metrics.total_internalized_volume)}
            subtitle={formatPercent(metrics.internalization_ratio)}
            trend="positive"
            definition={definitions['total_internalized_volume']}
          />
          <KPICard
            label="Externalized"
            value={formatCurrency(metrics.total_externalized_volume_usd || metrics.total_externalized_volume)}
            subtitle={formatPercent(1 - metrics.internalization_ratio)}
            trend="neutral"
            definition={definitions['total_externalized_volume']}
          />
          <KPICard
            label="Internalization %"
            value={formatPercent(metrics.internalization_ratio)}
            subtitle="Client-to-client matching"
            trend="neutral"
            definition={definitions['internalization_ratio']}
          />
        </div>
      </div>

      {/* Visual breakdown */}
      <div className="panel-section">
        <h3 className="panel-section-title">Flow Distribution</h3>
        <div className="internalization-bar">
          <div
            className="internalization-bar-internal"
            style={{ width: `${metrics.internalization_ratio * 100}%` }}
          >
            {metrics.internalization_ratio > 0.1 && (
              <span className="internalization-bar-label">
                {formatPercent(metrics.internalization_ratio)} Internalized
              </span>
            )}
          </div>
          <div
            className="internalization-bar-external"
            style={{ width: `${(1 - metrics.internalization_ratio) * 100}%` }}
          >
            {(1 - metrics.internalization_ratio) > 0.1 && (
              <span className="internalization-bar-label">
                {formatPercent(1 - metrics.internalization_ratio)} Externalized
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Per direct pair breakdown (USD normalized) */}
      {metrics.direct_pair_breakdown && metrics.direct_pair_breakdown.length > 0 && (
        <div className="panel-section">
          <h3 className="panel-section-title">By Direct Currency Pair (USD)</h3>
          <p className="panel-section-description">
            Volume breakdown by direct pairs after decrossing. All values in reporting currency.
          </p>
          <table className="metrics-table">
            <thead>
              <tr>
                <th>Pair</th>
                <th>Client Vol (USD)</th>
                <th>Internalized (USD)</th>
                <th>Externalized (USD)</th>
                <th>Int. %</th>
              </tr>
            </thead>
            <tbody>
              {metrics.direct_pair_breakdown.map((pair, index) => (
                <tr key={index}>
                  <td className="pair-name">{pair.pair}</td>
                  <td>{formatCurrency(pair.client_volume_usd)}</td>
                  <td className="positive">{formatCurrency(pair.internalized_volume_usd)}</td>
                  <td>{formatCurrency(pair.externalized_volume_usd)}</td>
                  <td>
                    <span className={pair.internalization_ratio > 0.5 ? 'positive' : ''}>
                      {formatPercent(pair.internalization_ratio)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
