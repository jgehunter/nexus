/**
 * CombinedPositionChart - displays net position over time for multiple pairs in a single chart.
 *
 * Features:
 * - Single Recharts LineChart with multiple lines (one per pair)
 * - Toggle controls to show/hide individual pairs
 * - Y-axis shows position in base currency
 * - Tooltip shows both base currency and USD value
 */

import { useState, useMemo, useCallback } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import type { PairPositionTimeseries } from '../../api/results'

interface CombinedPositionChartProps {
  positionTimeseries: PairPositionTimeseries[]
  height?: number
}

// Color palette for chart lines - distinct, colorblind-friendly colors
const PAIR_COLORS = [
  '#58a6ff', // Blue
  '#3fb950', // Green
  '#f85149', // Red
  '#d29922', // Yellow/Orange
  '#a371f7', // Purple
  '#79c0ff', // Light Blue
  '#56d364', // Light Green
  '#ff7b72', // Light Red
  '#e3b341', // Gold
  '#bc8cff', // Light Purple
  '#8b949e', // Gray
  '#f778ba', // Pink
  '#7ee787', // Mint
  '#ffa657', // Orange
  '#a5d6ff', // Sky Blue
]

function formatTimestamp(ms: number): string {
  const date = new Date(ms)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
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

function formatCurrency(value: number): string {
  const absValue = Math.abs(value)
  if (absValue >= 1000000) {
    return `${value >= 0 ? '' : '-'}$${(absValue / 1000000).toFixed(2)}M`
  }
  if (absValue >= 1000) {
    return `${value >= 0 ? '' : '-'}$${(absValue / 1000).toFixed(0)}K`
  }
  return `${value >= 0 ? '' : '-'}$${absValue.toFixed(0)}`
}

// Get base currency from pair (first 3 characters)
function getBaseCurrency(pair: string): string {
  return pair.substring(0, 3)
}

interface MergedDataPoint {
  timestamp_ms: number
  [key: string]: number // Dynamic keys for each pair's position and position_usd
}

interface CustomTooltipProps {
  active?: boolean
  payload?: Array<{
    dataKey: string
    value: number
    color: string
  }>
  label?: number
  visiblePairs: Set<string>
}

function CustomTooltip({ active, payload, label, visiblePairs }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0 || !label) return null

  const date = new Date(label)

  // Filter to only visible pairs and sort by absolute position
  const visiblePayloads = payload
    .filter((p) => {
      const pair = p.dataKey.replace('_position', '')
      return visiblePairs.has(pair)
    })
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))

  return (
    <div className="chart-tooltip combined-position-tooltip">
      <div className="chart-tooltip-time">{date.toLocaleString()}</div>
      {visiblePayloads.map((p) => {
        const pair = p.dataKey.replace('_position', '')
        const baseCurrency = getBaseCurrency(pair)
        // Find the USD value from the merged data
        const usdKey = `${pair}_position_usd`
        const usdValue = payload.find((item) => item.dataKey === usdKey)?.value ?? 0

        return (
          <div key={pair} className="chart-tooltip-value">
            <span
              className="chart-tooltip-pair-indicator"
              style={{ backgroundColor: p.color }}
            />
            <span className="chart-tooltip-label">{pair}:</span>
            <span className={p.value >= 0 ? 'positive' : 'negative'}>
              {formatPosition(p.value)} {baseCurrency}
            </span>
            <span className="chart-tooltip-usd">
              ({formatCurrency(usdValue)})
            </span>
          </div>
        )
      })}
    </div>
  )
}

export function CombinedPositionChart({
  positionTimeseries,
  height = 400,
}: CombinedPositionChartProps) {
  // Sort pairs by max position (descending) for default visibility
  const sortedPairs = useMemo(() => {
    return [...positionTimeseries].sort(
      (a, b) => b.max_position_usd - a.max_position_usd
    )
  }, [positionTimeseries])

  // Default: show top 5 pairs by max position
  const defaultVisible = useMemo(() => {
    return new Set(sortedPairs.slice(0, 5).map((p) => p.pair))
  }, [sortedPairs])

  const [visiblePairs, setVisiblePairs] = useState<Set<string>>(defaultVisible)

  // Assign colors to pairs (consistent across toggles)
  const pairColors = useMemo(() => {
    const colors = new Map<string, string>()
    sortedPairs.forEach((p, i) => {
      colors.set(p.pair, PAIR_COLORS[i % PAIR_COLORS.length])
    })
    return colors
  }, [sortedPairs])

  // Merge all timeseries data into a single array for the chart
  const mergedData = useMemo(() => {
    // Collect all unique timestamps
    const timestampSet = new Set<number>()
    positionTimeseries.forEach((pairTs) => {
      pairTs.points.forEach((pt) => timestampSet.add(pt.timestamp_ms))
    })

    const timestamps = Array.from(timestampSet).sort((a, b) => a - b)

    // Create lookup maps for each pair's data
    const pairMaps = new Map<string, Map<number, { position: number; position_usd: number }>>()
    positionTimeseries.forEach((pairTs) => {
      const pointMap = new Map<number, { position: number; position_usd: number }>()
      pairTs.points.forEach((pt) => {
        pointMap.set(pt.timestamp_ms, { position: pt.position, position_usd: pt.position_usd })
      })
      pairMaps.set(pairTs.pair, pointMap)
    })

    // Build merged data points
    const merged: MergedDataPoint[] = timestamps.map((ts) => {
      const point: MergedDataPoint = { timestamp_ms: ts }

      positionTimeseries.forEach((pairTs) => {
        const pairMap = pairMaps.get(pairTs.pair)
        const data = pairMap?.get(ts)

        // Use last known position if not available at this timestamp (forward fill)
        if (data) {
          point[`${pairTs.pair}_position`] = data.position
          point[`${pairTs.pair}_position_usd`] = data.position_usd
        }
      })

      return point
    })

    return merged
  }, [positionTimeseries])

  const togglePair = useCallback((pair: string) => {
    setVisiblePairs((prev) => {
      const next = new Set(prev)
      if (next.has(pair)) {
        next.delete(pair)
      } else {
        next.add(pair)
      }
      return next
    })
  }, [])

  const toggleAll = useCallback(() => {
    setVisiblePairs((prev) => {
      if (prev.size === positionTimeseries.length) {
        // All visible -> show none
        return new Set()
      } else {
        // Some or none visible -> show all
        return new Set(positionTimeseries.map((p) => p.pair))
      }
    })
  }, [positionTimeseries])

  const showTop5 = useCallback(() => {
    setVisiblePairs(new Set(sortedPairs.slice(0, 5).map((p) => p.pair)))
  }, [sortedPairs])

  if (positionTimeseries.length === 0) {
    return (
      <div className="combined-position-chart-container">
        <div className="chart-empty">
          <p>No position timeseries data available</p>
        </div>
      </div>
    )
  }

  const allSelected = visiblePairs.size === positionTimeseries.length
  const noneSelected = visiblePairs.size === 0

  return (
    <div className="combined-position-chart-container">
      {/* Toggle Controls */}
      <div className="position-toggle-controls">
        <div className="toggle-actions">
          <button
            className={`toggle-btn ${allSelected ? 'active' : ''}`}
            onClick={toggleAll}
          >
            {allSelected ? 'Hide All' : 'Show All'}
          </button>
          <button className="toggle-btn" onClick={showTop5}>
            Top 5
          </button>
        </div>
        <div className="pair-toggles">
          {sortedPairs.map((pairTs) => {
            const isVisible = visiblePairs.has(pairTs.pair)
            const color = pairColors.get(pairTs.pair)

            return (
              <label
                key={pairTs.pair}
                className={`pair-toggle ${isVisible ? 'active' : ''}`}
              >
                <input
                  type="checkbox"
                  checked={isVisible}
                  onChange={() => togglePair(pairTs.pair)}
                />
                <span
                  className="pair-toggle-indicator"
                  style={{ backgroundColor: isVisible ? color : 'transparent', borderColor: color }}
                />
                <span className="pair-toggle-label">{pairTs.pair}</span>
                <span className="pair-toggle-max">
                  ({formatCurrency(pairTs.max_position_usd)})
                </span>
              </label>
            )
          })}
        </div>
      </div>

      {/* Chart */}
      {noneSelected ? (
        <div className="chart-empty">
          <p>Select at least one pair to display</p>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <LineChart
            data={mergedData}
            margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
          >
            <XAxis
              dataKey="timestamp_ms"
              tickFormatter={formatTimestamp}
              stroke="#8b949e"
              tick={{ fill: '#8b949e', fontSize: 11 }}
              axisLine={{ stroke: '#30363d' }}
              tickLine={{ stroke: '#30363d' }}
            />
            <YAxis
              tickFormatter={formatPosition}
              stroke="#8b949e"
              tick={{ fill: '#8b949e', fontSize: 11 }}
              axisLine={{ stroke: '#30363d' }}
              tickLine={{ stroke: '#30363d' }}
              width={70}
              label={{
                value: 'Position (base currency)',
                angle: -90,
                position: 'insideLeft',
                fill: '#8b949e',
                fontSize: 11,
              }}
            />
            <Tooltip
              content={
                <CustomTooltip
                  visiblePairs={visiblePairs}
                />
              }
            />
            <ReferenceLine y={0} stroke="#484f58" strokeWidth={1} strokeDasharray="3 3" />

            {/* Render a Line for each pair */}
            {sortedPairs.map((pairTs) => {
              const isVisible = visiblePairs.has(pairTs.pair)
              const color = pairColors.get(pairTs.pair)

              return (
                <Line
                  key={pairTs.pair}
                  type="stepAfter"
                  dataKey={`${pairTs.pair}_position`}
                  stroke={color}
                  strokeWidth={isVisible ? 2 : 0}
                  dot={false}
                  activeDot={isVisible ? { r: 4, fill: color } : false}
                  hide={!isVisible}
                  connectNulls
                />
              )
            })}

            {/* Hidden lines for USD values (used by tooltip) */}
            {sortedPairs.map((pairTs) => (
              <Line
                key={`${pairTs.pair}_usd`}
                type="stepAfter"
                dataKey={`${pairTs.pair}_position_usd`}
                stroke="transparent"
                strokeWidth={0}
                dot={false}
                hide
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
