export function Runs() {
  return (
    <div className="page">
      <div className="page-header">
        <h1>Runs</h1>
        <p className="page-description">
          Configure and execute backtest simulations
        </p>
      </div>

      <div className="empty-state">
        <div className="empty-state-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <polygon points="5 3 19 12 5 21 5 3" />
          </svg>
        </div>
        <h3>No runs yet</h3>
        <p>Create a new run to simulate hedging strategies on your data</p>
      </div>
    </div>
  )
}
