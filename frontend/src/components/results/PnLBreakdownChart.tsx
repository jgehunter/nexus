/**
 * PnLBreakdownChart component - bar chart showing PnL by component or group.
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
  Cell,
} from 'recharts'
import type { PnLBreakdownEntry } from '../../api/results'

interface PnLBreakdownChartProps {
  data: PnLBreakdownEntry[]
  groupBy: string
  height?: number
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
  payload: PnLBreakdownEntry
  name: string
  value: number
  color: string
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!active || !payload || payload.length === 0) return null

  const entry = payload[0].payload

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-title">{entry.group}</div>
      <div className="chart-tooltip-rows">
        <div className="chart-tooltip-row">
          <span className="chart-tooltip-dot" style={{ background: '#3fb950' }} />
          <span>Execution:</span>
          <span>{formatCurrency(entry.execution_pnl)}</span>
        </div>
        <div className="chart-tooltip-row">
          <span className="chart-tooltip-dot" style={{ background: '#58a6ff' }} />
          <span>Inventory:</span>
          <span>{formatCurrency(entry.inventory_pnl)}</span>
        </div>
        <div className="chart-tooltip-row">
          <span className="chart-tooltip-dot" style={{ background: '#f85149' }} />
          <span>Hedge:</span>
          <span>{formatCurrency(entry.hedge_pnl)}</span>
        </div>
        <div className="chart-tooltip-row total">
          <span>Total:</span>
          <span className={entry.total_pnl >= 0 ? 'positive' : 'negative'}>
            {formatCurrency(entry.total_pnl)}
          </span>
        </div>
      </div>
    </div>
  )
}

export function PnLBreakdownChart({ data, groupBy, height = 300 }: PnLBreakdownChartProps) {
  if (data.length === 0) {
    return (
      <div className="chart-empty">
        <p>No breakdown data available</p>
      </div>
    )
  }

  const title = {
    total: 'PnL Breakdown',
    pair: 'PnL by Currency Pair',
    date: 'PnL by Date',
  }[groupBy] || 'PnL Breakdown'

  return (
    <div className="chart-container">
      <h4 className="chart-title">{title}</h4>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
          <XAxis
            dataKey="group"
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
          <Legend
            wrapperStyle={{ paddingTop: 10 }}
            formatter={(value) => <span style={{ color: '#c9d1d9' }}>{value}</span>}
          />
          <Bar dataKey="execution_pnl" name="Execution" fill="#3fb950" />
          <Bar dataKey="inventory_pnl" name="Inventory" fill="#58a6ff" />
          <Bar dataKey="hedge_pnl" name="Hedge" fill="#f85149" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

// Simple total bar chart showing just the total PnL per group
export function TotalPnLChart({ data, groupBy, height = 200 }: PnLBreakdownChartProps) {
  if (data.length === 0) {
    return null
  }

  return (
    <div className="chart-container">
      <h4 className="chart-title">Total PnL by {groupBy}</h4>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
          <XAxis
            dataKey="group"
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
          <Tooltip
            formatter={(value) => [formatCurrency(Number(value ?? 0)), 'Total PnL']}
            contentStyle={{
              background: '#161b22',
              border: '1px solid #30363d',
              borderRadius: 6,
            }}
            labelStyle={{ color: '#c9d1d9' }}
          />
          <Bar dataKey="total_pnl" name="Total PnL">
            {data.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={entry.total_pnl >= 0 ? '#3fb950' : '#f85149'}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
