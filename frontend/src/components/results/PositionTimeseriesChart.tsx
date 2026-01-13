/**
 * PositionTimeseriesChart component - displays position over time for a direct pair.
 */

import {
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Area,
  AreaChart,
} from 'recharts'
import type { PairPositionTimeseries, PositionTimeseriesPoint } from '../../api/results'

interface PositionTimeseriesChartProps {
  data: PairPositionTimeseries
  height?: number
}

function formatTimestamp(ms: number): string {
  const date = new Date(ms)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function formatCurrency(value: number): string {
  const absValue = Math.abs(value)
  if (absValue >= 1000000) {
    return `${value >= 0 ? '' : '-'}$${(absValue / 1000000).toFixed(1)}M`
  }
  if (absValue >= 1000) {
    return `${value >= 0 ? '' : '-'}$${(absValue / 1000).toFixed(0)}K`
  }
  return `${value >= 0 ? '' : '-'}$${absValue.toFixed(0)}`
}

function formatPosition(value: number): string {
  const absValue = Math.abs(value)
  if (absValue >= 1000000) {
    return `${value >= 0 ? '' : '-'}${(absValue / 1000000).toFixed(2)}M`
  }
  if (absValue >= 1000) {
    return `${value >= 0 ? '' : '-'}${(absValue / 1000).toFixed(1)}K`
  }
  return value.toFixed(0)
}

interface TooltipPayload {
  payload: PositionTimeseriesPoint
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!active || !payload || payload.length === 0) return null

  const point = payload[0].payload
  const date = new Date(point.timestamp_ms)

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-time">{date.toLocaleString()}</div>
      <div className="chart-tooltip-value">
        <span className="chart-tooltip-label">Position:</span>
        <span className={point.position >= 0 ? 'positive' : 'negative'}>
          {formatPosition(point.position)}
        </span>
      </div>
      <div className="chart-tooltip-value">
        <span className="chart-tooltip-label">Value (USD):</span>
        <span className={point.position_usd >= 0 ? 'positive' : 'negative'}>
          {formatCurrency(point.position_usd)}
        </span>
      </div>
    </div>
  )
}

export function PositionTimeseriesChart({ data, height = 200 }: PositionTimeseriesChartProps) {
  if (!data.points || data.points.length === 0) {
    return (
      <div className="position-chart-container">
        <h4 className="chart-title">{data.pair}</h4>
        <div className="chart-empty">
          <p>No position data available</p>
        </div>
      </div>
    )
  }

  // Use different colors for long vs short positions
  const gradientId = `positionGradient-${data.pair}`

  return (
    <div className="position-chart-container">
      <div className="position-chart-header">
        <h4 className="chart-title">{data.pair}</h4>
        <div className="position-chart-stats">
          <span className="stat">
            Max: <strong>{formatCurrency(data.max_position_usd)}</strong>
          </span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data.points} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3fb950" stopOpacity={0.3} />
              <stop offset="50%" stopColor="#3fb950" stopOpacity={0} />
              <stop offset="50%" stopColor="#f85149" stopOpacity={0} />
              <stop offset="95%" stopColor="#f85149" stopOpacity={0.3} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="timestamp_ms"
            tickFormatter={formatTimestamp}
            stroke="#8b949e"
            tick={{ fill: '#8b949e', fontSize: 10 }}
            axisLine={{ stroke: '#30363d' }}
            tickLine={{ stroke: '#30363d' }}
          />
          <YAxis
            tickFormatter={formatCurrency}
            stroke="#8b949e"
            tick={{ fill: '#8b949e', fontSize: 10 }}
            axisLine={{ stroke: '#30363d' }}
            tickLine={{ stroke: '#30363d' }}
            width={60}
          />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine y={0} stroke="#484f58" strokeWidth={1} />
          <Area
            type="stepAfter"
            dataKey="position_usd"
            stroke="#58a6ff"
            strokeWidth={1.5}
            fill={`url(#${gradientId})`}
            dot={false}
            activeDot={{ r: 3, fill: '#58a6ff' }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
