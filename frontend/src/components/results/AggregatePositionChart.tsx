/**
 * AggregatePositionChart component - displays total absolute USD position over time.
 */

import {
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
} from 'recharts'
import type { AggregatePositionTimeseries, AggregatePositionTimeseriesPoint } from '../../api/results'

interface AggregatePositionChartProps {
  data: AggregatePositionTimeseries
  height?: number
}

function formatTimestamp(ms: number): string {
  const date = new Date(ms)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function formatCurrency(value: number): string {
  const absValue = Math.abs(value)
  if (absValue >= 1000000) {
    return `$${(absValue / 1000000).toFixed(1)}M`
  }
  if (absValue >= 1000) {
    return `$${(absValue / 1000).toFixed(0)}K`
  }
  return `$${absValue.toFixed(0)}`
}

interface TooltipPayload {
  payload: AggregatePositionTimeseriesPoint
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!active || !payload || payload.length === 0) return null

  const point = payload[0].payload
  const date = new Date(point.timestamp_ms)

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-time">{date.toLocaleString()}</div>
      <div className="chart-tooltip-value">
        <span className="chart-tooltip-label">Total USD Exposure:</span>
        <span className="positive">
          {formatCurrency(point.total_abs_position_usd)}
        </span>
      </div>
    </div>
  )
}

export function AggregatePositionChart({ data, height = 200 }: AggregatePositionChartProps) {
  if (!data.points || data.points.length === 0) {
    return (
      <div className="position-chart-container aggregate-position-chart">
        <h4 className="chart-title">Total USD Exposure</h4>
        <div className="chart-empty">
          <p>No position data available</p>
        </div>
      </div>
    )
  }

  return (
    <div className="position-chart-container aggregate-position-chart">
      <div className="position-chart-header">
        <h4 className="chart-title">Total USD Exposure (All Pairs)</h4>
        <div className="position-chart-stats">
          <span className="stat">
            Peak: <strong>{formatCurrency(data.max_total_abs_position_usd)}</strong>
          </span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data.points} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
          <defs>
            <linearGradient id="aggregateGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#f0b429" stopOpacity={0.4} />
              <stop offset="95%" stopColor="#f0b429" stopOpacity={0.05} />
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
          <Area
            type="stepAfter"
            dataKey="total_abs_position_usd"
            stroke="#f0b429"
            strokeWidth={2}
            fill="url(#aggregateGradient)"
            dot={false}
            activeDot={{ r: 3, fill: '#f0b429' }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
