/**
 * KPICard component - displays a single KPI metric with tooltip.
 */

import { useState } from 'react'
import type { KPIDefinition } from '../../api/results'

interface KPICardProps {
  label: string
  value: string | number
  subtitle?: string
  trend?: 'positive' | 'negative' | 'neutral' | 'warning'
  definition?: KPIDefinition
}

export function KPICard({ label, value, subtitle, trend = 'neutral', definition }: KPICardProps) {
  const [showTooltip, setShowTooltip] = useState(false)

  const trendClass = {
    positive: 'kpi-trend-positive',
    negative: 'kpi-trend-negative',
    neutral: 'kpi-trend-neutral',
    warning: 'kpi-trend-warning',
  }[trend]

  return (
    <div
      className={`kpi-card ${trendClass}`}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <div className="kpi-label">
        {label}
        {definition && <span className="kpi-info-icon">i</span>}
      </div>
      <div className="kpi-value">{value}</div>
      {subtitle && <div className="kpi-subtitle">{subtitle}</div>}

      {showTooltip && definition && (
        <div className="kpi-tooltip">
          <div className="kpi-tooltip-title">{definition.name}</div>
          <div className="kpi-tooltip-description">{definition.description}</div>
          {definition.formula && (
            <div className="kpi-tooltip-formula">
              <strong>Formula:</strong> {definition.formula}
            </div>
          )}
          <div className="kpi-tooltip-meta">
            <span className="kpi-tooltip-unit">Unit: {definition.unit}</span>
            <span className="kpi-tooltip-interpretation">
              {definition.interpretation === 'higher_better' && 'Higher is better'}
              {definition.interpretation === 'lower_better' && 'Lower is better'}
              {definition.interpretation === 'neutral' && 'Neutral'}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
