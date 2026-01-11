export function Results() {
  return (
    <div className="page">
      <div className="page-header">
        <h1>Results</h1>
        <p className="page-description">
          Analyze PnL, risk metrics, and internalization from completed runs
        </p>
      </div>

      <div className="empty-state">
        <div className="empty-state-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M3 3v18h18" />
            <path d="M18 9l-5 5-4-4-3 3" />
          </svg>
        </div>
        <h3>No results yet</h3>
        <p>Complete a backtest run to view detailed results and analytics</p>
      </div>
    </div>
  )
}
