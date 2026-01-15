# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Nexus** is an eFX (Electronic Foreign Exchange) Hedging Backtester - a full-stack web application for backtesting FX hedging configurations for principal market-making desks. It features automatic trade decrossing, stateful per-shard simulation, and multiple PnL metrics.

## Development Commands

### Backend (Python with uv)

```bash
cd backend/efxbt

# Install dependencies
uv sync

# Start development server (auto-reload)
uv run uvicorn efxbt.app.main:app --reload

# Run all tests
uv run pytest tests/ -v

# Run single test file
uv run pytest tests/test_file.py -v

# Run tests with coverage
uv run pytest tests/ -v --cov=src/efxbt --cov-report=term-only

# Type checking
uv run mypy src/efxbt

# Linting
uv run ruff check src/efxbt

# Format code
uv run ruff format src/efxbt
```

### Frontend (Node.js)

```bash
cd frontend

# Install dependencies
npm install

# Start development server (port 5173)
npm run dev

# Run tests in watch mode
npm run test

# Run tests once
npm run test:run

# Test with coverage
npm run test:coverage

# Lint code
npm run lint

# Production build
npm run build

# E2E tests (requires both servers running)
npm run e2e              # Run all E2E tests
npm run e2e:headed       # Run with browser visible
npm run e2e:ui           # Open Playwright UI
npm run e2e:debug        # Debug mode
```

### Full Stack Startup

```powershell
# Start both servers
.\start-servers.ps1

# Or individually
.\start-backend.ps1
.\start-frontend.ps1
```

Backend runs on `http://127.0.0.1:8000`, Frontend on `http://localhost:5173`.

## Architecture

### Data Model: Independent Entities

Market data and trade books are **completely independent entities**:

1. **Market Datasets** (`data/datasets/{name}/market/`) - Tick data for observable pairs (EURUSD, GBPUSD), organized by pair and date
2. **Trade Books** (`data/tradebooks/{name}/`) - Independent trade collections organized by date; book name IS the entity identifier
3. **Run Configuration** - Associates trade_book + market_dataset + date_range at simulation time

### Backend Structure

```
backend/efxbt/src/efxbt/
├── app/
│   ├── main.py              # FastAPI app factory
│   ├── services/            # Business logic
│   │   ├── datasets.py      # Dataset service
│   │   ├── tradebooks.py    # Tradebook service
│   │   ├── runs.py          # Run management service
│   │   ├── decross.py       # Trade decrossing service
│   │   └── risk_metrics.py  # Risk metrics calculation service
│   └── api/
│       ├── router.py        # Aggregates all endpoints
│       ├── deps.py          # Dependency injection
│       ├── models.py        # Response models
│       ├── errors.py        # Error handling
│       └── endpoints/       # Route handlers (health, datasets, tradebooks, runs, results, kpi, etc.)
├── core/
│   ├── cache/               # Caching layer
│   │   ├── health_cache.py  # Health check caching
│   │   └── registry_cache.py # Registry data caching
│   ├── config/              # Settings via pydantic-settings (EFXBT_ prefix)
│   ├── data/
│   │   ├── schemas.py       # Pydantic + PyArrow schemas
│   │   ├── registry.py      # MarketDatasetRegistry, TradeBookRegistry
│   │   ├── run_registry.py  # Run registry management
│   │   ├── run_models.py    # Run data models
│   │   ├── duck.py          # DuckDB utilities
│   │   └── market_health.py # Market data health checks
│   ├── graph/               # Currency graph and pathfinding
│   │   ├── currency_graph.py # Currency relationship graph
│   │   ├── pathfinding.py   # Path finding algorithms
│   │   └── schemas.py       # Graph schemas
│   └── kpi/                 # KPI definitions and registry
│       └── definitions.py   # KPI metric definitions
├── engine/                  # Simulation engine
│   ├── decrosser.py         # Trade decrossing logic
│   ├── currency_flow.py     # Currency flow calculations
│   ├── io/                  # I/O utilities
│   │   └── pnl_writer.py    # PnL output writer
│   ├── orchestration/       # Run orchestration
│   │   └── orchestrator.py  # Multi-shard orchestration
│   ├── shard/               # Per-shard simulation
│   │   ├── shard_engine.py  # Main shard engine
│   │   ├── state.py         # Shard state management
│   │   ├── timeline.py      # Event timeline
│   │   ├── hedge_policy.py  # Hedging policy implementation
│   │   ├── fifo_matcher.py  # FIFO matching (Numba JIT)
│   │   ├── pnl_calculator.py # PnL calculations
│   │   ├── market_cache.py  # Market data cache
│   │   ├── market_fetcher.py # Market data fetching
│   │   └── fx_converter.py  # FX conversion utilities
│   └── simulation/          # Simulation execution
│       ├── simulator.py     # Main simulator
│       └── metrics.py       # Simulation metrics
└── util/                    # Logging, hashing, time utilities
```

### Frontend Structure

```
frontend/src/
├── api/                     # Typed HTTP client (client.ts, datasets.ts, etc.)
├── components/              # Reusable components (Layout, Navbar, HealthPanel)
├── hooks/                   # React hooks (useHealthMonitor)
├── pages/                   # Page components (Dashboard, Datasets, TradeBooks, Runs, Results)
└── styles/                  # Global CSS
```

### API Routes

All routes prefixed with `/api/v1`:

| Prefix         | Purpose                         |
| -------------- | ------------------------------- |
| `/health`      | Health checks and system status |
| `/datasets`    | Market dataset CRUD             |
| `/tradebooks`  | Trade book CRUD                 |
| `/data-health` | Data quality metrics            |
| `/decross`     | Trade decrossing operations     |
| `/runs`        | Backtest run management         |
| `/results`     | Run results retrieval           |
| `/kpi`         | KPI definitions and values      |
| `/sweeps`      | Parameter sweep operations      |

### Key Technical Patterns

- **DuckDB** for batched ASOF joins (no per-event DB queries)
- **Numba JIT** for hot loops (FIFO matching)
- **Pydantic + PyArrow** for data contracts and Parquet I/O
- **pydantic-settings** for typed configuration with EFXBT_ env prefix
- **Stub endpoints** return 501 for planned-but-unimplemented features

## Data Conventions

- **Timestamps**: int64 milliseconds
- **Pair format**: EURUSD (6-char uppercase, no separator)
- **Side**: +1 = buy base, -1 = sell base
- **Quantity**: Base currency units
- **Reference Mid**: (bid_tob + ask_tob) / 2

## Environment Variables

| Variable                  | Default       | Description                     |
| ------------------------- | ------------- | ------------------------------- |
| EFXBT_HOST                | 127.0.0.1     | Server bind host                |
| EFXBT_PORT                | 8000          | Server bind port                |
| EFXBT_DEBUG               | true          | Enable debug mode               |
| EFXBT_DATA_ROOT           | ../../data    | Data directory                  |
| EFXBT_RESULTS_ROOT        | ../../results | Results directory               |
| EFXBT_DUCKDB_MEMORY_LIMIT | 4GB           | Memory limit for DuckDB queries |

## Code Quality

- **Line length**: 100 characters (backend and frontend)
- **Python version**: 3.11+ required
- **Ruff**: Linting and formatting (replaces black/isort/flake8)
- **mypy**: Strict type checking enabled
- **ESLint**: React hooks and refresh plugins

## Style

- **For all implementations** particularly for those related with the core of the engine, prioritize being rigorous, correct and elegant
