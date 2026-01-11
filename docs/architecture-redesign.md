# Dataset Architecture Redesign

## Problem Statement

Current architecture bundles trade books (MAD_GLD, MAD_SLV) within datasets. However:
- **Trade books are independent**: Each has separate positions, hedging rules, and PnL
- **Results are per-book**: Cannot meaningfully aggregate across books
- **Market data is shared**: Same tick data used across multiple books
- **Current bundling is artificial**: No business reason to group books together

## Proposed Architecture

### Core Principle: Separation of Concerns

1. **Dataset = Market Data Observable Universe**
   - Contains only market tick data (prices, spreads)
   - Defines available pairs and date ranges
   - Shared resource across multiple backtests

2. **TradeBook = Independent Trading Entity**
   - Contains trades for a specific book (e.g., MAD_GLD)
   - Has own hedging policy, position limits, risk rules
   - Produces independent PnL and metrics

3. **BacktestRun = TradeBook + Dataset + Config**
   - References one trade book
   - References one dataset (market data)
   - Applies specific hedging configuration
   - Produces results for that book only

### New Directory Structure

```
data/
├── datasets/                    # Market data only
│   ├── efx_2024_q1/
│   │   └── market/
│   │       ├── EURUSD/
│   │       │   ├── 20240101.parquet
│   │       │   └── 20240102.parquet
│   │       ├── GBPUSD/
│   │       └── USDJPY/
│   └── efx_2024_q2/
│       └── market/
│           └── ...
│
└── tradebooks/                  # Trade books (independent)
    ├── MAD_GLD/
    │   ├── 20240101.parquet     # Trades for this book
    │   ├── 20240102.parquet
    │   └── metadata.json        # Book config
    └── MAD_SLV/
        ├── 20240101.parquet
        └── metadata.json
```

### Data Models

#### Dataset (Market Data)
```python
@dataclass(frozen=True)
class MarketDataInventory:
    """Inventory of market data (tick data)."""
    name: str                    # e.g., "efx_2024_q1"
    root_path: Path
    pairs: list[str]             # e.g., ["EURUSD", "GBPUSD"]
    dates: list[str]             # e.g., ["20240101", "20240102"]
    pair_dates: list[PairDateInventory]
    version_id: str
    total_files: int
```

#### TradeBook (Trades)
```python
@dataclass(frozen=True)
class TradeBookInventory:
    """Inventory of a trade book."""
    name: str                    # e.g., "MAD_GLD"
    root_path: Path
    pairs: list[str]             # Pairs traded in this book
    dates: list[str]             # Dates with trades
    total_trades: int
    total_volume: float
    version_id: str
```

#### BacktestRun (Execution)
```python
@dataclass(frozen=True)
class BacktestRunConfig:
    """Configuration for a backtest run."""
    run_id: str
    tradebook_name: str          # Which book to backtest
    dataset_name: str            # Which market data to use
    hedging_policy: str
    start_date: str
    end_date: str
```

### Registry Classes

#### DatasetRegistry (Market Data)
- `list_datasets()` → list of market datasets
- `discover_dataset(name)` → market data inventory
- `get_pairs(dataset)` → available pairs
- `get_dates(dataset)` → available dates

#### TradeBookRegistry (Trade Books)
- `list_tradebooks()` → list of trade books
- `discover_tradebook(name)` → trade book inventory  
- `get_pairs(tradebook)` → pairs traded
- `get_dates(tradebook)` → dates with trades

### Health Checks

#### Market Data Health
- Gap analysis (tick coverage)
- Schema validation
- Completeness per pair/date

#### TradeBook Health
- Trade count per date
- Volume distribution
- Schema validation
- Date coverage

## API Design

### Datasets (Market Data)
```
GET  /api/v1/datasets                    # List market datasets
GET  /api/v1/datasets/{name}             # Dataset details
GET  /api/v1/datasets/{name}/pairs       # Available pairs
GET  /api/v1/datasets/{name}/dates       # Available dates
GET  /api/v1/datasets/{name}/health      # Market data health
```

### TradeBooks
```
GET  /api/v1/tradebooks                  # List trade books
GET  /api/v1/tradebooks/{name}           # TradeBook details
GET  /api/v1/tradebooks/{name}/health    # Trade book health
```

### Runs
```
POST /api/v1/runs                        # Create backtest run
GET  /api/v1/runs                        # List runs
GET  /api/v1/runs/{id}                   # Run details
GET  /api/v1/runs/{id}/results           # Run results
```

## Frontend Pages

### Datasets Page
- Shows market data datasets only
- Health metrics: tick coverage, gaps
- Used for: selecting market data for backtests

### Trade Books Page (New)
- Shows available trade books
- Health metrics: trade counts, volume
- Used for: selecting which book to backtest

### Runs Page
- Create new run: select tradebook + dataset + config
- View historical runs
- Compare results across runs

## Migration Strategy

### Phase 1: Separate Data Models
1. Create `MarketDataInventory` (rename from `DatasetInventory`)
2. Create `TradeBookInventory` (new)
3. Keep old classes for backward compatibility

### Phase 2: Separate Registries
1. Create `TradeBookRegistry`
2. Refactor `DatasetRegistry` for market data only
3. Update discovery logic

### Phase 3: Update APIs
1. Add `/tradebooks` endpoints
2. Keep `/datasets` for market data
3. Update service layer

### Phase 4: Update Sample Data
1. Restructure `create_sample_dataset.py`
2. Separate market data and trade books
3. Create migration script for existing data

### Phase 5: Update Frontend
1. Update Datasets page (market data only)
2. Create Trade Books page
3. Update health displays

### Phase 6: Update Tests
1. Fix registry tests
2. Fix health tests
3. Fix API tests
4. Add tradebook tests

## Benefits

1. **Clarity**: Dataset = market data, TradeBook = trades
2. **Independence**: Each book has separate lifecycle and results
3. **No Duplication**: Market data shared across books
4. **Scalability**: Add books without touching market data
5. **Flexibility**: Mix and match books with datasets
6. **Correctness**: Aligns with business reality

## Implementation Plan

1. ✅ Create design document (this document)
2. [ ] Update core data models (registry.py)
3. [ ] Create TradeBook registry
4. [ ] Update health analyzer
5. [ ] Update API endpoints and services
6. [ ] Update sample data script
7. [ ] Update all tests
8. [ ] Update frontend
