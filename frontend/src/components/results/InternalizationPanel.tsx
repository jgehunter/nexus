/**
 * InternalizationPanel component - displays internalization metrics.
 */

import type { InternalizationMetrics, KPIDefinition } from '../../api/results'
import { KPICard } from './KPICard'

interface InternalizationPanelProps {
  metrics: InternalizationMetrics | null
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
        <h3 className="panel-section-title">Volume Summary</h3>
        <p className="panel-section-description">
          Breakdown of how client flow was handled - internalized vs externally hedged.
        </p>
        <div className="panel-metrics">
          <KPICard
            label="Client Volume"
            value={formatVolume(metrics.total_client_volume)}
            subtitle="Total traded"
            trend="neutral"
            definition={definitions['total_client_volume']}
          />
          <KPICard
            label="Internalized"
            value={formatVolume(metrics.total_internalized_volume)}
            subtitle={formatPercent(metrics.internalization_ratio)}
            trend="positive"
            definition={definitions['total_internalized_volume']}
          />
          <KPICard
            label="Externalized"
            value={formatVolume(metrics.total_externalized_volume)}
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

      {/* Per-pair breakdown */}
      {metrics.pair_breakdown.length > 0 && (
        <div className="panel-section">
          <h3 className="panel-section-title">By Currency Pair</h3>
          <table className="metrics-table">
            <thead>
              <tr>
                <th>Pair</th>
                <th>Client Vol</th>
                <th>Internalized</th>
                <th>Externalized</th>
                <th>Int. %</th>
              </tr>
            </thead>
            <tbody>
              {metrics.pair_breakdown.map((pair, index) => (
                <tr key={index}>
                  <td className="pair-name">{String(pair.pair || pair['pair'])}</td>
                  <td>{formatVolume(Number(pair.client_volume || 0))}</td>
                  <td>{formatVolume(Number(pair.internalized_volume || 0))}</td>
                  <td>{formatVolume(Number(pair.externalized_volume || 0))}</td>
                  <td>
                    {formatPercent(Number(pair.internalization_ratio || 0))}
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
