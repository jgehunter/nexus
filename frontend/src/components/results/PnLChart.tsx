/**
 * PnLChart component - cumulative PnL timeseries visualization.
 */

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import type { TimeseriesPoint } from '../../api/results'

interface PnLChartProps {
  data: TimeseriesPoint[]
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

interface TooltipPayload {
  payload: TimeseriesPoint
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!active || !payload || payload.length === 0) return null

  const point = payload[0].payload
  const date = new Date(point.timestamp_ms)

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-time">{date.toLocaleString()}</div>
      <div className="chart-tooltip-value">
        <span className="chart-tooltip-label">Cumulative PnL:</span>
        <span className={point.cumulative_pnl >= 0 ? 'positive' : 'negative'}>
          {formatCurrency(point.cumulative_pnl)}
        </span>
      </div>
    </div>
  )
}

export function PnLChart({ data, height = 300 }: PnLChartProps) {
  if (data.length === 0) {
    return (
      <div className="chart-empty">
        <p>No timeseries data available</p>
      </div>
    )
  }

  // Determine if we're mostly positive or negative for color
  const finalPnL = data[data.length - 1]?.cumulative_pnl ?? 0
  const lineColor = finalPnL >= 0 ? '#3fb950' : '#f85149'

  return (
    <div className="chart-container">
      <h4 className="chart-title">Cumulative PnL</h4>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
          <XAxis
            dataKey="timestamp_ms"
            tickFormatter={formatTimestamp}
            stroke="#8b949e"
            tick={{ fill: '#8b949e', fontSize: 11 }}
            axisLine={{ stroke: '#30363d' }}
            tickLine={{ stroke: '#30363d' }}
          />
          <YAxis
            tickFormatter={formatCurrency}
            stroke="#8b949e"
            tick={{ fill: '#8b949e', fontSize: 11 }}
            axisLine={{ stroke: '#30363d' }}
            tickLine={{ stroke: '#30363d' }}
            width={70}
          />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine y={0} stroke="#30363d" strokeDasharray="3 3" />
          <Line
            type="monotone"
            dataKey="cumulative_pnl"
            stroke={lineColor}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: lineColor }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
