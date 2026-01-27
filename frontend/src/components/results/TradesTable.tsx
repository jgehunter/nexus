/**
 * TradesTable component - displays paginated trades with filtering.
 */

import { useState, useEffect, useCallback } from 'react'
import { getTrades, TradeRecord, TradesResponse } from '../../api/results'

interface TradesTableProps {
  runId: string
  pairs: string[]
}

type EventTypeFilter = 'all' | 'client_fill' | 'hedge_fill'

function formatTimestamp(ms: number): string {
  const date = new Date(ms)
  return date.toISOString().replace('T', ' ').slice(0, 19)
}

function formatQty(qty: number): string {
  if (qty >= 1000000) {
    return `${(qty / 1000000).toFixed(2)}M`
  }
  if (qty >= 1000) {
    return `${(qty / 1000).toFixed(1)}K`
  }
  return qty.toFixed(0)
}

function formatPrice(price: number): string {
  return price.toFixed(5)
}

function formatPnL(pnl: number): string {
  const sign = pnl >= 0 ? '+' : ''
  if (Math.abs(pnl) >= 1000000) {
    return `${sign}${(pnl / 1000000).toFixed(2)}M`
  }
  if (Math.abs(pnl) >= 1000) {
    return `${sign}${(pnl / 1000).toFixed(1)}K`
  }
  return `${sign}${pnl.toFixed(2)}`
}

export function TradesTable({ runId, pairs }: TradesTableProps) {
  const [trades, setTrades] = useState<TradeRecord[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Filter state
  const [pairFilter, setPairFilter] = useState<string>('')
  const [eventTypeFilter, setEventTypeFilter] = useState<EventTypeFilter>('all')

  // Pagination state
  const [page, setPage] = useState(0)
  const pageSize = 50

  const fetchTrades = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const eventType =
        eventTypeFilter === 'all' ? undefined : eventTypeFilter
      const pair = pairFilter || undefined
      const response: TradesResponse = await getTrades(
        runId,
        pageSize,
        page * pageSize,
        pair,
        eventType
      )
      setTrades(response.trades)
      setTotal(response.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load trades')
      setTrades([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [runId, page, pairFilter, eventTypeFilter])

  useEffect(() => {
    fetchTrades()
  }, [fetchTrades])

  // Reset page when filters change
  useEffect(() => {
    setPage(0)
  }, [pairFilter, eventTypeFilter])

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="trades-table-container">
      <div className="trades-table-filters">
        <div className="filter-group">
          <label htmlFor="pair-filter">Pair</label>
          <select
            id="pair-filter"
            value={pairFilter}
            onChange={(e) => setPairFilter(e.target.value)}
          >
            <option value="">All Pairs</option>
            {pairs.map((pair) => (
              <option key={pair} value={pair}>
                {pair}
              </option>
            ))}
          </select>
        </div>
        <div className="filter-group">
          <label htmlFor="type-filter">Type</label>
          <select
            id="type-filter"
            value={eventTypeFilter}
            onChange={(e) => setEventTypeFilter(e.target.value as EventTypeFilter)}
          >
            <option value="all">All Types</option>
            <option value="client_fill">Client Fills</option>
            <option value="hedge_fill">Hedge Fills</option>
          </select>
        </div>
        <div className="filter-results">
          {total.toLocaleString()} trades
        </div>
      </div>

      {error && <div className="trades-table-error">{error}</div>}

      <div className="trades-table-wrapper">
        <table className="trades-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Pair</th>
              <th>Type</th>
              <th>Side</th>
              <th className="numeric">Qty</th>
              <th className="numeric">Price</th>
              <th className="numeric">PnL</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="loading-row">
                  Loading...
                </td>
              </tr>
            ) : trades.length === 0 ? (
              <tr>
                <td colSpan={7} className="empty-row">
                  No trades found
                </td>
              </tr>
            ) : (
              trades.map((trade, idx) => {
                const totalPnL =
                  trade.execution_pnl + trade.inventory_pnl + trade.hedge_pnl
                return (
                  <tr key={`${trade.timestamp_ms}-${idx}`}>
                    <td className="timestamp">
                      {formatTimestamp(trade.timestamp_ms)}
                    </td>
                    <td className="pair">{trade.pair}</td>
                    <td className={`event-type ${trade.event_type}`}>
                      {trade.event_type === 'client_fill' ? 'Client' : 'Hedge'}
                    </td>
                    <td className={`side ${trade.side > 0 ? 'buy' : 'sell'}`}>
                      {trade.side > 0 ? 'Buy' : 'Sell'}
                    </td>
                    <td className="numeric">{formatQty(trade.qty)}</td>
                    <td className="numeric">{formatPrice(trade.price)}</td>
                    <td className={`numeric ${totalPnL >= 0 ? 'positive' : 'negative'}`}>
                      {formatPnL(totalPnL)}
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="trades-table-pagination">
          <button
            className="pagination-btn"
            disabled={page === 0}
            onClick={() => setPage(0)}
          >
            First
          </button>
          <button
            className="pagination-btn"
            disabled={page === 0}
            onClick={() => setPage((p) => p - 1)}
          >
            Prev
          </button>
          <span className="pagination-info">
            Page {page + 1} of {totalPages}
          </span>
          <button
            className="pagination-btn"
            disabled={page >= totalPages - 1}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </button>
          <button
            className="pagination-btn"
            disabled={page >= totalPages - 1}
            onClick={() => setPage(totalPages - 1)}
          >
            Last
          </button>
        </div>
      )}
    </div>
  )
}
