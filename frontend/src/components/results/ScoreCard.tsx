/**
 * ScoreCard component - summary of key metrics for managers.
 */

import { KPICard } from './KPICard'
import type { RunSummary, KPIDefinition } from '../../api/results'

interface ScoreCardProps {
  summary: RunSummary
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

function formatNumber(value: number): string {
  if (value >= 1000000) {
    return `${(value / 1000000).toFixed(2)}M`
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}K`
  }
  return value.toFixed(0)
}

export function ScoreCard({ summary, definitions }: ScoreCardProps) {
  const pnlTrend = summary.total_pnl >= 0 ? 'positive' : 'negative'

  // Calculate drawdown trend (lower is better)
  const drawdownPct = summary.risk_metrics?.max_drawdown_pct ?? 0
  const drawdownTrend = drawdownPct > 20 ? 'negative' : drawdownPct > 10 ? 'warning' : 'positive'

  return (
    <div className="scorecard">
      <div className="scorecard-section">
        <h3 className="scorecard-section-title">Performance</h3>
        <div className="scorecard-metrics">
          <KPICard
            label="Total PnL"
            value={formatCurrency(summary.total_pnl)}
            trend={pnlTrend}
            definition={definitions['total_pnl']}
          />
          <KPICard
            label="Execution PnL"
            value={formatCurrency(summary.total_execution_pnl)}
            trend={summary.total_execution_pnl >= 0 ? 'positive' : 'negative'}
            definition={definitions['total_execution_pnl']}
          />
          <KPICard
            label="Inventory PnL"
            value={formatCurrency(summary.total_inventory_pnl)}
            trend={summary.total_inventory_pnl >= 0 ? 'positive' : 'negative'}
            definition={definitions['total_inventory_pnl']}
          />
          <KPICard
            label="Hedge Cost"
            value={formatCurrency(summary.total_hedge_pnl)}
            trend={summary.total_hedge_pnl >= -100 ? 'positive' : 'warning'}
            definition={definitions['total_hedge_pnl']}
          />
        </div>
      </div>

      <div className="scorecard-section">
        <h3 className="scorecard-section-title">Risk</h3>
        <div className="scorecard-metrics">
          <KPICard
            label="Max Drawdown"
            value={formatPercent(drawdownPct)}
            trend={drawdownTrend}
            definition={definitions['max_drawdown_pct']}
          />
          <KPICard
            label="Peak Position"
            value={formatNumber(summary.risk_metrics?.max_abs_inventory ?? 0)}
            subtitle="base units"
            trend="neutral"
            definition={definitions['max_abs_inventory']}
          />
          <KPICard
            label="Position P95"
            value={formatNumber(summary.risk_metrics?.inventory_p95 ?? 0)}
            subtitle="base units"
            trend="neutral"
            definition={definitions['inventory_p95']}
          />
          <KPICard
            label="CVaR 95%"
            value={formatCurrency(summary.risk_metrics?.cvar_95 ?? 0)}
            trend={
              (summary.risk_metrics?.cvar_95 ?? 0) > -100 ? 'positive' : 'warning'
            }
            definition={definitions['cvar_95']}
          />
        </div>
      </div>

      <div className="scorecard-section">
        <h3 className="scorecard-section-title">Efficiency</h3>
        <div className="scorecard-metrics">
          <KPICard
            label="Internalization"
            value={formatPercent(summary.internalization_ratio * 100)}
            trend="neutral"
            definition={definitions['internalization_ratio']}
          />
          <KPICard
            label="Hedge Count"
            value={formatNumber(summary.ops_metrics?.hedge_count ?? 0)}
            subtitle="trades"
            trend="neutral"
            definition={definitions['hedge_count']}
          />
          <KPICard
            label="Hedge Ratio"
            value={(summary.ops_metrics?.hedge_volume_ratio ?? 0).toFixed(2)}
            trend={
              (summary.ops_metrics?.hedge_volume_ratio ?? 0) < 0.5 ? 'positive' : 'neutral'
            }
            definition={definitions['hedge_volume_ratio']}
          />
          <KPICard
            label="PnL/Volume"
            value={`${(summary.frontier_scores?.pnl_per_volume_bps ?? 0).toFixed(1)} bps`}
            trend={
              (summary.frontier_scores?.pnl_per_volume_bps ?? 0) > 0 ? 'positive' : 'negative'
            }
            definition={definitions['pnl_per_volume_bps']}
          />
        </div>
      </div>
    </div>
  )
}
