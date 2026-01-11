# Project Brief: eFX Hedging Backtester (Nexus)

## Overview
A local web application to backtest hedging configurations for an eFX (electronic Foreign Exchange) principal market-making desk.

## Core Requirements

### Input Data
- Client trades (spot) including crosses
- Tick-level executable bid/ask ladder prices for multiple rung sizes

### Key Processing
- **Decrossing**: Automatically decompose cross trades into direct risk pairs using shortest-path approach on a currency graph (min hops, then min estimated executable cost)
- **Simulation**: Stateful per (date, risk_pair) shard; hedges modeled as direct-taking trades using the ladder

### Output Metrics
1. **Execution PnL**: `side * qty * (mid_ref(trade_ts) - client_px)`
2. **Inventory PnL**: FIFO, mid_ref(open_ts) to mid_ref(close_ts)
3. **Hedge Cost**: `side_h * qty_h * (px_h - mid_ref(hedge_ts))`, allocated proportionally
4. **Unrealized PnL**: Open lots marked at mid_ref(report_ts)
5. **Internalization Metrics**: Internalized vs externalized matched volume
6. **Risk Metrics**: Inventory peaks/percentiles, time above band, drawdowns

## Technical Constraints
- **No per-event DB queries**: Use DuckDB batched ASOF joins
- **Hot loops in Numba**: FIFO matching must be Numba-friendly
- **Windows-friendly**: ProcessPoolExecutor for parallel shards
- **Deterministic**: Same inputs + config = identical results
- **No pandas in core pipelines**: DuckDB + arrays only

## Tech Stack
- **Backend**: FastAPI + Uvicorn
- **Frontend**: React (Vite) + TypeScript
- **Data**: Parquet + DuckDB (embedded), PyArrow
- **Compute**: NumPy + Numba

## Conventions (from docs/conventions.md)
- Timestamps: int64 milliseconds
- Pair format: EURUSD (6-char uppercase, no separator)
- Side: +1 = buy base, -1 = sell base
- Quantity: base currency units
- Reference Mid: (bid_tob + ask_tob) / 2
