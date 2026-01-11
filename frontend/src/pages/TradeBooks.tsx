import { useEffect, useState } from 'react'
import { listTradeBooks, TradeBookSummary, getTradeBookHealth, TradeBookHealthReport } from '../api/tradebooks'

// Trade book management page with health metrics
export function TradeBooks() {
    const [tradeBooks, setTradeBooks] = useState<TradeBookSummary[]>([])
    const [healthReports, setHealthReports] = useState<Map<string, TradeBookHealthReport>>(new Map())
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [healthLoading, setHealthLoading] = useState(false)

    useEffect(() => {
        let mounted = true

        async function fetchTradeBooks() {
            try {
                setLoading(true)
                setError(null)
                const data = await listTradeBooks()
                if (mounted) {
                    setTradeBooks(data)
                    // Fetch health for each trade book
                    fetchHealth(data)
                }
            } catch (err) {
                if (mounted) {
                    setError(err instanceof Error ? err.message : 'Failed to load trade books')
                }
            } finally {
                if (mounted) {
                    setLoading(false)
                }
            }
        }

        async function fetchHealth(tradeBooks: TradeBookSummary[]) {
            setHealthLoading(true)
            const reports = new Map<string, TradeBookHealthReport>()

            for (const tradeBook of tradeBooks) {
                try {
                    const health = await getTradeBookHealth(tradeBook.name)
                    if (mounted) {
                        reports.set(tradeBook.name, health)
                        setHealthReports(new Map(reports))
                    }
                } catch (err) {
                    console.error(`Failed to load health for ${tradeBook.name}:`, err)
                }
            }

            if (mounted) {
                setHealthLoading(false)
            }
        }

        fetchTradeBooks()

        return () => {
            mounted = false
        }
    }, [])

    return (
        <div className="page">
            <div className="page-header">
                <h1>Trade Books</h1>
                <p className="page-description">
                    Manage independent trade books for backtesting analysis
                </p>
            </div>

            {loading && (
                <div className="loading-state">
                    <div className="spinner"></div>
                    <p>Loading trade books...</p>
                </div>
            )}

            {error && (
                <div className="error-state">
                    <div className="error-icon">⚠️</div>
                    <h3>Failed to load trade books</h3>
                    <p>{error}</p>
                    <button onClick={() => window.location.reload()}>Retry</button>
                </div>
            )}

            {!loading && !error && tradeBooks.length === 0 && (
                <div className="empty-state">
                    <div className="empty-state-icon">
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                            <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                    </div>
                    <h3>No trade books yet</h3>
                    <p>Upload your first trade book to get started with backtesting analysis</p>
                </div>
            )}

            {!loading && !error && tradeBooks.length > 0 && (
                <div className="datasets-grid">
                    {tradeBooks.map((tradeBook) => {
                        const health = healthReports.get(tradeBook.name)
                        return (
                            <div key={tradeBook.name} className="dataset-card">
                                <div className="dataset-header">
                                    <h3>{tradeBook.name}</h3>
                                    <span className="version-badge">{tradeBook.version_id}</span>
                                </div>

                                <div className="dataset-stats">
                                    <div className="stat">
                                        <span className="stat-label">Dates</span>
                                        <span className="stat-value">{tradeBook.dates.length}</span>
                                    </div>
                                    <div className="stat">
                                        <span className="stat-label">Total Trades</span>
                                        <span className="stat-value">{tradeBook.total_trades.toLocaleString()}</span>
                                    </div>
                                    <div className="stat">
                                        <span className="stat-label">Files</span>
                                        <span className="stat-value">{tradeBook.total_files}</span>
                                    </div>
                                </div>

                                {health && (
                                    <div className="health-section">
                                        <div className="health-header">
                                            <h4>Trade Activity</h4>
                                            {health.summary.total_trades > 0 ? (
                                                <span className="health-badge health-good">Active</span>
                                            ) : (
                                                <span className="health-badge health-warning">No Trades</span>
                                            )}
                                        </div>

                                        <div className="health-stats">
                                            <div className="health-stat">
                                                <span className="health-label">Total Trades</span>
                                                <span className="health-value">
                                                    {health.summary.total_trades.toLocaleString()}
                                                </span>
                                            </div>
                                            <div className="health-stat">
                                                <span className="health-label">Trade Files</span>
                                                <span className="health-value">
                                                    {health.summary.total_trade_files}
                                                </span>
                                            </div>
                                            <div className="health-stat">
                                                <span className="health-label">Dates Covered</span>
                                                <span className="health-value">
                                                    {tradeBook.dates.length}
                                                </span>
                                            </div>
                                        </div>

                                        {health.trade_stats.length > 0 && (
                                            <div className="health-details">
                                                <h5>Trades by Date</h5>
                                                <div className="trade-stats-list">
                                                    {health.trade_stats.slice(0, 5).map((stat) => (
                                                        <div key={stat.date} className="trade-stat-item">
                                                            <div className="trade-stat-header">
                                                                <span className="trade-stat-date">{stat.date}</span>
                                                                <span className="trade-stat-count">{stat.trade_count} trades</span>
                                                            </div>
                                                        </div>
                                                    ))}
                                                    {health.trade_stats.length > 5 && (
                                                        <div className="trade-stat-more">
                                                            +{health.trade_stats.length - 5} more dates
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}

                                {!health && healthLoading && (
                                    <div className="health-section">
                                        <div className="health-loading">
                                            <div className="spinner-small"></div>
                                            <span>Loading health data...</span>
                                        </div>
                                    </div>
                                )}

                                <div className="dataset-details">
                                    <div className="detail-row">
                                        <span className="detail-label">Date Range:</span>
                                        <span className="detail-value">
                                            {tradeBook.dates.length > 0
                                                ? `${tradeBook.dates[0]} - ${tradeBook.dates[tradeBook.dates.length - 1]}`
                                                : 'No dates'}
                                        </span>
                                    </div>
                                </div>

                                <div className="dataset-actions">
                                    <button className="btn-secondary">View Details</button>
                                    <button className="btn-primary">Use Trade Book</button>
                                </div>
                            </div>
                        )
                    })}
                </div>
            )}
        </div>
    )
}
