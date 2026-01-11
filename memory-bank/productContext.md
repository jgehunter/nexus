# Product Context: eFX Hedging Backtester

## Why This Project Exists
Principal market-making desks need to evaluate hedging strategies before deploying them in production. This backtester allows traders and quants to:
- Test different hedging policies on historical data
- Understand PnL attribution (execution vs inventory vs hedge cost)
- Optimize internalization vs externalization decisions
- Analyze risk metrics under various market conditions

## Problems It Solves
1. **Strategy Evaluation**: Test hedging parameters without real capital at risk
2. **PnL Decomposition**: Understand where profit/loss originates
3. **Risk Analysis**: Identify inventory peaks, drawdowns, and time-at-risk
4. **Parameter Optimization**: Sweep across configurations to find optimal settings

## How It Should Work

### User Workflow
1. **Upload Dataset**: Import Parquet files with trade and market data
2. **Configure Run**: Select dataset, pairs, date range, and hedging policy
3. **Execute Backtest**: Simulation runs with progress tracking
4. **Analyze Results**: View PnL breakdown, risk metrics, and trade-level details

### Key Features
- Real-time health monitoring of backend services
- Dataset management with validation
- Multiple hedging policies (band flatten, staged unwind, internalize-first)
- Parameter sweep capability for optimization
- Detailed results with PnL decomposition and risk metrics

## User Experience Goals
- **Fast**: Responsive UI with backend health indicators
- **Clear**: Intuitive navigation with Dashboard, Datasets, Runs, Results pages
- **Informative**: Real-time status updates and detailed error messages
- **Professional**: Clean, dark-themed interface suitable for trading desks
