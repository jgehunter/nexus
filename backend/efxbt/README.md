# eFX Backtester Backend

Python backend for the Nexus eFX Hedging Backtester. Built with FastAPI, DuckDB, and Numba.

## Quick Start

```bash
# Install dependencies
uv sync

# Start development server
uv run uvicorn efxbt.app.main:app --reload

# Run tests
uv run pytest tests/ -v
```

## Module Overview

```
src/efxbt/
├── app/                    # FastAPI application layer
│   ├── main.py            # App factory and startup
│   ├── api/               # REST API endpoints
│   │   ├── router.py      # Route aggregation
│   │   ├── endpoints/     # Individual endpoint handlers
│   │   └── models.py      # Response schemas
│   └── services/          # Business logic layer
│       ├── datasets.py    # Market data operations
│       ├── tradebooks.py  # Trade book operations
│       ├── runs.py        # Backtest run management
│       ├── decross.py     # Trade decrossing
│       └── risk_metrics.py # Risk calculations
│
├── core/                   # Core domain logic
│   ├── cache/             # Caching utilities
│   ├── config/            # Settings and configuration
│   ├── data/              # Data models and registries
│   │   ├── registry.py    # Dataset/TradeBook discovery
│   │   ├── schemas.py     # Pydantic + PyArrow schemas
│   │   └── duck.py        # DuckDB utilities
│   ├── graph/             # Currency graph for decrossing
│   └── kpi/               # KPI definitions
│
├── engine/                 # Simulation engine
│   ├── shard/             # Per-shard simulation
│   │   ├── shard_engine.py   # Main simulation loop
│   │   ├── hedge_policy.py   # Hedging policies
│   │   ├── fifo_matcher.py   # FIFO matching (Numba)
│   │   └── pnl_calculator.py # PnL calculations
│   ├── orchestration/     # Multi-shard coordination
│   └── decrosser.py       # Trade decrossing logic
│
└── util/                   # Utilities
    ├── logging.py         # Logging setup
    ├── hashing.py         # Deterministic hashing
    └── time.py            # Time utilities
```

## Key Concepts

### Data Model

- **Market Dataset**: Observable universe of tick data (EURUSD, GBPUSD, etc.)
- **Trade Book**: Independent collection of trades (MAD_GLD, MAD_SLV)
- **Backtest Run**: Trade Book + Market Dataset + Configuration

### Simulation Flow

1. **Decrossing**: Decompose cross-currency trades into direct pairs
2. **Shard Creation**: Group trades by pair for parallel processing
3. **Simulation**: Process events chronologically per shard
4. **Hedging**: Apply hedge policy when positions exceed risk bands
5. **Aggregation**: Combine results across shards

### Technical Patterns

- **DuckDB**: Batched ASOF joins for market data lookup
- **Numba JIT**: Optimized FIFO matching loops
- **Pydantic**: Data validation and serialization
- **PyArrow**: Parquet I/O with schema enforcement

## Testing

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/engine/test_hedge_policy.py -v

# Run with coverage
uv run pytest tests/ -v --cov=src/efxbt --cov-report=term-only

# Run integration tests only
uv run pytest tests/integration/ -v
```

### Test Organization

```
tests/
├── app/               # API and service tests
├── core/              # Data layer tests
├── engine/            # Simulation engine tests
└── integration/       # End-to-end tests
```

## Code Quality

```bash
# Type checking
uv run mypy src/efxbt

# Linting
uv run ruff check src/efxbt

# Format code
uv run ruff format src/efxbt
```

## Configuration

Environment variables (prefix: `EFXBT_`):

| Variable | Default | Description |
|----------|---------|-------------|
| EFXBT_HOST | 127.0.0.1 | Server bind host |
| EFXBT_PORT | 8000 | Server bind port |
| EFXBT_DEBUG | true | Enable debug mode |
| EFXBT_DATA_ROOT | ../../data | Data directory |
| EFXBT_RESULTS_ROOT | ../../results | Results directory |
| EFXBT_DUCKDB_MEMORY_LIMIT | 4GB | DuckDB memory limit |
