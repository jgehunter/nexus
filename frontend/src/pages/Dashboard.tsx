import { useEffect, useState } from 'react'
import { HealthPanel } from '../components/HealthPanel'
import { listDatasets, type DatasetSummary } from '../api/datasets'
import { listTradeBooks, type TradeBookSummary } from '../api/tradebooks'
import type { ConnectionState } from '../api/health'

interface DashboardProps {
  healthState: ConnectionState & { retry: () => void }
}

export function Dashboard({ healthState }: DashboardProps) {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([])
  const [tradeBooks, setTradeBooks] = useState<TradeBookSummary[]>([])
  const [loadingDatasets, setLoadingDatasets] = useState(true)
  const [loadingTradeBooks, setLoadingTradeBooks] = useState(true)

  useEffect(() => {
    let mounted = true

    async function fetchDatasets() {
      try {
        const data = await listDatasets()
        if (mounted) {
          setDatasets(data)
        }
      } catch (err) {
        console.error('Failed to load datasets:', err)
      } finally {
        if (mounted) {
          setLoadingDatasets(false)
        }
      }
    }

    async function fetchTradeBooks() {
      try {
        const data = await listTradeBooks()
        if (mounted) {
          setTradeBooks(data)
        }
      } catch (err) {
        console.error('Failed to load trade books:', err)
      } finally {
        if (mounted) {
          setLoadingTradeBooks(false)
        }
      }
    }

    fetchDatasets()
    fetchTradeBooks()

    return () => {
      mounted = false
    }
  }, [])

  const isLoading = loadingDatasets || loadingTradeBooks

  return (
    <div className="page dashboard">
      <div className="page-header">
        <h1>Dashboard</h1>
        <p className="page-description">
          eFX hedging backtest simulation overview
        </p>
      </div>

      <div className="dashboard-grid">
        {/* Health Panel */}
        <div className="dashboard-card">
          <HealthPanel state={healthState} onRetry={healthState.retry} />
        </div>

        {/* Market Datasets */}
        {!loadingDatasets && datasets.length > 0 && (
          <div className="dashboard-card">
            <div className="card-header">
              <h3>Market Datasets</h3>
              <a href="/datasets" className="card-link">View all →</a>
            </div>
            <div className="dataset-list">
              {datasets.slice(0, 3).map((dataset) => (
                <div key={dataset.name} className="dataset-summary">
                  <div className="dataset-info">
                    <h4>{dataset.name}</h4>
                    <span className="version-badge">{dataset.version_id}</span>
                  </div>
                  <div className="dataset-quick-stats">
                    <span>{dataset.pairs.length} pairs</span>
                    <span>•</span>
                    <span>{dataset.dates.length} dates</span>
                    <span>•</span>
                    <span>{dataset.total_market_files} files</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Trade Books */}
        {!loadingTradeBooks && tradeBooks.length > 0 && (
          <div className="dashboard-card">
            <div className="card-header">
              <h3>Trade Books</h3>
              <a href="/tradebooks" className="card-link">View all →</a>
            </div>
            <div className="dataset-list">
              {tradeBooks.slice(0, 3).map((tradeBook) => (
                <div key={tradeBook.name} className="dataset-summary">
                  <div className="dataset-info">
                    <h4>{tradeBook.name}</h4>
                    <span className="version-badge">{tradeBook.version_id}</span>
                  </div>
                  <div className="dataset-quick-stats">
                    <span>{tradeBook.total_trades} trades</span>
                    <span>•</span>
                    <span>{tradeBook.dates.length} dates</span>
                    <span>•</span>
                    <span>{tradeBook.total_files} files</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Empty State */}
        {!isLoading && datasets.length === 0 && tradeBooks.length === 0 && (
          <div className="dashboard-card full-width">
            <div className="empty-state">
              <div className="empty-state-icon">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
              </div>
              <h3>No data yet</h3>
              <p>Upload market datasets and trade books to get started with backtesting</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
