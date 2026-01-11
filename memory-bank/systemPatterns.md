# System Patterns: eFX Hedging Backtester

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (React)                        │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌─────────┐          │
│  │Dashboard│ │Datasets │ │TradeBooks│ │  Runs   │          │
│  └────┬────┘ └────┬────┘ └────┬─────┘ └────┬────┘          │
│       └───────────┴───────────┴────────────┘                │
│                          │                                   │
│                    API Client                                │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP (proxy via Vite)
┌──────────────────────────┴──────────────────────────────────┐
│                    Backend (FastAPI)                         │
│  ┌────────────────────────────────────────────────────┐     │
│  │                   API Layer                         │     │
│  │  /health  /datasets  /tradebooks  /runs  /sweeps   │     │
│  └────────────────────────┬───────────────────────────┘     │
│                           │                                  │
│  ┌────────────────────────┴───────────────────────────┐     │
│  │                   Core Layer                        │     │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │     │
│  │  │ Config  │ │  Data   │ │   Sim   │ │ Metrics │  │     │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘  │     │
│  └────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────┐
│                    Data Layer                                │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │  Parquet Files  │  │     DuckDB      │                   │
│  │ (market/trades) │  │  (ASOF joins)   │                   │
│  └─────────────────┘  └─────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

## Data Model: Independent Entities

### Key Insight: Separation of Concerns
Market data and trade books are **completely independent entities**:

1. **Market Datasets** (`data/datasets/{name}/market/`)
   - Tick data for observable pairs (EURUSD, GBPUSD, etc.)
   - Organized by pair and date
   - Used as the "observable universe" during simulation

2. **Trade Books** (`data/tradebooks/{name}/`)
   - Independent collections of trades organized by date
   - Book name IS the entity identifier (not a container of pairs)
   - Updated daily by the user
   - No volume aggregation (meaningless across currencies)

3. **Run Configuration** (at simulation time)
   - Associates a trade book with a market dataset
   - Allows date range subset selection
   - Same market data can be reused across different trade books

```
Market Datasets           Trade Books           Run Configuration
┌─────────────┐          ┌─────────────┐       ┌─────────────────┐
│ HEDGING_Q1  │          │  MAD_GLD    │       │ Run Config      │
│  └─market/  │──────┐   │  ├─20240101 │   ┌───│ - trade_book    │
│    ├─EURUSD │      │   │  ├─20240102 │   │   │ - market_dataset│
│    └─GBPUSD │      │   │  └─...      │   │   │ - date_range    │
└─────────────┘      │   └─────────────┘   │   └─────────────────┘
                     │                     │
                     └─────────────────────┘
                        Associated at run time
```

## Key Design Patterns

### 1. Data Contracts via Pydantic + PyArrow
- Pydantic models for validation and API contracts
- PyArrow schemas for Parquet I/O
- Both defined in `core/data/schemas.py`

### 2. Composable Functions over Classes
- Small, typed, well-documented functions
- Avoid large monolithic classes
- Enable easier testing and composition

### 3. Configuration via pydantic-settings
- Environment variables with EFXBT_ prefix
- Type-safe configuration at startup
- Sensible defaults for local development

### 4. Health Monitoring
- `/health` endpoint for basic status
- `/health/detailed` for system metrics
- Frontend auto-retry with exponential backoff

### 5. Stub Endpoints Pattern
- All future endpoints return 501 Not Implemented
- Clear indication of what's planned
- Enables frontend scaffolding in parallel

## Component Relationships

### Frontend Components
```
App
├── Layout
│   └── Navbar (with connection indicator)
├── Dashboard
│   ├── HealthPanel
│   ├── DataOverview (datasets + tradebooks)
│   └── QuickStats
├── Datasets
│   └── MarketDatasetCards (with health)
├── TradeBooks
│   └── TradeBookCards (with health, no volume)
├── Runs (empty state)
└── Results (empty state)
```

### Backend Structure
```
efxbt/
├── app/
│   ├── main.py (FastAPI app factory)
│   ├── services/
│   │   ├── datasets.py (market dataset service)
│   │   └── tradebooks.py (trade book service)
│   └── api/
│       ├── router.py (aggregates endpoints)
│       ├── deps.py (dependency injection)
│       ├── errors.py (custom exceptions)
│       ├── models.py (response models)
│       └── endpoints/ (health, datasets, tradebooks, runs, etc.)
├── core/
│   ├── config/ (settings, defaults, universe)
│   └── data/
│       ├── schemas.py (Pydantic + PyArrow schemas)
│       ├── registry.py (MarketDatasetRegistry, TradeBookRegistry)
│       ├── health.py (legacy health analyzer)
│       └── health_new.py (separate market/trade health analyzers)
└── util/ (logging, hashing, time)
```

## Data Flow

### Health Check Flow
1. Frontend `useHealthMonitor` hook polls `/api/v1/health/detailed`
2. Backend checks DuckDB connectivity
3. Returns status, version, and system metrics
4. Frontend displays connection status in navbar and dashboard

### Future: Backtest Flow
1. User uploads market data → `data/datasets/{name}/market/`
2. User uploads trade files → `data/tradebooks/{book_name}/`
3. User configures run → Selects trade book + market dataset + date range
4. Backend validates date overlap between book and market data
5. Simulation runs with DuckDB ASOF joins for market lookups
6. Numba FIFO matching for inventory attribution
7. Results written to `results/` directory
